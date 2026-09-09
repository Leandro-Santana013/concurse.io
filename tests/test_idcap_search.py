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

    first_page = search_exams_api(
        q="idecap",
        sources="idecap",
        refresh=False,
        page=1,
        page_size=DEFAULT_SEARCH_RESULT_LIMIT,
        db=search_db,
        current_user=SimpleNamespace(id=1),
    )
    second_page = search_exams_api(
        q="idecap",
        sources="idecap",
        refresh=False,
        page=2,
        page_size=DEFAULT_SEARCH_RESULT_LIMIT,
        db=search_db,
        current_user=SimpleNamespace(id=1),
    )
    all_items = [*first_page.items, *second_page.items]

    assert crawler_calls == [("idecap", "IDCAP")]
    assert len(first_page.items) == DEFAULT_SEARCH_RESULT_LIMIT
    assert len(second_page.items) == DEFAULT_SEARCH_RESULT_LIMIT
    assert first_page.total == second_page.total == DEFAULT_SEARCH_RESULT_LIMIT * 2
    assert len({result.url for result in all_items}) == DEFAULT_SEARCH_RESULT_LIMIT * 2
    assert sum(result.url.startswith("https://crawler.test/") for result in all_items) == DEFAULT_SEARCH_RESULT_LIMIT
    assert sum("pciconcursos.com.br" in result.url for result in all_items) == DEFAULT_SEARCH_RESULT_LIMIT
    assert first_page.has_next is True
    assert second_page.has_previous is True
    assert second_page.has_next is False


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
        page=1,
        page_size=DEFAULT_SEARCH_RESULT_LIMIT,
        db=search_db,
        current_user=SimpleNamespace(id=1),
    )

    assert crawler_calls == [("auditor", "")]
    assert len(results.items) == 16
    assert len({result.url for result in results.items}) == 16
    assert all("idcap" in result.url.lower() for result in results.items)
    assert sum(result.url.startswith("https://database.test/") for result in results.items) == 4


def test_search_api_paginates_cached_results(search_db):
    search_db.add_all([
        ExamCatalog(
            query_key="auditor",
            title=f"Auditor {index:03d}",
            source_url=f"https://catalog.test/auditor-{index:03d}.pdf",
            match_score=95,
            source="web",
        )
        for index in range(61)
    ])
    search_db.commit()

    first_page = search_exams_api(
        q="auditor",
        sources=None,
        refresh=False,
        page=1,
        page_size=DEFAULT_SEARCH_RESULT_LIMIT,
        db=search_db,
        current_user=SimpleNamespace(id=1),
    )
    second_page = search_exams_api(
        q="auditor",
        sources=None,
        refresh=False,
        page=2,
        page_size=DEFAULT_SEARCH_RESULT_LIMIT,
        db=search_db,
        current_user=SimpleNamespace(id=1),
    )
    third_page = search_exams_api(
        q="auditor",
        sources=None,
        refresh=False,
        page=3,
        page_size=DEFAULT_SEARCH_RESULT_LIMIT,
        db=search_db,
        current_user=SimpleNamespace(id=1),
    )

    assert len(first_page.items) == DEFAULT_SEARCH_RESULT_LIMIT
    assert len(second_page.items) == DEFAULT_SEARCH_RESULT_LIMIT
    assert len(third_page.items) == 11
    assert first_page.page == 1
    assert second_page.page == 2
    assert third_page.page == 3
    assert first_page.total == second_page.total == third_page.total == 61
    assert first_page.total_pages == second_page.total_pages == third_page.total_pages == 3
    assert first_page.has_previous is False
    assert first_page.has_next is True
    assert second_page.has_previous is True
    assert second_page.has_next is True
    assert third_page.has_previous is True
    assert third_page.has_next is False


def test_partial_pci_catalog_is_completed_by_exact_crawler(search_db, monkeypatch):
    cached_urls = [
        f"https://pci.test/dataprev-2024-{index:02d}.pdf"
        for index in range(3)
    ]
    search_db.add_all([
        ExamCatalog(
            query_key="dataprev 2024",
            title=f"Analista DATAPREV 2024 {index:02d}",
            source_url=url,
            match_score=95,
            source="pci",
        )
        for index, url in enumerate(cached_urls)
    ])
    search_db.commit()

    crawler_calls = []

    def fake_pci_crawler(query, nlp_data):
        crawler_calls.append((query, nlp_data["orgao"], nlp_data["ano"]))
        return [
            {
                "title": f"PCI - Cargo DATAPREV 2024 {index:02d}",
                "url": cached_urls[index] if index < 3 else f"https://pci.test/dataprev-2024-{index:02d}.pdf",
                "source": "pci",
                "match_score": 95,
            }
            for index in range(17)
        ]

    monkeypatch.setattr("services.crawlers._search_known_exams", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("services.crawlers._scrape_pci_pdfs", fake_pci_crawler)

    results = search_exams_api(
        q="dataprev 2024",
        sources="pci",
        refresh=False,
        page=1,
        page_size=DEFAULT_SEARCH_RESULT_LIMIT,
        db=search_db,
        current_user=SimpleNamespace(id=1),
    )

    assert crawler_calls == [("dataprev 2024", "DATAPREV", "2024")]
    assert len(results.items) == 17
    assert results.total == 17
    assert len({result.url for result in results.items}) == 17


def test_pci_crawler_follows_next_result_page(monkeypatch):
    from services.crawlers import scraper_service

    def pci_page(start, count, next_href=None):
        rows = []
        for index in range(start, start + count):
            rows.append(
                f"<tr><td><a href='/provas/download/dataprev-{index}.pdf'>Cargo {index}</a></td>"
                "<td>2024</td><td>DATAPREV</td><td>FGV</td></tr>"
            )
        next_link = f"<a href='{next_href}'>Próxima</a>" if next_href else "<a href='#'>Próxima</a>"
        return (
            "<html><body><table id='lista_provas'>"
            "<tr><th>Prova</th><th>Ano</th><th>Órgão</th><th>Banca</th></tr>"
            f"{''.join(rows)}</table>{next_link}</body></html>"
        ).encode("utf-8")

    class FakeResponse:
        status_code = 200

        def __init__(self, content, url):
            self.content = content
            self.url = url

    get_calls = []

    def fake_post(url, **_kwargs):
        return FakeResponse(
            pci_page(0, 25, "/provas/dataprev/2"),
            "https://www.pciconcursos.com.br/provas/dataprev",
        )

    def fake_get(url, **_kwargs):
        get_calls.append(url)
        return FakeResponse(
            pci_page(25, 10),
            "https://www.pciconcursos.com.br/provas/dataprev/2",
        )

    monkeypatch.setattr(scraper_service.requests, "post", fake_post)
    monkeypatch.setattr(scraper_service.requests, "get", fake_get)

    results = scraper_service._scrape_pci_pdfs(
        "dataprev",
        interpret_search_query_deterministic("dataprev"),
    )

    assert len(results) == 35
    assert get_calls == ["https://www.pciconcursos.com.br/provas/dataprev/2"]
    assert len({result["url"] for result in results}) == 35


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
