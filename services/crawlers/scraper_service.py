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

from services.search.exam_search_filter import (
    interpret_search_query_deterministic,
    standardize_card_title,
    calculate_card_match_score,
    filter_and_rank_exam_cards,
)

KNOWN_EXAMS_DB = []


DISCARD_TERMS = [
    'resultado', 'convoca', 'retifica', 'cronograma', 'rela',
    'recurso', 'divulga', 'homologa', 'inscri', 'isen', 'anexo',
    'aditivo', 'comunicado', 'aviso', 'lista', 'decreto', 'lei', 'portaria',
    'informa', 'classifica', 'quantitativo', 'local', 'data', 'nota',
    'judicial', 'decis', 'cumprimento', 'parecer', 'termo de posse', 'convocados',
    'audiometria', 'psicol', 'aptid', 'exame m', 'reintegra', 'curso de forma',
    'entrevista', 'devolutiva', 'apresenta', 'termo de', 'comprovação', 'comprovacao',
    'convenção', 'convencao', 'acordo coletivo', 'cct', 'laudo', 'atendimento especial',
    'edital de abertura', 'edital consolidado'
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
    """Busca rápida, expandida e filtrada de provas no PCI Concursos."""
    results = []
    try:
        ddgs_cls = get_ddgs_class()
        if not ddgs_cls:
            return results

        queries_to_try = [
            f"{query} site:pciconcursos.com.br/provas",
            f"{query} site:pciconcursos.com.br",
        ]
        if nlp_data:
            cargo = str(nlp_data.get('cargo', '')).strip()
            orgao = str(nlp_data.get('orgao', '')).strip()
            if cargo and cargo.lower() not in ['n/a', 'none', '']:
                queries_to_try.append(f"{cargo} site:pciconcursos.com.br/provas")
            if orgao and orgao.lower() not in ['n/a', 'none', '']:
                queries_to_try.append(f"{orgao} site:pciconcursos.com.br/provas")

        ddgs_results = []
        seen_hrefs = set()

        for search_q in queries_to_try[:3]:
            try:
                with ddgs_cls() as ddgs:
                    batch = list(ddgs.text(search_q, max_results=8))
                    for b in batch:
                        h = b.get('href', '')
                        if h and h not in seen_hrefs:
                            seen_hrefs.add(h)
                            ddgs_results.append(b)
                if len(ddgs_results) >= 8:
                    break
            except Exception:
                continue

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

            if '/download/' in href or '/provas/' in href:
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
        results = results[:10]
        
    except Exception as e:
        print(f"   │  [PCI Concursos] Aviso: {e}", flush=True)
    return results

def _scrape_idcap_pdfs(query, nlp_data=None):
    """
    Crawler HTTP concorrente para a banca IDCAP.
    Varre páginas de status, filtra documentos administrativos e pareia cadernos de prova e gabaritos.
    """
    results = []
    query_lower = query.lower()
    
    # Se uma banca explicitamente diferente foi identificada (ex: FGV, Cebraspe, FCC), pula o crawler do IDCAP
    if nlp_data and nlp_data.get('banca') and nlp_data.get('banca') not in ['IDCAP', ''] and 'idcap' not in query_lower:
        return results

    ignore_words = {'prova', 'provas', 'concurso', 'concursos', 'filetype:pdf', 'pdf', 'processo', 'seletivo', 'privado', 'de', 'do', 'da', 'para', 'em', 'no', 'na'}
    query_words = [w for w in re.findall(r'\b[\w\-/]+\b', query_lower) if len(w) > 1 and w not in ignore_words]

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
                    resp = session.get(url, timeout=5.0)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        for a in soup.find_all('a', href=lambda h: h and '/informacoes/' in h):
                            href = a['href']
                            parent_div = a.find_parent('div')
                            card_text = parent_div.get_text(separator=' ', strip=True) if parent_div else a.get_text(strip=True)
                            card_lower = card_text.lower()
                            
                            # Pontuação precisa de correspondência
                            score = sum(1 for w in query_words if w in card_lower) if query_words else 1
                            if nlp_data:
                                if nlp_data.get('orgao') and nlp_data['orgao'].lower() in card_lower:
                                    score += 6
                                if nlp_data.get('cargo') and nlp_data['cargo'].lower() in card_lower:
                                    score += 6
                                if nlp_data.get('ano') and nlp_data['ano'] in card_lower:
                                    score += 4
                            
                            if score > 0 or not query_words:
                                page_concursos.append((score, href, card_text))
                except Exception:
                    pass
                return page_concursos

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(fetch_status_page, sp) for sp in ['/index/1/', '/index/2/', '/index/3/', '/index/4/', '/index/5/']]
                for fut in concurrent.futures.as_completed(futures):
                    concurso_links.extend(fut.result())

        concurso_links.sort(key=lambda x: x[0], reverse=True)
        # Varre os concursos correspondentes encontrados (top 10)
        concurso_links = concurso_links[:10]

        def fetch_concurso_pdfs(item):
            concurso_score, href, concurso_title = item
            c_results = []
            try:
                url = f"https://idcap.selecao.net.br{href}" if href.startswith('/') else href
                resp = session.get(url, timeout=5.0)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    
                    prova_links = []
                    gabarito_links = []

                    for a in soup.find_all('a', href=True):
                        pdf_href = a['href']
                        if '.pdf' in pdf_href.lower() or '/download/' in pdf_href.lower() or 'anexos' in pdf_href.lower():
                            text = a.get_text(separator=' ', strip=True)
                            text_lower = text.lower()
                            
                            if is_administrative_document(text_lower):
                                continue

                            full_url = pdf_href if pdf_href.startswith('http') else f"https://idcap.selecao.net.br{pdf_href}"
                            
                            if 'gabarito' in text_lower:
                                gabarito_links.append((text, full_url))
                            else:
                                # Todo PDF não-administrativo na página do concurso é tratado como caderno de prova
                                prova_links.append((text, full_url))

                    # Pareamento e pontuação
                    for p_text, p_url in prova_links:
                        matched_gab_url = None
                        p_words = set(re.findall(r'\w{3,}', p_text.lower()))
                        for g_text, g_url in gabarito_links:
                            g_words = set(re.findall(r'\w{3,}', g_text.lower()))
                            if p_words & g_words or len(gabarito_links) == 1:
                                matched_gab_url = g_url
                                break

                        clean_title = re.sub(r'(inscri[çc][õo]es|pedidos de isen[çc][ãa]o|saiba mais|\d+\s*vagas).*', '', concurso_title, flags=re.IGNORECASE)
                        clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                        
                        # Cálculo refinado de match score
                        match_score = 70
                        if query_words:
                            combined_text = f"{clean_title} {p_text}".lower()
                            matches = sum(1 for w in query_words if w in combined_text)
                            term_ratio = matches / len(query_words)
                            match_score = int(50 + (term_ratio * 48))
                        
                        final_card_title = f"IDCAP - {clean_title} - {p_text}" if p_text.lower() not in clean_title.lower() else f"IDCAP - {clean_title}"
                        
                        c_results.append({
                            "title": final_card_title,
                            "url": p_url,
                            "gabarito_url": matched_gab_url,
                            "source": "idcap",
                            "match_score": min(98, max(60, match_score))
                        })
            except Exception:
                pass
            return c_results

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_concurso_pdfs, item) for item in concurso_links]
            for fut in concurrent.futures.as_completed(futures):
                results.extend(fut.result())
                if len(results) >= 15:
                    break

        if results:
            results.sort(key=lambda x: x.get('match_score', 0), reverse=True)
            return results[:10]
    except Exception as e:
        print(f"   │  [IDCAP Crawler] Aviso: {e}", flush=True)

    return results

def _search_pdfs_web(query, api_key_val=None):
    """
    Busca web concorrente rápida para identificar cadernos de questões em PDF.
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

    # 2. DuckDuckGo Search
    if len(results) < 10:
        try:
            ddgs_cls = get_ddgs_class()
            if ddgs_cls:
                ddg_query = f"{query} prova concurso pdf"
                ddg_results = []
                try:
                    with ddgs_cls() as ddgs:
                        ddg_results = list(ddgs.text(ddg_query, max_results=10))
                except Exception:
                    try:
                        with ddgs_cls() as ddgs:
                            ddg_results = list(ddgs.text(f"{query} prova pdf", max_results=8))
                    except Exception:
                        pass

                for r in ddg_results:
                    url = r.get('href', '')
                    title = r.get('title', '')
                    
                    if is_administrative_document(title) or is_administrative_document(url):
                        continue

                    if url and ('.pdf' in url.lower() or '/download/' in url.lower() or 'prova' in url.lower()):
                        _add_results([{
                            "title": f"Web - {title[:80]}",
                            "url": url,
                            "gabarito_url": None,
                            "match_score": 60,
                            "source": "web"
                        }])
        except Exception as e:
            print(f"   │  [Web Search] Aviso: {e}", flush=True)

    return results
