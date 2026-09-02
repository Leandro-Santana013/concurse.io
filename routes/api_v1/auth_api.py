import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from models.database import User, get_db
from routes.api_v1.user_context import get_current_user
from app_security import identifier_lookup_values
from services.auth import (
    GoogleOAuthError,
    OAUTH_MAX_AGE_SECONDS,
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
    normalize_return_path,
    session_token_needs_rotation,
)

router = APIRouter()


def _login_redirect(*, error: str, return_to: str = "/") -> RedirectResponse:
    query = urlencode({"error": error, "next": normalize_return_path(return_to)})
    response = RedirectResponse(f"{get_frontend_url()}/login?{query}", status_code=302)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/auth/config")
def get_auth_config():
    return {"google_enabled": google_oauth_configured()}


@router.get("/auth/google/login")
def google_login(
    request: Request,
    next_path: str = Query(default="/", alias="next"),
):
    """Inicia OAuth com state de uso único e retorno restrito à própria aplicação."""
    return_to = normalize_return_path(next_path)
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
    if error:
        return _login_redirect(error="access_denied", return_to=return_to)

    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not state or not expected_state or not secrets.compare_digest(state, expected_state):
        return _login_redirect(error="invalid_state", return_to=return_to)
    if not code:
        return _login_redirect(error="missing_code", return_to=return_to)

    try:
        identity = exchange_google_code(code, get_google_redirect_uri(request))
    except GoogleOAuthError:
        return _login_redirect(error="google_validation_failed", return_to=return_to)

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
    return response


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

