import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.database import Base, Exam, ExamAttempt, Question, User, UserExam, get_db
from routes.api_v1 import exam_api, exam_media
from routes.api_v1.user_context import get_current_user


@pytest.fixture()
def secured_exam_app(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_DATA_ENCRYPTION_KEY", "exam-access-key-with-more-than-32-bytes")
    monkeypatch.delenv("APP_ADMIN_USER_IDS", raising=False)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSession() as db:
        db.add_all([
            User(id=1, google_id="owner", email="owner@example.com", name="Owner"),
            User(id=2, google_id="other", email="other@example.com", name="Other"),
        ])
        exam = Exam(
            id=41,
            title="Prova privada",
            status="Aprovada",
            progress=100,
            progress_message="Aprovada",
            has_official_answers=1,
            gabarito_coverage=100.0,
        )
        db.add(exam)
        db.add(UserExam(user_id=1, exam_id=41, created_at="2026-09-02T00:00:00"))
        for number in range(1, 6):
            db.add(Question(
                exam_id=41,
                numero_questao=str(number),
                statement=f"Questão {number}",
                options='{"A": "Uma", "B": "Duas"}',
                correct_answer="A",
                subject="Geral",
                images=json.dumps(["/static/images/questions/private.png"]) if number == 1 else None,
            ))
        db.commit()

    media_dir = tmp_path / "questions"
    media_dir.mkdir()
    (media_dir / "private.png").write_bytes(b"\x89PNG\r\n\x1a\nprivate-image")
    (media_dir / "unreferenced.png").write_bytes(b"\x89PNG\r\n\x1a\nnot-linked")
    monkeypatch.setattr(exam_media, "QUESTION_MEDIA_DIR", media_dir.resolve())

    active_user = {"id": 1}
    app = FastAPI()
    app.include_router(exam_api.router, prefix="/api/v1")
    app.include_router(exam_media.router, prefix="/api/v1")

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=active_user["id"])
    client = TestClient(app)

    yield client, active_user, TestingSession, app

    client.close()
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_exam_detail_requires_login(secured_exam_app):
    client, _active_user, _session, app = secured_exam_app
    app.dependency_overrides.pop(get_current_user)

    response = client.get("/api/v1/exams/41")

    assert response.status_code == 401


def test_user_cannot_read_or_submit_an_exam_outside_library(secured_exam_app):
    client, active_user, TestingSession, _app = secured_exam_app
    active_user["id"] = 2

    assert client.get("/api/v1/exams/41").status_code == 404
    assert client.get("/api/v1/exams/41/progress").status_code == 404
    assert client.get("/api/v1/exams/41/progress/stream").status_code == 404
    attempt = client.post("/api/v1/exams/attempt", json={
        "exam_id": 41,
        "answers": {"1": "A"},
        "elapsed_seconds": 10,
    })
    assert attempt.status_code == 404
    with TestingSession() as db:
        assert db.query(ExamAttempt).count() == 0


def test_owner_can_read_and_explicit_claim_grants_access(secured_exam_app):
    client, active_user, _session, _app = secured_exam_app

    owner_response = client.get("/api/v1/exams/41")
    assert owner_response.status_code == 200
    assert len(owner_response.json()["questions"]) == 5
    assert owner_response.json()["questions"][0]["images"] == [
        "/api/v1/exams/41/media/private.png"
    ]

    active_user["id"] = 2
    claimed = client.post("/api/v1/exams/41/claim")
    assert claimed.status_code == 200
    assert client.get("/api/v1/exams/41").status_code == 200


def test_exam_media_requires_login_ownership_and_question_reference(secured_exam_app):
    client, active_user, _session, app = secured_exam_app

    allowed = client.get("/api/v1/exams/41/media/private.png")
    assert allowed.status_code == 200
    assert allowed.content.endswith(b"private-image")
    assert allowed.headers["cache-control"] == "private, no-store"
    assert client.get("/api/v1/exams/41/media/unreferenced.png").status_code == 404

    active_user["id"] = 2
    assert client.get("/api/v1/exams/41/media/private.png").status_code == 404

    app.dependency_overrides.pop(get_current_user)
    assert client.get("/api/v1/exams/41/media/private.png").status_code == 401


def test_status_mutation_is_admin_only_and_closed_by_default(secured_exam_app):
    client, _active_user, TestingSession, _app = secured_exam_app

    response = client.post("/api/v1/exams/41/status", json={"status": "Negada"})

    assert response.status_code == 403
    with TestingSession() as db:
        assert db.get(Exam, 41) is not None
