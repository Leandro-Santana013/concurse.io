from flask import Blueprint, request, jsonify, render_template, url_for, redirect, current_app, send_file, session
import os, json, threading, shutil
from flask_login import login_user, login_required, logout_user, current_user
from app_core.orchestrator import orchestrator
from models import Session, User, Folder, Exam, Question, AppConfig, ExamAttempt
from app_core.extensions import login_manager, oauth
import datetime
import requests

exam_bp = Blueprint('exam', __name__)

@exam_bp.route('/api/exams/<int:exam_id>/progress', methods=['GET'])
def get_exam_progress_route(exam_id):
    from app import get_exam_progress
    prog = get_exam_progress(exam_id)
    if prog.get('progress', 0) < 100 and prog.get('progress', 0) != -1:
        session = Session()
        exam = session.query(Exam).filter_by(id=exam_id).first()
        if exam and exam.status == 'Aprovada':
            prog['progress'] = 100
            prog['status'] = 'Prova já processada e disponível.'
        elif exam and exam.status == 'Erro':
            prog['progress'] = -1
            prog['status'] = 'Erro no processamento.'
        session.close()
    return jsonify(prog)

@exam_bp.route('/api/exams/<int:exam_id>/progress_clear', methods=['POST'])
def clear_exam_progress(exam_id):
    from app import progress_lock, exam_progress
    with progress_lock:
        if exam_id in exam_progress:
            del exam_progress[exam_id]
    return jsonify({'success': True})

@exam_bp.route('/api/downloads', methods=['GET'])
def get_active_downloads():
    from app import progress_lock, exam_progress
    session = Session()
    results = []
    with progress_lock:
        current_progs = dict(exam_progress)
    for (exam_id, prog) in current_progs.items():
        exam = session.query(Exam).filter_by(user_id=current_user.id).filter_by(id=exam_id).first()
        title = exam.title if exam else f'Prova {exam_id}'
        results.append({'id': exam_id, 'title': title, 'url': exam.source_url if exam else '', 'status': prog.get('status', ''), 'progress': prog.get('progress', 0), 'error_type': prog.get('error_type', None), 'total_chunks': prog.get('total_chunks', 0), 'done_chunks': prog.get('done_chunks', 0)})
    session.close()
    results.sort(key=lambda x: 0 if 0 <= x['progress'] < 100 else 1 if x['progress'] == -1 else 2)
    return jsonify(results)

@exam_bp.route('/api/exams/<int:exam_id>/manual_pdf', methods=['POST'])
def manual_pdf(exam_id):
    from datetime import datetime
    session = Session()
    exam = session.query(Exam).filter_by(user_id=current_user.id).filter_by(id=exam_id).first()
    if not exam:
        session.close()
        return (jsonify({'error': 'Prova não encontrada.'}), 404)

    os.makedirs('pdfs', exist_ok=True)
    filename = f'{exam_id}_{int(datetime.now().timestamp())}.pdf'
    filepath = os.path.join('pdfs', filename)

    if 'pdf_file' in request.files:
        file = request.files['pdf_file']
        if file.filename == '':
            session.close()
            return jsonify({'error': 'Nenhum arquivo selecionado.'}), 400
        file.save(filepath)
    else:
        # Tenta pegar url do JSON ou do Form
        data = request.json if request.is_json else request.form
        pdf_url = data.get('pdf_url')
        if not pdf_url:
            session.close()
            return (jsonify({'error': 'Nenhuma URL ou arquivo fornecido.'}), 400)
            
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.pciconcursos.com.br/',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'
            }
            r = requests.get(pdf_url, headers=headers, verify=False, allow_redirects=True, timeout=30)
            if r.status_code != 200:
                session.close()
                return (jsonify({'error': f'Falha ao baixar PDF (Status: {r.status_code}). Certifique-se de que o link é o link direto do arquivo.'}), 400)
            with open(filepath, 'wb') as f:
                f.write(r.content)
        except Exception as e:
            session.close()
            return (jsonify({'error': f'Erro ao baixar URL: {str(e)}'}), 400)
            
    # Independente de URL ou Upload, o arquivo já foi salvo em filepath.
    exam.pdf_path = filepath
    exam.status = 'Aprovada'
    clean_title = exam.title.replace('Prova - ', '').split('.')[0][:40]
    folder_name = clean_title if clean_title else f'Pasta Prova {exam.id}'
    folder = session.query(Folder).filter_by(user_id=current_user.id).filter_by(name=folder_name).first()
    if not folder:
        folder = Folder(name=folder_name, user_id=current_user.id)
        session.add(folder)
        session.flush()
    exam.folder_id = folder.id
    from app import set_exam_progress
    set_exam_progress(exam.id, 'Iniciando processamento (manual)...', 5)
    try:
        from services.exam_service import _real_scrape_exam
        (success, error_msg) = _real_scrape_exam(session, exam)
    except Exception as e:
        (success, error_msg) = (False, f'Erro interno: {str(e)}')
    if not success:
        exam.status = 'Pendente'
        session.commit()
        session.close()
        return (jsonify({'error': error_msg}), 400)
    session.commit()
    session.close()
    return jsonify({'message': 'Download manual concluído e processamento iniciado.'})

@exam_bp.route('/api/exams/<int:exam_id>/status', methods=['POST'])
def update_exam_status(exam_id):
    data = request.json
    new_status = data.get('status')
    session = Session()
    exam = session.query(Exam).filter_by(user_id=current_user.id).filter_by(id=exam_id).first()
    if not exam:
        session.close()
        return jsonify({'success': False, 'error': 'Exam not found'})
    if new_status == 'Negada':
        session.delete(exam)
        session.commit()
        session.close()
        return jsonify({'success': True, 'status': 'Negada'})
    if new_status == 'Aprovada':
        if exam.status == 'Aprovada':
            session.close()
            return jsonify({'success': True, 'status': 'Aprovada'})
        existing_global = session.query(Exam).filter(Exam.source_url == exam.source_url, Exam.status == 'Aprovada', Exam.id != exam.id).first()
        if existing_global:
            global_questions = session.query(Question).filter_by(exam_id=existing_global.id).all()
            if len(global_questions) > 0:
                exam.status = 'Aprovada'
                clean_title = exam.title.replace('Prova - ', '').split('.')[0][:40]
                folder_name = clean_title if clean_title else f'Pasta Prova {exam.id}'
                folder = session.query(Folder).filter_by(user_id=current_user.id).filter_by(name=folder_name).first()
                if not folder:
                    folder = Folder(name=folder_name, user_id=current_user.id)
                    session.add(folder)
                    session.flush()
                exam.folder_id = folder.id
                for q in global_questions:
                    new_q = Question(exam_id=exam.id, statement=q.statement, options=q.options, correct_answer=q.correct_answer, subject=q.subject, images=q.images)
                    session.add(new_q)
                session.commit()
                from app import set_exam_progress
                set_exam_progress(exam.id, 'Prova localizada no banco central. Copiada instantaneamente!', 100)
                session.close()
                return jsonify({'success': True, 'status': 'Aprovada'})
        exam.status = new_status
        clean_title = exam.title.replace('Prova - ', '').split('.')[0][:40]
        folder_name = clean_title if clean_title else f'Pasta Prova {exam.id}'
        folder = session.query(Folder).filter_by(user_id=current_user.id).filter_by(name=folder_name).first()
        if not folder:
            folder = Folder(name=folder_name, user_id=current_user.id)
            session.add(folder)
            session.flush()
        exam.folder_id = folder.id
        from app import set_exam_progress
        set_exam_progress(exam_id, 'Iniciando processamento...', 5)

        def bg_scrape(e_id):
            bg_session = Session()
            bg_exam = bg_session.query(Exam).filter_by(id=e_id).first()
            if bg_exam:
                try:
                    from services.exam_service import _real_scrape_exam
                    _real_scrape_exam(bg_session, bg_exam)
                except Exception as e:
                    print(f'Erro no scrape background: {e}')
            bg_session.close()
        threading.Thread(target=bg_scrape, args=(exam.id,), daemon=True).start()
        exam.status = 'Aprovada'
        session.commit()
        result = {'success': True, 'status': exam.status}
    else:
        exam.status = new_status
        session.commit()
        result = {'success': True, 'status': exam.status}
    session.close()
    return jsonify(result)

@exam_bp.route('/api/generate_exam', methods=['POST'])
def generate_custom_exam():
    """Gera um simulado aleatório com base na quantidade pedida."""
    data = request.json or {}
    count = min(int(data.get('count', 20)), 100)
    session = Session()
    from sqlalchemy.sql.expression import func
    questions = session.query(Question).order_by(func.random()).limit(count).all()
    q_data = [{'id': q.id, 'statement': q.statement, 'options': json.loads(q.options) if q.options else None, 'correct_answer': q.correct_answer, 'subject': q.subject or 'Geral'} for q in questions]
    session.close()
    return jsonify({'id': 'custom', 'title': f'Simulado Personalizado ({len(questions)} questões)', 'questions': q_data})

@exam_bp.route('/api/orchestrator/status', methods=['GET'])
def get_orchestrator_status():
    return jsonify(orchestrator.get_status())

@exam_bp.route('/api/folders', methods=['GET'])
def get_folders():
    session = Session()
    folders = session.query(Folder).filter_by(user_id=current_user.id).all()
    result = []
    for f in folders:
        exams_data = []
        for e in f.exams:
            if e.status != 'Aprovada':
                continue
            attempts = session.query(ExamAttempt).filter_by(user_id=current_user.id).filter_by(exam_id=e.id).order_by(ExamAttempt.id.desc()).all()
            best_pct = max((a.percentage for a in attempts), default=None)
            last_pct = attempts[0].percentage if attempts else None
            attempt_count = len(attempts)
            exams_data.append({'id': e.id, 'title': e.title, 'best_score': round(best_pct, 1) if best_pct is not None else None, 'last_score': round(last_pct, 1) if last_pct is not None else None, 'attempt_count': attempt_count})
        if exams_data:
            result.append({'id': f.id, 'name': f.name, 'exams': exams_data})
    orphan_exams = session.query(Exam).filter_by(user_id=current_user.id).filter_by(folder_id=None).all()
    orphan_data = []
    for e in orphan_exams:
        if e.status != 'Aprovada':
            continue
            
        attempts = session.query(ExamAttempt).filter_by(user_id=current_user.id).filter_by(exam_id=e.id).order_by(ExamAttempt.id.desc()).all()
        best_pct = max((a.percentage for a in attempts), default=None)
        last_pct = attempts[0].percentage if attempts else None
        attempt_count = len(attempts)
        orphan_data.append({'id': e.id, 'title': e.title, 'best_score': round(best_pct, 1) if best_pct is not None else None, 'last_score': round(last_pct, 1) if last_pct is not None else None, 'attempt_count': attempt_count})
    if orphan_data:
        result.append({'id': 'avulsas', 'name': 'Provas Avulsas', 'exams': orphan_data})
    session.close()
    return jsonify(result)

@exam_bp.route('/api/exams/<int:exam_id>', methods=['GET'])
def get_exam(exam_id):
    session = Session()
    exam = session.query(Exam).filter_by(user_id=current_user.id).filter_by(id=exam_id).first()
    if not exam:
        session.close()
        return (jsonify({'error': 'Exam not found'}), 404)
    questions = []
    for q in exam.questions:
        options_dict = json.loads(q.options) if q.options else None
        images_list = json.loads(q.images) if q.images else []
        questions.append({'id': q.id, 'statement': q.statement, 'options': options_dict, 'correct_answer': q.correct_answer, 'subject': getattr(q, 'subject', 'Geral') or 'Geral', 'images': images_list})
    result = {'id': exam.id, 'title': exam.title, 'questions': questions}
    session.close()
    return jsonify(result)

@exam_bp.route('/api/exams/<int:exam_id>', methods=['DELETE'])
def delete_exam(exam_id):
    session = Session()
    exam = session.query(Exam).filter_by(user_id=current_user.id).filter_by(id=exam_id).first()
    if not exam:
        session.close()
        return (jsonify({'success': False}), 404)
    folder_id = exam.folder_id
    session.delete(exam)
    if folder_id:
        session.flush()
        remaining = session.query(Exam).filter_by(user_id=current_user.id).filter_by(folder_id=folder_id).count()
        if remaining == 0:
            folder = session.query(Folder).filter_by(user_id=current_user.id).filter_by(id=folder_id, user_id=current_user.id).first()
            if folder:
                session.delete(folder)
    session.commit()
    session.close()
    return jsonify({'success': True})

@exam_bp.route('/api/exams/<int:exam_id>/submit', methods=['POST'])
def submit_exam_score(exam_id):
    """Salva o resultado de uma tentativa da prova."""
    data = request.json
    session = Session()
    exam = session.query(Exam).filter_by(user_id=current_user.id).filter_by(id=exam_id, user_id=current_user.id).first()
    if not exam:
        session.close()
        return (jsonify({'error': 'Prova não encontrada.'}), 404)
    from datetime import datetime
    attempt = ExamAttempt(exam_id=exam_id, score=data.get('score', 0), total=data.get('total', 0), percentage=data.get('percentage', 0.0), elapsed_seconds=data.get('elapsed_seconds', 0), answers_json=json.dumps(data.get('answers', {}), ensure_ascii=False), created_at=datetime.now().isoformat(), user_id=current_user.id)
    session.add(attempt)
    session.commit()
    attempt_id = attempt.id
    session.close()
    return jsonify({'success': True, 'attempt_id': attempt_id})

@exam_bp.route('/api/exams/<int:exam_id>/history', methods=['GET'])
def get_exam_history(exam_id):
    """Retorna o histórico de tentativas de uma prova."""
    session = Session()
    attempts = session.query(ExamAttempt).filter_by(user_id=current_user.id).filter_by(exam_id=exam_id).order_by(ExamAttempt.id.desc()).all()
    result = [{'id': a.id, 'score': a.score, 'total': a.total, 'percentage': round(a.percentage, 1), 'elapsed_seconds': a.elapsed_seconds, 'created_at': a.created_at} for a in attempts]
    session.close()
    return jsonify(result)

@exam_bp.route('/api/explain/<int:question_id>', methods=['POST'])
def explain_question(question_id):
    """Usa o Gemini para explicar o gabarito da questão."""
    session = Session()
    q = session.query(Question).filter_by(id=question_id).first()
    if not q:
        session.close()
        return (jsonify({'error': 'Questão não encontrada'}), 404)
    data = request.json or {}
    user_answer = data.get('user_answer', 'Nenhuma')
    prompt = f'\n    Atue como um professor de cursinho focado em concursos públicos.\n    Foi apresentada a seguinte questão de concurso:\n    \n    Enunciado: {q.statement}\n    \n    Alternativas disponíveis (se houver):\n    {q.options}\n    \n    O gabarito oficial é: {q.correct_answer}\n    O aluno marcou: {user_answer}\n    \n    Por favor, explique de forma didática e direta (em até 3 parágrafos curtos):\n    1. Por que a alternativa {q.correct_answer} está correta (qual a base legal/teórica)?\n    2. Por que a alternativa que o aluno marcou ({user_answer}) está errada (se ele tiver marcado uma diferente da correta).\n    '
    session.close()
    try:
        import openai
        import app_core.orchestrator as orch_module
        from app_core.orchestrator import orchestrator
        client = orchestrator.api_key_manager.get_current_client()
        if not client:
            return jsonify({'error': 'API Key não configurada.'}), 500
        model_name = orchestrator.api_key_manager.get_current_model_name()
        response = client.chat.completions.create(model=model_name, messages=[{'role': 'user', 'content': prompt}])
        explanation = response.choices[0].message.content
        return jsonify({'explanation': explanation})
    except Exception as e:
        return (jsonify({'error': f'Erro ao gerar explicação: {str(e)}'}), 500)

from services.exam_service import search_exams
exam_bp.add_url_rule('/api/search', view_func=search_exams, methods=['GET'])

@exam_bp.route('/api/qc/login', methods=['POST'])
def qc_login():
    import subprocess, sys
    try:
        subprocess.Popen([sys.executable, 'qc_auth.py'])
        return jsonify({'status': 'Janela aberta! Faça o login no QConcursos na janela que apareceu.'})
    except Exception as e:
        return (jsonify({'error': str(e)}), 500)
