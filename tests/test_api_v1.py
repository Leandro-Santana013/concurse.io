import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi_app import app
from models.database import Base, get_db
from routes.api_v1.user_context import get_current_user

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)


def _override_get_db():
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)
authenticated_user = SimpleNamespace(
    id=1,
    email="estudante@example.com",
    name="Pessoa Estudante",
    picture="",
)


def _override_authenticated_user():
    return authenticated_user


app.dependency_overrides[get_current_user] = _override_authenticated_user

def test_healthcheck():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "2.0.0"

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        data = response.json()
        assert "concurse.io API V2" in data.get("name", "")
    else:
        assert "<!DOCTYPE html>" in response.text or "<html" in response.text


def test_protected_routes_require_login():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        assert client.get("/api/v1/auth/me").status_code == 401
        assert client.get("/api/v1/ranking").status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = _override_authenticated_user


def test_legacy_question_media_is_not_public():
    response = client.get("/static/images/questions/qimg_exam41_q1_1.png")
    assert response.status_code == 404


def test_folders_api():
    response = client.get("/api/v1/folders")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_stats_overview():
    response = client.get("/api/v1/stats/overview")
    assert response.status_code == 200
    data = response.json()
    assert "total_exams" in data
    assert "global_accuracy" in data
    assert "streak" in data

def test_auth_me():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert data["is_authenticated"] is True

def test_custom_exam_generation():
    # If there are questions in DB, it generates custom exam
    response = client.post("/api/v1/exams/generate_custom?count=5")
    # Status can be 200 if questions exist, or 400 if DB is empty on first boot
    assert response.status_code in [200, 400]
    if response.status_code == 200:
        data = response.json()
        assert len(data["questions"]) <= 5

if __name__ == "__main__":
    test_healthcheck()
    test_root()
    test_folders_api()
    test_stats_overview()
    test_auth_me()
    test_custom_exam_generation()
    print(" SUCCESS: Todos os testes de test_api_v1.py passaram com sucesso!")

