"""Tokens curtos para o tráfego peer-to-peer autorizado pelo servidor."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from .content_store import normalize_asset_id


TOKEN_PREFIX = "m1."


def _secret() -> bytes:
    value = os.environ.get("MESH_SHARED_SECRET") or os.environ.get("SESSION_SECRET")
    if not value:
        raise RuntimeError("MESH_SHARED_SECRET ou SESSION_SECRET não configurado")
    return value.encode("utf-8")


def _encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    normalized = str(value or "").rstrip("=")
    padding = "=" * (-len(normalized) % 4)
    decoded = base64.urlsafe_b64decode(normalized + padding)
    if _encode(decoded) != normalized:
        raise ValueError("Token de malha não canônico")
    return decoded


def create_mesh_token(
    *,
    user_id: int,
    node_id: str,
    asset_id: str,
    expires_in: int = 120,
    now: int | None = None,
) -> str:
    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None:
        raise ValueError("asset_id inválido")
    payload = {
        "v": 1,
        "uid": int(user_id),
        "node": str(node_id)[:128],
        "asset": normalized_asset,
        "exp": int(now if now is not None else time.time()) + int(expires_in),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{TOKEN_PREFIX}{encoded}.{signature}"


def read_mesh_token(
    token: str | None,
    *,
    asset_id: str,
    node_id: str | None = None,
    now: int | None = None,
) -> dict[str, Any] | None:
    normalized_asset = normalize_asset_id(asset_id)
    if normalized_asset is None or not token or not token.startswith(TOKEN_PREFIX):
        return None
    try:
        encoded, provided_signature = token[len(TOKEN_PREFIX):].split(".", 1)
        expected_signature = hmac.new(
            _secret(),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, provided_signature):
            return None
        payload = json.loads(_decode(encoded).decode("utf-8"))
        if payload.get("v") != 1 or payload.get("asset") != normalized_asset:
            return None
        if node_id is not None and payload.get("node") != str(node_id):
            return None
        if int(payload["exp"]) <= int(now if now is not None else time.time()):
            return None
        user_id = int(payload["uid"])
        if user_id <= 0:
            return None
        return payload
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError, RuntimeError):
        return None
