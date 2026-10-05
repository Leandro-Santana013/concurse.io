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


class SupabaseAuthUnavailableError(SupabaseAuthError):
    """O serviço não pôde validar a sessão; não significa token inválido."""


def _network_error_kinds(error: BaseException) -> str:
    """Log only exception types and error numbers, never URLs or credentials."""
    pending = [error]
    seen = set()
    kinds = []
    while pending and len(seen) < 12:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        name = type(current).__name__
        number = getattr(current, "errno", None)
        kinds.append(f"{name}[errno={number}]" if isinstance(number, int) else name)
        pending.extend(value for value in (
            getattr(current, "__cause__", None),
            getattr(current, "__context__", None),
            getattr(current, "reason", None),
            *getattr(current, "args", ()),
        ) if isinstance(value, BaseException))
    return " -> ".join(kinds)


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
        if status not in (401, 403):
            LOGGER.warning("Supabase identity service unavailable (status=%s).", status)
            raise SupabaseAuthUnavailableError(
                "O serviço de login está indisponível. Tente novamente em instantes."
            ) from exc
        LOGGER.info("Supabase access token rejected (status=%s).", status)
        raise SupabaseAuthError("A sessão do Supabase expirou ou é inválida.") from exc
    except (requests.RequestException, ValueError, TypeError) as exc:
        LOGGER.warning("Supabase identity request failed (%s).", _network_error_kinds(exc))
        raise SupabaseAuthUnavailableError(
            "Não foi possível conectar ao serviço de login. Confira sua conexão e tente novamente."
        ) from exc

    if not isinstance(payload, dict):
        raise SupabaseAuthUnavailableError("Resposta de identidade do Supabase inválida.")
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
