import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from services.search import (
    interpret_search_query_deterministic,
    calculate_card_match_score,
    standardize_card_title,
    filter_and_rank_exam_cards,
)
from fastapi.testclient import TestClient
from fastapi_app import app

client = TestClient(app)

def test_nlp_extraction():
    print("\n--- Teste 1: Extração Determinística de Entidades (NLP) ---")
    
    # Caso 1: PF Agente 2024 Cebraspe
    q1 = "PF Agente 2024 Cebraspe"
    nlp1 = interpret_search_query_deterministic(q1)
    assert nlp1["ano"] == "2024", f"Esperado ano 2024, obtido {nlp1['ano']}"
    assert nlp1["banca"] == "CEBRASPE", f"Esperado banca CEBRASPE, obtido {nlp1['banca']}"
    assert nlp1["orgao"] == "POLÍCIA FEDERAL", f"Esperado órgão POLÍCIA FEDERAL, obtido {nlp1['orgao']}"
    print(f" -> OK: '{q1}' => {nlp1}")

    # Caso 2: Auditor Fiscal Receita Federal FGV Nível Superior
    q2 = "Auditor Fiscal Receita Federal FGV Nível Superior"
    nlp2 = interpret_search_query_deterministic(q2)
    assert nlp2["orgao"] == "RECEITA FEDERAL"
    assert nlp2["banca"] == "FGV"
    assert nlp2["cargo"] == "AUDITOR"
    assert nlp2["escolaridade"] == "Superior"
    print(f" -> OK: '{q2}' => {nlp2}")

    # Caso 3: Enfermeiro Prefeitura de Santos 2022 Vunesp SP
    q3 = "Enfermeiro Prefeitura de Santos 2022 Vunesp SP"
    nlp3 = interpret_search_query_deterministic(q3)
    assert nlp3["cargo"] == "ENFERMEIRO"
    assert nlp3["orgao"] == "PREFEITURA"
    assert nlp3["banca"] == "VUNESP"
    assert nlp3["ano"] == "2022"
    assert "SANTOS" in nlp3["local"]
    print(f" -> OK: '{q3}' => {nlp3}")


def test_standardize_card_title():
    print("\n--- Teste 2: Padronização Canônica de Títulos ---")
    
    nlp = {"ano": "2024", "orgao": "POLÍCIA FEDERAL", "local": "", "cargo": "AGENTE DE POLÍCIA"}
    raw_title = "PCI - Provas para download - Caderno de Questões - Polícia Federal - Agente de Polícia 2024.pdf"
    clean = standardize_card_title(raw_title, nlp, url="https://pci.com/provas/download/123-2024")
    
    print(f" -> Original: '{raw_title}'")
    print(f" -> Limpo:    '{clean}'")
    assert "[2024]" in clean
    assert "POLÍCIA FEDERAL" in clean


def test_calculate_card_match_score():
    print("\n--- Teste 3: Cálculo de Match Score ---")
    
    raw_query = "PF Agente 2024 Cebraspe"
    nlp = interpret_search_query_deterministic(raw_query)
    
    # Card altamente relevante
    card_relevant_title = "Cebraspe - Concurso Polícia Federal - Prova Agente 2024"
    card_relevant_url = "https://cebraspe.org/concursos/pf_2024_agente.pdf"
    score_high = calculate_card_match_score(card_relevant_title, card_relevant_url, nlp, raw_query)
    print(f" -> Score Relevante: {score_high}%")
    assert score_high >= 70, f"Esperado score >= 70, obtido {score_high}"

    # Card irrelevante
    card_irrelevant_title = "Edital de Convocação Prefeitura Linhares"
    card_irrelevant_url = "https://linhares.es.gov.br/edital.pdf"
    score_low = calculate_card_match_score(card_irrelevant_title, card_irrelevant_url, nlp, raw_query)
    print(f" -> Score Irrelevante: {score_low}%")
    assert score_low < score_high


def test_filter_and_rank_cards():
    print("\n--- Teste 4: Filtro e Ranqueamento de Cards ---")
    
    query = "PF Agente 2024 Cebraspe"
    mock_cards = [
        {"title": "Edital Prefeitura Concurso", "url": "https://random.com/edital", "source": "web"},
        {"title": "Prova PCI - Agente de Polícia Federal 2024", "url": "https://pci.com/download/123", "source": "pci"},
        {"title": "Cebraspe - Policia Federal - Agente 2024", "url": "https://cebraspe.org/pf_2024_agente.pdf", "source": "web"},
        {"title": "Prova PCI - Agente de Polícia Federal 2024", "url": "https://pci.com/download/123", "source": "pci"} # Duplicada
    ]
    
    ranked = filter_and_rank_exam_cards(mock_cards, query, min_score=20, limit=10)
    print(f" -> Total retornados: {len(ranked)}")
    for r in ranked:
        print(f"    [{r['match_score']}% Match] {r['title']} ({r['source']})")

    # Verifica deduplicação por URL
    urls = [c['url'] for c in ranked]
    assert len(urls) == len(set(urls)), "Deduplicação de URL falhou"
    # Verifica ordenação decrescente
    scores = [c['match_score'] for c in ranked]
    assert scores == sorted(scores, reverse=True), "Ordenação por match_score falhou"


def test_search_api_integration():
    print("\n--- Teste 5: Integração com Endpoint FastAPI /api/v1/search ---")
    
    response = client.get("/api/v1/search?q=Petrobras+Engenheiro+2024&refresh=true")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    print(f" -> API Search retornou {len(data)} resultados formatados.")
    if data:
        first = data[0]
        print(f" -> Primeiro resultado: {first}")
        assert "title" in first
        assert "url" in first
        assert "match_score" in first
        assert "has_gabarito_link" in first


if __name__ == "__main__":
    test_nlp_extraction()
    test_standardize_card_title()
    test_calculate_card_match_score()
    test_filter_and_rank_cards()
    test_search_api_integration()
    print("\n[SUCCESS] Todos os testes do módulo exam_search_filter passaram com 100% de sucesso!")
