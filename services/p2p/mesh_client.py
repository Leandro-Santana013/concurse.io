"""Cliente assíncrono para baixar assets diretamente dos peers.

O backend pode emitir um ticket em ``/mesh/ticket/{asset_id}``. Este módulo é
usado por um processo desktop ou outro nó confiável: o origin entrega apenas o
ticket e os peers trocam os blocos entre si, com fallback para o blob inteiro.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping

import httpx

from schemas.mesh_schemas import MeshManifestSchema
from services.exam_assets import asset_id_from_bytes
from services.p2p.content_store import ContentAddressedStore, normalize_asset_id


class MeshDownloadError(RuntimeError):
    """Todos os peers do ticket falharam ou entregaram conteúdo inválido."""


def _providers(ticket: Mapping) -> list[Mapping]:
    values = ticket.get("providers")
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, Mapping)]


def _headers(provider: Mapping) -> dict[str, str]:
    token = str(provider.get("token") or "")
    return {"X-Mesh-Token": token}


async def fetch_asset(
    asset_id: str,
    ticket: Mapping,
    *,
    store: ContentAddressedStore | None = None,
    concurrency: int = 8,
    timeout_seconds: float = 8.0,
) -> bytes:
    """Baixa um asset por blocos de vários peers e retorna os bytes íntegros.

    Quando ``store`` é fornecido, a montagem é gravada com troca atômica depois
    da validação de todos os hashes. Um cache já íntegro evita qualquer pedido
    de rede.
    """

    normalized = normalize_asset_id(asset_id)
    if normalized is None or str(ticket.get("asset_id")) != normalized:
        raise MeshDownloadError("ticket e asset_id não correspondem")
    target_store = store
    if target_store is not None and target_store.has_verified(normalized):
        return target_store.read_bytes(normalized)

    peers = _providers(ticket)
    if not peers:
        raise MeshDownloadError("ticket não possui providers")
    concurrency = max(1, min(32, int(concurrency or 1)))
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 3.0))
    limits = httpx.Limits(max_connections=max(4, concurrency * 2), max_keepalive_connections=concurrency)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, limits=limits) as client:
        manifests = await asyncio.gather(
            *(_manifest(client, provider) for provider in peers),
            return_exceptions=True,
        )
        manifest = next((value for value in manifests if isinstance(value, dict)), None)
        if manifest is not None:
            descriptors = manifest.get("chunks")
            if isinstance(descriptors, list) and descriptors:
                bodies = await _chunks(client, peers, normalized, descriptors, concurrency)
                if bodies is not None:
                    body = b"".join(bodies)
                    if asset_id_from_bytes(body) != normalized:
                        bodies = None
                    else:
                        if target_store is not None:
                            target_store.put_chunks(normalized, bodies, manifest=manifest)
                        return body

        for provider in peers:
            url = str(provider.get("content_url") or "")
            if not url:
                continue
            try:
                response = await client.get(url, headers=_headers(provider))
            except httpx.HTTPError:
                continue
            if response.status_code != 200:
                continue
            body = response.content
            if asset_id_from_bytes(body) != normalized:
                continue
            if target_store is not None:
                target_store.put_bytes(normalized, body)
            return body

    raise MeshDownloadError("nenhum peer entregou um asset íntegro")


async def _manifest(client: httpx.AsyncClient, provider: Mapping) -> dict | None:
    url = str(provider.get("manifest_url") or "")
    if not url:
        return None
    try:
        response = await client.get(url, headers=_headers(provider))
        if response.status_code != 200:
            return None
        return MeshManifestSchema.model_validate(response.json()).model_dump()
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None


async def _chunks(
    client: httpx.AsyncClient,
    peers: list[Mapping],
    asset_id: str,
    descriptors: list,
    concurrency: int,
) -> list[bytes] | None:
    semaphore = asyncio.Semaphore(concurrency)
    result: list[bytes | None] = [None] * len(descriptors)

    async def download(index: int, descriptor: Mapping) -> None:
        async with semaphore:
            for offset in range(len(peers)):
                provider = peers[(index + offset) % len(peers)]
                template = str(provider.get("chunk_url_template") or "")
                if not template:
                    continue
                url = template.replace("{index}", str(index))
                try:
                    response = await client.get(url, headers=_headers(provider))
                except httpx.HTTPError:
                    continue
                if response.status_code != 200:
                    continue
                body = response.content
                try:
                    valid = (
                        len(body) == int(descriptor["size"])
                        and hashlib.sha256(body).hexdigest() == str(descriptor["sha256"])
                    )
                except (KeyError, TypeError, ValueError):
                    valid = False
                if valid:
                    result[index] = body
                    return

    await asyncio.gather(*(download(index, descriptor) for index, descriptor in enumerate(descriptors)))
    return [body for body in result if body is not None] if all(body is not None for body in result) else None
