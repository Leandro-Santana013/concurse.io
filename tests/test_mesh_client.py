import asyncio

import httpx

from services.exam_assets import asset_id_from_bytes
from services.p2p import mesh_client
from services.p2p.content_store import ContentAddressedStore


def test_direct_mesh_client_downloads_from_ticket_peers(tmp_path, monkeypatch):
    monkeypatch.setenv("MESH_CHUNK_SIZE", str(256 * 1024))
    data = (b"desktop direct mesh " * 30_000)[:500_000]
    asset_id = asset_id_from_bytes(data)
    source = ContentAddressedStore(tmp_path / "source")
    source.put_bytes(asset_id, data)
    manifest = source.manifest_for(asset_id)
    chunks = [source.read_chunk(asset_id, index)[0] for index in range(manifest["chunk_count"])]

    ticket = {
        "asset_id": asset_id,
        "providers": [
            {
                "node_id": "desktop-a",
                "token": "m1.a.sig",
                "manifest_url": "https://desktop-a/manifest",
                "content_url": "https://desktop-a/content",
                "chunk_url_template": "https://desktop-a/chunk/{index}",
            },
            {
                "node_id": "desktop-b",
                "token": "m1.b.sig",
                "manifest_url": "https://desktop-b/manifest",
                "content_url": "https://desktop-b/content",
                "chunk_url_template": "https://desktop-b/chunk/{index}",
            },
        ],
    }

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url, headers=None):
            assert headers and headers["X-Mesh-Token"].startswith("m1.")
            request = httpx.Request("GET", url)
            if url.endswith("/manifest"):
                return httpx.Response(200, json=manifest, request=request)
            index = int(url.rsplit("/", 1)[1])
            return httpx.Response(200, content=chunks[index], request=request)

    monkeypatch.setattr(mesh_client.httpx, "AsyncClient", FakeAsyncClient)
    target = ContentAddressedStore(tmp_path / "target")
    fetched = asyncio.run(mesh_client.fetch_asset(asset_id, ticket, store=target))
    assert fetched == data
    assert target.read_bytes(asset_id) == data
