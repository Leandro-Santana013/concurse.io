from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.database import Base, ExamCatalog, User
from routes.api_v1.search_api import search_exams_api
from services.search import DEFAULT_SEARCH_RESULT_LIMIT, interpret_search_query_deterministic


@pytest.fixture()
def search_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    with session_factory() as db:
        db.add(User(id=1, google_id="idcap-user", email="idcap@example.com"))
        db.commit()
        yield db
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _catalog_card(index, *, query_key="idcap", score=95):
    return ExamCatalog(
        query_key=query_key,
        title=f"Analista {index:02d} - Prefeitura {index:02d} (IDCAP)",
        source_url=f"https://www.pciconcursos.com.br/provas/download/analista-{index:02d}-idcap-2025",
        match_score=score,
        source="pci",
    )


def test_idecap_alias_is_interpreted_as_idcap():
    assert interpret_search_query_deterministic("provas da idecap")["banca"] == "IDCAP"


def test_idcap_filter_combines_crawler_and_catalog_quotas(search_db, monkeypatch):
    search_db.add_all([_catalog_card(index) for index in range(DEFAULT_SEARCH_RESULT_LIMIT + 5)])
    search_db.commit()

    crawler_calls = []

    def fake_idcap_crawler(query, nlp_data):
        crawler_calls.append((query, nlp_data["banca"]))
        return [
            {
                "title": f"Crawler IDCAP {index:02d}",
                "url": f"https://crawler.test/idcap-{index:02d}.pdf",
                "source": "idcap",
                "match_score": 90,
            }
            for index in range(DEFAULT_SEARCH_RESULT_LIMIT)
        ]

    monkeypatch.setattr("services.crawlers._search_known_exams", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("services.crawlers._scrape_idcap_pdfs", fake_idcap_crawler)

    results = search_exams_api(
        q="idecap",
        sources="idecap",
        refresh=False,
        db=search_db,
        current_user=SimpleNamespace(id=1),
    )

    assert crawler_calls == [("idecap", "IDCAP")]
    assert len(results) == DEFAULT_SEARCH_RESULT_LIMIT * 2
    assert len({result.url for result in results}) == DEFAULT_SEARCH_RESULT_LIMIT * 2
    assert sum(result.url.startswith("https://crawler.test/") for result in results) == DEFAULT_SEARCH_RESULT_LIMIT
    assert sum("pciconcursos.com.br" in result.url for result in results) == DEFAULT_SEARCH_RESULT_LIMIT


def test_partial_idcap_catalog_is_appended_to_crawler_results(search_db, monkeypatch):
    search_db.add_all([
        ExamCatalog(
            query_key="auditor",
            title=f"Auditor {index:02d} (IDCAP)",
            source_url=f"https://database.test/auditor-{index:02d}-idcap.pdf",
            match_score=98,
            source="pci",
        )
        for index in range(4)
    ])
    search_db.commit()

    crawler_calls = []

    def fake_idcap_crawler(query, nlp_data):
        crawler_calls.append((query, nlp_data["banca"]))
        return [
            {
                "title": f"PCI - Auditor Externo {index:02d} (IDCAP)",
                "url": f"https://crawler.test/auditor-{index:02d}-idcap.pdf",
                "gabarito_url": None,
                "match_score": 90,
                "source": "pci",
            }
            for index in range(12)
        ]

    monkeypatch.setattr("services.crawlers._search_known_exams", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("services.crawlers._scrape_idcap_pdfs", fake_idcap_crawler)

    results = search_exams_api(
        q="auditor",
        sources="idcap",
        refresh=False,
        db=search_db,
        current_user=SimpleNamespace(id=1),
    )

    assert crawler_calls == [("auditor", "")]
    assert len(results) == 16
    assert len({result.url for result in results}) == 16
    assert all("idcap" in result.url.lower() for result in results)
    assert sum(result.url.startswith("https://database.test/") for result in results) == 4


def test_idcap_crawler_uses_pci_fallback_on_cloudflare_and_keeps_limit(monkeypatch):
    from services.crawlers import scraper_service

    class FakeResponse:
        status_code = 403
        headers = {"cf-mitigated": "challenge"}
        text = "Just a moment"

    class FakeSession:
        def __init__(self):
            self.headers = {}

        def get(self, *_args, **_kwargs):
            return FakeResponse()

    fallback_calls = []

    def fake_pci(query, nlp_data):
        fallback_calls.append((query, nlp_data["banca"]))
        rows = [
            {
                "title": f"Cargo {index:02d} (IDCAP)",
                "url": f"https://pci.test/cargo-{index:02d}-idcap.pdf",
                "source": "pci",
                "match_score": 90,
            }
            for index in range(DEFAULT_SEARCH_RESULT_LIMIT + 3)
        ]
        rows.append({
            "title": "Cargo de outra banca",
            "url": "https://pci.test/outra-banca.pdf",
            "source": "pci",
            "match_score": 99,
        })
        return rows

    monkeypatch.setattr(scraper_service.requests, "Session", FakeSession)
    monkeypatch.setattr(scraper_service, "_scrape_pci_pdfs", fake_pci)

    results = scraper_service._scrape_idcap_pdfs(
        "IDCAP",
        interpret_search_query_deterministic("IDCAP"),
    )

    assert fallback_calls == [("IDCAP", "IDCAP")]
    assert len(results) == DEFAULT_SEARCH_RESULT_LIMIT
    assert all(result["source"] == "idcap" for result in results)
    assert all("idcap" in result["url"] for result in results)
