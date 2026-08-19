import os, json, sys, sqlite3, subprocess, re, time
from flask import request, jsonify
from models import Session, Exam, Question, ExamAttempt, AppConfig, ExamCatalog, Folder
from bs4 import BeautifulSoup
import requests
import datetime
import fitz
import threading
import concurrent.futures
from services.pdf_parser import parse_exam_pdf_deterministic
from services.pdf_inspector import inspect_pdf_document
from services.gabarito_service import parse_gabarito_from_text, parse_gabarito_from_pdf, merge_exam_with_gabarito, format_gabarito_summary

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

def interpret_search_query_deterministic(query):
    """Interpreta termos de busca (órgão, banca, ano, cargo) com análise léxica determinística (Sem IA)."""
    query_clean = query.strip()
    data = {
        "orgao": "",
        "banca": "",
        "ano": "",
        "cargo": "",
        "local": "",
        "query_otimizada": query_clean
    }
    
    # 1. Identificar Ano (1990 - 2030)
    m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', query_clean)
    if m_ano:
        data["ano"] = m_ano.group(1)
        
    # 2. Identificar Bancas Conhecidas
    known_bancas = [
        "cesgranrio", "cebraspe", "cespe", "fgv", "fcc", "vunesp", "quadrix",
        "ibfc", "idecan", "instituto aocp", "aocp", "idcap", "selecon",
        "consulplan", "instituto mais", "avalia", "fundatec", "faepesul", "fundep"
    ]
    query_lower = query_clean.lower()
    for b in known_bancas:
        if re.search(rf'\b{re.escape(b)}\b', query_lower):
            data["banca"] = b.upper()
            break
            
    # 3. Identificar Órgãos Comuns
    known_orgaos = [
        "petrobras", "transpetro", "caixa", "banco do brasil", "bb", "correios", "inss",
        "receita federal", "ibge", "prf", "pf", "policia federal", "policia rodoviaria",
        "tj", "tjrj", "tjsp", "tjmg", "tjdft", "tre", "trt", "tst", "stj", "stf", "tcu",
        "anvisa", "anatel", "aneel", "ancine", "marinha", "exercito", "aeronautica",
        "prefeitura", "governo do estado", "camara", "senado", "spprev"
    ]
    for org in known_orgaos:
        if re.search(rf'\b{re.escape(org)}\b', query_lower):
            data["orgao"] = org.upper()
            break
            
    tokens = [t for t in query_clean.split() if t.lower() not in ['prova', 'provas', 'gabarito', 'pdf', 'download', 'de', 'do', 'da', 'para', 'em']]
    data["query_otimizada"] = " ".join(tokens) + " prova concurso pdf"
    return data

def search_exams():
    query = request.args.get('q', '').strip()
    sources_param = request.args.get('sources', '')
    refresh_param = request.args.get('refresh', '').lower() in ['1', 'true', 'yes']
    from flask_login import current_user
    
    if not query:
        return jsonify([])
        
    if 'qconcursos.com' in query:
        return jsonify([{'title': 'Extração Direta QConcursos', 'url': query, 'gabarito_url': None, 'source': 'QConcursos Direct'}])

    query_clean_lower = query.lower()
    
    # 1. Checagem no Catálogo de Cache (resposta em < 5ms)
    if not refresh_param:
        session = Session()
        try:
            cached_entries = session.query(ExamCatalog).filter(
                (ExamCatalog.query_key == query_clean_lower) | 
                (ExamCatalog.title.ilike(f"%{query_clean_lower}%"))
            ).order_by(ExamCatalog.match_score.desc()).limit(15).all()
            
            if cached_entries and len(cached_entries) >= 2:
                print(f"[Exam Catalog] {len(cached_entries)} provas recuperadas instantaneamente do cache.", flush=True)
                current_urls = {c.source_url for c in cached_entries}
                for c in cached_entries:
                    existing = session.query(Exam).filter_by(user_id=current_user.id, source_url=c.source_url).first()
                    if not existing:
                        session.add(Exam(
                            title=c.title,
                            source_url=c.source_url,
                            gabarito_url=c.gabarito_url,
                            status='Pendente',
                            match_score=c.match_score,
                            user_id=current_user.id
                        ))
                    else:
                        existing.match_score = c.match_score
                        if c.gabarito_url and not existing.gabarito_url:
                            existing.gabarito_url = c.gabarito_url
                session.commit()
                
                pending_exams = session.query(Exam).filter(Exam.user_id == current_user.id, Exam.status != 'Aprovada', Exam.source_url.in_(current_urls)).all()
                results = [{
                    'id': e.id,
                    'title': e.title,
                    'url': e.source_url.split('?v=')[0],
                    'gabarito_url': e.gabarito_url,
                    'has_gabarito_link': bool(e.gabarito_url),
                    'match_score': e.match_score or 0,
                    'status': e.status
                } for e in pending_exams]
                return jsonify(results)
        except Exception as err:
            print(f"[Exam Catalog Cache Error] {err}")
        finally:
            session.close()

    # 2. Execução dos Scrapers Concorrentes
    active_sources = [s.strip().lower() for s in sources_param.split(',')] if sources_param else ['web', 'idcap', 'pci', 'qconcursos']
    data = interpret_search_query_deterministic(query)
    interpreted_query = data.get('query_otimizada', query)
    
    banca_identificada = data.get('banca', '').strip().lower()
    scrapers_bancas_especificas = ['idcap']
    scraper_explicito = None
    mapa_scrapers = {'idcap': ['idcap', 'id cap'], 'pci': ['pci', 'pciconcurso', 'pciconcursos', 'pci concursos', 'pci concurso']}
    for (scraper_key, terms) in mapa_scrapers.items():
        if any((term in query_clean_lower for term in terms)):
            scraper_explicito = scraper_key
            break
            
    if scraper_explicito:
        for sb in ['idcap', 'pci']:
            if sb != scraper_explicito and sb in active_sources:
                active_sources.remove(sb)
    elif banca_identificada and banca_identificada != 'n/a':
        for sb in scrapers_bancas_especificas:
            if sb not in banca_identificada and sb in active_sources:
                active_sources.remove(sb)

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
            futures.append(executor.submit(run_scraper, _search_pdfs_web, interpreted_query, ''))
        if 'idcap' in active_sources:
            futures.append(executor.submit(run_scraper, _scrape_idcap_pdfs, query))
        if 'pci' in active_sources:
            futures.append(executor.submit(run_scraper, _scrape_pci_pdfs, query, data))
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                all_results.extend(res)

    def standardize_title(t, nlp_data, url=''):
        ano_original = ''
        m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', t)
        if not m_ano and url:
            m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', url)
        if m_ano:
            ano_original = m_ano.group(1)
        t = re.sub(r'[—–]', '-', t)
        t = re.sub(r'^(provas para download|prova para download|provas?)\s*-\s*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'^(IDCAP|IDECAN|PCI|QConcursos)\s*-\s*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'(processo seletivo(\s*privado|\s*priv|\s*pri)*)+', '', t, flags=re.IGNORECASE)
        t = re.sub(r'(concurso\s*p[uú]blico.*?)(para|-|\s|$)', '', t, flags=re.IGNORECASE)
        t = re.sub(r'psp\s*\d+/\d+\s*-\s*ogmo/s\s*-\s*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'\d{3}/\d{4}\s*-\s*', '', t)
        t = re.sub(r'(?i)\(?(edital|edt\.?)\s*(cbmmg)?\s*(nº)?\s*\d+([./]\d+)?(.*?de\s*\d+\s*de\s*[a-zç]+\s*de\s*\d+)?\)?', '', t)
        t = re.sub(r'\(\s*-\s*\)|\(\s*\)', '', t)
        t = t.strip(' -')
        t = re.sub(r'\s*-\s*-\s*', ' - ', t)
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
            orgao = re.sub(r'^(pri|priv|privado|processo\s*seletivo.*)$', '', orgao, flags=re.IGNORECASE).strip()
        if not orgao or str(orgao).lower() in ['n/a', '', 'null']:
            orgao = ''
        local_str = f' - {local}' if local and str(local).lower() not in ['n/a', '', 'null'] and local.lower() not in orgao.lower() else ''
        cargo = t.strip() or 'Geral / Conhecimentos Básicos'
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
                p_clean = re.sub(r'[^\w]', '', p).lower()
                last_clean = re.sub(r'[^\w]', '', dedup_parts[-1]).lower()
                if not (p_clean and last_clean and (p_clean == last_clean or p_clean in last_clean or last_clean in p_clean)):
                    dedup_parts.append(p)
        return f"{prefix}{' - '.join(dedup_parts)}"

    seen_urls = set()
    pdf_results = []
    for r in all_results:
        url = r.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            r['title'] = standardize_title(r.get('title', ''), data, url)
            pdf_results.append(r)

    # 3. Salvar no Banco de Dados (ExamCatalog + Exam do Usuário)
    session = Session()
    try:
        # Popula o catálogo de cache para futuras buscas
        for res in pdf_results:
            url_clean = res['url']
            cat_item = session.query(ExamCatalog).filter_by(source_url=url_clean).first()
            if not cat_item:
                session.add(ExamCatalog(
                    query_key=query_clean_lower,
                    title=res['title'],
                    source_url=url_clean,
                    gabarito_url=res.get('gabarito_url'),
                    match_score=res.get('match_score', 50),
                    source=res.get('source', 'web'),
                    created_at=datetime.datetime.now().isoformat()
                ))
            elif res.get('gabarito_url') and not cat_item.gabarito_url:
                cat_item.gabarito_url = res.get('gabarito_url')
        session.commit()

        # Atualiza a fila de pendentes do usuário
        current_urls = {r['url'] for r in pdf_results}
        old_pending = session.query(Exam).filter_by(user_id=current_user.id, status='Pendente').all()
        for old in old_pending:
            if old.source_url not in current_urls:
                session.delete(old)
        session.commit()

        for res in pdf_results:
            m_score = res.get('match_score', 0)
            existing = session.query(Exam).filter_by(user_id=current_user.id, source_url=res['url']).first()
            if not existing:
                session.add(Exam(
                    title=res['title'],
                    source_url=res['url'],
                    gabarito_url=res.get('gabarito_url'),
                    status='Pendente',
                    match_score=m_score,
                    user_id=current_user.id
                ))
            else:
                existing.match_score = m_score
                if res.get('gabarito_url') and not existing.gabarito_url:
                    existing.gabarito_url = res.get('gabarito_url')
        session.commit()

        pending_exams = session.query(Exam).filter(Exam.user_id == current_user.id, Exam.status != 'Aprovada', Exam.source_url.in_(current_urls)).all()
        results = [{
            'id': e.id,
            'title': e.title,
            'url': e.source_url.split('?v=')[0],
            'gabarito_url': e.gabarito_url,
            'has_gabarito_link': bool(e.gabarito_url),
            'match_score': e.match_score or 0,
            'status': e.status
        } for e in pending_exams]
        return jsonify(results)
    finally:
        session.close()

def _safe_delete_exam(exam_id):
    """Exclui com segurança um exame e suas dependências usando uma sessão dedicada e rápida."""
    try:
        with Session() as s:
            s.query(Question).filter_by(exam_id=exam_id).delete()
            s.query(ExamAttempt).filter_by(exam_id=exam_id).delete()
            e = s.query(Exam).filter_by(id=exam_id).first()
            if e:
                s.delete(e)
            s.commit()
    except Exception as err:
        print(f"Erro ao deletar exame {exam_id}: {err}", flush=True)

def _download_pdf_bytes(url, exam_id=None):
    """Baixa bytes de PDF via requests ou Playwright de forma resiliente."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'application/pdf,*/*'}
    
    # 1. Tentativa Requests direto
    try:
        import warnings
        from urllib3.exceptions import InsecureRequestWarning
        warnings.filterwarnings('ignore', category=InsecureRequestWarning)
        
        req_session = requests.Session()
        req_session.headers.update(headers)
        url_to_download = url
        
        if 'pciconcursos.com.br/provas/download/' in url_to_download:
            res_pci = req_session.get(url_to_download, timeout=15, verify=False)
            soup_pci = BeautifulSoup(res_pci.text, 'html.parser')
            for link in soup_pci.select('a'):
                arq = link.get('data-arquivo')
                tok = link.get('data-code')
                acao = link.get('data-acao')
                if arq and tok and (acao == 'baixar') and ('gabarito' not in arq.lower()):
                    url_to_download = f'https://www.pciconcursos.com.br/download/{arq}?token={tok}'
                    req_session.headers.update({'Referer': url})
                    break
        r = req_session.get(url_to_download, timeout=30, allow_redirects=True, verify=False)
        if r.status_code == 200 and (r.headers.get('Content-Type', '').startswith('application/pdf') or r.content[:4] == b'%PDF'):
            return r.content
    except Exception:
        pass

    # 2. Tentativa Playwright
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=headers['User-Agent'], accept_downloads=True, ignore_https_errors=True)
            page = context.new_page()
            
            if 'pciconcursos.com.br/provas/download/' in url:
                page.goto(url, timeout=20000)
                loc = page.locator("a.prova-pdf-link[data-acao='baixar']")
                for i in range(loc.count()):
                    arq = loc.nth(i).get_attribute('data-arquivo')
                    tok = loc.nth(i).get_attribute('data-code')
                    if arq and tok and ('gabarito' not in arq.lower()):
                        link = f'https://www.pciconcursos.com.br/download/{arq}?token={tok}'
                        try:
                            with page.expect_download(timeout=10000) as dl_info:
                                page.goto(link)
                            dl = dl_info.value
                            import tempfile
                            temp_path = os.path.join(tempfile.gettempdir(), f'pci_temp_{exam_id or 0}_{i}.pdf')
                            dl.save_as(temp_path)
                            with open(temp_path, 'rb') as f:
                                body = f.read()
                            if body[:4] == b'%PDF':
                                browser.close()
                                return body
                        except Exception:
                            pass
            else:
                r = context.request.get(url, headers={'Referer': url})
                if r.status == 200 and r.body()[:4] == b'%PDF':
                    browser.close()
                    return r.body()
            browser.close()
    except Exception:
        pass

    return None

def _real_scrape_exam(session, exam, gabarito_override=None):
    """
    Executa a extração determinística de questões, triagem de documento e pareamento de gabarito.
    """
    exam_id = exam.id
    source_url = exam.source_url or ''
    gabarito_url = exam.gabarito_url
    gabarito_text_input = exam.gabarito_text or gabarito_override
    pdf_override = getattr(exam, 'pdf_path', None)
    
    with Session() as s:
        s.query(Question).filter_by(exam_id=exam_id).delete()
        db_exam = s.query(Exam).filter_by(id=exam_id).first()
        if db_exam:
            db_exam.status = 'Processando'
            db_exam.progress = 10
            db_exam.progress_message = 'Iniciando extração e triagem de documentos...'
        s.commit()
    
    # Suporte ao QConcursos
    if source_url and 'qconcursos.com' in source_url and '.pdf' not in source_url.lower():
        def qc_bg_task(e_id, s_url):
            set_exam_progress(e_id, 'Extraindo questões via QConcursos...', 20)
            import subprocess, sys
            result = subprocess.run([sys.executable, 'qc_scraper.py', str(e_id), s_url], capture_output=True, text=True)
            if result.returncode == 0:
                set_exam_progress(e_id, 'Processamento concluído!', 100)
            else:
                err_msg = (result.stdout + result.stderr)[:100]
                set_exam_progress(e_id, f'Erro QC: {err_msg}', -1)
                _safe_delete_exam(e_id)
        threading.Thread(target=qc_bg_task, args=(exam_id, source_url), daemon=True).start()
        return (True, 'Scraper do QConcursos iniciado.')

    if not source_url and not pdf_override:
        return (False, 'URL ou arquivo da prova não informado.')

    def process_pdf_in_background(e_id, s_url, g_url, g_text, pdf_path_override=None):
        try:
            set_exam_progress(e_id, 'Baixando PDF da prova...', 20)
            pdf_bytes = None
            
            if pdf_path_override and os.path.exists(pdf_path_override):
                with open(pdf_path_override, 'rb') as f:
                    pdf_bytes = f.read()
            else:
                import glob
                local_matches = glob.glob(f'pdfs/{e_id}_*.pdf')
                if local_matches and os.path.exists(local_matches[0]) and (os.path.getsize(local_matches[0]) > 1000):
                    with open(local_matches[0], 'rb') as f:
                        pdf_bytes = f.read()
                        
            if not pdf_bytes and s_url:
                pdf_bytes = _download_pdf_bytes(s_url, e_id)

            if not pdf_bytes or pdf_bytes[:4] != b'%PDF':
                set_exam_progress(e_id, 'Não foi possível baixar o PDF. Tente enviar o arquivo diretamente.', -1, error_type='download_blocked')
                _safe_delete_exam(e_id)
                return

            # 1. Triagem e Inspeção Rápida de Documentos (PDF Inspector)
            set_exam_progress(e_id, 'Inspecionando estrutura do documento...', 35)
            inspection = inspect_pdf_document(pdf_bytes)
            
            if inspection['doc_type'] == 'ADMINISTRATIVE_DOC':
                set_exam_progress(e_id, f"Documento inválido: {inspection['reason']}", -1, error_type='administrative_doc')
                _safe_delete_exam(e_id)
                return
            elif inspection['doc_type'] == 'ANSWER_KEY_ONLY':
                set_exam_progress(e_id, "Este arquivo é apenas uma folha de gabarito. Por favor, envie o caderno de questões da prova.", -1, error_type='gabarito_only')
                _safe_delete_exam(e_id)
                return

            # 2. Extração Determinística de Questões e Imagens
            set_exam_progress(e_id, 'Extraindo questões e diagramas do PDF...', 55)
            parsed_questions = parse_exam_pdf_deterministic(pdf_bytes, exam_id=e_id)
            
            if not parsed_questions:
                set_exam_progress(e_id, 'Nenhuma questão legível encontrada no texto do PDF.', -1, error_type='no_questions')
                _safe_delete_exam(e_id)
                return

            # 3. Obtenção e Processamento de Gabarito Oficial
            set_exam_progress(e_id, 'Mapeando e pareando gabarito oficial...', 75)
            external_gabarito = {}
            answer_source = 'none'

            # A. Texto colado pelo usuário
            if g_text:
                external_gabarito = parse_gabarito_from_text(g_text)
                if external_gabarito:
                    answer_source = 'manual_text'

            # B. PDF de gabarito avulso via URL ou arquivo
            if not external_gabarito and g_url:
                gab_bytes = None
                if os.path.exists(g_url):
                    with open(g_url, 'rb') as f:
                        gab_bytes = f.read()
                else:
                    gab_bytes = _download_pdf_bytes(g_url, e_id)
                    
                if gab_bytes:
                    external_gabarito = parse_gabarito_from_pdf(gab_bytes)
                    if external_gabarito:
                        answer_source = 'attached_pdf'

            # C. Injeção e pareamento
            updated_questions, stats = merge_exam_with_gabarito(parsed_questions, external_gabarito)
            
            if stats['has_official_answers'] and answer_source == 'none':
                answer_source = 'embedded'

            # 4. Persistência no Banco de Dados
            set_exam_progress(e_id, 'Salvando questões e gabarito no banco...', 90)
            
            with Session() as s:
                target_exam = s.query(Exam).filter_by(id=e_id).first()
                if target_exam:
                    target_exam.status = 'Aprovada'
                    target_exam.has_official_answers = 1 if stats['has_official_answers'] else 0
                    target_exam.answer_key_source = answer_source
                    target_exam.gabarito_coverage = stats['coverage_pct']
                    if external_gabarito:
                        target_exam.gabarito_text = format_gabarito_summary(external_gabarito)
                    
                for q in updated_questions:
                    db_q = Question(
                        exam_id=e_id,
                        statement=q['enunciado'],
                        options=json.dumps(q['opcoes'], ensure_ascii=False) if q.get('opcoes') else None,
                        correct_answer=q.get('resposta', 'A'),
                        subject=q.get('disciplina', 'Geral'),
                        images=json.dumps(q['images'], ensure_ascii=False) if q.get('images') else None,
                        numero_questao=q.get('numero_questao')
                    )
                    s.add(db_q)
                s.commit()
                
            msg_gabarito = "com Gabarito Oficial" if stats['has_official_answers'] else "sem gabarito oficial (anexável a qualquer momento)"
            set_exam_progress(e_id, f'Concluído! {len(updated_questions)} questões extraídas {msg_gabarito}.', 100)
            
        except Exception as err:
            import traceback
            print(f"Erro fatal na extração do exame {e_id}: {err}", flush=True)
            traceback.print_exc()
            set_exam_progress(e_id, f"Erro interno: {str(err)[:50]}", -1, error_type='unknown')
            _safe_delete_exam(e_id)

    pdf_override = exam.pdf_path if hasattr(exam, 'pdf_path') else None
    threading.Thread(
        target=process_pdf_in_background,
        args=(exam_id, source_url, gabarito_url, gabarito_text_input, pdf_override),
        daemon=True
    ).start()
    return (True, 'Processamento determinístico iniciado.')
