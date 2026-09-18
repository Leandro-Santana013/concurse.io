from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.database import Base, get_db
from routes.api_v1 import mesh_api
from routes.api_v1.user_context import get_current_user
from services.exam_assets import asset_id_from_bytes
from services.p2p.content_store import ContentAddressedStore
from services.p2p.mesh_tokens import create_mesh_token


@pytest.fixture()
def mesh_client(tmp_path, monkeypatch):
    monkeypatch.setenv("MESH_SHARED_SECRET", "mesh-test-secret")
    monkeypatch.setenv("MESH_CONTENT_DIR", str(tmp_path / "content"))
    monkeypatch.delenv("MESH_NODE_ID", raising=False)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    app = FastAPI()
    app.include_router(mesh_api.router, prefix="/api/v1")
    current_user = SimpleNamespace(id=7)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    client = TestClient(app)
    try:
        yield client, session_factory
    finally:
        client.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_announce_discover_and_serve_blob(mesh_client):
    client, _session_factory = mesh_client
    data = b"shared exam image"
    asset_id = asset_id_from_bytes(data)
    ContentAddressedStore().put_bytes(asset_id, data)

    announced = client.post(
        "/api/v1/mesh/announce",
        json={
            "node_id": "desktop-node-1",
            "endpoint": "http://127.0.0.1:9876",
            "asset_ids": [asset_id],
            "lease_seconds": 120,
        },
    )
    assert announced.status_code == 200
    assert announced.json()["asset_count"] == 1

    providers = client.get(f"/api/v1/mesh/providers/{asset_id}")
    assert providers.status_code == 200
    assert providers.json()["providers"][0]["node_id"] == "desktop-node-1"

    token = create_mesh_token(
        user_id=7,
        node_id="desktop-node-1",
        asset_id=asset_id,
    )
    served = client.get(
        f"/api/v1/mesh/content/{asset_id}",
        headers={"X-Mesh-Token": token},
    )
    assert served.status_code == 200
    assert served.content == data
    assert client.get(f"/api/v1/mesh/content/{asset_id}").status_code == 401


def test_fetch_proxy_verifies_peer_bytes(mesh_client, monkeypatch):
    client, _session_factory = mesh_client
    data = b"proxy image"
    asset_id = asset_id_from_bytes(data)
    client.post(
        "/api/v1/mesh/announce",
        json={
            "node_id": "desktop-node-2",
            "endpoint": "http://peer.invalid",
            "asset_ids": [asset_id],
            "lease_seconds": 120,
        },
    )

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _url, headers=None):
            assert headers and headers["X-Mesh-Token"].startswith("m1.")
            return httpx.Response(
                200,
                content=data,
                headers={"content-type": "image/png"},
                request=httpx.Request("GET", "http://peer.invalid"),
            )

    monkeypatch.setattr(mesh_api.httpx, "AsyncClient", FakeAsyncClient)
    fetched = client.get(f"/api/v1/mesh/fetch/{asset_id}")
    assert fetched.status_code == 200
    assert fetched.content == data
    assert fetched.headers["x-mesh-provider"] == "desktop-node-2"
    assert ContentAddressedStore().read_bytes(asset_id) == data


def test_announce_rejects_node_reuse_by_another_user(mesh_client):
    client, _session_factory = mesh_client
    asset_id = asset_id_from_bytes(b"asset")
    body = {
        "node_id": "desktop-node-3",
        "endpoint": "http://127.0.0.1:9876",
        "asset_ids": [asset_id],
        "lease_seconds": 120,
    }
    assert client.post("/api/v1/mesh/announce", json=body).status_code == 200

    client.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=8)
    conflict = client.post("/api/v1/mesh/announce", json=body)
    assert conflict.status_code == 409


def test_manifest_and_chunk_endpoint_require_token_and_validate_ranges(mesh_client, monkeypatch):
    client, _session_factory = mesh_client
    monkeypatch.setenv("MESH_CHUNK_SIZE", str(256 * 1024))
    data = (b"manifested proof image " * 30_000)[:500_000]
    asset_id = asset_id_from_bytes(data)
    ContentAddressedStore().put_bytes(asset_id, data)
    token = create_mesh_token(user_id=7, node_id="desktop-node-4", asset_id=asset_id)

    manifest = client.get(
        f"/api/v1/mesh/manifest/{asset_id}",
        headers={"X-Mesh-Token": token},
    )
    assert manifest.status_code == 200
    payload = manifest.json()
    assert payload["chunk_count"] == 2
    assert payload["size"] == len(data)

    chunk = client.get(
        f"/api/v1/mesh/content/{asset_id}/chunk/1",
        headers={"X-Mesh-Token": token},
    )
    assert chunk.status_code == 200
    assert chunk.content == data[256 * 1024:]
    assert chunk.headers["x-mesh-chunk"] == "1"
    assert chunk.headers["accept-ranges"] == "bytes"
    assert client.get(f"/api/v1/mesh/manifest/{asset_id}").status_code == 401


def test_fetch_assembles_chunks_from_multiple_peers(mesh_client, monkeypatch):
    client, _session_factory = mesh_client
    monkeypatch.setenv("MESH_CHUNK_SIZE", str(256 * 1024))
    data = (b"distributed exam pdf " * 80_000)[:700_000]
    asset_id = asset_id_from_bytes(data)
    store = ContentAddressedStore()
    store.put_bytes(asset_id, data)
    manifest = store.manifest_for(asset_id)
    chunks = [store.read_chunk(asset_id, index)[0] for index in range(manifest["chunk_count"])]
    store.path_for(asset_id).unlink()
    store.manifest_path_for(asset_id).unlink()

    for node_id in ("desktop-node-5", "desktop-node-6"):
        announced = client.post(
            "/api/v1/mesh/announce",
            json={
                "node_id": node_id,
                "endpoint": f"http://{node_id}.invalid",
                "asset_ids": [asset_id],
                "lease_seconds": 120,
            },
        )
        assert announced.status_code == 200

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
            if "/manifest/" in url:
                return httpx.Response(200, json=manifest, request=request)
            if "/chunk/" in url:
                index = int(url.rsplit("/chunk/", 1)[1])
                return httpx.Response(200, content=chunks[index], request=request)
            raise AssertionError(f"rota inesperada: {url}")

    monkeypatch.setattr(mesh_api.httpx, "AsyncClient", FakeAsyncClient)
    fetched = client.get(f"/api/v1/mesh/fetch/{asset_id}")
    assert fetched.status_code == 200
    assert fetched.content == data
    assert fetched.headers["x-mesh-provider"].startswith("mesh:")
    assert set(fetched.headers["x-mesh-provider"].removeprefix("mesh:").split(",")) == {
        "desktop-node-5",
        "desktop-node-6",
    }
    assert ContentAddressedStore().read_bytes(asset_id) == data


def test_ticket_issues_direct_peer_urls_without_shared_secret(mesh_client):
    client, _session_factory = mesh_client
    asset_id = asset_id_from_bytes(b"ticketed proof")
    announced = client.post(
        "/api/v1/mesh/announce",
        json={
            "node_id": "desktop-node-7",
            "endpoint": "https://peer.example/mesh-node",
            "asset_ids": [asset_id],
            "lease_seconds": 120,
        },
    )
    assert announced.status_code == 200

    ticket = client.get(f"/api/v1/mesh/ticket/{asset_id}")
    assert ticket.status_code == 200
    provider = ticket.json()["providers"][0]
    assert provider["node_id"] == "desktop-node-7"
    assert provider["token"].startswith("m1.")
    assert provider["manifest_url"] == (
        f"https://peer.example/mesh-node/api/v1/mesh/manifest/{asset_id.replace(':', '%3A')}"
    )
    assert provider["chunk_url_template"].endswith("/chunk/{index}")
