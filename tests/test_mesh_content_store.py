import pytest

from services.exam_assets import asset_id_from_bytes
from services.p2p.content_store import ContentAddressedStore
from services.p2p.mesh_tokens import create_mesh_token, read_mesh_token


def test_content_store_writes_and_verifies_by_digest(tmp_path):
    store = ContentAddressedStore(tmp_path / "content")
    data = b"question image bytes"
    asset_id = asset_id_from_bytes(data)

    path = store.put_bytes(asset_id, data)
    assert path.is_file()
    assert store.has(asset_id)
    assert store.read_bytes(asset_id) == data
    assert path.name == asset_id.removeprefix("sha256:")

    with pytest.raises(ValueError):
        store.put_bytes(asset_id, b"tampered")


def test_mesh_token_is_scoped_to_node_asset_and_expiration(monkeypatch):
    monkeypatch.setenv("MESH_SHARED_SECRET", "mesh-secret")
    asset_id = asset_id_from_bytes(b"blob")
    token = create_mesh_token(
        user_id=7,
        node_id="desktop-node",
        asset_id=asset_id,
        now=100,
        expires_in=60,
    )

    assert read_mesh_token(token, asset_id=asset_id, node_id="desktop-node", now=159)["uid"] == 7
    assert read_mesh_token(token, asset_id=asset_id, node_id="other-node", now=120) is None
    assert read_mesh_token(token, asset_id=asset_id_from_bytes(b"other"), now=120) is None
    assert read_mesh_token(token, asset_id=asset_id, now=160) is None
    assert read_mesh_token(f"{token[:-1]}x", asset_id=asset_id, now=120) is None
