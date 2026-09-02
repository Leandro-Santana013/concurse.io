"""OAuth Google e cookies de sessão assinados sem estado no servidor."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import Request
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token


LOGGER = logging.getLogger(__name__)
SESSION_COOKIE = "concurse_session"
OAUTH_STATE_COOKIE = "concurse_oauth_state"
OAUTH_RETURN_COOKIE = "concurse_oauth_return"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
SESSION_TOKEN_PREFIX = "v2."
SESSION_TOKEN_AAD = b"concurse.io:session:v2"
OAUTH_MAX_AGE_SECONDS = 10 * 60
DEFAULT_GOOGLE_CLOCK_SKEW_SECONDS = 60
MAX_GOOGLE_CLOCK_SKEW_SECONDS = 300


class GoogleOAuthError(RuntimeError):
    """Erro esperado e seguro durante o fluxo OAuth."""


def _session_secret() -> bytes:
    secret = os.environ.get("SESSION_SECRET") or os.environ.get("FLASK_SECRET_KEY")
    if not secret:
        raise RuntimeError("SESSION_SECRET não configurado.")
    return secret.encode("utf-8")


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_session_token(
    user_id: int,
    *,
    now: Optional[int] = None,
    max_age: int = SESSION_MAX_AGE_SECONDS,
) -> str:
    issued_at = int(now if now is not None else time.time())
    payload = {
        "uid": int(user_id),
        "iat": issued_at,
        "exp": issued_at + int(max_age),
        "v": 2,
    }
    plaintext = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encryption_key = hmac.new(
        _session_secret(),
        b"concurse.io:session-encryption:v2",
        hashlib.sha256,
    ).digest()
    nonce = os.urandom(12)
    ciphertext = AESGCM(encryption_key).encrypt(
        nonce,
        plaintext,
        SESSION_TOKEN_AAD,
    )
    return f"{SESSION_TOKEN_PREFIX}{_b64encode(nonce + ciphertext)}"


def _read_legacy_session_token(token: str) -> Optional[Dict[str, Any]]:
    if token.count(".") != 1:
        return None
    encoded_payload, encoded_signature = token.split(".", 1)
    signature = hmac.new(
        _session_secret(),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    provided_signature = _b64decode(encoded_signature)
    if not hmac.compare_digest(signature, provided_signature):
        return None
    return json.loads(_b64decode(encoded_payload).decode("utf-8"))


def _read_encrypted_session_token(token: str) -> Dict[str, Any]:
    packed = _b64decode(token[len(SESSION_TOKEN_PREFIX):])
    nonce, ciphertext = packed[:12], packed[12:]
    if len(nonce) != 12 or not ciphertext:
        raise ValueError("Token de sessão incompleto.")
    encryption_key = hmac.new(
        _session_secret(),
        b"concurse.io:session-encryption:v2",
        hashlib.sha256,
    ).digest()
    plaintext = AESGCM(encryption_key).decrypt(
        nonce,
        ciphertext,
        SESSION_TOKEN_AAD,
    )
    return json.loads(plaintext.decode("utf-8"))


def read_session_token(token: Optional[str], *, now: Optional[int] = None) -> Optional[int]:
    if not token:
        return None
    try:
        if token.startswith(SESSION_TOKEN_PREFIX):
            payload = _read_encrypted_session_token(token)
            expected_version = 2
        else:
            payload = _read_legacy_session_token(token)
            expected_version = 1
        if payload is None:
            return None
        current_time = int(now if now is not None else time.time())
        user_id = int(payload["uid"])
        if (
            payload.get("v") != expected_version
            or user_id <= 0
            or int(payload["exp"]) <= current_time
            or int(payload["iat"]) > current_time + MAX_GOOGLE_CLOCK_SKEW_SECONDS
        ):
            return None
        return user_id
    except (
        InvalidTag,
        KeyError,
        RuntimeError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None


def session_token_needs_rotation(token: Optional[str]) -> bool:
    return bool(token and not token.startswith(SESSION_TOKEN_PREFIX))


def google_oauth_configured() -> bool:
    return bool(
        os.environ.get("GOOGLE_CLIENT_ID")
        and os.environ.get("GOOGLE_CLIENT_SECRET")
        and (os.environ.get("SESSION_SECRET") or os.environ.get("FLASK_SECRET_KEY"))
    )


def get_google_clock_skew_seconds() -> int:
    """Tolera pequenas diferenças entre o relógio local e o emissor do token."""
    configured = os.environ.get("GOOGLE_CLOCK_SKEW_SECONDS", "").strip()
    try:
        value = int(configured) if configured else DEFAULT_GOOGLE_CLOCK_SKEW_SECONDS
    except ValueError:
        value = DEFAULT_GOOGLE_CLOCK_SKEW_SECONDS
    return min(max(value, 0), MAX_GOOGLE_CLOCK_SKEW_SECONDS)


def get_frontend_url() -> str:
    return os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def get_google_redirect_uri(request: Request) -> str:
    configured = os.environ.get("GOOGLE_REDIRECT_URI")
    if configured:
        return configured

    if request.url.hostname in {"localhost", "127.0.0.1"}:
        return "http://localhost:8000/api/v1/auth/google/callback"
    return str(request.url_for("google_callback"))


def normalize_return_path(value: Optional[str]) -> str:
    candidate = str(value or "/").strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return "/"
    return candidate[:500]


def is_cookie_secure(request: Request) -> bool:
    configured = os.environ.get("SESSION_COOKIE_SECURE")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    return request.url.scheme == "https" or forwarded_proto == "https"


def build_google_authorization_url(request: Request, state: str) -> str:
    if not google_oauth_configured():
        raise GoogleOAuthError("Google OAuth não está configurado.")
    params = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": get_google_redirect_uri(request),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
        "include_granted_scopes": "true",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def exchange_google_code(code: str, redirect_uri: str) -> Dict[str, Any]:
    """Troca o código e valida assinatura, audiência, emissor e expiração do ID token."""
    if not google_oauth_configured():
        raise GoogleOAuthError("Google OAuth não está configurado.")
    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=12,
        )
        response.raise_for_status()
        token_payload = response.json()
        raw_id_token = token_payload.get("id_token")
        if not raw_id_token:
            raise GoogleOAuthError("O Google não retornou um token de identidade.")

        identity = google_id_token.verify_oauth2_token(
            raw_id_token,
            GoogleRequest(),
            os.environ["GOOGLE_CLIENT_ID"],
            clock_skew_in_seconds=get_google_clock_skew_seconds(),
        )
    except GoogleOAuthError:
        raise
    except requests.HTTPError as exc:
        response = exc.response
        google_error = "unknown"
        try:
            google_error = str(response.json().get("error") or google_error)[:80]
        except (AttributeError, TypeError, ValueError):
            pass
        LOGGER.warning(
            "Google OAuth token exchange failed (status=%s, error=%s).",
            getattr(response, "status_code", "unknown"),
            google_error,
        )
        raise GoogleOAuthError("O Google recusou a troca do código de autorização.") from exc
    except ValueError as exc:
        reason = " ".join(str(exc).split())[:240] or type(exc).__name__
        LOGGER.warning("Google ID token validation failed: %s", reason)
        raise GoogleOAuthError("O token de identidade retornado pelo Google é inválido.") from exc
    except requests.RequestException as exc:
        LOGGER.warning("Google OAuth request failed (%s).", type(exc).__name__)
        raise GoogleOAuthError("Não foi possível conectar ao Google para validar o login.") from exc
    except Exception as exc:
        LOGGER.exception("Unexpected Google OAuth validation failure.")
        raise GoogleOAuthError("Não foi possível validar a autenticação do Google.") from exc

    issuer = identity.get("iss")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise GoogleOAuthError("Emissor do token Google inválido.")
    if identity.get("email_verified") is not True:
        raise GoogleOAuthError("A conta Google precisa ter um e-mail verificado.")
    if not identity.get("sub") or not identity.get("email"):
        raise GoogleOAuthError("A conta Google não forneceu os dados mínimos.")
    return identity
