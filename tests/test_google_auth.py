from urllib.parse import parse_qs, urlparse
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.database import Base, User, get_db
from routes.api_v1 import auth_api
from services.auth import create_session_token, read_session_token
from app_security import identifier_lookup_values
from fastapi_app import _OAuthAccessLogFilter
from services.auth import auth_service


def test_signed_session_rejects_tampering_and_expiration(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-with-enough-entropy")
    token = create_session_token(42, now=100, max_age=60)

    assert token.startswith("v2.")
    assert read_session_token(token, now=159) == 42
    assert read_session_token(token, now=160) is None
    assert read_session_token(f"{token[:-1]}x", now=120) is None


def test_oauth_callback_query_is_redacted_from_access_log():
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1",
            "GET",
            "/api/v1/auth/google/callback?code=secret-code&state=secret-state",
            "1.1",
            302,
        ),
        exc_info=None,
    )

    assert _OAuthAccessLogFilter().filter(record) is True
    assert record.args[2] == "/api/v1/auth/google/callback?[REDACTED]"
    assert "secret-code" not in record.getMessage()


def test_google_id_token_validation_tolerates_clock_skew(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-with-enough-entropy")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    captured = {}

    class TokenResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id_token": "signed-google-id-token"}

    monkeypatch.setattr(auth_service.requests, "post", lambda *args, **kwargs: TokenResponse())

    def verify_token(_token, _request, _audience, *, clock_skew_in_seconds):
        captured["clock_skew"] = clock_skew_in_seconds
        return {
            "sub": "google-user-123",
            "email": "estudante@example.com",
            "email_verified": True,
            "iss": "https://accounts.google.com",
        }

    monkeypatch.setattr(auth_service.google_id_token, "verify_oauth2_token", verify_token)

    identity = auth_service.exchange_google_code("authorization-code", "http://localhost/callback")

    assert identity["sub"] == "google-user-123"
    assert captured["clock_skew"] == 60


@pytest.fixture()
def auth_client(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-with-enough-entropy")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("FRONTEND_URL", "http://frontend.test")
    monkeypatch.delenv("AUTH_DEV_BYPASS", raising=False)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(auth_api.router, prefix="/api/v1")

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, follow_redirects=False)
    try:
        yield client, session_factory
    finally:
        client.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_google_login_callback_session_and_logout(auth_client, monkeypatch):
    client, session_factory = auth_client
    login_response = client.get("/api/v1/auth/google/login", params={"next": "/biblioteca"})

    assert login_response.status_code == 302
    authorization_url = urlparse(login_response.headers["location"])
    assert authorization_url.netloc == "accounts.google.com"
    authorization_params = parse_qs(authorization_url.query)
    state = authorization_params["state"][0]
    assert authorization_params["scope"] == ["openid email profile"]

    monkeypatch.setattr(
        auth_api,
        "exchange_google_code",
        lambda _code, _redirect_uri: {
            "sub": "google-user-123",
            "email": "estudante@example.com",
            "email_verified": True,
            "name": "Pessoa Estudante",
            "picture": "https://example.test/avatar.png",
            "iss": "https://accounts.google.com",
        },
    )
    callback_response = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "authorization-code", "state": state},
    )

    assert callback_response.status_code == 302
    assert callback_response.headers["location"] == "http://frontend.test/biblioteca"
    assert client.cookies.get("concurse_session")

    profile_response = client.get("/api/v1/auth/me")
    assert profile_response.status_code == 200
    assert profile_response.json() == {
        "id": 1,
        "email": "estudante@example.com",
        "name": "Pessoa Estudante",
        "picture": "https://example.test/avatar.png",
        "is_authenticated": True,
    }

    with session_factory() as db:
        lookup_values = identifier_lookup_values("google-user-123")
        assert db.query(User).filter(User.google_subject_hash.in_(lookup_values)).count() == 1
        stored = db.execute(text(
            "SELECT google_id, email, name, picture, email_encrypted, "
            "name_encrypted, picture_encrypted FROM users"
        )).mappings().one()
        assert stored["google_id"].startswith("hmac:v1:")
        assert stored["email"].startswith("private+")
        assert stored["name"] is None
        assert stored["picture"] is None
        assert stored["email_encrypted"].startswith("enc:v1:")
        assert stored["name_encrypted"].startswith("enc:v1:")
        assert stored["picture_encrypted"].startswith("enc:v1:")

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_google_callback_rejects_invalid_state(auth_client):
    client, _ = auth_client

    response = client.get(
        "/api/v1/auth/google/callback",
        params={"code": "authorization-code", "state": "forged"},
    )

    assert response.status_code == 302
    assert response.headers["location"].startswith("http://frontend.test/login?error=invalid_state")


def test_delete_account_removes_user(auth_client, monkeypatch):
    client, _ = auth_client
    login_response = client.get("/api/v1/auth/google/login")
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]

    monkeypatch.setattr(
        auth_api,
        "exchange_google_code",
        lambda _code, _redirect_uri: {
            "sub": "user-to-delete",
            "email": "delete@example.com",
            "name": "Deletavel",
            "picture": "",
        },
    )

    client.get("/api/v1/auth/google/callback", params={"code": "code", "state": state})

    assert client.get("/api/v1/auth/me").status_code == 200

    del_resp = client.delete("/api/v1/auth/me")
    assert del_resp.status_code == 200
    assert del_resp.json()["ok"] is True

    assert client.get("/api/v1/auth/me").status_code == 401


