import requests
from bs4 import BeautifulSoup
import time
import re

KNOWN_EXAMS_DB = []

def _search_known_exams(query):
    """Busca no banco interno de provas conhecidas."""
    query_lower = query.lower()
    results = []
    for exam in KNOWN_EXAMS_DB:
        keywords = exam["keywords"]
        # Score = número de keywords que aparecem na query
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            results.append((score, exam))
    
    # Ordenar por relevância
    results.sort(key=lambda x: x[0], reverse=True)
    return [{"title": r["title"], "url": r["url"]} for _, r in results[:5]]



def _search_qc_provas(query):
    results = []
    try:
        from services.exam_service import get_ddgs_class
        ddgs_cls = get_ddgs_class()
        if ddgs_cls:
            q = f"site:qconcursos.com/questoes-de-concursos/provas {query}"
            ddgs_results = []
            for attempt in range(3):
                try:
                    with ddgs_cls() as ddgs:
                        ddgs_results = list(ddgs.text(q, max_results=3))
                    break
                except Exception:
                    import time; time.sleep(1)
                    
            for r in ddgs_results:
                if "qconcursos.com" in r['href']:
                    results.append({
                        "title": "[QC] " + r['title'][:60],
                        "url": r['href'],
                        "source": "qconcursos"
                    })
    except Exception as e:
        print("Erro busca QC:", e)
    return results

def _scrape_pci_pdfs(query, nlp_data=None):
    results = []
    try:
        from services.exam_service import get_ddgs_class
        ddgs_cls = get_ddgs_class()
        if not ddgs_cls:
            return results
        
        search_query = f'{query} site:pciconcursos.com.br/provas/download/'
        ddgs_results = []
        for attempt in range(3):
            try:
                ddgs_results = list(ddgs_cls().text(search_query, max_results=15))
                break
            except Exception as e:
                import time; time.sleep(1)
        
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
                    score = 10
                    
                results.append({
                    "title": f"PCI - {title[:100]}",
                    "url": href,
                    "match_score": score
                })
                
        results.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        results = results[:6]
        
    except Exception as e:
        print(f"Erro Busca PCI: {e}")
    return results






def _scrape_idcap_pdfs(query):
    results = []
    query_lower = query.lower()
    ignore_words = {'prova', 'provas', 'concurso', 'concursos', 'filetype:pdf', 'pdf'}
    query_words = [w for w in query_lower.split() if len(w) > 3 and w not in ignore_words]

    PROVA_KEYWORDS = ['prova', 'gabarito', 'caderno', 'questões']
    SKIP_KEYWORDS = ['resultado', 'convoca', 'retifica', 'cronograma', 'edital', 'rela', 'resposta', 'recurso', 'divulga', 'homologa', 'inscri', 'isen', 'anexo', 'aditivo', 'comunicado', 'aviso', 'lista', 'decreto', 'lei', 'portaria', 'informa', 'classifica', 'quantitativo', 'local', 'data', 'nota', 'judicial', 'decis', 'cumprimento', 'gabarito', 'preliminar', 'definitiv', 'parecer']

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            concurso_links = []
            if query.startswith('http') and 'idcap' in query:
                concurso_links.append((999, query, "Link Direto"))
            else:
                for status_page in ['/index/1/', '/index/3/', '/index/4/', '/index/5/']:
                    try:
                        page.goto(f'https://idcap.selecao.net.br{status_page}', timeout=60000, wait_until='domcontentloaded')
                        
                        links = page.query_selector_all("a[href*='/informacoes/']")
                        for a in links:
                            href = a.get_attribute("href")
                            text = a.evaluate("el => el.innerText.toLowerCase()")
                            if not href: continue
                            
                            if query_words:
                                score = sum(1 for w in query_words if w in text)
                                if score > 0:
                                    concurso_links.append((score, href, text))
                            else:
                                concurso_links.append((1, href, text))
                    except Exception as e:
                        print(f"Playwright IDCAP {status_page} erro: {e}")
                        
            concurso_links.sort(key=lambda x: x[0], reverse=True)
            for score, href, concurso_title in concurso_links[:10]:
                try:
                    url = f"https://idcap.selecao.net.br{href}" if href.startswith('/') else href
                    page.goto(url, timeout=60000, wait_until='domcontentloaded')
                    
                    pdf_links = page.query_selector_all("a[href*='.pdf'], a[href*='/download/']")
                    for a in pdf_links:
                        pdf_href = a.get_attribute("href")
                        if not pdf_href: continue
                        
                        text = a.evaluate("el => el.innerText.trim()")
                        text_lower = text.lower()
                        
                        should_skip = any(kw in text_lower for kw in SKIP_KEYWORDS)
                        is_prova = any(kw in text_lower for kw in PROVA_KEYWORDS)
                        
                        # Aceitar se tiver palavra de prova OU se não tiver nenhuma palavra a ser ignorada (SKIP)
                        # Assim capturamos "Estivador", "Arrumador" porque eles não estão na lista de SKIP
                        if not should_skip:
                            clean_title = concurso_title.replace('\n', ' ').strip()
                            results.append({
                                "title": f"IDCAP - {clean_title[:100]} - {text[:80]}",
                                "url": pdf_href
                            })
                            if len(results) >= 25:
                                break
                except Exception as e:
                    print(f"Playwright IDCAP concurso {href} erro: {e}")
            
            browser.close()
    except Exception as e:
        print(f"Erro Playwright IDCAP: {e}")
    return results

def _search_pdfs_web(query, api_key_val=None):
    """Busca PDFs de provas: IDCAP + IDECAN + banco interno + GLM + DDG."""

    results = []
    seen_urls = set()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'pt-BR,pt;q=0.9',
    }

    def _add_results(new_results):
        for r in new_results:
            url = r.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                results.append(r)

    # Estratégia 1: Banco interno de provas conhecidas (sempre funciona, sem quota)
    known = _search_known_exams(query)
    print(f"Banco interno: {len(known)} provas")
    _add_results(known)

    # Estratégia 3: DuckDuckGo via DDGS (Busca Genérica Reforçada)
    if len(results) < 10:
        try:
            from services.exam_service import get_ddgs_class
            ddgs_cls = get_ddgs_class()
            if ddgs_cls:
                ddg_query = f'{query} prova concurso filetype:pdf'
                with ddgs_cls() as ddgs:
                    ddg_results = ddgs.text(ddg_query, max_results=8)
                    for r in ddg_results:
                        url = r.get('href', '')
                        title = r.get('title', '')
                        if url and '.pdf' in url.lower():
                            _add_results([{"title": f"Web - {title[:60]}", "url": url}])
        except Exception as e:
            print(f"Erro DDGS: {e}")

    return results

