import os, json, sys, sqlite3, subprocess, re
from flask import request, jsonify
from playwright.sync_api import sync_playwright
import google.generativeai as genai
from models import Session, Exam, Question, AppConfig
from app_core.orchestrator import orchestrator
from bs4 import BeautifulSoup
import requests
import datetime
import fitz
import threading

def set_exam_progress(*args, **kwargs):
    from app import set_exam_progress as _real_set_prog
    _real_set_prog(*args, **kwargs)

def get_ddgs_class():
    try:
        from ddgs import DDGS
        return DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            return DDGS
        except ImportError:
            return None

def search_exams():
    query = request.args.get('q', '')
    sources_param = request.args.get('sources', '')
    interpreted_query = query
    from routes.config_routes import get_glm_key
    from flask_login import current_user
    api_key_val = get_glm_key()
    if 'qconcursos.com' in query:
        return jsonify([{'title': 'Extração Direta QConcursos', 'url': query, 'source': 'QConcursos Direct'}])
    active_sources = [s.strip().lower() for s in sources_param.split(',')] if sources_param else ['web', 'idcap', 'pci', 'qconcursos']
    data = {}
    if api_key_val and query:
        try:
            import app_core.orchestrator as orch_module
            from app_core.orchestrator import orchestrator
            import app_core.orchestrator as orch_module
            from app_core.orchestrator import orchestrator
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    import openai
                    from app_core.orchestrator import orchestrator, get_client_for_key
                    key_data = None
                    try:
                        key_data = orchestrator.key_manager.get_best_key()
                        client = get_client_for_key(key_data)
                        model_name = "gemini-1.5-flash" if key_data['provider'] != 'nvidia' else "z-ai/glm-5.2"
                    except Exception:
                        valid_api_key = api_key_val.split(',')[0].strip()
                        if valid_api_key.startswith('AIza'):
                            client = openai.OpenAI(api_key=valid_api_key, base_url='https://generativelanguage.googleapis.com/v1beta/openai/')
                            model_name = 'gemini-1.5-flash'
                        else:
                            client = openai.OpenAI(api_key=valid_api_key, base_url='https://integrate.api.nvidia.com/v1')
                            model_name = 'z-ai/glm-5.2'
                            
                    prompt = f'\n                    O usuário digitou a seguinte busca para encontrar provas de concurso: "{query}".\n                    Interprete essa busca e extraia as informações estruturadas. \n                    IMPORTANTE: Não invente, deduza ou assuma uma "banca" ou "órgão" se o usuário não citou explicitamente na busca.\n                    Retorne APENAS um JSON válido no seguinte formato e nada mais:\n                    {{\n                      "orgao": "Nome do órgão (ou vazio se não souber)",\n                      "banca": "Nome da banca explícita na busca (ou vazio)",\n                      "ano": "Ano (ou vazio)",\n                      "cargo": "Cargo (ou vazio)",\n                      "local": "Local/Cidade/Estado (ou vazio)",\n                      "query_otimizada": "Uma string de busca limpa e otimizada para encontrar a prova em PDF (inclua apenas as infos dadas pelo usuario)"\n                    }}\n                    '
                    response = client.chat.completions.create(model=model_name, messages=[{'role': 'user', 'content': prompt}])
                    clean_json = response.choices[0].message.content.replace('```json', '').replace('```', '').strip()
                    data = json.loads(clean_json)
                    if key_data:
                        orchestrator.key_manager.release_key(key_data)
                    break
                except Exception as e:
                    print(f'Erro ao usar Gemini (Tentativa {attempt + 1}/{max_attempts}):', e, flush=True)
                    if key_data and ('429' in str(e) or 'quota' in str(e).lower() or '401' in str(e)):
                        error_type = "429" if '429' in str(e) or 'quota' in str(e).lower() else "401"
                        orchestrator.key_manager.report_error(key_data, error_type=error_type)
                    else:
                        if key_data:
                            orchestrator.key_manager.release_key(key_data, success=False)
                        data = {}
                        break
            if not data:
                data = {}
            interpreted_query = data.get('query_otimizada', query)
            print('\n' + '=' * 30, flush=True)
            print('LOG DE BUSCA (GEMINI NLP)', flush=True)
            print(f"Órgão: {data.get('orgao', 'N/A')}", flush=True)
            print(f"Banca: {data.get('banca', 'N/A')}", flush=True)
            print(f"Ano: {data.get('ano', 'N/A')}", flush=True)
            print(f'Query Melhorada: {interpreted_query}', flush=True)
            print('=' * 30 + '\n', flush=True)
            banca_identificada = data.get('banca', '').strip().lower()
            scrapers_bancas_especificas = ['idcap']
            query_lower = query.lower()
            scraper_explicito = None
            mapa_scrapers = {'idcap': ['idcap', 'id cap'], 'pci': ['pci', 'pciconcurso', 'pciconcursos', 'pci concursos', 'pci concurso']}
            for (scraper_key, terms) in mapa_scrapers.items():
                if any((term in query_lower for term in terms)):
                    scraper_explicito = scraper_key
                    break
            if scraper_explicito:
                for sb in ['idcap', 'pci']:
                    if sb != scraper_explicito and sb in active_sources:
                        active_sources.remove(sb)
                        print(f"Otimização: scraper '{sb}' ignorado pois o usuário digitou '{scraper_explicito}' explicitamente.", flush=True)
            elif banca_identificada and banca_identificada != 'n/a':
                for sb in scrapers_bancas_especificas:
                    if sb not in banca_identificada and sb in active_sources:
                        active_sources.remove(sb)
                        print(f"Otimização: scraper '{sb}' ignorado pois a banca buscada é '{banca_identificada}'.", flush=True)
        except Exception as e:
            print('Erro ao usar Gemini:', e, flush=True)
    import concurrent.futures
    all_results = []

    def run_scraper(func, *args):
        try:
            return func(*args)
        except Exception as e:
            print(f'Erro no scraper {func.__name__}: {e}')
            return []
    from services.scraper_service import _search_pdfs_web, _scrape_idcap_pdfs, _scrape_pci_pdfs
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        if 'web' in active_sources:
            futures.append(executor.submit(run_scraper, _search_pdfs_web, interpreted_query, api_key_val))
        if 'idcap' in active_sources:
            futures.append(executor.submit(run_scraper, _scrape_idcap_pdfs, query))
        if 'pci' in active_sources:
            futures.append(executor.submit(run_scraper, _scrape_pci_pdfs, query, data))
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                print(f"Futuro resolvido com {len(res)} resultados. Exemplo: {(res[0] if res else 'None')}", flush=True)
                all_results.extend(res)

    def standardize_title(t, nlp_data, url=''):
        import re
        ano_original = ''
        m_ano = re.search('\\b(19\\d{2}|20\\d{2})\\b', t)
        if not m_ano and url:
            m_ano = re.search('\\b(19\\d{2}|20\\d{2})\\b', url)
        if m_ano:
            ano_original = m_ano.group(1)
        t = re.sub('[—–]', '-', t)
        t = re.sub('^(provas para download|prova para download|provas?)\\s*-\\s*', '', t, flags=re.IGNORECASE)
        t = re.sub('^(IDCAP|IDECAN|PCI|QConcursos)\\s*-\\s*', '', t, flags=re.IGNORECASE)
        t = re.sub('(processo seletivo(\\s*privado|\\s*priv|\\s*pri)*)+', '', t, flags=re.IGNORECASE)
        t = re.sub('(concurso\\s*p[uú]blico.*?)(para|-|\\s|$)', '', t, flags=re.IGNORECASE)
        t = re.sub('psp\\s*\\d+/\\d+\\s*-\\s*ogmo/s\\s*-\\s*', '', t, flags=re.IGNORECASE)
        t = re.sub('\\d{3}/\\d{4}\\s*-\\s*', '', t)
        t = re.sub('(?i)\\(?(edital|edt\\.?)\\s*(cbmmg)?\\s*(nº)?\\s*\\d+([./]\\d+)?(.*?de\\s*\\d+\\s*de\\s*[a-zç]+\\s*de\\s*\\d+)?\\)?', '', t)
        t = re.sub('\\(\\s*-\\s*\\)|\\(\\s*\\)', '', t)
        t = re.sub('1ª Nota Pública.*', '', t, flags=re.IGNORECASE)
        t = re.sub('Cumprimento de decis.*', '', t, flags=re.IGNORECASE)
        t = t.strip(' -')
        t = re.sub('\\s*-\\s*-\\s*', ' - ', t)
        parts = [p.strip() for p in t.split('-')]
        seen = set()
        clean_parts = []
        for p in parts:
            p_lower = p.lower()
            if p_lower not in seen and p_lower:
                seen.add(p_lower)
                clean_parts.append(p)
        t = ' - '.join(clean_parts)
        ano = nlp_data.get('ano', '') if nlp_data else ''
        orgao = nlp_data.get('orgao', '') if nlp_data else ''
        local = nlp_data.get('local', '') if nlp_data else ''
        if orgao:
            import re
            orgao = re.sub('^(pri|priv|privado|processo\\s*seletivo.*)$', '', orgao, flags=re.IGNORECASE).strip()
        if not orgao or str(orgao).lower() in ['n/a', '', 'null']:
            orgao = ''
        if not local or str(local).lower() in ['n/a', '', 'null']:
            local_str = ''
        elif local.lower() in orgao.lower():
            local_str = ''
        else:
            local_str = f' - {local}'
        cargo = t.strip()
        if orgao and cargo:
            cargo_parts = [p.strip() for p in cargo.split('-')]
            if len(cargo_parts) > 1:
                import re
                first_part = re.sub('[^\\w\\s]', ' ', cargo_parts[0]).strip().lower()
                orgao_clean = re.sub('[^\\w\\s]', ' ', orgao).strip().lower()
                first_part = re.sub('\\s+', ' ', first_part)
                orgao_clean = re.sub('\\s+', ' ', orgao_clean)
                if first_part and orgao_clean and (first_part in orgao_clean or orgao_clean in first_part):
                    cargo = ' - '.join(cargo_parts[1:]).strip()
        if not cargo:
            cargo = 'Geral / Conhecimentos Básicos'
        if ano_original:
            ano = ano_original
        elif not ano or str(ano).lower() in ['n/a', '', 'null']:
            ano = ''
        prefix = f'[{ano}] ' if ano and str(ano).lower() not in ['n/a', '', 'null'] else ''
        orgao_final = f'{orgao}{local_str} - ' if orgao else f'{local} - ' if local_str else ''
        final_string = f'{orgao_final}{cargo}'.upper()
        final_parts = [p.strip() for p in final_string.split('-') if p.strip()]
        dedup_parts = []
        for p in final_parts:
            if not dedup_parts:
                dedup_parts.append(p)
            else:
                p_clean = re.sub('[^\\w]', '', p).lower()
                last_clean = re.sub('[^\\w]', '', dedup_parts[-1]).lower()
                if p_clean and last_clean and (p_clean == last_clean or p_clean in last_clean or last_clean in p_clean):
                    pass
                else:
                    dedup_parts.append(p)
        return f"{prefix}{' - '.join(dedup_parts)}"
    seen_urls = set()
    pdf_results = []
    print(f'Total all_results coletados para deduplicar: {len(all_results)}', flush=True)
    for r in all_results:
        url = r.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            r['title'] = standardize_title(r.get('title', ''), data, url)
            pdf_results.append(r)
    print(f'PDFs encontrados pelos scrapers: {len(pdf_results)}')
    if not pdf_results:
        print('Nenhum PDF encontrado para esta busca.')
    session = Session()
    current_urls = {r['url'] for r in pdf_results}
    old_pending = session.query(Exam).filter_by(user_id=current_user.id).filter_by(status='Pendente', user_id=current_user.id).all()
    for old in old_pending:
        if old.source_url not in current_urls:
            session.delete(old)
    session.commit()
    for res in pdf_results:
        m_score = res.get('match_score', 0)
        existing = session.query(Exam).filter_by(user_id=current_user.id).filter_by(source_url=res['url'], user_id=current_user.id).first()
        if not existing:
            new_exam = Exam(title=res['title'], source_url=res['url'], status='Pendente', match_score=m_score, user_id=current_user.id)
            session.add(new_exam)
        else:
            existing.match_score = m_score
    session.commit()
    current_urls = [r['url'] for r in pdf_results]
    pending_exams = session.query(Exam).filter(Exam.user_id == current_user.id, Exam.status != 'Aprovada', Exam.source_url.in_(current_urls)).all()
    results = [{'id': e.id, 'title': e.title, 'url': e.source_url.split('?v=')[0], 'match_score': e.match_score or 0, 'status': e.status} for e in pending_exams]
    session.close()
    return jsonify(results)

def _real_scrape_exam(session, exam):
    """Baixa o PDF e usa o GLM para extrair as questões."""
    if session.query(Question).filter_by(exam_id=exam.id).count() > 0:
        session.query(Question).filter_by(exam_id=exam.id).delete()
    session.commit() # Libera o lock do DB para as outras threads!
    exam.status = 'Aprovada'
    session.commit()
    set_exam_progress(exam.id, 'Iniciando...', 0)
    if 'qconcursos.com' in exam.source_url and '.pdf' not in exam.source_url.lower():

        def qc_bg_task(e_id, source_url):
            bg_session = Session()
            set_exam_progress(e_id, 'Extraindo questões via QConcursos (Login)...', 10)
            import subprocess, sys
            result = subprocess.run([sys.executable, 'qc_scraper.py', str(e_id), source_url], capture_output=True, text=True)
            bg_exam = bg_session.query(Exam).filter_by(id=e_id).first()
            if result.returncode == 0:
                set_exam_progress(e_id, 'Processamento concluído!', 100)
            else:
                err_msg = (result.stdout + result.stderr)[:100]
                set_exam_progress(e_id, f'Erro QC: {err_msg}', -1)
                if bg_exam:
                    bg_session.delete(bg_exam)
            bg_session.commit()
            bg_session.close()
        t = threading.Thread(target=qc_bg_task, args=(exam.id, exam.source_url), daemon=True)
        t.start()
        return (True, 'Scraper do QConcursos iniciado.')
    # (Legacy check removido: O orquestrador cuidará de aguardar as chaves se estiverem em cooldown)
    if not exam.source_url:
        print('URL da prova não definida!')
        return (False, 'URL da prova vazia.')
    try:
        set_exam_progress(exam.id, 'Baixando prova original...', 15)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'application/pdf,*/*'}
        text = ''
        pdf_downloaded = False
        pdf_bytes = None
        if hasattr(exam, 'pdf_path') and exam.pdf_path and os.path.exists(exam.pdf_path):
            print(f'Bypassing download, using existing PDF: {exam.pdf_path}')
            with open(exam.pdf_path, 'rb') as f:
                pdf_bytes = f.read()
        elif not pdf_bytes:
            import glob
            local_matches = glob.glob(f'pdfs/{exam.id}_*.pdf')
            if local_matches and os.path.exists(local_matches[0]) and (os.path.getsize(local_matches[0]) > 1000):
                print(f'Bypassing download, using existing PDF on disk: {local_matches[0]}')
                with open(local_matches[0], 'rb') as f:
                    pdf_bytes = f.read()
        try:
            if not pdf_bytes:
                import warnings
                from urllib3.exceptions import InsecureRequestWarning
                warnings.filterwarnings('ignore', category=InsecureRequestWarning)
                req_session = requests.Session()
                req_session.headers.update(headers)
                url_to_download = exam.source_url
                if 'pciconcursos.com.br/provas/download/' in url_to_download:
                    print(f'Buscando token atualizado do PCI para: {url_to_download}')
                    from bs4 import BeautifulSoup
                    res_pci = req_session.get(url_to_download, timeout=20, verify=False)
                    soup_pci = BeautifulSoup(res_pci.text, 'html.parser')
                    for link in soup_pci.select('a'):
                        arq = link.get('data-arquivo')
                        tok = link.get('data-code')
                        acao = link.get('data-acao')
                        if arq and tok and (acao == 'baixar') and ('gabarito' not in arq.lower()):
                            url_to_download = f'https://www.pciconcursos.com.br/download/{arq}?token={tok}'
                            req_session.headers.update({'Referer': exam.source_url})
                            print(f'Token fresco obtido, baixando PDF...')
                            break
                r = req_session.get(url_to_download, timeout=30, allow_redirects=True, verify=False)
                r.raise_for_status()
                if r.headers.get('Content-Type', '').startswith('application/pdf') or r.content[:4] == b'%PDF':
                    pdf_bytes = r.content
                    print(f'PDF baixado via requests: {len(pdf_bytes)} bytes')
                else:
                    print(f"requests retornou {r.headers.get('Content-Type', '?')} - nao e PDF")
        except Exception as e:
            print(f'requests falhou ({type(e).__name__}), tentando Playwright...')
        if not pdf_bytes:
            try:
                from playwright.sync_api import sync_playwright
                import tempfile as _tempfile
                dl_dir = _tempfile.mkdtemp(prefix='pw_dl_')
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(user_agent=headers['User-Agent'], accept_downloads=True, ignore_https_errors=True)
                    page = context.new_page()
                    captured = []

                    def handle_response(response):
                        ct = response.headers.get('content-type', '')
                        if 'pdf' in ct or response.url.lower().endswith('.pdf'):
                            try:
                                captured.append(response.body())
                            except Exception:
                                pass
                    page.on('response', handle_response)
                    try:
                        if 'pciconcursos.com.br/provas/download/' in exam.source_url:
                            page.goto(exam.source_url, timeout=20000)
                            try:
                                page.wait_for_selector("a.prova-pdf-link[data-acao='baixar']", timeout=15000)
                            except Exception:
                                pass
                            loc = page.locator("a.prova-pdf-link[data-acao='baixar']")
                            pdf_url = None
                            links_to_try = []
                            # Se a url original tinha um nome de arquivo especifico, tenta achar ele
                            target_filename = exam.source_url.split('/')[-1] if '.pdf' in exam.source_url.lower() else None
                            
                            for i in range(loc.count()):
                                arq = loc.nth(i).get_attribute('data-arquivo')
                                tok = loc.nth(i).get_attribute('data-code')
                                if arq and tok and ('gabarito' not in arq.lower()):
                                    link = f'https://www.pciconcursos.com.br/download/{arq}?token={tok}'
                                    if target_filename and arq == target_filename:
                                        links_to_try.insert(0, link) # Prioridade maxima
                                    else:
                                        links_to_try.append(link)
                            print(f'Encontrados {len(links_to_try)} links de prova no PCI para testar.')
                            for (i, test_url) in enumerate(links_to_try):
                                print(f'Tentando link {i + 1}/{len(links_to_try)}: {test_url}')
                                try:
                                    with page.expect_download(timeout=10000) as dl_info:
                                        page.goto(test_url)
                                    dl = dl_info.value
                                    import tempfile
                                    temp_path = os.path.join(tempfile.gettempdir(), f'pci_temp_{exam.id}_{i}.pdf')
                                    dl.save_as(temp_path)
                                    with open(temp_path, 'rb') as f:
                                        body = f.read()
                                    if body[:4] == b'%PDF':
                                        print(f'PDF capturado com sucesso via download: {len(body)} bytes')
                                        pdf_url = test_url
                                        pdf_bytes = body
                                        break
                                    else:
                                        print('Download concluído mas não é um PDF válido.')
                                except Exception as e:
                                    print(f'Link falhou (provável 404 no PCI ou timeout): {type(e).__name__}')
                            if not pdf_url:
                                raise Exception('Nenhum link PDF válido foi encontrado (todos deram erro ou 404).')
                        else:
                            r = context.request.get(exam.source_url, headers={'Referer': exam.source_url})
                            if r.status == 200:
                                pdf_bytes = r.body()
                                if pdf_bytes[:4] == b'%PDF':
                                    print(f'PDF capturado via context.request.get genérico: {len(pdf_bytes)} bytes')
                                else:
                                    raise Exception('Conteúdo genérico baixado não é um PDF válido.')
                            else:
                                raise Exception(f'Falha genérica no download: HTTP {r.status}')
                    except Exception as e:
                        last_error = str(e)
                        print(f'Erro Playwright get: {e}')
                    browser.close()
            except Exception as e:
                last_error = str(e)
                print(f'Playwright falhou: {type(e).__name__}: {str(e)[:120]}')
        if pdf_bytes and pdf_bytes[:4] == b'%PDF':
            set_exam_progress(exam.id, 'Extraindo texto do PDF...', 30)
            try:
                import fitz
                import io
                import tempfile
                import re

                temp_dir = tempfile.mkdtemp(prefix=f'exam_{exam.id}_')
                full_pdf_path = os.path.join(temp_dir, 'full.pdf')
                with open(full_pdf_path, 'wb') as f:
                    f.write(pdf_bytes)

                doc = fitz.open(full_pdf_path)
                pages_text = []
                for page in doc:
                    pages_text.append(page.get_text() or '')
                doc.close()

                chunk_texts = []
                chunk_size = 3
                overlap = 1
                idx = 0
                while idx < len(pages_text):
                    chunk = '\n'.join(pages_text[idx : idx + chunk_size])
                    if chunk.strip():
                        chunk_texts.append(chunk)
                    if idx + chunk_size >= len(pages_text):
                        break
                    idx += (chunk_size - overlap)
                    
                pdf_downloaded = True
                print(f'PDF dividido em {len(chunk_texts)} blocos de páginas.')
            except Exception as e:
                print(f'Erro ao processar PDF com fitz: {e}')
                pdf_downloaded = False
        else:
            print(f'Nenhuma estrategia conseguiu baixar o PDF de: {exam.source_url}')
            pdf_downloaded = False
        task_ids = []
        if pdf_downloaded:
            set_exam_progress(exam.id, f'Enviando {len(chunk_texts)} blocos para IA...', 35, total_chunks=len(chunk_texts), done_chunks=0)
            for (idx, text_block) in enumerate(chunk_texts):
                t_id = orchestrator.push_task(exam.id, 'extract_questions', {
                    'file_path': full_pdf_path, 
                    'text': text_block,
                    'attempts': 0, 
                    'chunk_info': f'{idx + 1}/{len(chunk_texts)}'
                })
                task_ids.append(t_id)
        else:
            set_exam_progress(exam.id, 'Site bloqueou o robô ou PDF saiu do ar.', -1, error_type='download_blocked')
            return (False, "O site oficial bloqueou nosso robô ou o PDF saiu do ar. Por favor, clique em 'Ignorar' neste e tente BAIXAR OUTRO LINK da lista!")

        def background_processing(t_ids, e_id, source_url, temp_cleanup_dir=None):
            try:
                bg_session = Session()
                bg_exam = bg_session.query(Exam).filter_by(id=e_id).first()
                if not bg_exam:
                    bg_session.close()
                    return
                bg_session.commit() # IMPORTANTÍSSIMO: Libera o lock de leitura antes de ficar ocioso!
                if 'qconcursos.com' in bg_exam.source_url and '.pdf' not in bg_exam.source_url.lower():
                    set_exam_progress(bg_exam.id, 'Extraindo questões via QConcursos (Login)...', 10)
                    import subprocess, sys
                    result = subprocess.run([sys.executable, 'qc_scraper.py', str(bg_exam.id), bg_exam.source_url], capture_output=True, text=True)
                    if result.returncode == 0:
                        set_exam_progress(bg_exam.id, 'Processamento concluído!', 100)
                    else:
                        err_msg = (result.stdout + result.stderr)[:100]
                        set_exam_progress(bg_exam.id, f'Erro QC: {err_msg}', -1)
                        bg_session.delete(bg_exam)
                    bg_session.commit()
                    bg_session.close()
                    return
                import time
                finished_tasks = {}
                start_wait = time.time()
                MAX_WAIT = 1800
                total_chunks = len(t_ids)
                while len(finished_tasks) < len(t_ids):
                    elapsed = time.time() - start_wait
                    if elapsed > MAX_WAIT:
                        set_exam_progress(e_id, 'Tempo limite excedido. Tente novamente.', -1, error_type='timeout')
                        bg_session.close()
                        return
                    for t in list(orchestrator.history):
                        if t.id in t_ids and t.id not in finished_tasks:
                            finished_tasks[t.id] = t
                    done = len(finished_tasks)
                    chunk_pct = 35 + int(done / total_chunks * 55) if total_chunks > 0 else 55
                    set_exam_progress(e_id, f'Extraindo questões ({done}/{total_chunks} blocos)...', min(chunk_pct, 90), total_chunks=total_chunks, done_chunks=done)
                    time.sleep(1)
                questoes = []
                has_error = False
                error_str = ''
                for t_id in t_ids:
                    t = finished_tasks[t_id]
                    if t.status == 'erro':
                        has_error = True
                        error_str = t.error or 'Erro desconhecido'
                    elif isinstance(t.result, list):
                        questoes.extend(t.result)
                if not questoes and has_error:
                    if '429' in error_str or 'Quota' in error_str or 'exhausted' in error_str.lower():
                        db_q = Question(exam_id=bg_exam.id, statement=f'⚠️ Limite gratuito da Inteligência Artificial excedido.\n\nAs questões não puderam ser extraídas automaticamente.\n\nLink original: {source_url}', options=None, correct_answer='Certo')
                        bg_session.add(db_q)
                        set_exam_progress(bg_exam.id, 'Limite da IA atingido. Aguarde 1 min ou adicione mais chaves.', -1, error_type='quota_exceeded')
                    elif '404' in error_str or 'not found' in error_str.lower():
                        set_exam_progress(bg_exam.id, 'Modelo de IA indisponível. Verifique no Manager.', -1, error_type='model_not_found')
                        bg_session.delete(bg_exam)
                    else:
                        set_exam_progress(bg_exam.id, f'Erro: {error_str[:60]}', -1, error_type='unknown')
                        bg_session.delete(bg_exam)
                    bg_session.commit()
                elif not questoes:
                    set_exam_progress(bg_exam.id, 'A IA não conseguiu ler questões neste PDF.', -1, error_type='no_questions')
                    bg_session.delete(bg_exam)
                    bg_session.commit()
                else:
                    full_pdf_path = os.path.join(temp_cleanup_dir, 'full.pdf') if temp_cleanup_dir else None
                    
                    # 100% DETERMINISMO: Validador Numérico (Gap Finder) e Auto-Healing
                    import re
                    def extrai_int(num_str):
                        try: return int(re.sub(r'\D', '', str(num_str)))
                        except: return 0
                        
                    numeros_vistos = set()
                    for q in questoes:
                        if isinstance(q, dict) and q.get('numero_questao'):
                            n = extrai_int(q['numero_questao'])
                            if n > 0: numeros_vistos.add(n)
                            
                    if numeros_vistos and full_pdf_path and os.path.exists(full_pdf_path):
                        max_num = max(numeros_vistos)
                        gaps = [i for i in range(1, max_num + 1) if i not in numeros_vistos]
                        
                        retries = 0
                        while gaps and retries < 2:
                            set_exam_progress(bg_exam.id, f'Corrigindo {len(gaps)} falhas da IA (Tentativa {retries+1})...', 80)
                            
                            healing_task_ids = []
                            gap_batches = [gaps[i:i+5] for i in range(0, len(gaps), 5)]
                            for gb in gap_batches:
                                tid = orchestrator.push_task(bg_exam.id, 'extract_questions_focused', {'file_path': full_pdf_path, 'gaps': gb}, model_name=None)
                                healing_task_ids.append(tid)
                                
                            start_wait = time.time()
                            finished_healing = {}
                            while len(finished_healing) < len(healing_task_ids):
                                if time.time() - start_wait > 300: break
                                for t in list(orchestrator.history):
                                    if t.id in healing_task_ids and t.id not in finished_healing:
                                        finished_healing[t.id] = t
                                time.sleep(1)
                                
                            for tid in healing_task_ids:
                                t = finished_healing.get(tid)
                                if t and isinstance(t.result, list):
                                    questoes.extend(t.result)
                                    for q in t.result:
                                        if isinstance(q, dict) and q.get('numero_questao'):
                                            n = extrai_int(q.get('numero_questao'))
                                            if n > 0: numeros_vistos.add(n)
                            
                            gaps = [i for i in range(1, max_num + 1) if i not in numeros_vistos]
                            retries += 1
                            
                        if gaps:
                            # FAIL-FAST: Deterministico estrito
                            set_exam_progress(bg_exam.id, f'Falha Crítica de Exatidão: A IA pulou as questões {gaps[:5]}.', -1, error_type='validation_failed')
                            bg_session.delete(bg_exam)
                            bg_session.commit()
                            return

                    set_exam_progress(bg_exam.id, 'Atrelando imagens às questões...', 85)
                    if full_pdf_path and os.path.exists(full_pdf_path):
                        orchestrator._post_process_images(full_pdf_path, questoes, bg_exam.id)
                    set_exam_progress(bg_exam.id, 'Salvando questões...', 90)
                    import re
                    import difflib
                    import json
                    final_db_questions = []

                    for q in questoes:
                        if not isinstance(q, dict):
                            continue
                        
                        raw_num = str(q.get('numero_questao', '')).strip()
                        if raw_num.lower() == 'none' or not raw_num:
                            continue
                        
                        enunciado = str(q.get('enunciado', '')).strip()
                        if not enunciado or enunciado.lower() == 'none':
                            continue
                        enunciado = enunciado.replace('\x00', '')
                        
                        opts = q.get('opcoes')
                        if not opts or (isinstance(opts, dict) and not opts):
                            opts_str = 'None'
                        else:
                            opts_str = str(opts)
                            
                        opts_len = len(opts) if isinstance(opts, dict) else 0

                        is_dup = False
                        to_remove_idx = -1
                        matched_idx = -1
                        for idx, seen in enumerate(final_db_questions):
                            seen_num = seen['num']
                            seen_en = seen['raw_en']
                            seen_opts_len = seen['opts_len']
                            
                            if raw_num and seen_num == raw_num:
                                if opts_len > seen_opts_len:
                                    to_remove_idx = idx
                                elif seen_opts_len > opts_len:
                                    is_dup = True
                                    matched_idx = idx
                                else:
                                    if len(enunciado) > len(seen_en):
                                        to_remove_idx = idx
                                    else:
                                        is_dup = True
                                        matched_idx = idx
                                break
                            elif not raw_num and not seen_num:
                                if len(enunciado) > 20 and len(seen_en) > 20 and (enunciado in seen_en or seen_en in enunciado):
                                    is_dup = True
                                    matched_idx = idx
                                    break
                                        
                        if to_remove_idx >= 0:
                            old_q = final_db_questions.pop(to_remove_idx)
                            if old_q['db_q'].images:
                                old_imgs = json.loads(old_q['db_q'].images)
                                if 'images' not in q or not q['images']:
                                    q['images'] = old_imgs
                                else:
                                    q['images'] = list(set(q['images'] + old_imgs))
                            
                        if is_dup:
                            if q.get('images'):
                                seen_db_q = final_db_questions[matched_idx]['db_q']
                                curr_imgs = json.loads(seen_db_q.images) if seen_db_q.images else []
                                new_imgs = [img for img in q['images'] if img not in curr_imgs]
                                if new_imgs:
                                    seen_db_q.images = json.dumps(curr_imgs + new_imgs, ensure_ascii=False)
                            continue
                        
                        enunciado = re.sub(r'\(?\s*(?:Correta|Gabarito|Resposta)\s*:\s*[A-E]\s*\)?', '', enunciado, flags=re.IGNORECASE).strip()
                        
                        if isinstance(opts, dict):
                            clean_opts = {k: str(v).replace('\x00', '') for k, v in opts.items() if v}
                        else:
                            clean_opts = None
                            
                        db_q = Question(
                            exam_id=bg_exam.id, 
                            statement=enunciado, 
                            options=json.dumps(clean_opts, ensure_ascii=False) if clean_opts else None, 
                            correct_answer=str(q.get('resposta', 'A')).strip().replace('\x00', '')[:10], 
                            subject=str(q.get('disciplina', 'Geral')).strip().replace('\x00', '')[:100], 
                            images=json.dumps(q.get('images'), ensure_ascii=False) if q.get('images') else None,
                            numero_questao=raw_num if raw_num else None
                        )
                        final_db_questions.append({
                            'num': raw_num,
                            'opts_len': opts_len,
                            'db_q': db_q,
                            'raw_en': enunciado
                        })
                    
                    saved_count = len(final_db_questions)
                    if saved_count == 0:
                        bg_session.delete(bg_exam)
                        bg_session.commit()
                        set_exam_progress(e_id, 'Nenhuma questão legível encontrada no PDF.', -1, error_type='no_questions')
                    else:
                        def sort_key(q_dict):
                            try:
                                n = int(re.sub(r'\D', '', str(q_dict['num'])))
                                return n if n > 0 else 999999
                            except:
                                return 999999
                        final_db_questions.sort(key=sort_key)
                        
                        bg_exam.status = 'Aprovada'
                        for fq in final_db_questions:
                            fq['db_q'].exam_id = e_id
                            bg_session.add(fq['db_q'])
                        bg_session.commit()
                        set_exam_progress(e_id, f'Concluído! {saved_count} questões extraídas.', 100)
                        
                bg_session.close()
            except Exception as e:
                import traceback
                print(f"Erro fatal no background_processing: {e}")
                traceback.print_exc()
                try:
                    bg_session.rollback()
                    set_exam_progress(e_id, f"Erro interno: {str(e)[:50]}", -1, error_type='unknown')
                    bg_exam = bg_session.query(Exam).filter_by(id=e_id).first()
                    if bg_exam:
                        bg_session.delete(bg_exam)
                        bg_session.commit()
                    bg_session.close()
                except:
                    pass
            finally:
                if temp_cleanup_dir and os.path.exists(temp_cleanup_dir):
                    try:
                        import shutil
                        shutil.rmtree(temp_cleanup_dir, ignore_errors=True)
                    except Exception as e:
                        print(f'Erro ao limpar temp_dir {temp_cleanup_dir}: {e}')
        clean_target = temp_dir if pdf_downloaded and 'temp_dir' in locals() else None
        threading.Thread(target=background_processing, args=(task_ids, exam.id, exam.source_url, clean_target), daemon=True).start()
        return (True, '')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return (False, f'Erro inesperado: {str(e)[:50]}')


