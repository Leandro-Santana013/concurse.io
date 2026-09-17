import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.database import Base, Exam, Question, User, UserExam, get_db
from routes.api_v1 import exam_api
from routes.api_v1.user_context import get_current_user
from services.exam_assets import asset_id_from_bytes


@pytest.fixture()
def snapshot_client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    media_root = tmp_path / "questions"
    media_root.mkdir()
    (media_root / "diagram.png").write_bytes(b"snapshot image")
    monkeypatch.setattr(exam_api, "QUESTION_MEDIA_DIR", media_root.resolve())

    app = FastAPI()
    app.include_router(exam_api.router, prefix="/api/v1")
    current_user = SimpleNamespace(id=7)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    client = TestClient(app)
    try:
        yield client, session_factory
    finally:
        client.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_snapshot_contains_linked_library_and_hashed_media(snapshot_client):
    client, session_factory = snapshot_client
    with session_factory() as db:
        db.add(User(
            id=7,
            google_id="google-sub-for-test",
            email="student@example.com",
            name="Student",
        ))
        exam = Exam(
            id=72,
            title="Prova compartilhada",
            status="Aprovada",
            user_id=None,
            has_official_answers=1,
            answer_key_source="official",
            gabarito_coverage=100.0,
        )
        db.add(exam)
        db.add(UserExam(user_id=7, exam_id=72, created_at="2026-09-17T10:00:00"))
        db.add(Question(
            exam_id=72,
            statement="Enunciado",
            options=json.dumps({"A": "Resposta"}),
            correct_answer="A",
            images=json.dumps(["/static/images/questions/diagram.png"]),
        ))
        db.commit()

    first = client.get("/api/v1/library/snapshot")
    second = client.get("/api/v1/library/snapshot")
    assert first.status_code == 200
    assert second.status_code == 200
    payload = first.json()
    assert payload["user_id"] == 7
    assert [item["id"] for item in payload["exams"]] == [72]
    assert payload["folders"][0]["exams"][0]["id"] == 72
    assert payload["library_version"] == second.json()["library_version"]

    manifest = payload["asset_manifests"]["72"]
    assert manifest["assets"][0]["asset_id"] == asset_id_from_bytes(b"snapshot image")
    assert manifest["assets"][0]["references"][0]["question_id"] == 1
    assert "google-sub-for-test" not in json.dumps(payload)
