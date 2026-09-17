"""Descoberta e transporte autenticado de blobs entre peers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from models.database import MeshPeer, get_db
from routes.api_v1.user_context import get_current_user
from schemas.mesh_schemas import MeshAnnounceRequest, MeshPeerSchema, MeshProvidersSchema
from services.exam_assets import asset_id_from_bytes
from services.p2p.content_store import ContentAddressedStore, normalize_asset_id
from services.p2p.mesh_tokens import create_mesh_token, read_mesh_token


router = APIRouter()
MESH_NODE_ID_ENV = "MESH_NODE_ID"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


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


@router.post("/mesh/announce")
def announce_peer(
    payload: MeshAnnounceRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Registra um peer da conta por um lease curto e renovável."""

    endpoint = _normalize_endpoint(payload.endpoint)
    peer = db.get(MeshPeer, payload.node_id)
    if peer is not None and int(peer.user_id) != int(current_user.id):
        raise HTTPException(status_code=409, detail="node_id já pertence a outra conta")

    now = _now()
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
    peers = [peer for peer in _active_peers(db, current_user.id) if normalized_asset in _assets_for_peer(peer)]
    return MeshProvidersSchema(
        asset_id=normalized_asset,
        providers=[_peer_response(peer) for peer in peers],
    )


@router.get("/mesh/fetch/{asset_id}", include_in_schema=False)
async def fetch_from_mesh(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Busca em peers da conta e só retorna bytes cujo digest confere."""

    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None:
        raise HTTPException(status_code=422, detail="asset_id inválido")
    peers = [peer for peer in _active_peers(db, current_user.id) if normalized_asset in _assets_for_peer(peer)]
    if not peers:
        raise HTTPException(status_code=404, detail="Nenhum peer disponível para este asset")

    timeout = httpx.Timeout(8.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for peer in peers:
            token = create_mesh_token(
                user_id=int(current_user.id),
                node_id=peer.node_id,
                asset_id=normalized_asset,
                expires_in=60,
            )
            remote_url = (
                f"{peer.endpoint.rstrip('/')}/api/v1/mesh/content/"
                f"{quote(normalized_asset, safe='')}"
            )
            try:
                response = await client.get(remote_url, headers={"X-Mesh-Token": token})
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            body = response.content
            if asset_id_from_bytes(body) != normalized_asset:
                continue
            media_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0]
            result = Response(content=body, media_type=media_type)
            result.headers["Cache-Control"] = "private, no-store"
            result.headers["X-Mesh-Provider"] = peer.node_id
            return result

    raise HTTPException(status_code=404, detail="Peers não entregaram um blob íntegro")


@router.get("/mesh/content/{asset_id}", include_in_schema=False)
def serve_mesh_content(
    asset_id: str,
    x_mesh_token: str | None = Header(default=None, alias="X-Mesh-Token"),
):
    """Endpoint usado por outro nó; nunca aceita caminho de arquivo do cliente."""

    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None:
        raise HTTPException(status_code=422, detail="asset_id inválido")
    expected_node = None
    # Quando definido, impede que um token emitido para outro nó seja usado
    # neste processo. Em desenvolvimento pode permanecer vazio para facilitar
    # a execução de vários nós com o mesmo binário.
    import os

    expected_node = os.environ.get(MESH_NODE_ID_ENV) or None
    token_payload = read_mesh_token(
        x_mesh_token,
        asset_id=normalized_asset,
        node_id=expected_node,
    )
    if token_payload is None:
        raise HTTPException(status_code=401, detail="Token de peer inválido ou expirado")

    store = ContentAddressedStore()
    if not store.has(normalized_asset):
        raise HTTPException(status_code=404, detail="Blob não está disponível neste peer")
    try:
        body = store.read_bytes(normalized_asset)
    except (OSError, IOError, ValueError):
        raise HTTPException(status_code=404, detail="Blob corrompido ou indisponível")
    return Response(
        content=body,
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )
