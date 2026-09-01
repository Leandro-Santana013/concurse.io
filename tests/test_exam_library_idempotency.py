import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi_app import app
from models.database import (
    Base,
    Exam,
    ExamCatalog,
    ExamSource,
    Folder,
    Question,
    User,
    UserExam,
    get_db,
)
from routes.api_v1.user_context import get_current_user
from services.exam_library import claim_exam_for_user, source_key


@pytest.fixture()
def library_api(monkeypatch):
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
        db.add_all([
            User(id=1, google_id="user-one", email="one@example.com", name="Um"),
            User(id=2, google_id="user-two", email="two@example.com", name="Dois"),
        ])
        db.commit()

    active_user = {"id": 1}
    dispatched_exam_ids = []

    def override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=active_user["id"])
    monkeypatch.setattr(
        "app_core.async_worker.dispatch_async_exam_task",
        lambda exam_id, *_args, **_kwargs: dispatched_exam_ids.append(exam_id),
    )
    for crawler_name in (
        "_scrape_idcap_pdfs",
        "_scrape_pci_pdfs",
        "_search_pdfs_web",
        "_search_known_exams",
        "_search_qc_provas",
    ):
        monkeypatch.setattr(f"services.crawlers.{crawler_name}", lambda *_args, **_kwargs: [])

    client = TestClient(app)
    try:
        yield client, test_session_factory, active_user, dispatched_exam_ids
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


def _seed_ready_exam(session_factory, source_url: str) -> int:
    with session_factory() as db:
        folder = Folder(name="Auditor Fiscal", user_id=1)
        db.add(folder)
        db.flush()
        exam = Exam(
            title="Auditor Fiscal — FGV 2025",
            status="Aprovada",
            progress=100,
            progress_message="Prova pronta",
            source_url=source_url,
            gabarito_url="https://example.test/gabarito.pdf",
            folder_id=folder.id,
            user_id=1,
            has_official_answers=1,
            gabarito_coverage=100.0,
        )
        db.add(exam)
        db.flush()
        for number in range(1, 6):
            db.add(Question(
                exam_id=exam.id,
                statement=f"Questão {number}",
                options=json.dumps({"A": "Certa", "B": "Errada"}),
                correct_answer="A",
                numero_questao=str(number),
            ))
        db.add_all([
            ExamSource(
                source_key=source_key(source_url),
                source_url=source_url,
                exam_id=exam.id,
                created_at="2026-09-01T08:00:00",
            ),
            UserExam(
                user_id=1,
                exam_id=exam.id,
                created_at="2026-09-01T08:00:00",
            ),
            ExamCatalog(
                query_key="auditor",
                title=exam.title,
                source_url=source_url,
                gabarito_url=exam.gabarito_url,
                match_score=98,
                source="ingested",
            ),
        ])
        db.commit()
        return exam.id


def test_ready_exam_is_hidden_for_owner_and_reused_for_another_user(library_api):
    client, session_factory, active_user, dispatched_exam_ids = library_api
    source_url = "https://example.test/provas/auditor.pdf"
    exam_id = _seed_ready_exam(session_factory, source_url)

    owner_results = client.get("/api/v1/search", params={"q": "auditor"})
    assert owner_results.status_code == 200
    assert owner_results.json() == []

    active_user["id"] = 2
    available_results = client.get("/api/v1/search", params={"q": "auditor"})
    assert available_results.status_code == 200
    assert len(available_results.json()) == 1
    assert available_results.json()[0]["id"] == exam_id
    assert available_results.json()[0]["match_score"] == 98
    assert available_results.json()[0]["reuse_available"] is True

    reused = client.post("/api/v1/exams/ingest", json={
        "url": source_url,
        "title": "Título enviado novamente",
        "gabarito_url": "https://example.test/outro-gabarito.pdf",
    })
    assert reused.status_code == 200
    assert reused.json()["exam_id"] == exam_id
    assert reused.json()["status"] == "Aprovada"
    assert reused.json()["reused"] is True
    assert "sem nova extração" in reused.json()["message"]
    assert dispatched_exam_ids == []

    attempt = client.post("/api/v1/exams/attempt", json={
        "exam_id": exam_id,
        "elapsed_seconds": 90,
        "answers": {str(number): "A" for number in range(1, 6)},
    })
    assert attempt.status_code == 200
    assert attempt.json()["score"] == 5
    assert client.get("/api/v1/stats/overview").json()["total_questions"] == 5

    with session_factory() as db:
        assert db.query(Exam).count() == 1
        assert db.query(UserExam).filter_by(exam_id=exam_id).count() == 2
        assert db.get(Exam, exam_id).gabarito_url == "https://example.test/gabarito.pdf"

    assert client.get("/api/v1/search", params={"q": "auditor"}).json() == []
    folders = client.get("/api/v1/folders").json()
    assert [exam["id"] for folder in folders for exam in folder["exams"]] == [exam_id]
    assert folders[0]["exams"][0]["attempt_count"] == 1

    active_user["id"] = 1
    assert client.get("/api/v1/stats/overview").json()["total_questions"] == 0


def test_claim_processed_exam_only_creates_user_link(library_api):
    client, session_factory, active_user, dispatched_exam_ids = library_api
    exam_id = _seed_ready_exam(
        session_factory,
        "https://example.test/provas/idcap-processada.pdf",
    )
    active_user["id"] = 2

    claimed = client.post(f"/api/v1/exams/{exam_id}/claim")
    assert claimed.status_code == 200
    assert claimed.json()["exam_id"] == exam_id
    assert claimed.json()["status"] == "Aprovada"
    assert claimed.json()["reused"] is True
    assert claimed.json()["already_in_library"] is False
    assert "sem nova extração" in claimed.json()["message"]

    claimed_again = client.post(f"/api/v1/exams/{exam_id}/claim")
    assert claimed_again.status_code == 200
    assert claimed_again.json()["already_in_library"] is True
    assert dispatched_exam_ids == []

    with session_factory() as db:
        assert db.query(Exam).count() == 1
        assert db.query(ExamSource).count() == 1
        assert db.query(Question).count() == 5
        assert db.query(ExamCatalog).count() == 1
        assert db.query(UserExam).filter_by(exam_id=exam_id).count() == 2

    assert client.get("/api/v1/search", params={"q": "auditor"}).json() == []


def test_repeated_and_equivalent_urls_share_exam_and_worker(library_api):
    client, session_factory, active_user, dispatched_exam_ids = library_api
    first_url = "https://EXAMPLE.test/provas/tecnico/?utm_source=newsletter"
    equivalent_url = "https://example.test/provas/tecnico"

    first = client.post("/api/v1/exams/ingest", json={
        "url": first_url,
        "title": "Técnico Administrativo",
    })
    second = client.post("/api/v1/exams/ingest", json={
        "url": equivalent_url,
        "title": "Técnico Administrativo duplicado",
    })

    assert first.status_code == second.status_code == 200
    assert first.json()["exam_id"] == second.json()["exam_id"]
    assert first.json()["already_in_library"] is False
    assert second.json()["already_in_library"] is True
    assert second.json()["reused"] is True
    assert len(dispatched_exam_ids) == 1

    with session_factory() as db:
        assert db.query(Exam).count() == 1
        assert db.query(ExamSource).count() == 1
        assert db.query(UserExam).count() == 1

    assert len(client.get("/api/v1/downloads/active").json()) == 1
    active_user["id"] = 2
    assert client.get("/api/v1/downloads/active").json() == []


def test_concurrent_claims_create_one_canonical_exam(tmp_path):
    db_path = tmp_path / "library-race.db"
    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    test_session_factory = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=test_engine)
    with test_session_factory() as db:
        db.add_all([
            User(id=1, google_id="race-one", email="race-one@example.com"),
            User(id=2, google_id="race-two", email="race-two@example.com"),
        ])
        db.commit()

    barrier = Barrier(2)

    def claim(user_id: int):
        with test_session_factory() as db:
            barrier.wait()
            result = claim_exam_for_user(
                db,
                user_id=user_id,
                raw_url="https://example.test/prova-concorrente.pdf",
                title="Prova concorrente",
            )
            return result.exam.id, result.should_process

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, (1, 2)))

    assert len({exam_id for exam_id, _ in results}) == 1
    assert sum(1 for _, should_process in results if should_process) == 1
    with test_session_factory() as db:
        assert db.query(Exam).count() == 1
        assert db.query(ExamSource).count() == 1
        assert db.query(UserExam).count() == 2

    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
