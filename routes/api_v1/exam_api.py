import os
import re
import json
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import func
from datetime import datetime

from models.database import get_db, Exam, Folder, Question, ExamAttempt, User
from schemas.exam_schemas import (
    ExamSummarySchema,
    FolderSchema,
    ExamDetailSchema,
    QuestionSchema,
    AttemptSubmission,
    AttemptResult,
)

router = APIRouter()

def _get_current_user_id(request: Request, db: Session) -> Optional[int]:
    """Recupera o ID do usuário da sessão ou retorna o primeiro usuário padrão."""
    user = db.query(User).first()
    if not user:
        user = User(google_id="default_dev_user", email="dev@concurse.io", name="Concurseiro Dev")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user.id

@router.get("/folders", response_model=List[FolderSchema])
def list_folders(db: Session = Depends(get_db)):
    """Lista todas as pastas e provas aprovadas com estatísticas de desempenho."""
    user_id = 1
    folders = db.query(Folder).all()
    result = []

    for f in folders:
        exams_data = []
        for e in f.exams:
            if e.status != 'Aprovada':
                continue
            attempts = db.query(ExamAttempt).filter_by(exam_id=e.id).order_by(ExamAttempt.id.desc()).all()
            best_pct = max((a.percentage for a in attempts), default=None)
            last_pct = attempts[0].percentage if attempts else None
            
            exams_data.append(ExamSummarySchema(
                id=e.id,
                title=e.title,
                status=e.status,
                question_count=len(e.questions),
                best_score=round(best_pct, 1) if best_pct is not None else None,
                last_score=round(last_pct, 1) if last_pct is not None else None,
                attempt_count=len(attempts),
                has_official_answers=bool(e.has_official_answers),
                answer_key_source=e.answer_key_source or "none",
                gabarito_coverage=e.gabarito_coverage or 0.0,
                gabarito_summary=e.gabarito_text,
                source_url=e.source_url
            ))
        if exams_data:
            result.append(FolderSchema(id=f.id, name=f.name, exams=exams_data))

    orphan_exams = db.query(Exam).filter(Exam.folder_id == None, Exam.status == 'Aprovada').all()
    if orphan_exams:
        orphan_data = []
        for e in orphan_exams:
            attempts = db.query(ExamAttempt).filter_by(exam_id=e.id).order_by(ExamAttempt.id.desc()).all()
            best_pct = max((a.percentage for a in attempts), default=None)
            last_pct = attempts[0].percentage if attempts else None
            orphan_data.append(ExamSummarySchema(
                id=e.id,
                title=e.title,
                status=e.status,
                question_count=len(e.questions),
                best_score=round(best_pct, 1) if best_pct is not None else None,
                last_score=round(last_pct, 1) if last_pct is not None else None,
                attempt_count=len(attempts),
                has_official_answers=bool(e.has_official_answers),
                answer_key_source=e.answer_key_source or "none",
                gabarito_coverage=e.gabarito_coverage or 0.0,
                gabarito_summary=e.gabarito_text,
                source_url=e.source_url
            ))
        if orphan_data:
            result.append(FolderSchema(id="avulsas", name="Provas Avulsas", exams=orphan_data))

    return result

def _sort_questions_key(q):
    raw = str(getattr(q, 'numero_questao', None) or (q.get('numero_questao') if isinstance(q, dict) else '') or '').strip()
    item_id = getattr(q, 'id', 0) if hasattr(q, 'id') else (q.get('id', 0) if isinstance(q, dict) else 0) or 0
    if raw.isdigit():
        return (0, int(raw), item_id)
    m = re.match(r'^(\d+)', raw)
    if m:
        return (0, int(m.group(1)), item_id)
    return (1, item_id, raw)

@router.get("/exams/{exam_id}", response_model=ExamDetailSchema)
def get_exam_detail(exam_id: int, db: Session = Depends(get_db)):
    """Retorna detalhes completos da prova com todas as questões formatadas para o simulado."""
    exam = db.query(Exam).filter_by(id=exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")

    questions_list = []
    sorted_questions = sorted(exam.questions, key=_sort_questions_key)
    for q in sorted_questions:
        try:
            raw_opts = json.loads(q.options) if q.options else {}
            if isinstance(raw_opts, dict):
                options_dict = raw_opts
            elif isinstance(raw_opts, list):
                options_dict = {}
                for item in raw_opts:
                    if isinstance(item, dict):
                        k = item.get('letter') or item.get('key') or item.get('letra') or ''
                        v = item.get('text') or item.get('texto') or ''
                        if k:
                            options_dict[k.upper()] = v
                    elif isinstance(item, str):
                        m = re.match(r'^\(?([A-Ea-e])\)?[\.\:\-\s]+(.*)', item)
                        if m:
                            options_dict[m.group(1).upper()] = m.group(2)
            else:
                options_dict = {}
        except Exception:
            options_dict = {}

        try:
            images_list = json.loads(q.images) if q.images else []
            if isinstance(images_list, str):
                images_list = [images_list]
        except Exception:
            images_list = []

        is_latex = bool(q.latex_support) or ('$$' in q.statement or '\\frac' in q.statement or '\\sqrt' in q.statement)

        questions_list.append(QuestionSchema(
            id=q.id,
            numero_questao=str(q.numero_questao or ""),
            statement=q.statement,
            options=options_dict,
            correct_answer=q.correct_answer,
            subject=q.subject or "Geral",
            images=images_list if images_list else None,
            has_official_answer=bool(exam.has_official_answers),
            latex_support=is_latex
        ))

    return ExamDetailSchema(
        id=exam.id,
        title=exam.title,
        status=exam.status,
        folder_id=exam.folder_id,
        source_url=exam.source_url,
        gabarito_url=exam.gabarito_url,
        has_official_answers=bool(exam.has_official_answers),
        gabarito_coverage=exam.gabarito_coverage or 0.0,
        gabarito_text=exam.gabarito_text,
        questions=questions_list
    )

@router.get("/exams/{exam_id}/progress")
def get_progress(exam_id: int, db: Session = Depends(get_db)):
    """Consulta pontual do progresso de processamento da prova."""
    exam = db.query(Exam).filter_by(id=exam_id).first()
    if not exam:
        return {"status": "Pendente", "progress": 0, "error_type": None}
    return {
        "status": exam.progress_message or exam.status or "Pendente",
        "progress": exam.progress or 0,
        "error_type": exam.error_type
    }

@router.get("/exams/{exam_id}/progress/stream")
async def stream_exam_progress(exam_id: int):
    """
    Endpoint Server-Sent Events (SSE) que envia o progresso em tempo real
    para o cliente até que o exame seja aprovado ou ocorra erro.
    """
    async def event_generator():
        last_progress = -999
        last_msg = ""
        while True:
            from models.database import Session as SyncSession
            with SyncSession() as session:
                exam = session.query(Exam).filter_by(id=exam_id).first()
                if not exam:
                    data = json.dumps({"status": "Pendente", "progress": 0, "error_type": None})
                    yield f"data: {data}\n\n"
                    break
                
                curr_prog = exam.progress or 0
                curr_msg = exam.progress_message or exam.status or "Pendente"
                err = exam.error_type

                if curr_prog != last_progress or curr_msg != last_msg:
                    data = json.dumps({"status": curr_msg, "progress": curr_prog, "error_type": err})
                    yield f"data: {data}\n\n"
                    last_progress = curr_prog
                    last_msg = curr_msg

                if curr_prog >= 100 or curr_prog == -1 or exam.status in ['Aprovada', 'Erro']:
                    break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.post("/exams/attempt", response_model=AttemptResult)
def submit_attempt(submission: AttemptSubmission, db: Session = Depends(get_db)):
    """Submete as respostas de um simulado, calcula pontuação e gera detalhamento por matéria."""
    exam = db.query(Exam).filter_by(id=submission.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")

    user_id = 1
    score = 0
    total = len(exam.questions)
    detailed_answers = {}
    feedback_per_subject = {}

    for q in exam.questions:
        q_num = str(q.numero_questao or q.id)
        user_ans = submission.answers.get(q_num, "").strip().upper()
        correct_ans = q.correct_answer.strip().upper() if q.correct_answer else "A"
        
        is_correct = (user_ans == correct_ans) or (correct_ans == 'X')
        if is_correct:
            score += 1

        detailed_answers[q_num] = {
            "question_id": q.id,
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "is_correct": is_correct,
            "subject": q.subject or "Geral"
        }

        subj = q.subject or "Geral"
        if subj not in feedback_per_subject:
            feedback_per_subject[subj] = {"total": 0, "correct": 0, "percentage": 0.0}
        feedback_per_subject[subj]["total"] += 1
        if is_correct:
            feedback_per_subject[subj]["correct"] += 1

    for s_info in feedback_per_subject.values():
        if s_info["total"] > 0:
            s_info["percentage"] = round((s_info["correct"] / s_info["total"]) * 100, 1)

    pct = round((score / total) * 100, 1) if total > 0 else 0.0
    now_str = datetime.now().isoformat()

    attempt = ExamAttempt(
        exam_id=exam.id,
        score=score,
        total=total,
        percentage=pct,
        elapsed_seconds=submission.elapsed_seconds,
        answers_json=json.dumps(submission.answers),
        created_at=now_str,
        user_id=user_id
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return AttemptResult(
        attempt_id=attempt.id,
        exam_id=exam.id,
        score=score,
        total=total,
        percentage=pct,
        elapsed_seconds=submission.elapsed_seconds,
        detailed_answers=detailed_answers,
        feedback_per_subject=feedback_per_subject
    )

@router.post("/exams/generate_custom", response_model=ExamDetailSchema)
def generate_custom_exam(count: int = Query(20, ge=5, le=100), db: Session = Depends(get_db)):
    """Gera um simulado personalizado aleatório a partir de todas as questões do banco."""
    questions = db.query(Question).order_by(func.random()).limit(count).all()
    if not questions:
        raise HTTPException(status_code=400, detail="Nenhuma questão cadastrada no banco de dados.")

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

    return ExamDetailSchema(
        id=999999,
        title=f"Simulado Personalizado ({len(questions_list)} Questões)",
        status="Aprovada",
        has_official_answers=True,
        gabarito_coverage=100.0,
        questions=questions_list
    )

@router.post("/exams/ingest")
def ingest_exam_from_url(
    payload: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Cria uma nova prova a partir de URL e inicia o processamento assíncrono em background."""
    from app_core.async_worker import dispatch_async_exam_task
    url = payload.get("url")
    title = payload.get("title", "Nova Prova de Concurso")
    gabarito_url = payload.get("gabarito_url")

    if not url:
        raise HTTPException(status_code=400, detail="URL da prova é obrigatória.")

    force_reprocess = bool(payload.get("force") or payload.get("reprocess"))

    # Verifica se já existe
    existing = db.query(Exam).filter_by(source_url=url).first()
    if existing and existing.status == 'Aprovada' and not gabarito_url and not force_reprocess and len(existing.questions) >= 5:
        return {"exam_id": existing.id, "status": "Aprovada", "message": "Prova já cadastrada e processada."}

    if not existing:
        exam = Exam(
            title=title,
            source_url=url,
            gabarito_url=gabarito_url,
            status="Processando",
            progress=5,
            progress_message="Iniciando download e processamento...",
            user_id=1
        )
        db.add(exam)
        db.commit()
        db.refresh(exam)
    else:
        exam = existing
        exam.status = "Processando"
        exam.progress = 5
        exam.progress_message = "Reiniciando processamento..."
        if title and title != "Nova Prova de Concurso":
            exam.title = title
        if gabarito_url:
            exam.gabarito_url = gabarito_url
        db.commit()

    dispatch_async_exam_task(exam.id)
    return {
        "exam_id": exam.id,
        "title": exam.title,
        "status": "Processando",
        "progress": 5,
        "message": "Processamento assíncrono iniciado com sucesso."
    }


@router.post("/exams/{exam_id}/status")
def update_exam_status(exam_id: int, payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Atualiza o status de um exame (Aprovar, Negar ou Reprocessar)."""
    from app_core.async_worker import dispatch_async_exam_task
    new_status = payload.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="Status é obrigatório.")

    exam = db.query(Exam).filter_by(id=exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")

    if new_status == 'Negada':
        db.delete(exam)
        db.commit()
        return {"success": True, "status": "Negada"}

    if new_status == 'Aprovada' or new_status == 'Processando':
        exam.status = 'Processando'
        exam.progress = 5
        exam.progress_message = "Iniciando processamento..."
        db.commit()
        dispatch_async_exam_task(exam.id)
        return {"success": True, "status": "Processando", "exam_id": exam.id}

    exam.status = new_status
    db.commit()
    return {"success": True, "status": exam.status}
