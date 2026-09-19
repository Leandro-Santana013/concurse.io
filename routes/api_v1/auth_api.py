import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from models.database import DesktopOAuthCode, User, get_db
from routes.api_v1.user_context import get_current_user
from app_security import identifier_lookup_values
from services.auth import (
    GoogleOAuthError,
    DESKTOP_OAUTH_CODE_MAX_AGE_SECONDS,
    OAUTH_MAX_AGE_SECONDS,
    OAUTH_CLIENT_COOKIE,
    OAUTH_RETURN_COOKIE,
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    SESSION_MAX_AGE_SECONDS,
    build_google_authorization_url,
    create_session_token,
    exchange_google_code,
    get_frontend_url,
    get_google_redirect_uri,
    google_oauth_configured,
    is_cookie_secure,
    normalize_desktop_return,
    normalize_return_path,
    session_token_needs_rotation,
)

router = APIRouter()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _desktop_code_hash(code: str) -> str:
    return hashlib.sha256(str(code).encode("utf-8")).hexdigest()


def _login_redirect(*, error: str, return_to: str = "/") -> RedirectResponse:
    query = urlencode({"error": error, "next": normalize_return_path(return_to)})
    response = RedirectResponse(f"{get_frontend_url()}/login?{query}", status_code=302)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _oauth_error_redirect(
    *,
    error: str,
    return_to: str,
    desktop_redirect: str | None,
) -> RedirectResponse:
    if desktop_redirect is None:
        return _login_redirect(error=error, return_to=return_to)
    response = RedirectResponse(
        f"{desktop_redirect}?{urlencode({'error': error})}",
        status_code=302,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    for cookie_name in (OAUTH_STATE_COOKIE, OAUTH_RETURN_COOKIE, OAUTH_CLIENT_COOKIE):
        response.delete_cookie(cookie_name, path="/api/v1/auth/google")
    return response


@router.get("/auth/config")
def get_auth_config():
    return {"google_enabled": google_oauth_configured()}


@router.get("/auth/google/login")
def google_login(
    request: Request,
    next_path: str = Query(default="/", alias="next"),
    client: str = Query(default="web"),
    desktop_return: str = Query(default=""),
):
    """Inicia OAuth com state de uso único e retorno restrito à própria aplicação."""
    return_to = normalize_return_path(next_path)
    desktop_redirect = normalize_desktop_return(desktop_return) if client == "desktop" else None
    if client == "desktop" and desktop_redirect is None:
        return _login_redirect(error="invalid_desktop_callback", return_to=return_to)
    state = secrets.token_urlsafe(32)
    try:
        authorization_url = build_google_authorization_url(request, state)
    except GoogleOAuthError:
        return _login_redirect(error="google_not_configured", return_to=return_to)

    response = RedirectResponse(authorization_url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    cookie_options = {
        "max_age": OAUTH_MAX_AGE_SECONDS,
        "httponly": True,
        "secure": is_cookie_secure(request),
        "samesite": "lax",
        "path": "/api/v1/auth/google",
    }
    response.set_cookie(OAUTH_STATE_COOKIE, state, **cookie_options)
    response.set_cookie(OAUTH_RETURN_COOKIE, return_to, **cookie_options)
    if desktop_redirect is not None:
        response.set_cookie(OAUTH_CLIENT_COOKIE, desktop_redirect, **cookie_options)
    return response


@router.get("/auth/google/callback", name="google_callback")
def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    """Valida o retorno do Google, cria/atualiza o usuário e emite a sessão."""
    return_to = normalize_return_path(request.cookies.get(OAUTH_RETURN_COOKIE))
    desktop_redirect = normalize_desktop_return(request.cookies.get(OAUTH_CLIENT_COOKIE))
    if error:
        return _oauth_error_redirect(
            error="access_denied",
            return_to=return_to,
            desktop_redirect=desktop_redirect,
        )

    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        return _oauth_error_redirect(
            error="invalid_state",
            return_to=return_to,
            desktop_redirect=desktop_redirect,
        )
    if not code:
        return _oauth_error_redirect(
            error="missing_code",
            return_to=return_to,
            desktop_redirect=desktop_redirect,
        )

    try:
        identity = exchange_google_code(code, get_google_redirect_uri(request))
    except GoogleOAuthError:
        return _oauth_error_redirect(
            error="google_validation_failed",
            return_to=return_to,
            desktop_redirect=desktop_redirect,
        )

    google_id = str(identity["sub"])[:200]
    lookup_values = identifier_lookup_values(google_id)
    user = db.query(User).filter(User.google_subject_hash.in_(lookup_values)).first()
    if user is None:
        user = User(
            google_id=google_id,
            email=str(identity["email"])[:200],
            name=str(identity.get("name") or "Concurseiro")[:200],
            picture=str(identity.get("picture") or "")[:500] or None,
        )
        db.add(user)
    else:
        # Recalcula com a chave ativa durante rotações; o `sub` bruto nunca é persistido.
        user.google_id = google_id
        user.email = str(identity["email"])[:200]
        user.name = str(identity.get("name") or user.name or "Concurseiro")[:200]
        user.picture = str(identity.get("picture") or user.picture or "")[:500] or None
    db.commit()
    db.refresh(user)

    if desktop_redirect is not None:
        # O código curto não contém identidade; só o hash fica persistido e a
        # troca invalida o registro. O navegador nunca recebe a sessão final.
        raw_code = secrets.token_urlsafe(32)
        now = _now()
        db.query(DesktopOAuthCode).filter(
            DesktopOAuthCode.expires_at <= _iso(now),
        ).delete(synchronize_session=False)
        db.add(DesktopOAuthCode(
            code_hash=_desktop_code_hash(raw_code),
            user_id=int(user.id),
            expires_at=_iso(now + timedelta(seconds=DESKTOP_OAUTH_CODE_MAX_AGE_SECONDS)),
            created_at=_iso(now),
        ))
        db.commit()
        response = RedirectResponse(
            f"{desktop_redirect}?{urlencode({'code': raw_code})}",
            status_code=302,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth/google")
        response.delete_cookie(OAUTH_RETURN_COOKIE, path="/api/v1/auth/google")
        response.delete_cookie(OAUTH_CLIENT_COOKIE, path="/api/v1/auth/google")
        return response

    response = RedirectResponse(f"{get_frontend_url()}{return_to}", status_code=302)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user.id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=is_cookie_secure(request),
        samesite="lax",
        path="/",
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth/google")
    response.delete_cookie(OAUTH_RETURN_COOKIE, path="/api/v1/auth/google")
    response.delete_cookie(OAUTH_CLIENT_COOKIE, path="/api/v1/auth/google")
    return response


@router.post("/auth/google/desktop/exchange")
def exchange_desktop_oauth_code(
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
):
    """Troca o código loopback por uma sessão Bearer para o app Tauri."""

    raw_code = str(payload.get("code") or "").strip()
    if len(raw_code) < 20:
        raise HTTPException(status_code=400, detail="Código OAuth desktop inválido.")
    now = _now()
    code = db.get(DesktopOAuthCode, _desktop_code_hash(raw_code))
    if (
        code is None
        or code.used_at is not None
        or code.expires_at <= _iso(now)
    ):
        raise HTTPException(status_code=400, detail="Código OAuth desktop expirado ou já utilizado.")
    user = db.get(User, int(code.user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="Usuário OAuth não encontrado.")
    code.used_at = _iso(now)
    db.commit()
    return {
        "session_token": create_session_token(int(user.id)),
        "user": {
            "id": int(user.id),
            "email": user.email,
            "name": user.name or "Concurseiro",
            "picture": user.picture or "",
            "is_authenticated": True,
        },
    }


@router.get("/auth/me")
def get_current_user_profile(
    request: Request,
    current_user=Depends(get_current_user),
):
    response = JSONResponse({
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name or "Concurseiro",
        "picture": current_user.picture or "",
        "is_authenticated": True,
    })
    response.headers["Cache-Control"] = "no-store"
    if session_token_needs_rotation(request.cookies.get(SESSION_COOKIE)):
        response.set_cookie(
            SESSION_COOKIE,
            create_session_token(current_user.id),
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            secure=is_cookie_secure(request),
            samesite="lax",
            path="/",
        )
    return response


@router.post("/auth/logout")
def logout(request: Request):
    response = JSONResponse({"ok": True})
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=is_cookie_secure(request),
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Clear-Site-Data"] = '"cache", "storage"'
    return response


@router.delete("/auth/me")
def delete_account(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Exclui permanentemente a conta do usuário e limpa os cookies de sessão."""
    db.delete(current_user)
    db.commit()

    response = JSONResponse({"ok": True, "message": "Conta excluída com sucesso."})
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=is_cookie_secure(request),
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Clear-Site-Data"] = '"cache", "storage"'
    return response

