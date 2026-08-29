import json
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from models.database import get_db, ExamAttempt, Question, User, Exam
from schemas.exam_schemas import ExamDetailSchema, QuestionSchema

router = APIRouter()

def _sort_questions_key(q):
    raw = str(getattr(q, 'numero_questao', None) or '').strip()
    item_id = getattr(q, 'id', 0) or 0
    if raw.isdigit():
        return (0, int(raw), item_id)
    m = re.match(r'^(\d+)', raw)
    if m:
        return (0, int(m.group(1)), item_id)
    return (1, item_id, raw)

def _find_question(exam_q_list, idx_str):
    for q in exam_q_list:
        if str(q.numero_questao or '') == str(idx_str):
            return q
    for q in exam_q_list:
        if str(q.id) == str(idx_str):
            return q
    try:
        idx = int(idx_str) - 1
        if 0 <= idx < len(exam_q_list):
            return exam_q_list[idx]
    except Exception:
        pass
    return None

@router.get("/stats/overview")
def get_global_stats(db: Session = Depends(get_db)):
    """Retorna estatísticas consolidadas de desempenho do usuário."""
    user_id = 1
    attempts = db.query(ExamAttempt).all()
    
    total_exams = len(set(a.exam_id for a in attempts))
    total_questions = sum((a.total for a in attempts))
    total_correct = sum((a.score for a in attempts))
    global_accuracy = (total_correct / total_questions * 100) if total_questions > 0 else 0.0

    # Cálculo de Streak diário
    dates = set(a.created_at[:10] for a in attempts if a.created_at)
    dates_sorted = sorted(list(dates), reverse=True)
    streak = 0
    today = datetime.now().strftime('%Y-%m-%d')
    
    if dates_sorted and (dates_sorted[0] == today or (datetime.now() - datetime.strptime(dates_sorted[0], '%Y-%m-%d')).days <= 1):
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

    return {
        "total_exams": total_exams,
        "total_questions": total_questions,
        "total_correct": total_correct,
        "global_accuracy": round(global_accuracy, 1),
        "streak": streak,
        "study_time": study_time,
        "rank": "1º"
    }

@router.get("/notebook/stats")
def get_notebook_subject_stats(db: Session = Depends(get_db)):
    """Estatísticas de erros agrupados por disciplina para o Caderno de Erros."""
    attempts = db.query(ExamAttempt).all()
    wrong_q_counts = {}
    exam_q_cache = {}

    for a in attempts:
        if not a.answers_json:
            continue
        try:
            answers = json.loads(a.answers_json)
            if a.exam_id not in exam_q_cache:
                raw_qs = db.query(Question).filter_by(exam_id=a.exam_id).all()
                exam_q_cache[a.exam_id] = sorted(raw_qs, key=_sort_questions_key)
            exam_q_list = exam_q_cache[a.exam_id]

            for idx_str, given_ans in answers.items():
                q = _find_question(exam_q_list, idx_str)
                if q and given_ans.strip().upper() != q.correct_answer.strip().upper():
                    subject = q.subject or 'Geral'
                    wrong_q_counts[subject] = wrong_q_counts.get(subject, 0) + 1
        except Exception:
            pass

    stats = [{'subject': k, 'count': v} for k, v in sorted(wrong_q_counts.items(), key=lambda x: x[1], reverse=True)]
    return stats

@router.get("/notebook", response_model=ExamDetailSchema)
def get_error_notebook(subject: Optional[str] = None, db: Session = Depends(get_db)):
    """Gera um simulado exclusivo contendo apenas as questões que o usuário errou."""
    attempts = db.query(ExamAttempt).all()
    wrong_question_ids = set()
    exam_q_cache = {}

    for a in attempts:
        if not a.answers_json:
            continue
        try:
            answers = json.loads(a.answers_json)
            if a.exam_id not in exam_q_cache:
                raw_qs = db.query(Question).filter_by(exam_id=a.exam_id).all()
                exam_q_cache[a.exam_id] = sorted(raw_qs, key=_sort_questions_key)
            exam_q_list = exam_q_cache[a.exam_id]

            for idx_str, given_ans in answers.items():
                q = _find_question(exam_q_list, idx_str)
                if q and given_ans.strip().upper() != q.correct_answer.strip().upper():
                    wrong_question_ids.add(q.id)
        except Exception:
            pass

    query = db.query(Question).filter(Question.id.in_(wrong_question_ids))
    if subject:
        query = query.filter(Question.subject == subject)
    questions = query.limit(100).all()

    questions_list = []
    for idx, q in enumerate(questions, start=1):
        try:
            options_dict = json.loads(q.options) if q.options else {}
        except Exception:
            options_dict = {}

        try:
            images_list = json.loads(q.images) if q.images else []
        except Exception:
            images_list = []

        is_latex = bool(q.latex_support) or ('$$' in q.statement or '\\frac' in q.statement)

        questions_list.append(QuestionSchema(
            id=q.id,
            numero_questao=str(idx),
            statement=q.statement,
            options=options_dict,
            correct_answer=q.correct_answer,
            subject=q.subject or "Geral",
            images=images_list if images_list else None,
            has_official_answer=True,
            latex_support=is_latex
        ))

    title_suffix = f" - {subject}" if subject else " (Todas as Matérias)"
    return ExamDetailSchema(
        id=888888,
        title=f"Caderno de Erros Inteligente{title_suffix}",
        status="Aprovada",
        has_official_answers=True,
        gabarito_coverage=100.0,
        questions=questions_list
    )

@router.get("/ranking")
def get_global_ranking(db: Session = Depends(get_db)):
    """Retorna o ranking global dos concurseiros."""
    results = db.query(
        User,
        func.sum(ExamAttempt.total).label('total_questions'),
        func.sum(ExamAttempt.score).label('total_correct')
    ).outerjoin(ExamAttempt, User.id == ExamAttempt.user_id).group_by(User.id).all()

    ranking = []
    for user, total_q, total_c in results:
        total_q = total_q or 0
        total_c = total_c or 0
        accuracy = (total_c / total_q * 100) if total_q > 0 else 0.0
        ranking.append({
            'name': user.name or 'Concurseiro',
            'picture': user.picture or '',
            'total_questions': total_q,
            'accuracy': round(accuracy, 1)
        })

    ranking.sort(key=lambda x: (x['total_questions'], x['accuracy']), reverse=True)
    return ranking
