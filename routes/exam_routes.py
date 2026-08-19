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
    return jsonify(prog)

@exam_bp.route('/api/exams/<int:exam_id>/progress_clear', methods=['POST'])
def clear_exam_progress(exam_id):
    try:
        with Session() as session:
            exam = session.query(Exam).filter_by(id=exam_id).first()
            if exam and exam.status == 'Pendente':
                exam.progress = 0
                exam.progress_message = 'Pendente'
                session.commit()
    except Exception as e:
        print(f"Erro ao limpar progresso: {e}")
    return jsonify({'success': True})

@exam_bp.route('/api/downloads', methods=['GET'])
def get_active_downloads():
    results = []
    try:
        with Session() as session:
            # Apenas exames que o usuário clicou para baixar/processar (ignora resultados de busca pendentes de triagem)
            active_exams = session.query(Exam).filter(
                Exam.user_id == current_user.id,
                Exam.status != 'Pendente',
                ((Exam.progress < 100) & (Exam.progress > 0)) | (Exam.progress == -1)
            ).all()
            for exam in active_exams:
                results.append({
                    'id': exam.id,
                    'title': exam.title,
                    'url': exam.source_url or '',
                    'status': exam.progress_message or exam.status or '',
                    'progress': exam.progress or 0,
                    'error_type': exam.error_type,
                    'total_chunks': 0,
                    'done_chunks': 0
                })
    except Exception as e:
        print(f"Erro ao obter downloads ativos: {e}")
    results.sort(key=lambda x: 0 if 0 <= x['progress'] < 100 else 1 if x['progress'] == -1 else 2)
    return jsonify(results)

@exam_bp.route('/api/exams/<int:exam_id>/manual_pdf', methods=['POST'])
def manual_pdf(exam_id):
    from datetime import datetime
    with Session() as session:
        exam = session.query(Exam).filter_by(user_id=current_user.id, id=exam_id).first()
        if not exam:
            return jsonify({'error': 'Prova não encontrada.'}), 404

        os.makedirs('pdfs', exist_ok=True)
        ts = int(datetime.now().timestamp())
        filepath = os.path.join('pdfs', f'{exam_id}_{ts}.pdf')

        # 1. Processar arquivo ou URL da Prova
        if 'pdf_file' in request.files and request.files['pdf_file'].filename:
            file = request.files['pdf_file']
            file.save(filepath)
        else:
            data = request.get_json(silent=True) or request.form or {}
            pdf_url = data.get('pdf_url')
            if not pdf_url:
                return jsonify({'error': 'Nenhuma URL ou arquivo da prova fornecido.'}), 400
                
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://www.pciconcursos.com.br/',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
                r = requests.get(pdf_url, headers=headers, verify=False, allow_redirects=True, timeout=30)
                if r.status_code != 200:
                    return jsonify({'error': f'Falha ao baixar PDF da prova (Status: {r.status_code}).'}), 400
                with open(filepath, 'wb') as f:
                    f.write(r.content)
            except Exception as e:
                return jsonify({'error': f'Erro ao baixar URL da prova: {str(e)}'}), 400
                
        exam.pdf_path = filepath
        
        # 2. Processar arquivo, texto ou URL de Gabarito Avulso (se fornecido)
        data = request.get_json(silent=True) or request.form or {}
        gabarito_text = data.get('gabarito_text')
        gabarito_url = data.get('gabarito_url')

        if 'gabarito_file' in request.files and request.files['gabarito_file'].filename:
            gab_file = request.files['gabarito_file']
            gab_filepath = os.path.join('pdfs', f'{exam_id}_gab_{ts}.pdf')
            gab_file.save(gab_filepath)
            exam.gabarito_url = gab_filepath
        elif gabarito_url:
            exam.gabarito_url = gabarito_url
            
        if gabarito_text:
            exam.gabarito_text = gabarito_text

        exam.status = 'Aprovada'
        clean_title = exam.title.replace('Prova - ', '').split('.')[0][:40]
        folder_name = clean_title if clean_title else f'Pasta Prova {exam.id}'
        folder = session.query(Folder).filter_by(user_id=current_user.id, name=folder_name).first()
        if not folder:
            folder = Folder(name=folder_name, user_id=current_user.id)
            session.add(folder)
            session.flush()
        exam.folder_id = folder.id
        
        from app import set_exam_progress
        set_exam_progress(exam.id, 'Iniciando processamento e triagem de documentos...', 5)
        try:
            from services.exam_service import _real_scrape_exam
            (success, error_msg) = _real_scrape_exam(session, exam, gabarito_override=gabarito_text)
        except Exception as e:
            (success, error_msg) = (False, f'Erro interno: {str(e)}')
            
        if not success:
            exam.status = 'Pendente'
            session.commit()
            return jsonify({'error': error_msg}), 400
            
        session.commit()
        return jsonify({'message': 'Upload realizado com sucesso e processamento iniciado.'})

@exam_bp.route('/api/exams/create_manual', methods=['POST'])
def create_manual_exam():
    """Cria uma nova prova e inicia o processamento conjunto de Prova + Gabarito."""
    from datetime import datetime
    
    if not current_user.is_authenticated:
        return jsonify({'error': 'Você precisa estar logado para enviar uma prova.'}), 401
        
    user_id = current_user.id
    title = request.form.get('title') or (request.get_json(silent=True) or {}).get('title') or ''
    title = title.strip()
    
    with Session() as session:
        # Se não informou título, usa título padrão provisório
        if not title:
            title = f"Prova Manual - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            
        new_exam = Exam(
            title=title,
            status='Processando',
            user_id=user_id,
            progress=5,
            progress_message='Iniciando ingestão de prova e gabarito...'
        )
        session.add(new_exam)
        session.flush()
        
        exam_id = new_exam.id
        clean_title = title.replace('Prova - ', '').split('.')[0][:40]
        folder_name = clean_title if clean_title else f'Pasta Prova {exam_id}'
        folder = session.query(Folder).filter_by(user_id=user_id, name=folder_name).first()
        if not folder:
            folder = Folder(name=folder_name, user_id=user_id)
            session.add(folder)
            session.flush()
        new_exam.folder_id = folder.id
        
        os.makedirs('pdfs', exist_ok=True)
        ts = int(datetime.now().timestamp())
        filepath = os.path.join('pdfs', f'{exam_id}_{ts}.pdf')
        
        # 1. Arquivo ou URL da Prova
        if 'pdf_file' in request.files and request.files['pdf_file'].filename:
            file = request.files['pdf_file']
            file.save(filepath)
            new_exam.pdf_path = filepath
        else:
            data = request.get_json(silent=True) or request.form or {}
            pdf_url = data.get('pdf_url')
            if not pdf_url:
                session.delete(new_exam)
                session.commit()
                return jsonify({'error': 'Nenhum arquivo ou URL da prova fornecido.'}), 400
            new_exam.source_url = pdf_url

        # 2. Arquivo, URL ou Texto do Gabarito
        data = request.get_json(silent=True) or request.form or {}
        gabarito_text = data.get('gabarito_text')
        gabarito_url = data.get('gabarito_url')

        if 'gabarito_file' in request.files and request.files['gabarito_file'].filename:
            gab_file = request.files['gabarito_file']
            gab_filepath = os.path.join('pdfs', f'{exam_id}_gab_{ts}.pdf')
            gab_file.save(gab_filepath)
            new_exam.gabarito_url = gab_filepath
        elif gabarito_url:
            new_exam.gabarito_url = gabarito_url
            
        if gabarito_text:
            new_exam.gabarito_text = gabarito_text

        session.commit()

        # Inicia extração em background
        from services.exam_service import _real_scrape_exam
        _real_scrape_exam(session, new_exam, gabarito_override=gabarito_text)
        
        return jsonify({
            'success': True,
            'exam_id': exam_id,
            'message': 'Prova e gabarito enviados com sucesso! O processamento foi iniciado.'
        })

@exam_bp.route('/api/exams/<int:exam_id>/attach_gabarito', methods=['POST'])
def attach_gabarito(exam_id):
    """Permite anexar ou editar o gabarito oficial de uma prova já existente."""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Você precisa estar logado para anexar um gabarito.'}), 401
        
    user_id = current_user.id
    from services.gabarito_service import parse_gabarito_from_text, parse_gabarito_from_pdf, merge_exam_with_gabarito, format_gabarito_summary
    
    with Session() as session:
        exam = session.query(Exam).filter_by(user_id=user_id, id=exam_id).first()
        if not exam:
            return jsonify({'error': 'Prova não encontrada.'}), 404

        questions = session.query(Question).filter_by(exam_id=exam_id).order_by(Question.id.asc()).all()
        if not questions:
            return jsonify({'error': 'Esta prova não possui questões cadastradas.'}), 400

        data = request.get_json(silent=True) or request.form or {}
        gabarito_dict = {}
        answer_source = 'manual_text'

        if 'gabarito_file' in request.files and request.files['gabarito_file'].filename:
            file = request.files['gabarito_file']
            file_bytes = file.read()
            gabarito_dict = parse_gabarito_from_pdf(file_bytes)
            answer_source = 'attached_pdf'
        elif data.get('gabarito_text'):
            gabarito_dict = parse_gabarito_from_text(data.get('gabarito_text'))
            answer_source = 'manual_text'
        elif data.get('gabarito_url'):
            from services.exam_service import _download_pdf_bytes
            pdf_bytes = _download_pdf_bytes(data.get('gabarito_url'), exam_id)
            if pdf_bytes:
                gabarito_dict = parse_gabarito_from_pdf(pdf_bytes)
                answer_source = 'attached_pdf'

        if not gabarito_dict:
            return jsonify({'error': 'Não foi possível extrair respostas válidas do gabarito informado.'}), 400

        # Mapeia questões existentes para formato dict
        q_dicts = []
        for q in questions:
            q_dicts.append({
                'id': q.id,
                'numero_questao': q.numero_questao,
                'enunciado': q.statement,
                'opcoes': json.loads(q.options) if q.options else {},
                'resposta': q.correct_answer
            })

        updated_q_dicts, stats = merge_exam_with_gabarito(q_dicts, gabarito_dict)

        # Atualiza banco de dados
        for u_q in updated_q_dicts:
            db_q = session.query(Question).filter_by(id=u_q['id']).first()
            if db_q:
                db_q.correct_answer = u_q['resposta']

        exam.has_official_answers = 1 if stats['has_official_answers'] else 0
        exam.answer_key_source = answer_source
        exam.gabarito_coverage = stats['coverage_pct']
        exam.gabarito_text = format_gabarito_summary(gabarito_dict)
        session.commit()

        return jsonify({
            'success': True,
            'message': f'Gabarito atualizado com sucesso! {stats["matched_answers"]} de {stats["total_questions"]} questões sincronizadas ({stats["coverage_pct"]}%).',
            'stats': stats,
            'gabarito_summary': exam.gabarito_text
        })

@exam_bp.route('/api/exams/<int:exam_id>/status', methods=['POST'])
def update_exam_status(exam_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get('status')
    if not new_status:
        return jsonify({'success': False, 'error': 'Status obrigatório'}), 400

    with Session() as session:
        exam = session.query(Exam).filter_by(user_id=current_user.id, id=exam_id).first()
        if not exam:
            return jsonify({'success': False, 'error': 'Exam not found'}), 404
            
        if new_status == 'Negada':
            session.delete(exam)
            session.commit()
            return jsonify({'success': True, 'status': 'Negada'})
            
        if new_status == 'Aprovada':
            if exam.status == 'Aprovada':
                return jsonify({'success': True, 'status': 'Aprovada'})
                
            existing_global = session.query(Exam).filter(Exam.source_url == exam.source_url, Exam.status == 'Aprovada', Exam.id != exam.id).first()
            if existing_global:
                global_questions = session.query(Question).filter_by(exam_id=existing_global.id).all()
                if len(global_questions) > 0:
                    exam.status = 'Aprovada'
                    clean_title = exam.title.replace('Prova - ', '').split('.')[0][:40]
                    folder_name = clean_title if clean_title else f'Pasta Prova {exam.id}'
                    folder = session.query(Folder).filter_by(user_id=current_user.id, name=folder_name).first()
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
                    return jsonify({'success': True, 'status': 'Aprovada'})
                    
            exam.status = 'Processando'
            clean_title = exam.title.replace('Prova - ', '').split('.')[0][:40]
            folder_name = clean_title if clean_title else f'Pasta Prova {exam.id}'
            folder = session.query(Folder).filter_by(user_id=current_user.id, name=folder_name).first()
            if not folder:
                folder = Folder(name=folder_name, user_id=current_user.id)
                session.add(folder)
                session.flush()
            exam.folder_id = folder.id
            from app import set_exam_progress
            set_exam_progress(exam_id, 'Iniciando processamento...', 5)
            session.commit()

            def bg_scrape(e_id):
                with Session() as bg_session:
                    bg_exam = bg_session.query(Exam).filter_by(id=e_id).first()
                    if bg_exam:
                        try:
                            from services.exam_service import _real_scrape_exam
                            _real_scrape_exam(bg_session, bg_exam)
                        except Exception as e:
                            print(f'Erro no scrape background: {e}')
            threading.Thread(target=bg_scrape, args=(exam.id,), daemon=True).start()
            return jsonify({'success': True, 'status': 'Processando'})
        else:
            exam.status = new_status
            session.commit()
            return jsonify({'success': True, 'status': exam.status})

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
            q_count = len(e.questions)
            exams_data.append({
                'id': e.id,
                'title': e.title,
                'best_score': round(best_pct, 1) if best_pct is not None else None,
                'last_score': round(last_pct, 1) if last_pct is not None else None,
                'attempt_count': attempt_count,
                'question_count': q_count,
                'has_official_answers': bool(e.has_official_answers),
                'answer_key_source': e.answer_key_source or 'none',
                'gabarito_coverage': e.gabarito_coverage or 0.0,
                'gabarito_text': e.gabarito_text
            })
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
        q_count = len(e.questions)
        orphan_data.append({
            'id': e.id,
            'title': e.title,
            'best_score': round(best_pct, 1) if best_pct is not None else None,
            'last_score': round(last_pct, 1) if last_pct is not None else None,
            'attempt_count': attempt_count,
            'question_count': q_count,
            'has_official_answers': bool(e.has_official_answers),
            'answer_key_source': e.answer_key_source or 'none',
            'gabarito_coverage': e.gabarito_coverage or 0.0,
            'gabarito_text': e.gabarito_text
        })
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
        questions.append({
            'id': q.id,
            'statement': q.statement,
            'options': options_dict,
            'correct_answer': q.correct_answer,
            'subject': getattr(q, 'subject', 'Geral') or 'Geral',
            'images': images_list,
            'numero_questao': q.numero_questao
        })
    result = {
        'id': exam.id,
        'title': exam.title,
        'has_official_answers': bool(exam.has_official_answers),
        'answer_key_source': exam.answer_key_source or 'none',
        'gabarito_coverage': exam.gabarito_coverage or 0.0,
        'gabarito_text': exam.gabarito_text,
        'questions': questions
    }
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
    """Retorna detalhes determinísticos do gabarito da questão (Modo 100% Sem IA)."""
    session = Session()
    q = session.query(Question).filter_by(id=question_id).first()
    if not q:
        session.close()
        return (jsonify({'error': 'Questão não encontrada'}), 404)
    data = request.json or {}
    user_answer = data.get('user_answer', 'Nenhuma')
    correct = q.correct_answer
    subject = q.subject or 'Geral'
    
    explanation = f"📌 **Disciplina:** {subject}\n\n" \
                  f"✅ **Gabarito Oficial:** Alternativa **{correct}**\n\n" \
                  f"🎯 **Sua Resposta:** {user_answer}\n\n" \
                  f"{'🎉 Parabéns! Você acertou a questão.' if user_answer == correct else '❌ Atenção: Revise o conteúdo teórico desta disciplina para fixar o conceito.'}"
    session.close()
    return jsonify({'explanation': explanation})

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
