import requests
from bs4 import BeautifulSoup
import time
import re
import concurrent.futures

def get_ddgs_class():
    """Retorna a classe DuckDuckGo Search disponível no ambiente."""
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            return DDGS
        except ImportError:
            return None

from services.exam_search_filter import (
    interpret_search_query_deterministic,
    standardize_card_title,
    calculate_card_match_score,
    filter_and_rank_exam_cards,
)

KNOWN_EXAMS_DB = []


# Termos que identificam inequivocamente documentos administrativos que NÃO devem aparecer na busca
DISCARD_TERMS = [
    'resultado', 'convoca', 'retifica', 'cronograma', 'edital', 'rela',
    'recurso', 'divulga', 'homologa', 'inscri', 'isen', 'anexo',
    'aditivo', 'comunicado', 'aviso', 'lista', 'decreto', 'lei', 'portaria',
    'informa', 'classifica', 'quantitativo', 'local', 'data', 'nota',
    'judicial', 'decis', 'cumprimento', 'parecer', 'termo de posse', 'convocados'
]

def is_administrative_document(text_or_url):
    """Verifica se um título ou URL pertence a um documento administrativo/edital."""
    if not text_or_url:
        return False
    lower = str(text_or_url).lower()
    return any(term in lower for term in DISCARD_TERMS)

def is_caderno_or_gabarito(text_or_url):
    """Verifica se o título ou URL remete a caderno de questões ou gabarito."""
    if not text_or_url:
        return False
    lower = str(text_or_url).lower()
    keywords = ['prova', 'caderno', 'quest', 'gabarito', 'folha de resposta']
    return any(k in lower for k in keywords)

def _search_known_exams(query):
    """Busca no banco interno de provas conhecidas."""
    query_lower = query.lower()
    results = []
    for exam in KNOWN_EXAMS_DB:
        keywords = exam.get("keywords", [])
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            results.append((score, exam))
    
    results.sort(key=lambda x: x[0], reverse=True)
    return [{
        "title": r["title"],
        "url": r["url"],
        "gabarito_url": r.get("gabarito_url"),
        "match_score": 90,
        "source": "known_db"
    } for _, r in results[:5]]

def _search_qc_provas(query):
    results = []
    try:
        ddgs_cls = get_ddgs_class()
        if ddgs_cls:
            q = f"site:qconcursos.com/questoes-de-concursos/provas {query}"
            ddgs_results = []
            for attempt in range(2):
                try:
                    with ddgs_cls() as ddgs:
                        ddgs_results = list(ddgs.text(q, max_results=3))
                    break
                except Exception:
                    time.sleep(0.5)

                    
            for r in ddgs_results:
                if "qconcursos.com" in r['href']:
                    results.append({
                        "title": "[QC] " + r['title'][:60],
                        "url": r['href'],
                        "gabarito_url": None,
                        "source": "qconcursos",
                        "match_score": 70
                    })
    except Exception as e:
        print(f"Erro busca QC: {e}")
    return results

def _scrape_pci_pdfs(query, nlp_data=None):
    """Busca rápida e filtrada de provas no PCI Concursos."""
    results = []
    try:
        ddgs_cls = get_ddgs_class()
        if not ddgs_cls:
            return results
        
        # Query com exclusão de editais
        search_query = f'{query} site:pciconcursos.com.br/provas/download/ -edital -gabarito'
        ddgs_results = []
        for attempt in range(2):
            try:
                with ddgs_cls() as ddgs:
                    ddgs_results = list(ddgs.text(search_query, max_results=15))
                break
            except Exception:
                time.sleep(0.5)
        
        if not ddgs_results:
            return results
            
        target_words = set(query.lower().split())
        if nlp_data:
            orgao = str(nlp_data.get('orgao', '')).lower()
            cargo = str(nlp_data.get('cargo', '')).lower()
            if orgao and orgao != 'n/a': target_words.update(orgao.split())
            if cargo and cargo != 'n/a': target_words.update(cargo.split())
            
        stop_words = {'prova', 'de', 'para', 'em', 'da', 'do', 'concurso', 'pdf', 'a', 'o', 'e'}
        target_words = {w for w in target_words if len(w) > 2 and w not in stop_words}
            
        for r in ddgs_results:
            href = r.get('href', '')
            title = r.get('title', 'Prova PCI')
            
            # Filtro rigoroso: descarta editais e arquivos administrativos
            if is_administrative_document(title) or is_administrative_document(href):
                continue

            if '/download/' in href:
                title_lower = title.lower()
                score = 0
                if target_words:
                    matches = sum(1 for w in target_words if w in title_lower)
                    score = int((matches / len(target_words)) * 100)
                    
                if nlp_data and nlp_data.get('cargo') and str(nlp_data['cargo']).lower() != 'n/a':
                    if str(nlp_data['cargo']).lower() in title_lower:
                        score = min(100, score + 30)
                else:
                    if not target_words: score = 50
                
                if score == 0 and target_words:
                    score = 20
                    
                results.append({
                    "title": f"PCI - {title[:100]}",
                    "url": href,
                    "gabarito_url": None,
                    "match_score": max(score, 45),
                    "source": "pci"
                })
                
        results.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        results = results[:8]
        
    except Exception as e:
        print(f"Erro Busca PCI: {e}")
    return results

def _scrape_idcap_pdfs(query):
    """
    Crawler HTTP concorrente para a banca IDCAP.
    Filtra estritamente documentos administrativos e faz o pareamento automático de Prova + Gabarito.
    """
    results = []
    query_lower = query.lower()
    ignore_words = {'prova', 'provas', 'concurso', 'concursos', 'filetype:pdf', 'pdf'}
    query_words = [w for w in query_lower.split() if len(w) > 2 and w not in ignore_words]

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'pt-BR,pt;q=0.9',
    })

    try:
        concurso_links = []
        if query.startswith('http') and 'idcap' in query:
            concurso_links.append((999, query, "Link Direto"))
        else:
            def fetch_status_page(status_page):
                url = f"https://idcap.selecao.net.br{status_page}"
                page_concursos = []
                try:
                    resp = session.get(url, timeout=5)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        for a in soup.find_all('a', href=lambda h: h and '/informacoes/' in h):
                            href = a['href']
                            parent_div = a.find_parent('div')
                            card_text = parent_div.get_text(separator=' ', strip=True) if parent_div else a.get_text(strip=True)
                            card_lower = card_text.lower()
                            score = sum(1 for w in query_words if w in card_lower) if query_words else 1
                            if score > 0 or not query_words:
                                page_concursos.append((score, href, card_text))
                except Exception:
                    pass
                return page_concursos

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(fetch_status_page, sp) for sp in ['/index/1/', '/index/3/', '/index/4/', '/index/5/']]
                for fut in concurrent.futures.as_completed(futures):
                    concurso_links.extend(fut.result())

        concurso_links.sort(key=lambda x: x[0], reverse=True)

        def fetch_concurso_pdfs(item):
            score, href, concurso_title = item
            c_results = []
            try:
                url = f"https://idcap.selecao.net.br{href}" if href.startswith('/') else href
                resp = session.get(url, timeout=5)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    
                    # Identifica cadernos de prova e gabaritos
                    prova_links = []
                    gabarito_links = []

                    for a in soup.find_all('a', href=True):
                        pdf_href = a['href']
                        if '.pdf' in pdf_href.lower() or '/download/' in pdf_href.lower() or 'anexos-r2.selecao.net.br' in pdf_href.lower():
                            text = a.get_text(strip=True)
                            text_lower = text.lower()
                            
                            # Se for documento administrativo (edital, resultado, cronograma, etc.), descarta categoricamente
                            if is_administrative_document(text_lower):
                                continue

                            full_url = pdf_href if pdf_href.startswith('http') else f"https://idcap.selecao.net.br{pdf_href}"
                            
                            if 'gabarito' in text_lower:
                                gabarito_links.append((text, full_url))
                            elif any(k in text_lower for k in ['prova', 'caderno', 'quest']):
                                prova_links.append((text, full_url))

                    # Pareamento automático de Prova + Gabarito
                    for p_text, p_url in prova_links:
                        # Tenta achar o gabarito mais correspondente pelo cargo/título
                        matched_gab_url = None
                        p_words = set(re.findall(r'\w{3,}', p_text.lower()))
                        for g_text, g_url in gabarito_links:
                            g_words = set(re.findall(r'\w{3,}', g_text.lower()))
                            if p_words & g_words or len(gabarito_links) == 1:
                                matched_gab_url = g_url
                                break

                        clean_title = concurso_title.replace('\n', ' ').strip()
                        match_score = 90 if query_words and any(w in clean_title.lower() for w in query_words) else 65
                        
                        c_results.append({
                            "title": f"IDCAP - {clean_title[:80]} - {p_text[:60]}",
                            "url": p_url,
                            "gabarito_url": matched_gab_url,
                            "source": "idcap",
                            "match_score": match_score
                        })
            except Exception:
                pass
            return c_results

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(fetch_concurso_pdfs, item) for item in concurso_links[:8]]
            for fut in concurrent.futures.as_completed(futures):
                results.extend(fut.result())
                if len(results) >= 20:
                    break

        if results:
            return results[:15]
    except Exception as e:
        print(f"Aviso: Crawling HTTP IDCAP falhou: {e}")

    return results

def _search_pdfs_web(query, api_key_val=None):
    """
    Busca web concorrente com operadores negativos estritos para eliminar editais e resultados.
    """
    results = []
    seen_urls = set()

    def _add_results(new_results):
        for r in new_results:
            url = r.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                results.append(r)

    # 1. Banco interno de provas
    known = _search_known_exams(query)
    _add_results(known)

    # 2. DuckDuckGo Search com operadores booleanos de exclusão
    if len(results) < 10:
        try:
            ddgs_cls = get_ddgs_class()
            if ddgs_cls:
                ddg_query = f'{query} (prova OR "caderno de questoes") filetype:pdf -edital -retificacao -resultado -homologacao -convocacao -cronograma -recurso'
                with ddgs_cls() as ddgs:
                    ddg_results = list(ddgs.text(ddg_query, max_results=12))
                    for r in ddg_results:
                        url = r.get('href', '')
                        title = r.get('title', '')
                        
                        # Filtro rigoroso na saída da web
                        if is_administrative_document(title) or is_administrative_document(url):
                            continue

                        if url and ('.pdf' in url.lower() or '/download/' in url.lower()):
                            _add_results([{
                                "title": f"Web - {title[:80]}",
                                "url": url,
                                "gabarito_url": None,
                                "match_score": 60,
                                "source": "web"
                            }])
        except Exception as e:
            print(f"Erro DDGS Web: {e}")

    return results
