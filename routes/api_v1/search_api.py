from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from models.database import get_db, Exam, ExamCatalog
from schemas.exam_schemas import SearchResultItem
from services.exam_search_filter import (
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
    query_clean = q.strip().lower()
    nlp_data = interpret_search_query_deterministic(q)
    
    # 1. Checagem em Cache do Catálogo (Resposta em < 5ms)
    if not refresh:
        catalog_query = db.query(ExamCatalog).filter(
            (ExamCatalog.query_key == query_clean) | 
            (ExamCatalog.title.ilike(f"%{query_clean}%"))
        )
        if nlp_data.get("orgao"):
            catalog_query = catalog_query.filter(ExamCatalog.title.ilike(f"%{nlp_data['orgao']}%"))
        if nlp_data.get("cargo"):
            catalog_query = catalog_query.filter(ExamCatalog.title.ilike(f"%{nlp_data['cargo']}%"))

        cached_entries = catalog_query.order_by(ExamCatalog.match_score.desc()).limit(20).all()

        if cached_entries and len(cached_entries) >= 2:
            raw_cached_cards = [{
                "title": c.title,
                "url": c.source_url,
                "gabarito_url": c.gabarito_url,
                "source": c.source or "catalog_cache",
                "match_score": c.match_score
            } for c in cached_entries]
            
            ranked_cached = filter_and_rank_exam_cards(raw_cached_cards, q, min_score=25, limit=15)
            if len(ranked_cached) >= 2:
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
    active_sources = [s.strip().lower() for s in sources.split(',')] if sources else ['web', 'idcap', 'pci', 'qconcursos']
    from services.scraper_service import _scrape_idcap_pdfs, _scrape_pci_pdfs, _search_pdfs_web
    import concurrent.futures

    raw_results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        if 'idcap' in active_sources:
            futures[executor.submit(_scrape_idcap_pdfs, q)] = 'idcap'
        if 'pci' in active_sources:
            futures[executor.submit(_scrape_pci_pdfs, q, nlp_data)] = 'pci'
        if 'web' in active_sources:
            futures[executor.submit(_search_pdfs_web, q)] = 'web'

        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                if res:
                    raw_results.extend(res)
            except Exception:
                pass

    # 3. Filtragem, Padronização Canônica ([ANO] ÓRGÃO - CARGO) e Ranqueamento por Match Score
    ranked_cards = filter_and_rank_exam_cards(raw_results, q, min_score=20, limit=15)

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
