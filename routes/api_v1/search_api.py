import re
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from models.database import get_db, Exam, ExamCatalog
from schemas.exam_schemas import SearchResultItem
from routes.api_v1.user_context import get_current_user
from services.exam_library import get_user_exam_ids, prepare_search_results_for_user
from services.search import (
    DEFAULT_SEARCH_RESULT_LIMIT,
    interpret_search_query_deterministic,
    standardize_card_title,
    calculate_card_match_score,
    filter_and_rank_exam_cards,
)

router = APIRouter()

SEARCH_CANDIDATE_LIMIT = DEFAULT_SEARCH_RESULT_LIMIT * 4
COMBINED_IDCAP_RESULT_LIMIT = DEFAULT_SEARCH_RESULT_LIMIT * 2
SOURCE_ALIASES = {"idecap": "idcap"}


def _normalize_active_sources(sources: Optional[str]):
    if not sources:
        return ['web', 'idcap', 'pci', 'qconcursos']

    normalized = []
    for raw_source in sources.split(','):
        source = SOURCE_ALIASES.get(raw_source.strip().lower(), raw_source.strip().lower())
        if source and source not in normalized:
            normalized.append(source)
    return normalized


def _idcap_catalog_clause():
    return or_(
        ExamCatalog.source.ilike('idcap'),
        ExamCatalog.title.ilike('%idcap%'),
        ExamCatalog.title.ilike('%idecap%'),
        ExamCatalog.source_url.ilike('%idcap%'),
    )


def _catalog_source_clause(active_sources):
    clauses = []
    regular_sources = [source for source in active_sources if source != 'idcap']
    if regular_sources:
        clauses.append(ExamCatalog.source.in_(regular_sources))
    if 'idcap' in active_sources:
        clauses.append(_idcap_catalog_clause())
    return or_(*clauses) if clauses else None


def _is_idcap_only_query(query: str):
    ignored = {'prova', 'provas', 'concurso', 'concursos', 'pdf', 'banca', 'da', 'do', 'de'}
    tokens = {token for token in re.findall(r'\b\w+\b', query.lower()) if token not in ignored}
    return bool(tokens) and tokens.issubset({'idcap', 'idecap'})


def _card_is_from_idcap(card):
    searchable = ' '.join(str(card.get(field) or '') for field in ('source', 'title', 'url')).lower()
    return bool(re.search(r'\b(?:idcap|idecap)\b', searchable))


def _card_matches_sources(card, active_sources):
    source = str(card.get('source') or '').lower()
    if source in active_sources:
        return True
    if 'idcap' in active_sources and _card_is_from_idcap(card):
        return True
    return source == 'local_repository' and 'idcap' not in active_sources


def _merge_ranked_groups(*groups):
    """Aplica uma cota por grupo e remove somente URLs repetidas entre eles."""
    merged = []
    seen_urls = set()
    for cards, quota in groups:
        added = 0
        for card in cards:
            url = str(card.get('url') or '')
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            merged.append(card)
            added += 1
            if added >= quota:
                break
    return merged


def _search_result_items(cards):
    return [
        SearchResultItem(
            id=card.get("id"),
            title=str(card.get("title", "Prova de Concurso")),
            url=str(card.get("url", "")),
            gabarito_url=card.get("gabarito_url"),
            has_gabarito_link=bool(card.get("has_gabarito_link") or card.get("gabarito_url")),
            match_score=int(card.get("match_score") or 0),
            source=str(card.get("source") or "web"),
            status=str(card.get("status") or "Pendente"),
            reuse_available=bool(card.get("reuse_available")),
        )
        for card in cards
    ]

@router.get("/search", response_model=List[SearchResultItem])
def search_exams_api(
    q: str = Query(..., min_length=1),
    sources: Optional[str] = Query(None),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
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
    
    active_sources = _normalize_active_sources(sources)
    combine_idcap_results = _is_idcap_only_query(query_clean) or bool(
        sources and 'idcap' in active_sources
    )
    response_limit = (
        COMBINED_IDCAP_RESULT_LIMIT
        if combine_idcap_results
        else DEFAULT_SEARCH_RESULT_LIMIT
    )
    ranked_cached = []

    # 1. Checagem em Cache do Catálogo (Resposta instantânea)
    if not refresh:
        catalog_query = db.query(ExamCatalog)
        if _is_idcap_only_query(query_clean):
            catalog_query = catalog_query.filter(_idcap_catalog_clause())
        else:
            catalog_query = catalog_query.filter(
                (ExamCatalog.query_key == query_clean) |
                (ExamCatalog.title.ilike(f"%{query_clean}%"))
            )
        if sources:
            source_clause = _catalog_source_clause(active_sources)
            if source_clause is not None:
                catalog_query = catalog_query.filter(source_clause)
        if nlp_data.get("orgao"):
            catalog_query = catalog_query.filter(ExamCatalog.title.ilike(f"%{nlp_data['orgao']}%"))
        if nlp_data.get("cargo"):
            catalog_query = catalog_query.filter(ExamCatalog.title.ilike(f"%{nlp_data['cargo']}%"))

        cached_entries = catalog_query.order_by(ExamCatalog.match_score.desc()).limit(SEARCH_CANDIDATE_LIMIT).all()

        if cached_entries and len(cached_entries) >= 1:
            raw_cached_cards = [{
                "title": c.title,
                "url": c.source_url,
                "gabarito_url": c.gabarito_url,
                "source": c.source or "catalog_cache",
                "match_score": c.match_score if c.match_score is not None else 50
            } for c in cached_entries]
            
            ranked_cached = filter_and_rank_exam_cards(
                raw_cached_cards,
                q,
                min_score=25,
                limit=SEARCH_CANDIDATE_LIMIT,
            )
            if ranked_cached:
                prepared_cached = prepare_search_results_for_user(db, ranked_cached, current_user.id)
                elapsed = round((time.time() - t_start) * 1000, 1)
                print(f"   ├─ ⚡ [CACHE HIT] {len(prepared_cached)} provas disponíveis no catálogo local ({elapsed}ms)", flush=True)
                if not combine_idcap_results and len(prepared_cached) >= DEFAULT_SEARCH_RESULT_LIMIT:
                    print(f"{'='*70}\n", flush=True)
                    return _search_result_items(prepared_cached[:DEFAULT_SEARCH_RESULT_LIMIT])

    # 2. Scrapers Concorrentes
    from services.crawlers import _scrape_idcap_pdfs, _scrape_pci_pdfs, _search_pdfs_web, _search_known_exams, _search_qc_provas
    import concurrent.futures

    print(f"   ├─ 🌐 [SCRAPERS/CRAWLERS] Disparando em paralelo: {active_sources}", flush=True)
    crawler_results = []
    
    # Adiciona sempre provas conhecidas/locais relevantes imediatamente
    try:
        known_local = _search_known_exams(q, nlp_data)
        if known_local:
            print(f"   │  ├─ [Acervo Local/Bancas]: {len(known_local)} PDFs encontrados", flush=True)
            crawler_results.extend(known_local)
    except Exception as ex:
        print(f"   │  ├─ [Acervo Local] Aviso: {ex}", flush=True)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    futures = {}
    if 'idcap' in active_sources:
        futures[executor.submit(_scrape_idcap_pdfs, q, nlp_data)] = 'IDCAP (Crawler)'
    if 'pci' in active_sources:
        futures[executor.submit(_scrape_pci_pdfs, q, nlp_data)] = 'PCI Concursos'
    if 'qconcursos' in active_sources:
        futures[executor.submit(_search_qc_provas, q)] = 'QConcursos'
    if 'web' in active_sources:
        futures[executor.submit(_search_pdfs_web, q, nlp_data)] = 'DuckDuckGo Web'

    try:
        for fut in concurrent.futures.as_completed(futures, timeout=8.0):
            src_name = futures[fut]
            try:
                res = fut.result()
                count = len(res) if res else 0
                print(f"   │  ├─ [{src_name}]: {count} PDFs encontrados", flush=True)
                if res:
                    crawler_results.extend(res)
            except Exception as ex:
                print(f"   │  ├─ [{src_name}] Erro: {ex}", flush=True)
    except concurrent.futures.TimeoutError:
        print("   │  ├─ [Aviso] Timeout parcial em scrapers mais lentos. Retornando resultados capturados até o momento.", flush=True)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    # 3. Filtragem Estrita de Fontes, Padronização Canônica e Ranqueamento
    if sources:
        crawler_results = [
            result for result in crawler_results
            if _card_matches_sources(result, active_sources)
        ]
        ranked_cached = [
            result for result in ranked_cached
            if _card_matches_sources(result, active_sources)
        ]

    if combine_idcap_results:
        ranked_crawler = filter_and_rank_exam_cards(
            crawler_results,
            q,
            min_score=20,
            limit=SEARCH_CANDIDATE_LIMIT,
        )
        ranked_cards = _merge_ranked_groups(
            (ranked_crawler, DEFAULT_SEARCH_RESULT_LIMIT),
            (ranked_cached, DEFAULT_SEARCH_RESULT_LIMIT),
        )
        raw_result_count = len(crawler_results) + len(ranked_cached)
    else:
        raw_results = [*ranked_cached, *crawler_results]
        ranked_cards = filter_and_rank_exam_cards(
            raw_results,
            q,
            min_score=20,
            limit=SEARCH_CANDIDATE_LIMIT,
        )
        raw_result_count = len(raw_results)
    
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
                    match_score=int(c.get('match_score') or 50),
                    source=c.get('source', 'web'),
                    created_at=str(int(time.time()))
                ))
        db.commit()
    except Exception as db_err:
        db.rollback()

    total_time = round(time.time() - t_start, 2)
    print(f"   ├─ 🎯 [RANQUEAMENTO] Total Bruto: {raw_result_count} | Filtrados e Qualificados: {len(ranked_cards)}", flush=True)
    if ranked_cards:
        top1 = ranked_cards[0]
        print(f"   │  └─ Top #1: \"{top1['title']}\" (Score: {top1.get('match_score', 0)}%)", flush=True)
    print(f"   └─ ⏱️ Tempo total da busca: {total_time}s", flush=True)
    print(f"{'='*70}\n", flush=True)

    prepared_cards = prepare_search_results_for_user(db, ranked_cards, current_user.id)
    return _search_result_items(prepared_cards[:response_limit])

@router.get("/downloads/active")
def get_active_downloads_api(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retorna apenas processamentos associados ao usuário atual."""
    user_exam_ids = get_user_exam_ids(db, current_user.id)
    if not user_exam_ids:
        return []

    active_exams = db.query(Exam).filter(
        Exam.id.in_(user_exam_ids),
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
