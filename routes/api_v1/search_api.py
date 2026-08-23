from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from models.database import get_db, Exam, ExamCatalog
from schemas.exam_schemas import SearchResultItem
from services.search import (
    interpret_search_query_deterministic,
    standardize_card_title,
    calculate_card_match_score,
    filter_and_rank_exam_cards,
)

router = APIRouter()

@router.get("/search", response_model=List[SearchResultItem])
def search_exams_api(
    q: str = Query(..., min_length=1),
    sources: Optional[str] = Query(None),
    refresh: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Busca de provas com cache de catálogo instantâneo, NLP determinístico,
    padronização canônica de títulos e ranqueamento por Match Score.
    """
    import time
    t_start = time.time()
    query_clean = q.strip().lower()
    nlp_data = interpret_search_query_deterministic(q)

    print(f"\n{'='*70}", flush=True)
    print(f"🔍 [BUSCA CONCURSE.IO] Nova Consulta: '{q}'", flush=True)
    print(f"   ├─ 🧠 Entidades NLP Extraídas: Órgão='{nlp_data.get('orgao') or '-'}' | Banca='{nlp_data.get('banca') or '-'}' | Cargo='{nlp_data.get('cargo') or '-'}' | Ano='{nlp_data.get('ano') or '-'}'", flush=True)
    
    active_sources = [s.strip().lower() for s in sources.split(',')] if sources else ['web', 'idcap', 'pci', 'qconcursos']

    # 1. Checagem em Cache do Catálogo (Resposta instantânea)
    if not refresh:
        catalog_query = db.query(ExamCatalog).filter(
            (ExamCatalog.query_key == query_clean) | 
            (ExamCatalog.title.ilike(f"%{query_clean}%"))
        )
        if sources:
            catalog_query = catalog_query.filter(ExamCatalog.source.in_(active_sources))
        if nlp_data.get("orgao"):
            catalog_query = catalog_query.filter(ExamCatalog.title.ilike(f"%{nlp_data['orgao']}%"))
        if nlp_data.get("cargo"):
            catalog_query = catalog_query.filter(ExamCatalog.title.ilike(f"%{nlp_data['cargo']}%"))

        cached_entries = catalog_query.order_by(ExamCatalog.match_score.desc()).limit(20).all()

        if cached_entries and len(cached_entries) >= 1:
            raw_cached_cards = [{
                "title": c.title,
                "url": c.source_url,
                "gabarito_url": c.gabarito_url,
                "source": c.source or "catalog_cache",
                "match_score": c.match_score
            } for c in cached_entries]
            
            ranked_cached = filter_and_rank_exam_cards(raw_cached_cards, q, min_score=25, limit=15)
            if ranked_cached:
                elapsed = round((time.time() - t_start) * 1000, 1)
                print(f"   ├─ ⚡ [CACHE HIT] {len(ranked_cached)} provas recuperadas do catálogo local ({elapsed}ms)", flush=True)
                print(f"{'='*70}\n", flush=True)
                return [
                    SearchResultItem(
                        id=None,
                        title=c["title"],
                        url=c["url"],
                        gabarito_url=c.get("gabarito_url"),
                        has_gabarito_link=bool(c.get("gabarito_url")),
                        match_score=c["match_score"],
                        source=c.get("source", "catalog_cache"),
                        status="Pendente"
                    ) for c in ranked_cached
                ]

    # 2. Scrapers Concorrentes
    from services.crawlers import _scrape_idcap_pdfs, _scrape_pci_pdfs, _search_pdfs_web
    import concurrent.futures

    print(f"   ├─ 🌐 [SCRAPERS/CRAWLERS] Disparando em paralelo: {active_sources}", flush=True)
    raw_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {}
        if 'idcap' in active_sources:
            futures[executor.submit(_scrape_idcap_pdfs, q, nlp_data)] = 'IDCAP (Crawler)'
        if 'pci' in active_sources:
            futures[executor.submit(_scrape_pci_pdfs, q, nlp_data)] = 'PCI Concursos'
        if 'web' in active_sources:
            futures[executor.submit(_search_pdfs_web, q)] = 'DuckDuckGo Web'

        try:
            for fut in concurrent.futures.as_completed(futures, timeout=12.0):
                src_name = futures[fut]
                try:
                    res = fut.result()
                    count = len(res) if res else 0
                    print(f"   │  ├─ [{src_name}]: {count} PDFs encontrados", flush=True)
                    if res:
                        raw_results.extend(res)
                except Exception as ex:
                    print(f"   │  ├─ [{src_name}] Erro: {ex}", flush=True)
        except concurrent.futures.TimeoutError:
            print("   │  ├─ [Aviso] Timeout parcial em scrapers mais lentos. Retornando resultados capturados até o momento.", flush=True)

    # 3. Filtragem Estrita de Fontes, Padronização Canônica e Ranqueamento
    if sources:
        raw_results = [r for r in raw_results if str(r.get('source', '')).lower() in active_sources]

    ranked_cards = filter_and_rank_exam_cards(raw_results, q, min_score=20, limit=15)
    
    # 4. Salva no cache do catálogo para respostas instantâneas futuras
    try:
        for c in ranked_cards:
            existing = db.query(ExamCatalog).filter_by(source_url=c['url']).first()
            if not existing:
                db.add(ExamCatalog(
                    query_key=query_clean,
                    title=c['title'],
                    source_url=c['url'],
                    gabarito_url=c.get('gabarito_url'),
                    match_score=c.get('match_score', 50),
                    source=c.get('source', 'web'),
                    created_at=str(int(time.time()))
                ))
        db.commit()
    except Exception as db_err:
        db.rollback()

    total_time = round(time.time() - t_start, 2)
    print(f"   ├─ 🎯 [RANQUEAMENTO] Total Bruto: {len(raw_results)} | Filtrados e Qualificados: {len(ranked_cards)}", flush=True)
    if ranked_cards:
        top1 = ranked_cards[0]
        print(f"   │  └─ Top #1: \"{top1['title']}\" (Score: {top1['match_score']}%)", flush=True)
    print(f"   └─ ⏱️ Tempo total da busca: {total_time}s", flush=True)
    print(f"{'='*70}\n", flush=True)

    return [
        SearchResultItem(
            id=None,
            title=c['title'],
            url=c['url'],
            gabarito_url=c.get('gabarito_url'),
            has_gabarito_link=bool(c.get('gabarito_url')),
            match_score=c['match_score'],
            source=c.get('source', 'web'),
            status="Pendente"
        )
        for c in ranked_cards
    ]

@router.get("/downloads/active")
def get_active_downloads_api(db: Session = Depends(get_db)):
    """Retorna a lista de todas as provas atualmente sendo processadas em background."""
    active_exams = db.query(Exam).filter(
        Exam.status != 'Pendente',
        ((Exam.progress < 100) & (Exam.progress > 0)) | (Exam.progress == -1)
    ).all()

    return [{
        "id": e.id,
        "title": e.title,
        "url": e.source_url or "",
        "status": e.progress_message or e.status or "",
        "progress": e.progress or 0,
        "error_type": e.error_type
    } for e in active_exams]
