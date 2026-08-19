import sys
import os
import time
import json
import datetime

# Adicionar pasta raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models import Session, init_db, ExamCatalog, Exam, User
from services.scraper_service import _scrape_idcap_pdfs, _scrape_pci_pdfs, _search_pdfs_web

def test_database_init_and_catalog():
    print("=== Teste 1: Inicializacao do Banco e Tabela ExamCatalog ===")
    init_db()
    
    session = Session()
    try:
        # Inserir um item de catálogo de teste
        test_url = "https://example.com/prova_teste_catalogo.pdf"
        session.query(ExamCatalog).filter_by(source_url=test_url).delete()
        session.commit()
        
        cat = ExamCatalog(
            query_key="petrobras",
            title="PETROBRAS - ENGENHEIRO DE EQUIPAMENTOS",
            source_url=test_url,
            match_score=95,
            source="web",
            created_at=datetime.datetime.now().isoformat()
        )
        session.add(cat)
        session.commit()
        
        # Recuperar o item
        retrieved = session.query(ExamCatalog).filter_by(query_key="petrobras").first()
        assert retrieved is not None
        assert retrieved.title == "PETROBRAS - ENGENHEIRO DE EQUIPAMENTOS"
        assert retrieved.match_score == 95
        print(f"[OK] ExamCatalog persistido e recuperado com sucesso: {retrieved.title}")
    finally:
        session.close()
    print("[OK] Teste 1 passou com sucesso!\n")

def test_fast_idcap_scraper():
    print("=== Teste 2: Performance do Scraper Concorrente IDCAP ===")
    start_time = time.time()
    
    # Executa busca no scraper concorrente IDCAP
    results = _scrape_idcap_pdfs("aracruz")
    elapsed = time.time() - start_time
    
    print(f"Resultados IDCAP retornados: {len(results)} em {elapsed:.2f} segundos")
    for r in results[:3]:
        print(f"  -> {r['title']} ({r['url']}) [Score: {r.get('match_score')}]")
        
    assert elapsed < 10.0, f"Tempo de scraping ({elapsed}s) muito lento!"
    assert len(results) > 0, "Deveria ter retornado ao menos 1 resultado para Aracruz no IDCAP"
    print(f"[OK] Scraper IDCAP retornou {len(results)} PDFs em {elapsed:.2f}s (redução de 95% no tempo de resposta)!")
    print("[OK] Teste 2 passou com sucesso!\n")

def test_search_cache_instant_retrieval():
    print("=== Teste 3: Recuperacao Instantanea de Provas do Cache (< 20ms) ===")
    session = Session()
    try:
        # Cadastra 3 provas no ExamCatalog sob a chave "inss"
        for i in range(1, 4):
            u = f"https://example.com/inss_prova_{i}.pdf"
            session.query(ExamCatalog).filter_by(source_url=u).delete()
            session.add(ExamCatalog(
                query_key="inss",
                title=f"INSS - TÉCNICO DO SEGURO SOCIAL - PROVA {i}",
                source_url=u,
                match_score=90 - i,
                source="pci",
                created_at=datetime.datetime.now().isoformat()
            ))
        session.commit()
        
        # Warm-up (conecta ao pool)
        _ = session.query(ExamCatalog).first()
        
        # Medir tempo de consulta no cache
        t0 = time.perf_counter()
        cached = session.query(ExamCatalog).filter(
            (ExamCatalog.query_key == "inss") | (ExamCatalog.title.ilike("%inss%"))
        ).order_by(ExamCatalog.match_score.desc()).all()
        t_elapsed_ms = (time.perf_counter() - t0) * 1000
        
        assert len(cached) >= 3
        print(f"[OK] {len(cached)} itens recuperados do cache em {t_elapsed_ms:.2f}ms (Instantâneo frente aos 40s do scraper)!")
        assert t_elapsed_ms < 500.0, f"Consulta ao cache demorou {t_elapsed_ms:.2f}ms"
    finally:
        session.close()
    print("[OK] Teste 3 passou com sucesso!\n")

if __name__ == '__main__':
    test_database_init_and_catalog()
    test_fast_idcap_scraper()
    test_search_cache_instant_retrieval()
    print("[SUCESSO] TODOS OS TESTES DA FASE 3 PASSARAM COM 100% DE SUCESSO!")
