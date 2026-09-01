import requests
from bs4 import BeautifulSoup
import time
import re
import concurrent.futures
from urllib.parse import quote_plus, urljoin

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
    DEFAULT_SEARCH_RESULT_LIMIT,
    interpret_search_query_deterministic,
    standardize_card_title,
    calculate_card_match_score,
    filter_and_rank_exam_cards,
)

import os

def _load_known_exams_catalog():
    """Carrega dinamicamente o catálogo de provas locais conhecidas a partir dos repositórios de bancas."""
    known = []
    base_dirs = [
        os.path.abspath('provas_bancas'),
        os.path.abspath(r'c:\Users\nicky\Downloads\provas_bancas\provas_bancas'),
        os.path.abspath(r'..\..\Downloads\provas_bancas\provas_bancas'),
    ]
    seen_files = set()
    for b_dir in base_dirs:
        if not os.path.exists(b_dir):
            continue
        try:
            for banca in os.listdir(b_dir):
                b_path = os.path.join(b_dir, banca)
                if not os.path.isdir(b_path):
                    continue
                for fname in os.listdir(b_path):
                    if not fname.lower().endswith('.pdf'):
                        continue
                    full_path = os.path.abspath(os.path.join(b_path, fname))
                    if full_path in seen_files:
                        continue
                    seen_files.add(full_path)
                    
                    m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', fname)
                    ano_str = f'[{m_ano.group(1)}] ' if m_ano else ''
                    
                    name_clean = fname[:-4]
                    name_clean = re.sub(r'^\[.*?\]\s*', '', name_clean)
                    name_clean = re.sub(r'[_—–]', ' ', name_clean)
                    name_clean = re.sub(r'\s+', ' ', name_clean).strip()
                    
                    display_title = f"{ano_str}{banca.upper()} - {name_clean}".upper()
                    
                    raw_tokens = set(re.findall(r'\b[\w\-]+\b', f"{banca} {fname}".lower()))
                    keywords = [t for t in raw_tokens if len(t) > 2]
                    
                    known.append({
                        "title": display_title,
                        "url": full_path,
                        "gabarito_url": None,
                        "keywords": keywords,
                        "banca": banca.upper(),
                        "source": "local_repository",
                        "match_score": 85
                    })
        except Exception:
            pass
    return known

KNOWN_EXAMS_DB = _load_known_exams_catalog()


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

def _search_known_exams(query, nlp_data=None):
    """Busca no banco interno de provas conhecidas com NLP e ponderação refinada."""
    if not KNOWN_EXAMS_DB:
        return []
    
    query_lower = query.lower()
    stop_words = {'prova', 'provas', 'concurso', 'concursos', 'de', 'da', 'do', 'para', 'em', 'pdf', 'caderno'}
    query_tokens = [w for w in re.findall(r'\b[\w\-]+\b', query_lower) if len(w) > 2 and w not in stop_words]
    
    banca_filter = (nlp_data.get('banca', '') if nlp_data else '').upper()
    cargo_filter = (nlp_data.get('cargo', '') if nlp_data else '').lower()
    orgao_filter = (nlp_data.get('orgao', '') if nlp_data else '').lower()
    ano_filter = (nlp_data.get('ano', '') if nlp_data else '')
    
    results = []
    for exam in KNOWN_EXAMS_DB:
        keywords = exam.get("keywords", [])
        title_lower = exam.get("title", "").lower()
        exam_banca = exam.get("banca", "")
        score = 0
        
        # Banca match (+35)
        if banca_filter:
            if banca_filter in exam_banca or banca_filter.lower() in title_lower:
                score += 35
        elif any(b in title_lower for b in ['cebraspe', 'fgv', 'fcc', 'vunesp', 'cesgranrio', 'ibam', 'idcap', 'idecan']):
            for tok in query_tokens:
                if tok.upper() == exam_banca:
                    score += 35
        
        # Cargo match (+30)
        if cargo_filter and cargo_filter not in ['n/a', 'none', '']:
            if cargo_filter in title_lower:
                score += 30
                
        # Órgão match (+25)
        if orgao_filter and orgao_filter not in ['n/a', 'none', '']:
            if orgao_filter in title_lower:
                score += 25
                
        # Ano match (+15)
        if ano_filter and ano_filter in title_lower:
            score += 15
            
        # Individual tokens match (+40 max)
        if query_tokens:
            matches = sum(1 for kw in query_tokens if kw in keywords or kw in title_lower)
            if matches > 0:
                score += int((matches / len(query_tokens)) * 40)
            
        if score >= 25 or (not query_tokens and score > 0):
            results.append((score, exam))
            
    results.sort(key=lambda x: x[0], reverse=True)
    return [{
        "title": r["title"],
        "url": r["url"],
        "gabarito_url": r.get("gabarito_url"),
        "match_score": min(99, max(50, s)),
        "source": "local_repository"
    } for s, r in results[:15]]

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
                        ddgs_results = list(ddgs.text(q, max_results=4))
                    break
                except Exception:
                    time.sleep(0.3)
                    
            for r in ddgs_results:
                href = r.get('href', '')
                title = r.get('title', '')
                if "qconcursos.com" in href and not is_administrative_document(title):
                    results.append({
                        "title": f"QC - {title[:80]}",
                        "url": href,
                        "gabarito_url": None,
                        "source": "qconcursos",
                        "match_score": 75
                    })
    except Exception as e:
        pass
    return results

def _scrape_pci_pdfs(query, nlp_data=None):
    """
    Busca ultrarrápida e direta de provas no PCI Concursos.
    Utiliza o formulário de busca nativo do PCI e analisa as tabelas estruturadas de provas.
    """
    results = []
    seen_urls = set()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    target_words = set(re.findall(r'\w{3,}', query.lower()))
    stop_words = {'prova', 'provas', 'concurso', 'concursos', 'para', 'com', 'sem', 'pdf', 'download', 'ano', 'pci'}
    target_words = {w for w in target_words if w not in stop_words}

    orgao_val = str(nlp_data.get('orgao', '')).strip().lower() if nlp_data else ''
    cargo_val = str(nlp_data.get('cargo', '')).strip().lower() if nlp_data else ''
    banca_val = str(nlp_data.get('banca', '')).strip().lower() if nlp_data else ''

    queries_to_post = []
    clean_q = ' '.join([w for w in query.split() if w.lower() not in stop_words]).strip()
    if clean_q:
        queries_to_post.append(clean_q)
    if orgao_val and orgao_val not in queries_to_post:
        queries_to_post.append(orgao_val)
    if cargo_val and cargo_val not in queries_to_post:
        queries_to_post.append(cargo_val)

    def extract_pci_table(html_bytes):
        try:
            text = html_bytes.decode('utf-8')
        except UnicodeDecodeError:
            text = html_bytes.decode('iso-8859-1', errors='replace')
        soup = BeautifulSoup(text, 'html.parser')
        
        # 1. Extração estruturada de tabelas de provas do PCI
        for tr in soup.find_all('tr'):
            tds = tr.find_all('td')
            a = tr.find('a', href=lambda h: h and '/provas/download/' in h)
            if not a:
                continue
            href = a['href']
            full_href = href if href.startswith('http') else f"https://www.pciconcursos.com.br{href}"
            if full_href in seen_urls:
                continue
            seen_urls.add(full_href)

            prova_name = a.get_text(separator=' ', strip=True)
            ano_val = tds[1].get_text(strip=True) if len(tds) > 1 else ''
            orgao_col = tds[2].get_text(strip=True) if len(tds) > 2 else ''
            banca_col = tds[3].get_text(strip=True) if len(tds) > 3 else ''

            ano_str = f" {ano_val}" if ano_val and re.match(r'^(19|20)\d{2}$', ano_val) else ''
            banca_suffix = f" ({banca_col})" if banca_col else ''
            orgao_str = f" - {orgao_col}" if orgao_col else ''

            display_title = f"{prova_name}{orgao_str}{ano_str}{banca_suffix}"
            combined_text = f"{prova_name} {orgao_col} {banca_col} {ano_val} {full_href}".lower()
            
            score = 60
            if cargo_val and cargo_val in combined_text:
                score += 20
            if banca_val and banca_val in combined_text:
                score += 15
            if orgao_val and orgao_val in combined_text:
                score += 15
            if target_words:
                matches = sum(1 for tw in target_words if tw in combined_text)
                score += int((matches / len(target_words)) * 20)

            results.append({
                "title": f"PCI - {display_title}",
                "url": full_href,
                "gabarito_url": None,
                "match_score": min(98, max(50, score)),
                "source": "pci"
            })

    # 1. Consulta o endpoint nativo de busca do PCI via POST
    for q_post in queries_to_post[:2]:
        try:
            resp = requests.post('https://www.pciconcursos.com.br/provas/', data={'prova': q_post}, headers=headers, timeout=3.5)
            if resp.status_code == 200:
                extract_pci_table(resp.content)
        except Exception:
            pass

    # 2. Fallback de Slug Direto caso a busca não retorne nada (ex: /provas/{orgao})
    if not results and orgao_val:
        try:
            slug = re.sub(r'[^\w\-]+', '-', orgao_val).strip('-')
            resp = requests.get(f"https://www.pciconcursos.com.br/provas/{slug}", headers=headers, timeout=3.0)
            if resp.status_code == 200:
                extract_pci_table(resp.content)
        except Exception:
            pass

    results.sort(key=lambda x: x.get('match_score', 0), reverse=True)
    return results[:DEFAULT_SEARCH_RESULT_LIMIT]

def _is_cloudflare_challenge(response):
    """Identifica a pagina de desafio sem tentar contornar a protecao do site."""
    if str(response.headers.get('cf-mitigated', '')).lower() == 'challenge':
        return True
    if response.status_code not in {403, 429, 503}:
        return False
    body = (response.text or '').lower()
    return any(marker in body for marker in (
        'cf-chl-',
        'challenge-platform',
        'security verification',
        'verificacao de seguranca',
        'just a moment',
    ))


def _scrape_idcap_pdfs(query, nlp_data=None):
    """
    Crawler HTTP concorrente para a banca IDCAP.
    Varre páginas de status, filtra documentos administrativos e pareia cadernos de prova e gabaritos.
    """
    results = []
    query_lower = query.lower()
    
    # Se uma banca explicitamente diferente foi identificada (ex: FGV, Cebraspe, FCC), pula o crawler do IDCAP
    if nlp_data and nlp_data.get('banca') and nlp_data.get('banca') not in ['IDCAP', ''] and not re.search(r'\b(?:idcap|idecap)\b', query_lower):
        return results

    ignore_words = {
        'prova', 'provas', 'concurso', 'concursos', 'filetype:pdf', 'pdf',
        'processo', 'seletivo', 'privado', 'de', 'do', 'da', 'para', 'em',
        'no', 'na', 'idcap', 'idecap',
    }
    query_words = [w for w in re.findall(r'\b[\w\-/]+\b', query_lower) if len(w) > 1 and w not in ignore_words]

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'pt-BR,pt;q=0.9',
    })

    official_blocked = False

    try:
        concurso_links = []
        if query.startswith('http') and 'idcap' in query_lower:
            concurso_links.append((999, query, "Link Direto"))
        else:
            def fetch_status_page(status_page):
                nonlocal official_blocked
                url = urljoin("https://idcap.selecao.net.br", status_page)
                page_concursos = []
                try:
                    resp = session.get(url, timeout=4.0)
                    if _is_cloudflare_challenge(resp):
                        official_blocked = True
                        return page_concursos
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        for a in soup.find_all('a', href=lambda h: h and '/informacoes/' in h):
                            href = urljoin(url, a['href'])
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

            status_pages = ['/index/1/', '/index/2/', '/index/3/', '/index/4/', '/index/5/']
            if query_words:
                status_pages.insert(0, f"/index/todos/?busca={quote_plus(' '.join(query_words))}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(fetch_status_page, status_page) for status_page in status_pages]
                for fut in concurrent.futures.as_completed(futures):
                    concurso_links.extend(fut.result())

        unique_concursos = {}
        for score, href, title in concurso_links:
            previous = unique_concursos.get(href)
            if previous is None or score > previous[0]:
                unique_concursos[href] = (score, href, title)
        concurso_links = sorted(unique_concursos.values(), key=lambda item: item[0], reverse=True)
        concurso_links = concurso_links[:DEFAULT_SEARCH_RESULT_LIMIT]

        def fetch_concurso_pdfs(item):
            concurso_score, href, concurso_title = item
            c_results = []
            try:
                url = urljoin("https://idcap.selecao.net.br", href)
                resp = session.get(url, timeout=5.0)
                if resp.status_code == 200 and not _is_cloudflare_challenge(resp):
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

                            full_url = urljoin(url, pdf_href)
                            
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
                if len(results) >= DEFAULT_SEARCH_RESULT_LIMIT:
                    break

        if results:
            results.sort(key=lambda x: x.get('match_score', 0), reverse=True)
            unique_results = {result['url']: result for result in results}
            return list(unique_results.values())[:DEFAULT_SEARCH_RESULT_LIMIT]
    except Exception as e:
        print(f"      [IDCAP Crawler] Aviso: {e}", flush=True)

    fallback_query = query.strip()
    if not re.search(r'\b(?:idcap|idecap|id\s*cap)\b', fallback_query, re.IGNORECASE):
        fallback_query = f"{fallback_query} IDCAP".strip()
    fallback_nlp = dict(nlp_data or {})
    fallback_nlp['banca'] = 'IDCAP'

    try:
        pci_results = _scrape_pci_pdfs(fallback_query, fallback_nlp)
        idcap_results = []
        for result in pci_results:
            if re.search(
                r'\b(?:idcap|idecap)\b',
                f"{result.get('title', '')} {result.get('url', '')}",
                re.IGNORECASE,
            ):
                item = dict(result)
                item['source'] = 'idcap'
                idcap_results.append(item)
        if official_blocked:
            print(
                "      [IDCAP Crawler] Portal oficial protegido por Cloudflare; "
                f"usando {len(idcap_results)} resultado(s) do catalogo PCI.",
                flush=True,
            )
        return idcap_results[:DEFAULT_SEARCH_RESULT_LIMIT]
    except Exception as fallback_error:
        print(f"      [IDCAP Crawler] Fallback indisponivel: {fallback_error}", flush=True)
        return []

def _search_pdfs_web(query, nlp_data=None):
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

    # 1. Banco interno e repositório local de provas
    known = _search_known_exams(query, nlp_data)
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


def extract_pci_page_pdfs(pci_url: str) -> tuple[str | None, str | None, str | None]:
    """
    Inspeciona determinística e diretamente uma página do PCI Concursos ou link direto de arquivo.
    Retorna: (prova_pdf_url, gabarito_pdf_url, page_title)
    Garante que nunca troca por outra prova, capturando estritamente os links oficiais presentes na página.
    """
    if not pci_url:
        return None, None, None

    pci_url_clean = pci_url.strip()

    # Se já for link direto de PDF
    if '.pdf' in pci_url_clean.lower() or 'arquivo.pciconcursos.com.br' in pci_url_clean:
        if 'gabarito' in pci_url_clean.lower():
            return None, pci_url_clean, None
        gab_candidate = None
        if 'arquivo_prova' in pci_url_clean:
            gab_candidate = pci_url_clean.replace('arquivo_prova', 'arquivo_gabarito').replace('-prova.pdf', '-gabarito.pdf')
        elif 'prova.pdf' in pci_url_clean.lower():
            gab_candidate = pci_url_clean.lower().replace('prova.pdf', 'gabarito.pdf')
        return pci_url_clean, gab_candidate, None

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.pciconcursos.com.br/'
    }

    try:
        resp = requests.get(pci_url_clean, headers=headers, timeout=8.0, verify=False)
        if resp.status_code != 200:
            return None, None, None

        if resp.content[:4] == b'%PDF':
            return pci_url_clean, None, None

        try:
            html_text = resp.content.decode('utf-8')
        except UnicodeDecodeError:
            html_text = resp.content.decode('iso-8859-1', errors='replace')

        soup = BeautifulSoup(html_text, 'html.parser')

        page_title = None
        title_tag = soup.find('h1') or soup.find('title')
        if title_tag:
            page_title = title_tag.get_text(separator=' ', strip=True)
            page_title = re.sub(r'(\s*-\s*PCI Concursos|\s*-\s*Provas para Download|\s*-\s*Download).*', '', page_title, flags=re.IGNORECASE).strip()

        prova_url = None
        gabarito_url = None

        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            text = a.get_text(separator=' ', strip=True).lower()
            href_lower = href.lower()

            full_href = href if href.startswith('http') else f"https://www.pciconcursos.com.br{href}"

            if 'arquivo.pciconcursos.com.br' in href_lower or '.pdf' in href_lower or '/download/' in href_lower:
                if 'gabarito' in text or 'gabarito' in href_lower:
                    if not gabarito_url:
                        gabarito_url = full_href
                elif any(k in text for k in ['prova', 'caderno', 'download']) or 'prova' in href_lower or '.pdf' in href_lower:
                    if not prova_url and not is_administrative_document(text):
                        prova_url = full_href

        return prova_url, gabarito_url, page_title

    except Exception as e:
        print(f"[PCI Page Extract Error] {e}", flush=True)
        return None, None, None


