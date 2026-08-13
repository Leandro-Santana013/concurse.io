from flask import Blueprint, request, jsonify, render_template, url_for, redirect, current_app, send_file, session
import os, json, threading, shutil
from flask_login import login_user, login_required, logout_user, current_user
from app_core.orchestrator import orchestrator
from models import Session, User, Folder, Exam, Question, AppConfig, ExamAttempt
from app_core.extensions import login_manager, oauth
import datetime

stats_bp = Blueprint('stats', __name__)

@stats_bp.route('/api/notebook/stats', methods=['GET'])
def get_notebook_stats():
    session = Session()
    attempts = session.query(ExamAttempt).filter_by(user_id=current_user.id).all()
    wrong_q_counts = {}
    exam_q_cache = {}
    for a in attempts:
        if not a.answers_json:
            continue
        try:
            answers = json.loads(a.answers_json)
            if a.exam_id not in exam_q_cache:
                exam_q_cache[a.exam_id] = session.query(Question).filter_by(exam_id=a.exam_id).order_by(Question.id).all()
            exam_q_list = exam_q_cache[a.exam_id]
            for (idx_str, given_ans) in answers.items():
                idx = int(idx_str)
                if idx < len(exam_q_list):
                    q = exam_q_list[idx]
                    if given_ans.strip().upper() != q.correct_answer.strip().upper():
                        subject = q.subject or 'Geral'
                        wrong_q_counts[subject] = wrong_q_counts.get(subject, 0) + 1
        except Exception as e:
            print(f"Erro ao processar estatística: {e}")
    session.close()
    stats = [{'subject': k, 'count': v} for (k, v) in sorted(wrong_q_counts.items(), key=lambda x: x[1], reverse=True)]
    return jsonify(stats)

@stats_bp.route('/api/notebook', methods=['GET'])
def get_error_notebook():
    """Retorna uma 'prova' contendo apenas as questões que o usuário errou historicamente."""
    subject_filter = request.args.get('subject')
    session = Session()
    attempts = session.query(ExamAttempt).filter_by(user_id=current_user.id).all()
    wrong_q_counts = {}
    exam_q_cache = {}
    for a in attempts:
        if not a.answers_json:
            continue
        try:
            answers = json.loads(a.answers_json)
            if a.exam_id not in exam_q_cache:
                exam_q_cache[a.exam_id] = session.query(Question).filter_by(exam_id=a.exam_id).order_by(Question.id).all()
            exam_q_list = exam_q_cache[a.exam_id]
            for (idx_str, given_ans) in answers.items():
                idx = int(idx_str)
                if idx < len(exam_q_list):
                    q = exam_q_list[idx]
                    if given_ans.strip().upper() != q.correct_answer.strip().upper():
                        wrong_q_counts[q.id] = wrong_q_counts.get(q.id, 0) + 1
        except Exception as e:
            print(f"Erro ao gerar caderno de erros: {e}")
    query = session.query(Question).filter(Question.id.in_(wrong_q_counts.keys()))
    if subject_filter:
        query = query.filter(Question.subject == subject_filter)
    questions = query.limit(100).all()
    q_data = [{'id': q.id, 'statement': q.statement, 'options': json.loads(q.options) if q.options else None, 'correct_answer': q.correct_answer, 'subject': q.subject or 'Geral', 'error_count': wrong_q_counts.get(q.id, 1)} for q in questions]
    session.close()
    title_suffix = f' - {subject_filter}' if subject_filter else ' (Todas as matérias)'
    return jsonify({'id': 'notebook', 'title': f'Caderno de Erros{title_suffix}', 'questions': q_data})

@stats_bp.route('/api/stats', methods=['GET'])
def get_global_stats():
    session = Session()
    attempts = session.query(ExamAttempt).filter_by(user_id=current_user.id).all()
    total_exams = len(set((a.exam_id for a in attempts)))
    total_questions = sum((a.total for a in attempts))
    total_correct = sum((a.score for a in attempts))
    global_accuracy = total_correct / total_questions * 100 if total_questions > 0 else 0
    from datetime import datetime
    dates = set((a.created_at[:10] for a in attempts if a.created_at))
    dates_sorted = sorted(list(dates), reverse=True)
    streak = 0
    today = datetime.now().strftime('%Y-%m-%d')
    if dates_sorted and (dates_sorted[0] == today or (len(dates_sorted) > 0 and (datetime.now() - datetime.strptime(dates_sorted[0], '%Y-%m-%d')).days == 1)):
        for i in range(len(dates_sorted)):
            if i == 0:
                streak = 1
                continue
            prev_date = datetime.strptime(dates_sorted[i - 1], '%Y-%m-%d')
            curr_date = datetime.strptime(dates_sorted[i], '%Y-%m-%d')
            if (prev_date - curr_date).days == 1:
                streak += 1
            else:
                break
                
    total_seconds = sum((a.elapsed_seconds or 0 for a in attempts))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    study_time = f"{h}h {m}m" if h > 0 else f"{m}m"

    from sqlalchemy.sql import func
    results = session.query(User.id, func.sum(ExamAttempt.total).label('t_q'), func.sum(ExamAttempt.score).label('t_c')).outerjoin(ExamAttempt, User.id == ExamAttempt.user_id).group_by(User.id).all()
    user_ranking = []
    for (uid, total_q, total_c) in results:
        total_q = total_q or 0
        total_c = total_c or 0
        acc = total_c / total_q * 100 if total_q > 0 else 0
        user_ranking.append((uid, total_q, acc))
    user_ranking.sort(key=lambda x: (x[1], x[2]), reverse=True)
    
    current_user_rank = "-"
    if total_questions > 0:
        for idx, (uid, _, _) in enumerate(user_ranking):
            if uid == current_user.id:
                current_user_rank = f"{idx + 1}º"
                break

    session.close()
    return jsonify({
        'total_exams': total_exams, 
        'total_questions': total_questions, 
        'total_correct': total_correct, 
        'global_accuracy': round(global_accuracy, 1), 
        'streak': streak,
        'study_time': study_time,
        'rank': current_user_rank
    })

@stats_bp.route('/api/ranking', methods=['GET'])
def get_ranking():
    """Retorna o ranking global dos usuários baseado em questões resolvidas e taxa de acerto."""
    session = Session()
    from sqlalchemy.sql import func
    results = session.query(User, func.sum(ExamAttempt.total).label('total_questions'), func.sum(ExamAttempt.score).label('total_correct')).outerjoin(ExamAttempt, User.id == ExamAttempt.user_id).group_by(User.id).all()
    ranking = []
    for (user, total_q, total_c) in results:
        total_q = total_q or 0
        total_c = total_c or 0
        accuracy = total_c / total_q * 100 if total_q > 0 else 0
        ranking.append({'name': user.name or 'Concurseiro', 'picture': user.picture or '', 'total_questions': total_q, 'accuracy': round(accuracy, 1)})
    session.close()
    ranking.sort(key=lambda x: (x['total_questions'], x['accuracy']), reverse=True)
    return jsonify(ranking)

