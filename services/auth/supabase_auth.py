"""Validação server-side de sessões emitidas pelo Supabase Auth.

O access token permanece no cliente. A API só o envia ao endpoint oficial
``/auth/v1/user`` para obter a identidade verificada e então emite a sessão
criptografada já usada pelo restante do concurse.io.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

import requests


LOGGER = logging.getLogger(__name__)
DEFAULT_TIMEOUT_SECONDS = 12


class SupabaseAuthError(RuntimeError):
    """Erro esperado ao validar um token do Supabase Auth."""


def _project_url() -> str:
    return str(os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")


def _publishable_key() -> str:
    return str(
        os.environ.get("SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or ""
    ).strip()


def supabase_auth_configured() -> bool:
    return bool(_project_url() and _publishable_key())


def _metadata_value(metadata: object, *keys: str) -> str:
    if not isinstance(metadata, dict):
        return ""
    for key in keys:
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return ""


def verify_supabase_access_token(access_token: str) -> Dict[str, Any]:
    """Consulta a identidade do Supabase sem aceitar claims não verificados."""

    token = str(access_token or "").strip()
    if len(token) < 20:
        raise SupabaseAuthError("Token do Supabase ausente ou inválido.")
    if not supabase_auth_configured():
        raise SupabaseAuthError("Supabase Auth não está configurado no servidor.")

    try:
        response = requests.get(
            f"{_project_url()}/auth/v1/user",
            headers={
                "apikey": _publishable_key(),
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", "unknown")
        LOGGER.info("Supabase access token rejected (status=%s).", status)
        raise SupabaseAuthError("A sessão do Supabase expirou ou é inválida.") from exc
    except (requests.RequestException, ValueError, TypeError) as exc:
        LOGGER.warning("Supabase identity request failed (%s).", type(exc).__name__)
        raise SupabaseAuthError("Não foi possível validar a sessão do Supabase.") from exc

    if not isinstance(payload, dict):
        raise SupabaseAuthError("Resposta de identidade do Supabase inválida.")
    subject = str(payload.get("id") or "").strip()
    email = str(payload.get("email") or "").strip()
    if not subject or not email:
        raise SupabaseAuthError("A conta do Supabase não forneceu os dados mínimos.")

    metadata = payload.get("user_metadata")
    name = _metadata_value(metadata, "full_name", "name", "user_name") or "Concurseiro"
    picture = _metadata_value(metadata, "avatar_url", "picture")
    return {
        "sub": subject[:200],
        "email": email[:200],
        "name": name[:200],
        "picture": picture[:500],
    }
