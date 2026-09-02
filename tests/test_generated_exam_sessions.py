import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi_app import app
from models.database import (
    Base,
    Exam,
    ExamAttempt,
    GeneratedExamSession,
    Question,
    User,
    get_db,
)
from routes.api_v1.user_context import get_current_user


@pytest.fixture()
def api_and_session_factory():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session_factory = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )
    Base.metadata.create_all(bind=test_engine)

    with test_session_factory() as db:
        db.add(User(
            id=1,
            google_id="generated-session-test-user",
            email="generated-session@example.com",
            name="Test User",
        ))
        db.add(User(
            id=2,
            google_id="foreign-generated-session-user",
            email="foreign-generated-session@example.com",
            name="Foreign User",
        ))
        source_exam = Exam(
            title="Prova fonte",
            status="Aprovada",
            user_id=1,
            has_official_answers=1,
            gabarito_coverage=100.0,
        )
        db.add(source_exam)
        db.flush()
        for index in range(1, 6):
            db.add(Question(
                exam_id=source_exam.id,
                statement=f"Enunciado {index}",
                options=json.dumps({"A": "Correta", "B": "Incorreta"}),
                correct_answer="A",
                subject="Português" if index <= 3 else "Direito",
                numero_questao=str(100 + index),
            ))
        foreign_exam = Exam(
            title="Prova de outro usuário",
            status="Aprovada",
            user_id=2,
            has_official_answers=1,
            gabarito_coverage=100.0,
        )
        db.add(foreign_exam)
        db.flush()
        for index in range(1, 6):
            db.add(Question(
                exam_id=foreign_exam.id,
                statement=f"Conteúdo privado estrangeiro {index}",
                options=json.dumps({"A": "Correta", "B": "Incorreta"}),
                correct_answer="A",
                subject="Privado",
                numero_questao=str(index),
            ))
        db.commit()

    def override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    client = TestClient(app)
    try:
        yield client, test_session_factory
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def test_custom_exam_has_real_id_can_reload_and_submit(api_and_session_factory):
    client, session_factory = api_and_session_factory

    empty_overview = client.get("/api/v1/stats/overview").json()
    assert empty_overview["rank"] == "—"

    generated_response = client.post("/api/v1/exams/generate_custom?count=5")
    assert generated_response.status_code == 200
    generated = generated_response.json()

    assert generated["id"] not in (888888, 999999)
    assert generated["status"] == "Sessão"
    assert [question["numero_questao"] for question in generated["questions"]] == ["1", "2", "3", "4", "5"]
    original_question_ids = [question["id"] for question in generated["questions"]]

    with session_factory() as db:
        exam = db.get(Exam, generated["id"])
        session = db.get(GeneratedExamSession, generated["id"])
        assert exam is not None
        assert exam.status == "Sessão"
        assert exam.questions == []
        assert session is not None
        assert session.kind == "custom"
        assert json.loads(session.question_ids_json) == original_question_ids

    reloaded_response = client.get(f"/api/v1/exams/{generated['id']}")
    assert reloaded_response.status_code == 200
    reloaded = reloaded_response.json()
    assert [question["id"] for question in reloaded["questions"]] == original_question_ids
    assert [question["numero_questao"] for question in reloaded["questions"]] == ["1", "2", "3", "4", "5"]

    answers = {
        question["numero_questao"]: question["correct_answer"]
        for question in reloaded["questions"]
    }
    attempt_response = client.post("/api/v1/exams/attempt", json={
        "exam_id": generated["id"],
        "elapsed_seconds": 321,
        "answers": answers,
    })
    assert attempt_response.status_code == 200
    attempt = attempt_response.json()
    assert attempt["exam_id"] == generated["id"]
    assert attempt["score"] == 5
    assert attempt["total"] == 5
    assert attempt["percentage"] == 100.0
    assert [details["question_id"] for details in attempt["detailed_answers"].values()] == original_question_ids

    overview = client.get("/api/v1/stats/overview").json()
    assert overview["total_questions"] == 5
    assert overview["rank"] == "1º"

    with session_factory() as db:
        stored_attempt = db.query(ExamAttempt).filter_by(exam_id=generated["id"]).one()
        assert stored_attempt.total == 5
        assert stored_attempt.score == 5


def test_custom_exam_uses_only_questions_from_the_current_users_library(api_and_session_factory):
    client, session_factory = api_and_session_factory

    response = client.post("/api/v1/exams/generate_custom?count=10")

    assert response.status_code == 200
    returned_ids = {question["id"] for question in response.json()["questions"]}
    with session_factory() as db:
        owned_exam_id = db.query(Exam.id).filter(Exam.user_id == 1, Exam.doc_type != "generated_session").scalar()
        foreign_exam_id = db.query(Exam.id).filter(Exam.user_id == 2).scalar()
        owned_ids = {row[0] for row in db.query(Question.id).filter(Question.exam_id == owned_exam_id)}
        foreign_ids = {row[0] for row in db.query(Question.id).filter(Question.exam_id == foreign_exam_id)}

    assert returned_ids == owned_ids
    assert returned_ids.isdisjoint(foreign_ids)


def test_notebook_resolves_generated_attempts_and_deduplicates_original_questions(api_and_session_factory):
    client, session_factory = api_and_session_factory

    generated = client.post("/api/v1/exams/generate_custom?count=5").json()
    wrong_answers = {
        question["numero_questao"]: "B"
        for question in generated["questions"]
    }
    for _ in range(2):
        response = client.post("/api/v1/exams/attempt", json={
            "exam_id": generated["id"],
            "elapsed_seconds": 60,
            "answers": wrong_answers,
        })
        assert response.status_code == 200
        assert response.json()["score"] == 0

    stats_response = client.get("/api/v1/notebook/stats")
    assert stats_response.status_code == 200
    stats = {item["subject"]: item["count"] for item in stats_response.json()}
    assert stats == {"Português": 3, "Direito": 2}

    notebook_response = client.get("/api/v1/notebook")
    assert notebook_response.status_code == 200
    notebook = notebook_response.json()
    assert notebook["id"] not in (888888, 999999, generated["id"])
    assert notebook["status"] == "Sessão"

    notebook_question_ids = [question["id"] for question in notebook["questions"]]
    assert len(notebook_question_ids) == 5
    assert len(set(notebook_question_ids)) == 5

    with session_factory() as db:
        session = db.get(GeneratedExamSession, notebook["id"])
        assert session is not None
        assert session.kind == "notebook"
        assert json.loads(session.question_ids_json) == notebook_question_ids

    reloaded_response = client.get(f"/api/v1/exams/{notebook['id']}")
    assert reloaded_response.status_code == 200
    reloaded = reloaded_response.json()
    assert [question["id"] for question in reloaded["questions"]] == notebook_question_ids
    assert [question["numero_questao"] for question in reloaded["questions"]] == ["1", "2", "3", "4", "5"]

    correct_answers = {
        question["numero_questao"]: question["correct_answer"]
        for question in reloaded["questions"]
    }
    submit_response = client.post("/api/v1/exams/attempt", json={
        "exam_id": notebook["id"],
        "elapsed_seconds": 90,
        "answers": correct_answers,
    })
    assert submit_response.status_code == 200
    assert submit_response.json()["score"] == 5
    assert submit_response.json()["total"] == 5
