import json
from types import SimpleNamespace

from services.exam_assets import (
    asset_id_from_bytes,
    build_exam_asset_manifest,
)


def test_asset_id_is_deterministic_and_content_based():
    assert asset_id_from_bytes(b"same image") == asset_id_from_bytes(b"same image")
    assert asset_id_from_bytes(b"same image") != asset_id_from_bytes(b"different image")
    assert asset_id_from_bytes(b"same image").startswith("sha256:")


def test_manifest_deduplicates_body_and_option_references(tmp_path):
    media_root = tmp_path / "questions"
    media_root.mkdir()
    (media_root / "diagram.png").write_bytes(b"png bytes")

    question = SimpleNamespace(
        id=41,
        images=json.dumps(["/static/images/questions/diagram.png"]),
        option_images=json.dumps({"A": ["/static/images/questions/diagram.png"]}),
    )
    manifest = build_exam_asset_manifest(72, [question], media_root=media_root)

    assert manifest["exam_id"] == 72
    assert manifest["manifest_id"].startswith("sha256:")
    assert len(manifest["assets"]) == 1
    asset = manifest["assets"][0]
    assert asset["available"] is True
    assert asset["size"] == len(b"png bytes")
    assert {reference["slot"] for reference in asset["references"]} == {"body", "option:A"}


def test_manifest_keeps_unresolved_reference_without_trusting_path(tmp_path):
    question = SimpleNamespace(
        id=9,
        images=json.dumps(["/static/images/questions/missing.png"]),
        option_images=None,
    )
    manifest = build_exam_asset_manifest(3, [question], media_root=tmp_path)

    asset = manifest["assets"][0]
    assert asset["available"] is False
    assert asset["asset_id"].startswith("ref:")
    assert "missing.png" in asset["media_url"]
