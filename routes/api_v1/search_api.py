import re
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from models.database import get_db, Exam, ExamCatalog
from schemas.exam_schemas import SearchResultItem, SearchResultsResponse
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


def _merge_cached_idcap_results(cards):
    """Reconstrói a janela paginável do IDCAP a partir do cache persistido."""
    cached_crawler = [
        card for card in cards
        if str(card.get("source") or "").lower() == "idcap"
    ]
    cached_catalog = [
        card for card in cards
        if str(card.get("source") or "").lower() != "idcap"
    ]
    return _merge_ranked_groups(
        (cached_crawler, DEFAULT_SEARCH_RESULT_LIMIT),
        (cached_catalog, DEFAULT_SEARCH_RESULT_LIMIT),
    )[:COMBINED_IDCAP_RESULT_LIMIT]


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

def _has_search_page(cards, page: int, page_size: int) -> bool:
    """Indica se o cache já consegue preencher a página solicitada."""
    required_count = page * page_size
    return len(cards) >= required_count


def _paginated_search_response(cards, page: int, page_size: int) -> SearchResultsResponse:
    total = len(cards)
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    end = start + page_size
    return SearchResultsResponse(
        items=_search_result_items(cards[start:end]),
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_previous=page > 1 and total > 0,
        has_next=end < total,
    )


@router.get("/search", response_model=SearchResultsResponse)
def search_exams_api(
    q: str = Query(..., min_length=1),
    sources: Optional[str] = Query(None),
    refresh: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_SEARCH_RESULT_LIMIT, ge=1, le=DEFAULT_SEARCH_RESULT_LIMIT),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Busca de provas com cache de catálogo instantâneo, NLP determinístico,
    padronização canônica de títulos e ranqueamento por Match Score.
    """
    # Chamadas diretas em testes/integrações não passam pelo resolvedor do
    # FastAPI e recebem os objetos Query como defaults; normalize-os aqui.
    if not isinstance(sources, str):
        sources = None
    if not isinstance(refresh, bool):
        refresh = False
    if not isinstance(page, int) or isinstance(page, bool):
        page = 1
    if not isinstance(page_size, int) or isinstance(page_size, bool):
        page_size = DEFAULT_SEARCH_RESULT_LIMIT

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
        if nlp_data.get("ano"):
            catalog_query = catalog_query.filter(
                or_(
                    ExamCatalog.title.ilike(f"%{nlp_data['ano']}%"),
                    ExamCatalog.source_url.ilike(f"%{nlp_data['ano']}%"),
                )
            )

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
                if combine_idcap_results and page > 1:
                    ranked_cached = _merge_cached_idcap_results(ranked_cached)
                prepared_cached = prepare_search_results_for_user(db, ranked_cached, current_user.id)
                elapsed = round((time.time() - t_start) * 1000, 1)
                print(f"   ├─ ⚡ [CACHE HIT] {len(prepared_cached)} provas disponíveis no catálogo local ({elapsed}ms)", flush=True)
                if _has_search_page(prepared_cached, page, page_size) and (
                    not combine_idcap_results or page > 1
                ):
                    print(f"{'='*70}\n", flush=True)
                    return _paginated_search_response(prepared_cached, page, page_size)

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
        )[:COMBINED_IDCAP_RESULT_LIMIT]
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
    return _paginated_search_response(prepared_cards, page, page_size)

@router.get("/downloads/active")
def get_active_downloads_api(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retorna apenas processamentos associados ao usuário atual."""
    user_exam_ids = get_user_exam_ids(db, current_user.id)
    if not user_exam_ids:
        return []

    # Erros são estados terminais e não podem continuar aparecendo na Navbar
    # como se o worker ainda estivesse processando a prova. O detalhe do erro
    # continua disponível no acompanhamento da ingestão e nos avisos da UI.
    active_exams = db.query(Exam).filter(
        Exam.id.in_(user_exam_ids),
        Exam.status == 'Processando',
        Exam.progress > 0,
        Exam.progress < 100,
        Exam.error_type.is_(None),
    ).all()

    return [{
        "id": e.id,
        "title": e.title,
        "url": e.source_url or "",
        "status": e.progress_message or e.status or "",
        "progress": e.progress or 0,
        "error_type": e.error_type
    } for e in active_exams]
