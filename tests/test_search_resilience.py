import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fastapi.testclient import TestClient
from fastapi_app import app
from schemas.exam_schemas import SearchResultItem


def test_search_schemas():
    print("[1/3] Testing SearchResultItem schema with edge cases...")
    # Test None match_score
    item1 = SearchResultItem(title="Test 1", url="https://example.com/1", match_score=None)
    assert item1.match_score == 0 or item1.match_score is None
    # Test float match_score
    item2 = SearchResultItem(title="Test 2", url="https://example.com/2", match_score=85)
    assert item2.match_score == 85
    print("      SearchResultItem schema tests passed.")

def test_search_queries():
    print("[2/3] Testing Search API queries with TestClient...")
    client = TestClient(app)
    queries = [
        'Cebraspe',
        'FGV',
        'FCC',
        'IBAM',
        'Vunesp',
        'IDCAP',
        'Cesgranrio',
        'Polícia Federal',
        'INSS',
        'Enfermeiro',
        'TJ',
        'Banco do Brasil'
    ]

    for q in queries:
        res = client.get(f'/api/v1/search?q={q}')
        assert res.status_code == 200, f"Query '{q}' failed with status {res.status_code}: {res.text}"
        data = res.json()
        assert isinstance(data, list), f"Expected list for '{q}', got {type(data)}"
        print(f"      [OK] '{q:16}' -> HTTP 200 | {len(data)} resultados | Top: {data[0]['title'] if data else 'Nenhum'}")

def test_local_catalog():
    print("[3/3] Testing KNOWN_EXAMS_DB indexing and matching...")
    from services.crawlers.scraper_service import KNOWN_EXAMS_DB, _search_known_exams
    print(f"      Indexed {len(KNOWN_EXAMS_DB)} exams in KNOWN_EXAMS_DB.")
    assert len(KNOWN_EXAMS_DB) > 0, "KNOWN_EXAMS_DB should have indexed available exam files."
    
    match_fgv = _search_known_exams("FGV")
    assert len(match_fgv) > 0, "Search for FGV should return known exams."
    print(f"      [OK] 'FGV' matched {len(match_fgv)} local exams.")

if __name__ == '__main__':
    print("=" * 60)
    print("RUNNING COMPREHENSIVE SEARCH SUITE")
    print("=" * 60)
    test_search_schemas()
    test_local_catalog()
    test_search_queries()
    print("=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)
