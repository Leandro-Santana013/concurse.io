"""Serviços de autenticação e sessão do concurse.io."""

from .auth_service import (
    GoogleOAuthError,
    OAUTH_MAX_AGE_SECONDS,
    OAUTH_RETURN_COOKIE,
    OAUTH_STATE_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    SESSION_COOKIE,
    build_google_authorization_url,
    create_session_token,
    exchange_google_code,
    get_frontend_url,
    get_google_redirect_uri,
    google_oauth_configured,
    is_cookie_secure,
    normalize_return_path,
    read_session_token,
    session_token_needs_rotation,
)

__all__ = [
    "GoogleOAuthError",
    "OAUTH_MAX_AGE_SECONDS",
    "OAUTH_RETURN_COOKIE",
    "OAUTH_STATE_COOKIE",
    "SESSION_MAX_AGE_SECONDS",
    "SESSION_COOKIE",
    "build_google_authorization_url",
    "create_session_token",
    "exchange_google_code",
    "get_frontend_url",
    "get_google_redirect_uri",
    "google_oauth_configured",
    "is_cookie_secure",
    "normalize_return_path",
    "read_session_token",
    "session_token_needs_rotation",
]
