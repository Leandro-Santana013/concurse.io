import re
import json
import asyncio
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import func
from datetime import datetime

from models.database import (
    get_db,
    Exam,
    Question,
    ExamAttempt,
    create_generated_exam_session,
    resolve_exam_questions,
)
from schemas.exam_schemas import (
    ExamSummarySchema,
    FolderSchema,
    ExamDetailSchema,
    QuestionSchema,
    AttemptSubmission,
    AttemptResult,
    ExamIngestResponse,
)
from routes.api_v1.user_context import (
    get_accessible_exam_or_404,
    get_current_user,
    require_admin_user,
)
from routes.api_v1.exam_media import secure_exam_image_urls
from services.exam_library import claim_exam_for_user, get_user_exam_ids, link_ready_exam_to_user

router = APIRouter()

@router.get("/folders", response_model=List[FolderSchema])
def list_folders(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista somente as provas aprovadas vinculadas ao usuário atual com queries otimizadas em lote."""
    from sqlalchemy.orm import joinedload
    exam_ids = list(get_user_exam_ids(db, current_user.id))
    if not exam_ids:
        return []

    exams = (
        db.query(Exam)
        .options(joinedload(Exam.folder))
        .filter(Exam.id.in_(exam_ids), Exam.status == "Aprovada")
        .order_by(Exam.title.asc())
        .all()
    )
    if not exams:
        return []

    active_exam_ids = [e.id for e in exams]

    # Contagem de questões em uma única query agrupada
    question_counts = dict(
        db.query(Question.exam_id, func.count(Question.id))
        .filter(Question.exam_id.in_(active_exam_ids))
        .group_by(Question.exam_id)
        .all()
    )

    # Tentativas do usuário em uma única query
    attempts_by_exam: Dict[int, List[ExamAttempt]] = {}
    all_attempts = (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.exam_id.in_(active_exam_ids),
            ExamAttempt.user_id == current_user.id,
        )
        .order_by(ExamAttempt.id.desc())
        .all()
    )
    for att in all_attempts:
        attempts_by_exam.setdefault(att.exam_id, []).append(att)

    grouped: Dict[Any, Dict[str, Any]] = {}

    for exam in exams:
        attempts = attempts_by_exam.get(exam.id, [])
        best_pct = max((attempt.percentage for attempt in attempts), default=None)
        last_pct = attempts[0].percentage if attempts else None
        q_count = question_counts.get(exam.id, 0)

        summary = ExamSummarySchema(
            id=exam.id,
            title=exam.title,
            status=exam.status,
            question_count=q_count,
            best_score=round(best_pct, 1) if best_pct is not None else None,
            last_score=round(last_pct, 1) if last_pct is not None else None,
            attempt_count=len(attempts),
            has_official_answers=bool(exam.has_official_answers),
            answer_key_source=exam.answer_key_source or "none",
            gabarito_coverage=exam.gabarito_coverage or 0.0,
            gabarito_summary=exam.gabarito_text,
            source_url=exam.source_url,
        )

        owns_folder = exam.folder is not None and exam.folder.user_id == current_user.id
        if owns_folder:
            folder_key = exam.folder_id
            folder_name = exam.folder.name
        elif exam.folder is not None:
            folder_key = "acervo"
            folder_name = "Provas do acervo"
        else:
            folder_key = "avulsas"
            folder_name = "Provas Avulsas"
        group = grouped.setdefault(folder_key, {"name": folder_name, "exams": []})
        group["exams"].append(summary)

    return [
        FolderSchema(id=folder_id, name=data["name"], exams=data["exams"])
        for folder_id, data in grouped.items()
    ]

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
def get_exam_detail(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retorna detalhes completos da prova com todas as questões formatadas para o simulado."""
    exam = get_accessible_exam_or_404(db, user_id=current_user.id, exam_id=exam_id)

    questions_list = []
    resolved_questions, is_generated_session = resolve_exam_questions(db, exam)
    sorted_questions = (
        resolved_questions
        if is_generated_session
        else sorted(resolved_questions, key=_sort_questions_key)
    )
    for idx, q in enumerate(sorted_questions, start=1):
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
            numero_questao=str(idx) if is_generated_session else str(q.numero_questao or ""),
            statement=q.statement,
            options=options_dict,
            correct_answer=q.correct_answer,
            subject=q.subject or "Geral",
            images=secure_exam_image_urls(exam.id, images_list),
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
def get_progress(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Consulta pontual do progresso de processamento da prova."""
    exam = get_accessible_exam_or_404(db, user_id=current_user.id, exam_id=exam_id)
    return {
        "status": exam.progress_message or exam.status or "Pendente",
        "progress": exam.progress or 0,
        "error_type": exam.error_type
    }

@router.get("/exams/{exam_id}/progress/stream")
async def stream_exam_progress(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Endpoint Server-Sent Events (SSE) que envia o progresso em tempo real
    para o cliente até que o exame seja aprovado ou ocorra erro.
    """
    get_accessible_exam_or_404(db, user_id=current_user.id, exam_id=exam_id)

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
def submit_attempt(
    submission: AttemptSubmission,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submete as respostas de um simulado, calcula pontuação e gera detalhamento por matéria."""
    exam = get_accessible_exam_or_404(
        db,
        user_id=current_user.id,
        exam_id=submission.exam_id,
    )

    user_id = current_user.id
    score = 0
    resolved_questions, is_generated_session = resolve_exam_questions(db, exam)
    exam_questions = (
        resolved_questions
        if is_generated_session
        else sorted(resolved_questions, key=_sort_questions_key)
    )
    total = len(exam_questions)
    detailed_answers = {}
    feedback_per_subject = {}

    for idx, q in enumerate(exam_questions, start=1):
        q_num = str(idx) if is_generated_session else str(q.numero_questao or q.id)
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
def generate_custom_exam(
    count: int = Query(20, ge=5, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Gera um simulado aleatório apenas com questões do acervo do usuário."""
    accessible_exam_ids = get_user_exam_ids(db, current_user.id)
    questions = (
        db.query(Question)
        .filter(Question.exam_id.in_(accessible_exam_ids))
        .order_by(func.random())
        .limit(count)
        .all()
    ) if accessible_exam_ids else []
    if not questions:
        raise HTTPException(status_code=400, detail="Nenhuma questão disponível na sua biblioteca.")

    title = f"Simulado Personalizado ({len(questions)} Questões)"
    exam = create_generated_exam_session(
        db,
        title=title,
        kind="custom",
        question_ids=[question.id for question in questions],
        user_id=current_user.id,
    )

    questions_list = []
    for idx, q in enumerate(questions, start=1):
        try:
            options_dict = json.loads(q.options) if q.options else {}
        except Exception:
            options_dict = {}

        try:
            images_list = json.loads(q.images) if q.images else []
            if isinstance(images_list, str):
                images_list = [images_list]
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
            images=secure_exam_image_urls(exam.id, images_list),
            has_official_answer=True,
            latex_support=is_latex
        ))

    return ExamDetailSchema(
        id=exam.id,
        title=exam.title,
        status=exam.status,
        has_official_answers=True,
        gabarito_coverage=100.0,
        questions=questions_list
    )

@router.post("/exams/ingest", response_model=ExamIngestResponse)
def ingest_exam_from_url(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Associa uma prova canônica ao usuário e só processa conteúdo ainda inexistente."""
    from app_core.async_worker import dispatch_async_exam_task
    url = payload.get("url")
    title = payload.get("title", "Nova Prova de Concurso")
    gabarito_url = payload.get("gabarito_url")

    if not url:
        raise HTTPException(status_code=400, detail="URL da prova é obrigatória.")

    force_reprocess = bool(payload.get("force") or payload.get("reprocess"))

    claim = claim_exam_for_user(
        db,
        user_id=current_user.id,
        raw_url=str(url),
        title=str(title),
        gabarito_url=str(gabarito_url) if gabarito_url else None,
        force_reprocess=force_reprocess,
    )
    exam = claim.exam

    if claim.should_process:
        dispatch_async_exam_task(exam.id)

    if exam.status == "Aprovada" and claim.reused:
        message = "Prova pronta recuperada do banco, sem nova extração."
    elif not claim.should_process:
        message = "Esta prova já está sendo processada; o processamento existente foi reutilizado."
    else:
        message = "Processamento assíncrono iniciado com sucesso."

    return {
        "exam_id": exam.id,
        "title": exam.title,
        "status": exam.status,
        "progress": exam.progress or 0,
        "message": message,
        "reused": claim.reused,
        "already_in_library": claim.already_in_library,
    }


@router.post("/exams/{exam_id}/claim", response_model=ExamIngestResponse)
def claim_processed_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Vincula uma prova pronta ao usuário sem acionar ingestão ou worker."""
    try:
        exam, already_in_library = link_ready_exam_to_user(
            db,
            user_id=current_user.id,
            exam_id=exam_id,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return {
        "exam_id": exam.id,
        "title": exam.title,
        "status": exam.status,
        "progress": exam.progress or 0,
        "message": "Prova já processada adicionada à biblioteca sem nova extração.",
        "reused": True,
        "already_in_library": already_in_library,
    }


@router.post("/exams/{exam_id}/status")
def update_exam_status(
    exam_id: int,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Atualiza o status de um exame (Aprovar, Negar ou Reprocessar)."""
    require_admin_user(current_user)
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
