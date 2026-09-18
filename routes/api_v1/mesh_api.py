"""Descoberta e transporte autenticado de blobs entre peers.

O protocolo mantém o transporte legado de arquivo inteiro e acrescenta uma
camada de blocos verificáveis. Clientes novos podem consultar o manifesto e
baixar blocos em paralelo de vários peers; clientes antigos continuam usando
``/mesh/fetch`` sem precisar conhecer o protocolo novo.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from models.database import MeshPeer, get_db
from routes.api_v1.user_context import get_current_user
from schemas.mesh_schemas import (
    MeshAnnounceRequest,
    MeshManifestSchema,
    MeshPeerSchema,
    MeshPeerTicketSchema,
    MeshProvidersSchema,
    MeshTicketSchema,
)
from services.exam_assets import asset_id_from_bytes
from services.p2p.content_store import ContentAddressedStore, normalize_asset_id
from services.p2p.mesh_tokens import create_mesh_token, read_mesh_token


router = APIRouter()
MESH_NODE_ID_ENV = "MESH_NODE_ID"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _normalize_endpoint(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=422, detail="endpoint deve ser uma URL HTTP ou HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="endpoint não pode conter credenciais ou query string")
    netloc = parsed.hostname
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def _assets_for_peer(peer: MeshPeer) -> set[str]:
    try:
        values = json.loads(peer.asset_ids_json or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return set()
    if not isinstance(values, list):
        return set()
    return {
        asset_id
        for value in values
        if (asset_id := normalize_asset_id(value)) is not None
    }


def _active_peers(db: Session, user_id: int) -> list[MeshPeer]:
    now = _iso(_now())
    return (
        db.query(MeshPeer)
        .filter(
            MeshPeer.user_id == int(user_id),
            MeshPeer.expires_at > now,
        )
        .order_by(MeshPeer.last_seen.desc(), MeshPeer.node_id.asc())
        .all()
    )


def _peer_response(peer: MeshPeer) -> MeshPeerSchema:
    return MeshPeerSchema(
        node_id=peer.node_id,
        endpoint=peer.endpoint,
        asset_count=len(_assets_for_peer(peer)),
        last_seen=peer.last_seen,
    )


def _peer_asset_peers(db: Session, user_id: int, asset_id: str) -> list[MeshPeer]:
    peers = [peer for peer in _active_peers(db, user_id) if asset_id in _assets_for_peer(peer)]
    # Uma rotação estável distribui o primeiro bloco entre os peers sem perder
    # a ordenação por atividade para os nós recém-renovados.
    if len(peers) > 1:
        offset = int(hashlib.sha256(asset_id.encode("ascii")).hexdigest()[:8], 16) % len(peers)
        peers = peers[offset:] + peers[:offset]
    return peers


def _token_headers(user_id: int, peer: MeshPeer, asset_id: str) -> dict[str, str]:
    return {
        "X-Mesh-Token": create_mesh_token(
            user_id=int(user_id),
            node_id=peer.node_id,
            asset_id=asset_id,
            expires_in=90,
        )
    }


def _remote_path(peer: MeshPeer, path: str) -> str:
    return f"{peer.endpoint.rstrip('/')}/api/v1/mesh/{path}"


def _cache_response(store: ContentAddressedStore, asset_id: str, provider: str) -> FileResponse:
    return FileResponse(
        store.path_for(asset_id),
        media_type="application/octet-stream",
        headers={
            # O asset é content-addressed; o cache do navegador nunca precisa
            # ser invalidado por uma atualização de conteúdo.
            "Cache-Control": "private, max-age=86400, immutable",
            "X-Mesh-Provider": provider,
            "X-Mesh-Cache": "hit" if provider == "local-cache" else "miss",
            "X-Mesh-Asset-ID": asset_id,
            "Accept-Ranges": "bytes",
        },
    )


@router.post("/mesh/announce")
def announce_peer(
    payload: MeshAnnounceRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Registra um peer da conta por um lease curto e renovável."""

    endpoint = _normalize_endpoint(payload.endpoint)
    now = _now()
    # Leases expirados não precisam permanecer no plano de controle. A
    # limpeza oportunista mantém a consulta pequena sem um worker adicional.
    db.query(MeshPeer).filter(MeshPeer.expires_at <= _iso(now)).delete(
        synchronize_session=False,
    )
    peer = db.get(MeshPeer, payload.node_id)
    if peer is not None and int(peer.user_id) != int(current_user.id):
        raise HTTPException(status_code=409, detail="node_id já pertence a outra conta")

    if peer is None:
        peer = MeshPeer(
            node_id=payload.node_id,
            user_id=int(current_user.id),
            created_at=_iso(now),
        )
        db.add(peer)
    peer.endpoint = endpoint
    peer.asset_ids_json = json.dumps(payload.asset_ids, separators=(",", ":"))
    peer.last_seen = _iso(now)
    peer.expires_at = _iso(now + timedelta(seconds=payload.lease_seconds))
    db.commit()

    return {
        "node_id": peer.node_id,
        "last_seen": peer.last_seen,
        "expires_at": peer.expires_at,
        "asset_count": len(payload.asset_ids),
        "lease_seconds": payload.lease_seconds,
        "protocol": {"whole_blob": 1, "chunked": 1},
    }


@router.delete("/mesh/announce/{node_id}")
def withdraw_peer(
    node_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    peer = db.get(MeshPeer, node_id)
    if peer is None or int(peer.user_id) != int(current_user.id):
        return {"ok": True}
    db.delete(peer)
    db.commit()
    return {"ok": True}


@router.get("/mesh/providers/{asset_id}", response_model=MeshProvidersSchema)
def list_providers(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None:
        raise HTTPException(status_code=422, detail="asset_id inválido")
    peers = _peer_asset_peers(db, current_user.id, normalized_asset)
    return MeshProvidersSchema(
        asset_id=normalized_asset,
        providers=[_peer_response(peer) for peer in peers],
    )


@router.get("/mesh/ticket/{asset_id}", response_model=MeshTicketSchema)
def issue_mesh_ticket(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Emite URLs temporárias para um cliente desktop buscar blocos direto.

    O origin continua controlando a autorização; o cliente não recebe o
    segredo compartilhado dos nós. Cada token é limitado a um asset e a um
    node e expira rapidamente.
    """

    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None:
        raise HTTPException(status_code=422, detail="asset_id inválido")
    peers = _peer_asset_peers(db, current_user.id, normalized_asset)
    expires_in = 90
    expires_at = int(_now().timestamp()) + expires_in
    providers = []
    encoded_asset = quote(normalized_asset, safe="")
    for peer in peers:
        providers.append(MeshPeerTicketSchema(
            node_id=peer.node_id,
            endpoint=peer.endpoint,
            token=create_mesh_token(
                user_id=int(current_user.id),
                node_id=peer.node_id,
                asset_id=normalized_asset,
                expires_in=expires_in,
            ),
            expires_at=expires_at,
            manifest_url=_remote_path(peer, f"manifest/{encoded_asset}"),
            content_url=_remote_path(peer, f"content/{encoded_asset}"),
            chunk_url_template=_remote_path(peer, f"content/{encoded_asset}/chunk/{{index}}"),
        ))
    return MeshTicketSchema(
        asset_id=normalized_asset,
        expires_in=expires_in,
        providers=providers,
    )


async def _fetch_remote_manifest(
    client: httpx.AsyncClient,
    peer: MeshPeer,
    user_id: int,
    asset_id: str,
) -> dict | None:
    url = _remote_path(peer, f"manifest/{quote(asset_id, safe='')}")
    try:
        response = await client.get(url, headers=_token_headers(user_id, peer, asset_id))
        if response.status_code != 200:
            return None
        payload = MeshManifestSchema.model_validate(response.json())
        return payload.model_dump()
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None


async def _fetch_remote_chunk(
    client: httpx.AsyncClient,
    peer: MeshPeer,
    user_id: int,
    asset_id: str,
    chunk_index: int,
    descriptor: dict,
) -> bytes | None:
    url = _remote_path(
        peer,
        f"content/{quote(asset_id, safe='')}/chunk/{int(chunk_index)}",
    )
    try:
        response = await client.get(url, headers=_token_headers(user_id, peer, asset_id))
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    body = response.content
    try:
        if (
            len(body) != int(descriptor["size"])
            or hashlib.sha256(body).hexdigest() != str(descriptor["sha256"])
        ):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return body


async def _fetch_chunked(
    client: httpx.AsyncClient,
    peers: list[MeshPeer],
    user_id: int,
    asset_id: str,
    manifest: dict,
) -> tuple[list[bytes], list[str]] | None:
    descriptors = manifest.get("chunks")
    if not isinstance(descriptors, list) or not descriptors:
        return None
    concurrency = _int_env("MESH_FETCH_CONCURRENCY", 8, minimum=1, maximum=32)
    semaphore = asyncio.Semaphore(concurrency)
    bodies: list[bytes | None] = [None] * len(descriptors)
    providers: list[str | None] = [None] * len(descriptors)

    async def download(index: int, descriptor: dict) -> None:
        async with semaphore:
            # Cada bloco começa em um peer diferente quando possível. Em erro,
            # tenta todos os demais antes de declarar a transferência perdida.
            for offset in range(len(peers)):
                peer = peers[(index + offset) % len(peers)]
                body = await _fetch_remote_chunk(
                    client,
                    peer,
                    user_id,
                    asset_id,
                    index,
                    descriptor,
                )
                if body is not None:
                    bodies[index] = body
                    providers[index] = peer.node_id
                    return

    await asyncio.gather(*(download(index, descriptor) for index, descriptor in enumerate(descriptors)))
    if any(body is None for body in bodies):
        return None
    return [body for body in bodies if body is not None], [name for name in providers if name]


async def _fetch_whole(
    client: httpx.AsyncClient,
    peers: list[MeshPeer],
    user_id: int,
    asset_id: str,
) -> tuple[bytes, MeshPeer, str] | None:
    for peer in peers:
        url = _remote_path(peer, f"content/{quote(asset_id, safe='')}")
        try:
            response = await client.get(url, headers=_token_headers(user_id, peer, asset_id))
        except httpx.HTTPError:
            continue
        if response.status_code != 200:
            continue
        body = response.content
        if asset_id_from_bytes(body) != asset_id:
            continue
        media_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
        return body, peer, media_type
    return None


@router.get("/mesh/fetch/{asset_id}", include_in_schema=False)
async def fetch_from_mesh(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Busca um asset com cache-first e blocos paralelos entre vários peers."""

    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None:
        raise HTTPException(status_code=422, detail="asset_id inválido")
    store = ContentAddressedStore()
    if store.has_verified(normalized_asset):
        return _cache_response(store, normalized_asset, "local-cache")

    peers = _peer_asset_peers(db, current_user.id, normalized_asset)
    if not peers:
        raise HTTPException(status_code=404, detail="Nenhum peer disponível para este asset")

    timeout = httpx.Timeout(
        _int_env("MESH_PEER_TIMEOUT_SECONDS", 8, minimum=2, maximum=60),
        connect=_int_env("MESH_PEER_CONNECT_TIMEOUT_SECONDS", 3, minimum=1, maximum=15),
    )
    limits = httpx.Limits(
        max_connections=_int_env("MESH_HTTP_MAX_CONNECTIONS", 32, minimum=4, maximum=128),
        max_keepalive_connections=_int_env("MESH_HTTP_KEEPALIVE", 16, minimum=2, maximum=64),
    )
    async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=False) as client:
        manifests = await asyncio.gather(
            *(_fetch_remote_manifest(client, peer, int(current_user.id), normalized_asset) for peer in peers),
            return_exceptions=True,
        )
        manifest = next((value for value in manifests if isinstance(value, dict)), None)
        if manifest is not None and int(manifest.get("chunk_count", 0)) > 1:
            fetched = await _fetch_chunked(
                client,
                peers,
                int(current_user.id),
                normalized_asset,
                manifest,
            )
            if fetched is not None:
                bodies, provider_ids = fetched
                try:
                    store.put_chunks(normalized_asset, bodies, manifest=manifest)
                    return _cache_response(
                        store,
                        normalized_asset,
                        "mesh:" + ",".join(sorted(set(provider_ids))),
                    )
                except (OSError, ValueError, TypeError, KeyError):
                    pass

        # Compatibilidade com nós antigos e fallback em caso de manifesto
        # indisponível, incompleto ou incompatível.
        whole = await _fetch_whole(client, peers, int(current_user.id), normalized_asset)
        if whole is not None:
            body, peer, media_type = whole
            try:
                # O proxy também se torna provider depois de uma transferência
                # íntegra, formando a redistribuição em cadeia da malha.
                store.put_bytes(normalized_asset, body)
                return _cache_response(store, normalized_asset, peer.node_id)
            except (OSError, ValueError):
                result = Response(content=body, media_type=media_type)
                result.headers["Cache-Control"] = "private, no-store"
                result.headers["X-Mesh-Provider"] = peer.node_id
                return result

    raise HTTPException(status_code=404, detail="Peers não entregaram um blob íntegro")


def _expected_node() -> str | None:
    # Em desenvolvimento vazio permite vários nós no mesmo processo; em
    # produção o compose define um identificador único por máquina.
    return os.environ.get(MESH_NODE_ID_ENV) or None


def _validate_peer_token(asset_id: str, token: str | None) -> None:
    if read_mesh_token(token, asset_id=asset_id, node_id=_expected_node()) is None:
        raise HTTPException(status_code=401, detail="Token de peer inválido ou expirado")


@router.get("/mesh/manifest/{asset_id}", include_in_schema=False)
def serve_mesh_manifest(
    asset_id: str,
    x_mesh_token: str | None = Header(default=None, alias="X-Mesh-Token"),
):
    """Entrega metadados de blocos sem expor caminho ou conteúdo do arquivo."""

    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None:
        raise HTTPException(status_code=422, detail="asset_id inválido")
    _validate_peer_token(normalized_asset, x_mesh_token)
    store = ContentAddressedStore()
    try:
        manifest = store.manifest_for(normalized_asset)
        MeshManifestSchema.model_validate(manifest)
    except (FileNotFoundError, OSError, IOError, ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Manifesto não está disponível neste peer")
    return JSONResponse(
        content=manifest,
        headers={"Cache-Control": "private, max-age=60"},
    )


@router.get("/mesh/content/{asset_id}/chunk/{chunk_index}", include_in_schema=False)
def serve_mesh_chunk(
    asset_id: str,
    chunk_index: int,
    x_mesh_token: str | None = Header(default=None, alias="X-Mesh-Token"),
):
    """Entrega apenas um bloco, validando seu hash antes da resposta."""

    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None:
        raise HTTPException(status_code=422, detail="asset_id inválido")
    _validate_peer_token(normalized_asset, x_mesh_token)
    store = ContentAddressedStore()
    try:
        body, descriptor = store.read_chunk(normalized_asset, chunk_index)
        manifest = store.manifest_for(normalized_asset)
    except (FileNotFoundError, OSError, IOError, ValueError, IndexError):
        raise HTTPException(status_code=404, detail="Bloco não está disponível neste peer")
    end = int(descriptor["offset"]) + len(body) - 1
    total = int(manifest["size"])
    return Response(
        content=body,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=3600, immutable",
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {descriptor['offset']}-{end}/{total}",
            "X-Mesh-Chunk": str(chunk_index),
            "X-Mesh-Chunk-SHA256": str(descriptor["sha256"]),
            "X-Mesh-Asset-ID": normalized_asset,
        },
    )


@router.get("/mesh/content/{asset_id}", include_in_schema=False)
def serve_mesh_content(
    asset_id: str,
    x_mesh_token: str | None = Header(default=None, alias="X-Mesh-Token"),
):
    """Endpoint legado de arquivo inteiro usado por peers antigos."""

    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None:
        raise HTTPException(status_code=422, detail="asset_id inválido")
    _validate_peer_token(normalized_asset, x_mesh_token)

    store = ContentAddressedStore()
    if not store.has_verified(normalized_asset):
        raise HTTPException(status_code=404, detail="Blob não está disponível neste peer")
    try:
        store.manifest_for(normalized_asset)
    except (OSError, IOError, ValueError):
        raise HTTPException(status_code=404, detail="Blob corrompido ou indisponível")
    return FileResponse(
        store.path_for(normalized_asset),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=3600, immutable",
            "Accept-Ranges": "bytes",
            "X-Mesh-Asset-ID": normalized_asset,
        },
    )
