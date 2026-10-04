from services.crawlers import scraper_service
from services.search import card_matches_search_query, filter_and_rank_exam_cards, interpret_search_query_deterministic


def _card(title, slug, **fields):
    return {"title": title, "url": f"https://pci.test/provas/download/{slug}",
            "source": "pci", "match_score": 98, **fields}


def test_fiscal_specialty_plural_and_combined_roles_keep_city_bank_year():
    query = "Fiscal de Postura Ibirataia BA 2024 idecap"
    candidates = [
        _card("Fiscal de Obras, Posturas e Meio Ambiente - Pref. Ibirataia/BA 2024 (IDCAP)", "ibirataia-2024-idcap"),
        _card("Auditor Fiscal - Pref. Ibirataia/BA 2024 (IDCAP)", "auditor-2024-idcap"),
        _card("Fiscal de Posturas - Pref. Ibirataia/BA 2024 (FGV)", "posturas-2024-fgv"),
        _card("Fiscal de Posturas - Pref. Ibirataia/BA 2023 (IDCAP)", "posturas-2023-idcap"),
        _card("Fiscal de Posturas - Pref. Serra/ES 2024 (IDCAP)", "serra-2024-idcap"),
    ]
    ranked = filter_and_rank_exam_cards(candidates, query)
    assert [card["url"] for card in ranked] == [candidates[0]["url"]]
    assert card_matches_search_query(candidates[0], "Fiscais de Posturas IDCAP")


def test_ordinary_search_does_not_require_unpublished_metadata():
    card = _card("Enfermeiro - Prefeitura", "enfermeiro")
    assert card_matches_search_query(card, "Enfermeiro IDCAP 2024")


def test_pci_relaxes_discovery_but_filters_the_original_query(monkeypatch):
    calls = []
    candidates = [
        ("Fiscal de Obras, Posturas e Meio Ambiente", "2024", "Pref. Ibirataia/BA", "IDCAP", "ibirataia-2024-idcap"),
        ("Auditor Fiscal", "2024", "Pref. Ibirataia/BA", "IDCAP", "auditor-2024-idcap"),
        ("Fiscal de Posturas", "2024", "Pref. Serra/ES", "IDCAP", "serra-2024-idcap"),
        ("Fiscal de Posturas", "2023", "Pref. Ibirataia/BA", "IDCAP", "ibirataia-2023-idcap"),
        ("Fiscal de Posturas", "2024", "Pref. Ibirataia/BA", "FGV", "ibirataia-2024-fgv"),
    ]

    def post(url, *, data, **_kwargs):
        calls.append(data["prova"])
        rows = candidates if data["prova"] == "IDCAP fiscal" else []
        html = "<table>" + "".join(
            f"<tr><td><a href='/provas/download/{slug}'>{role}</a></td><td>{year}</td>"
            f"<td>{city}</td><td>{bank}</td></tr>" for role, year, city, bank, slug in rows
        ) + "</table>"
        return type("Response", (), {"status_code": 200, "content": html.encode(), "url": url})()

    monkeypatch.setattr(scraper_service.requests, "post", post)
    query = "fiscal de postura Ibirataia BA 2024 idecap"
    rows = scraper_service._scrape_pci_pdfs(query, interpret_search_query_deterministic(query))
    assert calls == ["fiscal de postura Ibirataia BA 2024 IDCAP", "IDCAP fiscal"]
    assert len(rows) == 1
    assert "Obras, Posturas" in rows[0]["title"]


def test_unrelated_official_fiscal_exams_do_not_suppress_idcap_fallback(monkeypatch):
    class Response:
        status_code = 200
        headers = {}

        def __init__(self, text):
            self.text = text

    class Session:
        def __init__(self):
            self.headers = {}

        def get(self, url, **_kwargs):
            if "/informacoes/" in url:
                return Response("<a href='https://official.test/auditor.pdf'>Auditor Fiscal de Atividades Urbanas</a>")
            return Response("<div>Prefeitura Serra - Auditor Fiscal 2024 "
                            "<a href='/informacoes/1/'>Informações</a></div>")

    calls = []

    def pci(query, nlp_data):
        calls.append((query, nlp_data["banca"]))
        return [
            _card("Fiscal de Obras, Posturas e Meio Ambiente - Ibirataia 2024 (IDCAP)", "fiscal-posturas-idcap"),
            _card("Auditor Fiscal - Serra 2024 (IDCAP)", "auditor-idcap"),
        ]

    monkeypatch.setattr(scraper_service.requests, "Session", Session)
    monkeypatch.setattr(scraper_service, "_scrape_pci_pdfs", pci)
    query = "Fiscal de Postura idecap"
    rows = scraper_service._scrape_idcap_pdfs(query, interpret_search_query_deterministic(query))
    assert calls == [(query, "IDCAP")]
    assert len(rows) == 1
    assert rows[0]["source"] == "idcap"
    assert rows[0]["url"].endswith("fiscal-posturas-idcap")


def test_pci_protected_file_resolves_the_same_official_booklet_not_a_share(monkeypatch):
    pci = "https://www.pciconcursos.com.br/provas/download/fiscal-de-obras-posturas-e-meio-ambiente-prefeitura-ibirataia-ba-idcap-2024"
    official = "https://official.test/matriz.pdf"
    pages = {
        pci: "<h1></h1><title>Provas para Download - Fiscal de Obras, Posturas e Meio Ambiente - Ibirataia/BA</title>"
             "<a href='https://t.me/share/url?url=https://pci.test/provas/download/example'>Compartilhar</a>"
             "<a class='prova-pdf-link' href='javascript:void(0)'>Baixar caderno.pdf</a>",
        "https://idcap.selecao.net.br/index/todos/?busca=ibirataia":
            "<div>Prefeitura Municipal de Ibirataia - 2024 <a href='/informacoes/777/'>Informações</a></div>",
        "https://idcap.selecao.net.br/informacoes/777/":
            "<a href='https://official.test/auditor.pdf'>Auditor Fiscal</a>"
            f"<a href='{official}'>Fiscal de Obras, Posturas e Meio Ambiente</a>",
    }

    def get(url, **_kwargs):
        html = pages[url]
        return type("Response", (), {"status_code": 200, "text": html, "content": html.encode(), "headers": {}})()

    monkeypatch.setattr(scraper_service.requests, "get", get)
    pdf, answer_key, title = scraper_service.extract_pci_page_pdfs(pci)
    assert pdf == official
    assert answer_key is None
    assert "Fiscal de Obras" in title


def test_public_copy_never_uses_a_different_job_listed_on_the_same_page(monkeypatch):
    pci = "https://www.pciconcursos.com.br/provas/download/fiscal-de-obras-posturas-e-meio-ambiente-prefeitura-ibirataia-ba-idcap-2024"

    def get(url, **_kwargs):
        if "/index/" in url:
            html = "<div>Prefeitura Ibirataia 2024 <a href='/informacoes/777/'>Concurso</a></div>"
        else:
            html = "<h1>Fiscal de Obras, Posturas e Meio Ambiente</h1>" \
                   "<a href='https://official.test/auditor.pdf'>Auditor Fiscal</a>"
        return type("Response", (), {"status_code": 200, "text": html, "content": html.encode(), "headers": {}})()

    monkeypatch.setattr(scraper_service.requests, "get", get)
    assert scraper_service._find_idcap_official_copy(pci) is None


def test_social_share_query_pdf_is_not_a_download(monkeypatch):
    html = "<title>Outra prova</title><a href='https://facebook.com/share?url=https://pci.test/prova.pdf'>Prova</a>"
    response = type("Response", (), {"status_code": 200, "content": html.encode()})()
    monkeypatch.setattr(scraper_service.requests, "get", lambda *_args, **_kwargs: response)
    assert scraper_service.extract_pci_page_pdfs("https://www.pciconcursos.com.br/provas/download/sem-identidade")[:2] == (None, None)
