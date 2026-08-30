import os
import re
import time
import json
import asyncio
import threading
import requests
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from models.database import Session, Exam, Folder, Question, ExamCatalog
from services.pdf_pipeline import parse_exam_document
from services.diagnostics import inspect_pdf_document
from services.gabarito import parse_gabarito_from_pdf, parse_gabarito_from_text, merge_exam_with_gabarito, format_gabarito_summary
from services.search import standardize_card_title, interpret_search_query_deterministic

def set_exam_progress(exam_id: int, status_msg: str, pct: int, error_type: Optional[str] = None):
    """Atualiza o progresso do exame no banco de dados de forma thread-safe com retentativas e garantias de integridade."""
    safe_msg = (status_msg[:285] + '...') if len(status_msg) > 290 else status_msg
    safe_error = (error_type[:45] + '...') if error_type and len(error_type) > 48 else error_type
    max_retries = 5
    for attempt in range(max_retries):
        session = Session()
        try:
            exam = session.query(Exam).filter_by(id=exam_id).first()
            if exam:
                exam.progress = pct
                exam.progress_message = safe_msg
                if safe_error is not None:
                    exam.error_type = safe_error
                if pct == 100:
                    exam.status = 'Aprovada'
                elif pct == -1:
                    exam.status = 'Erro'
                session.commit()
                return
        except Exception as e:
            session.rollback()
            if attempt < max_retries - 1:
                time.sleep(0.2 * (attempt + 1))
            else:
                print(f"[Progress Error] Falha ao atualizar progresso do exame {exam_id}: {e}", flush=True)
        finally:
            session.close()

def download_pdf_file(url: str, dest_path: str, timeout: int = 30) -> bool:
    """Faz o download de um arquivo PDF com headers de navegador ou copia se for arquivo local."""
    import shutil
    
    # Suporte para arquivos locais do repositório / catálogo
    clean_local = url.replace('file:///', '').replace('file://', '')
    if os.path.exists(clean_local) and os.path.isfile(clean_local):
        try:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(clean_local, dest_path)
            return True
        except Exception as e:
            print(f"[Local Copy Error] Falha ao copiar PDF local ({url}): {e}")
            return False

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8',
        'Referer': 'https://www.pciconcursos.com.br/'
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, verify=False)
        if response.status_code == 200 and len(response.content) > 500:
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, 'wb') as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"[Download Error] Falha ao baixar PDF ({url}): {e}")
    return False


from services.crawlers import parse_html_exam, extract_pci_page_pdfs

def process_exam_async(exam_id: int, gabarito_override: Optional[str] = None):
    """
    Worker completo de ingestão e processamento assíncrono com tolerância a falhas:
    1. Download do PDF da Prova ou Resolução Determinística de PCI Concursos (0-20%)
    2. Triagem rápida com PDF Inspector (20-35%)
    3. Extração das Questões e Recorte de Diagramas (35-70%)
    4. Download e Extração do Gabarito Oficial (70-85%)
    5. Pareamento e Persistência Resiliente no Banco de Dados (85-100%)
    """
    try:
        with Session() as session:
            exam = session.query(Exam).filter_by(id=exam_id).first()
            if not exam:
                return

            user_id = exam.user_id or 1
            source_url = exam.source_url or ""
            gabarito_url = exam.gabarito_url
            clean_title = standardize_card_title(exam.title, url=source_url)
            exam.title = clean_title
            session.commit()

        set_exam_progress(exam_id, "Iniciando download da prova...", 10)

        os.makedirs('pdfs', exist_ok=True)
        ts = int(time.time())
        pdf_path = os.path.join('pdfs', f"{exam_id}_{ts}.pdf")

        # 1. Resolução Determinística e Download do Arquivo Exato
        is_html_source = False
        html_data = None

        # Se a URL for página do PCI Concursos, extrai diretamente os PDFs oficiais daquela página
        if source_url and ('pciconcursos.com.br' in source_url) and not source_url.lower().endswith('.pdf') and ('arquivo.pciconcursos.com.br' not in source_url):
            set_exam_progress(exam_id, "Obtendo PDF oficial direto do PCI Concursos...", 15)
            pci_prova, pci_gab, pci_title = extract_pci_page_pdfs(source_url)
            if pci_prova:
                source_url = pci_prova
            if pci_gab and not gabarito_url:
                gabarito_url = pci_gab
            if pci_title and (not exam.title or exam.title.startswith("Nova Prova") or exam.title.startswith("PCI -")):
                with Session() as session:
                    ex_update = session.query(Exam).filter_by(id=exam_id).first()
                    if ex_update:
                        ex_update.title = standardize_card_title(pci_title, url=source_url)
                        clean_title = ex_update.title
                        session.commit()

        if source_url and source_url.startswith('http'):
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8',
                'Referer': 'https://www.pciconcursos.com.br/'
            }
            try:
                resp = requests.get(source_url, headers=headers, timeout=30, allow_redirects=True, verify=False)
                if resp.status_code == 200:
                    if resp.content[:4] == b'%PDF':
                        with open(pdf_path, 'wb') as f:
                            f.write(resp.content)
                    elif b'<html' in resp.content[:300].lower() or b'<!doctype' in resp.content[:300].lower():
                        # É uma página HTML com questões/simulado
                        is_html_source = True
                        html_data = resp.content
            except Exception as e:
                print(f"[Download Error] {e}")

        elif source_url and os.path.exists(source_url):
            pdf_path = source_url
        elif os.path.exists(pdf_path):
            pass
        else:
            existing = [f for f in os.listdir('pdfs') if f.startswith(f"{exam_id}_") and f.endswith('.pdf')]
            if existing:
                pdf_path = os.path.join('pdfs', existing[0])

        extracted_questions = []
        gabarito_dict = {}
        answer_source = "none"

        if is_html_source and html_data:
            set_exam_progress(exam_id, "Extraindo questões da página web...", 45)
            extracted_questions = parse_html_exam(html_data, source_url)
            answer_source = "embedded_html"
        else:
            if not os.path.exists(pdf_path):
                set_exam_progress(exam_id, "Não foi possível obter o arquivo da prova.", -1, "DOWNLOAD_FAILED")
                return

            set_exam_progress(exam_id, "Inspecionando estrutura do documento...", 25)
            inspection = inspect_pdf_document(pdf_path)
            if not inspection["is_valid_exam"] and inspection["doc_type"] == "ADMINISTRATIVE_DOC":
                set_exam_progress(exam_id, f"Documento rejeitado: {inspection['reason']}", -1, "ADMINISTRATIVE_DOC")
                return

            set_exam_progress(exam_id, "Extraindo questões, alternativas e diagramas...", 45)
            try:
                extracted_questions = parse_exam_document(
                    pdf_bytes_or_path=pdf_path,
                    exam_id=exam_id,
                    extract_images=True,
                    gabarito_override=gabarito_override
                )
            except Exception as e:
                set_exam_progress(exam_id, f"Erro na extração de questões: {str(e)}", -1, "EXTRACTION_ERROR")
                return

        if not extracted_questions or len(extracted_questions) < 2:
            set_exam_progress(exam_id, "Nenhuma questão estruturada encontrada no documento.", -1, "NO_QUESTIONS_FOUND")
            return

        set_exam_progress(exam_id, f"{len(extracted_questions)} questões lidas! Processando gabarito...", 70)

        # 4. Processamento do Gabarito
        if gabarito_override:
            gabarito_dict = parse_gabarito_from_text(gabarito_override)
            answer_source = "manual_text"
        elif gabarito_url:
            gab_pdf_path = os.path.join('pdfs', f"{exam_id}_gab_{ts}.pdf")
            if gabarito_url.startswith('http'):
                if download_pdf_file(gabarito_url, gab_pdf_path):
                    gabarito_dict = parse_gabarito_from_pdf(gab_pdf_path, cargo_or_title=clean_title)
                    answer_source = "attached_pdf"
            elif os.path.exists(gabarito_url):
                gabarito_dict = parse_gabarito_from_pdf(gabarito_url, cargo_or_title=clean_title)
                answer_source = "attached_pdf"

        if not gabarito_dict and not is_html_source and os.path.exists(pdf_path):
            gabarito_dict = parse_gabarito_from_pdf(pdf_path, cargo_or_title=clean_title)
            if gabarito_dict:
                answer_source = "embedded_pdf"

        # 5. Pareamento e Persistência no Banco de Dados
        updated_questions, stats = merge_exam_with_gabarito(extracted_questions, gabarito_dict)

        set_exam_progress(exam_id, "Salvando prova e questões no banco de dados...", 88)

        db_save_success = False
        max_save_retries = 5
        for attempt in range(max_save_retries):
            try:
                with Session() as session:
                    exam = session.query(Exam).filter_by(id=exam_id).first()
                    if not exam:
                        return

                    # Criação ou associação de pasta
                    folder_name = (clean_title if clean_title else f"Pasta Prova {exam.id}")[:95].strip()
                    folder = session.query(Folder).filter_by(name=folder_name).first()
                    if not folder:
                        folder = Folder(name=folder_name, user_id=user_id)
                        session.add(folder)
                        session.flush()

                    exam.folder_id = folder.id
                    exam.has_official_answers = 1 if stats['has_official_answers'] else 0
                    exam.answer_key_source = answer_source
                    exam.gabarito_coverage = stats['coverage_pct']
                    exam.gabarito_text = format_gabarito_summary(gabarito_dict)

                    # Remove questões antigas se houver
                    session.query(Question).filter_by(exam_id=exam.id).delete()

                    def _q_sort_key(q):
                        raw = str(q.get('numero_questao', '')).strip()
                        if raw.isdigit():
                            return (0, int(raw))
                        m = re.match(r'^(\d+)', raw)
                        if m:
                            return (0, int(m.group(1)))
                        return (1, 99999)

                    sorted_questions = sorted(updated_questions, key=_q_sort_key)

                    # Insere novas questões ordenadas com sanitização completa
                    for idx, q_data in enumerate(sorted_questions, start=1):
                        raw_enunciado = q_data.get('enunciado') or f"Questão {idx}"
                        statement_clean = str(raw_enunciado).replace('\x00', '').strip()
                        if not statement_clean:
                            statement_clean = f"Questão {idx}"

                        raw_resposta = q_data.get('resposta')
                        if not raw_resposta or not str(raw_resposta).strip():
                            correct_ans = 'A'
                        else:
                            correct_ans = str(raw_resposta).replace('\x00', '').strip().upper()[:10]

                        raw_opcoes = q_data.get('opcoes')
                        if isinstance(raw_opcoes, (dict, list)):
                            try:
                                options_json = json.dumps(raw_opcoes, ensure_ascii=False, default=str)
                            except Exception:
                                options_json = json.dumps({})
                        else:
                            options_json = json.dumps({})
                        options_json = options_json.replace('\x00', '')

                        raw_subject = q_data.get('disciplina') or 'Geral'
                        subject_clean = str(raw_subject).replace('\x00', '').strip()[:100] or 'Geral'

                        raw_images = q_data.get('images')
                        if raw_images:
                            try:
                                images_json = json.dumps(raw_images, ensure_ascii=False, default=str).replace('\x00', '')
                            except Exception:
                                images_json = None
                        else:
                            images_json = None

                        num_q = str(q_data.get('numero_questao') or idx).replace('\x00', '').strip()[:50]

                        new_q = Question(
                            exam_id=exam.id,
                            statement=statement_clean,
                            options=options_json,
                            correct_answer=correct_ans,
                            subject=subject_clean,
                            images=images_json,
                            numero_questao=num_q,
                            latex_support=int(q_data.get('latex_support', 0) or 0)
                        )
                        session.add(new_q)

                    session.commit()
                    db_save_success = True

                    # Salva no catálogo de busca em sessão isolada (evita falhar o commit principal se houver chave duplicada)
                    if source_url:
                        try:
                            with Session() as cat_session:
                                cat_entry = cat_session.query(ExamCatalog).filter_by(source_url=source_url).first()
                                if not cat_entry:
                                    cat_session.add(ExamCatalog(
                                        query_key=clean_title.lower()[:100],
                                        title=exam.title[:300],
                                        source_url=source_url[:500],
                                        gabarito_url=gabarito_url[:500] if gabarito_url else None,
                                        match_score=95,
                                        source="ingested",
                                        created_at=datetime.now().isoformat()
                                    ))
                                    cat_session.commit()
                        except Exception as cat_err:
                            print(f"[ExamCatalog Save Warning] {cat_err}", flush=True)

                    break
            except Exception as db_err:
                print(f"[DB Save Attempt {attempt+1}/{max_save_retries} Error] {db_err}", flush=True)
                if attempt < max_save_retries - 1:
                    time.sleep(0.3 * (attempt + 1))
                else:
                    raise db_err

        if not db_save_success:
            set_exam_progress(exam_id, "Falha ao gravar questões no banco de dados.", -1, "DATABASE_ERROR")
            return

        set_exam_progress(
            exam_id,
            f"Prova concluída com sucesso! ({len(updated_questions)} questões, {stats['coverage_pct']}% gabarito)",
            100
        )
    except Exception as unexpected_err:
        import traceback
        traceback.print_exc()
        set_exam_progress(exam_id, f"Erro inesperado: {str(unexpected_err)[:200]}", -1, "INTERNAL_ERROR")

def dispatch_async_exam_task(exam_id: int, gabarito_override: Optional[str] = None):
    """Inicia a execução da tarefa em uma thread dedicada não-bloqueante."""
    worker_thread = threading.Thread(
        target=process_exam_async,
        args=(exam_id, gabarito_override),
        daemon=True
    )
    worker_thread.start()
    return worker_thread
