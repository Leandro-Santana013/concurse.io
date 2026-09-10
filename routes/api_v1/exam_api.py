import re
import json
import asyncio
from collections import Counter
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
    GeneratedExamSession,
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
    CustomSimulationOptionsSchema,
    CustomSimulationSummarySchema,
)
from routes.api_v1.user_context import (
    get_accessible_exam_or_404,
    get_current_user,
    require_admin_user,
)
from routes.api_v1.exam_media import secure_exam_image_urls, secure_exam_option_image_urls
from services.exam_library import claim_exam_for_user, get_user_exam_ids, link_ready_exam_to_user

router = APIRouter()


def _normalized_subject(value: Any) -> str:
    normalized = str(value or '').strip()
    return normalized or 'Geral'


def _normalized_subject_filters(subjects: Optional[List[str]]) -> List[str]:
    result = []
    seen = set()
    for subject in subjects or []:
        normalized = _normalized_subject(subject)
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _custom_question_query(db: Session, user_id: int):
    """Questões válidas de provas reais que pertencem à biblioteca do usuário."""
    accessible_exam_ids = get_user_exam_ids(db, user_id)
    if not accessible_exam_ids:
        return None

    return (
        db.query(Question)
        .join(Exam, Exam.id == Question.exam_id)
        .filter(
            Question.exam_id.in_(accessible_exam_ids),
            Exam.status == 'Aprovada',
            func.upper(func.trim(Question.correct_answer)).in_(['A', 'B', 'C', 'D', 'E']),
        )
    )


def _decode_generated_question_ids(session: GeneratedExamSession) -> List[int]:
    try:
        raw_ids = json.loads(session.question_ids_json or '[]')
    except (TypeError, ValueError, json.JSONDecodeError):
        raw_ids = []
    if not isinstance(raw_ids, list):
        return []
    normalized = []
    seen = set()
    for raw_id in raw_ids:
        try:
            question_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if question_id <= 0 or question_id in seen:
            continue
        seen.add(question_id)
        normalized.append(question_id)
    return normalized


@router.get("/custom-simulations/options", response_model=CustomSimulationOptionsSchema)
def get_custom_simulation_options(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Retorna os filtros disponíveis para montar um simulado personalizado."""
    query = _custom_question_query(db, current_user.id)
    if query is None:
        return CustomSimulationOptionsSchema()

    rows = query.with_entities(Question.subject, Question.exam_id, Exam.title).all()
    subject_counts = Counter(_normalized_subject(subject) for subject, _exam_id, _title in rows)
    source_counts = Counter(
        (int(exam_id), str(title or 'Prova sem título'))
        for _subject, exam_id, title in rows
    )

    subjects = [
        {"name": name, "count": count}
        for name, count in sorted(
            subject_counts.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )
    ]
    sources = [
        {"id": exam_id, "title": title, "count": count}
        for (exam_id, title), count in sorted(
            source_counts.items(),
            key=lambda item: (-item[1], item[0][1].casefold()),
        )
    ]
    return CustomSimulationOptionsSchema(
        available_questions=len(rows),
        subjects=subjects,
        sources=sources,
    )


@router.get("/custom-simulations", response_model=List[CustomSimulationSummarySchema])
def list_custom_simulations(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lista somente os simulados personalizados do usuário, separados das provas reais."""
    sessions = (
        db.query(GeneratedExamSession, Exam)
        .join(Exam, Exam.id == GeneratedExamSession.exam_id)
        .filter(
            Exam.user_id == current_user.id,
            GeneratedExamSession.kind == 'custom',
        )
        .order_by(GeneratedExamSession.created_at.desc(), GeneratedExamSession.exam_id.desc())
        .all()
    )
    if not sessions:
        return []

    exam_ids = [exam.id for _session, exam in sessions]
    attempts_by_exam: Dict[int, List[ExamAttempt]] = {}
    for attempt in (
        db.query(ExamAttempt)
        .filter(
            ExamAttempt.user_id == current_user.id,
            ExamAttempt.exam_id.in_(exam_ids),
        )
        .order_by(ExamAttempt.id.desc())
        .all()
    ):
        attempts_by_exam.setdefault(attempt.exam_id, []).append(attempt)

    result = []
    for session, exam in sessions:
        attempts = attempts_by_exam.get(exam.id, [])
        scores = [attempt.percentage for attempt in attempts]
        result.append(CustomSimulationSummarySchema(
            id=exam.id,
            title=exam.title,
            kind=session.kind,
            created_at=session.created_at,
            question_count=len(_decode_generated_question_ids(session)),
            attempt_count=len(attempts),
            best_score=round(max(scores), 1) if scores else None,
            last_score=round(attempts[0].percentage, 1) if attempts else None,
        ))
    return result


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
            gabarito_url=exam.gabarito_url,
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
    q_index = getattr(q, 'question_index', None) if not isinstance(q, dict) else q.get('question_index')
    item_id = getattr(q, 'id', 0) if hasattr(q, 'id') else (q.get('id', 0) if isinstance(q, dict) else 0) or 0
    # Âncora primária: índice da Cadeia de Encadeamento persistido pelo worker
    if isinstance(q_index, int):
        return (0, q_index, item_id)
    raw = str(getattr(q, 'numero_questao', None) or (q.get('numero_questao') if isinstance(q, dict) else '') or '').strip()
    if raw.isdigit():
        return (1, int(raw), item_id)
    m = re.match(r'^(\d+)', raw)
    if m:
        return (1, int(m.group(1)), item_id)
    return (2, item_id, raw)

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

        try:
            option_images_dict = json.loads(q.option_images) if q.option_images else {}
            if not isinstance(option_images_dict, dict):
                option_images_dict = {}
        except Exception:
            option_images_dict = {}

        is_latex = bool(q.latex_support) or ('$$' in q.statement or '\\frac' in q.statement or '\\sqrt' in q.statement)

        questions_list.append(QuestionSchema(
            id=q.id,
            numero_questao=str(idx) if is_generated_session else str(q.numero_questao or ""),
            statement=q.statement,
            options=options_dict,
            correct_answer=q.correct_answer,
            subject=q.subject or "Geral",
            images=secure_exam_image_urls(exam.id, images_list),
            option_images=secure_exam_option_image_urls(exam.id, option_images_dict),
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
        q_num = str(idx) if is_generated_session else str(q.numero_questao or idx)
        
        # Resolução polimórfica: busca prioritariamente por question.id, com fallback para numero_questao e idx
        raw_user_ans = (
            submission.answers.get(str(q.id))
            or submission.answers.get(q_num)
            or submission.answers.get(str(idx))
            or ""
        )
        user_ans = str(raw_user_ans).strip().upper()
        correct_ans = q.correct_answer.strip().upper() if q.correct_answer else ""
        
        is_correct = bool(correct_ans) and ((user_ans == correct_ans) or (correct_ans == 'X'))
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
    subjects: Optional[List[str]] = Query(default=None),
    source_exam_id: Optional[int] = Query(default=None, ge=1),
    strict: bool = Query(False),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Gera uma sessão persistida com filtros explícitos da biblioteca do usuário."""
    normalized_subjects = _normalized_subject_filters(subjects)
    query = _custom_question_query(db, current_user.id)
    if query is None:
        raise HTTPException(status_code=400, detail="Nenhuma questão disponível na sua biblioteca.")

    if normalized_subjects:
        subject_expression = func.coalesce(
            func.nullif(func.trim(Question.subject), ''),
            'Geral',
        )
        query = query.filter(subject_expression.in_(normalized_subjects))

    if source_exam_id is not None:
        query = query.filter(Question.exam_id == source_exam_id)

    available_count = int(query.count())
    if available_count < count and strict:
        raise HTTPException(
            status_code=400,
            detail=f"Há apenas {available_count} questões válidas para os filtros escolhidos; reduza a quantidade ou amplie a seleção.",
        )

    count = min(count, available_count)
    questions = query.order_by(func.random()).limit(count).all()
    if not questions:
        raise HTTPException(status_code=400, detail="Nenhuma questão disponível na sua biblioteca.")

    if len(normalized_subjects) == 1:
        title = f"Simulado personalizado · {normalized_subjects[0]} ({len(questions)} questões)"
    elif normalized_subjects:
        title = f"Simulado personalizado · {len(normalized_subjects)} disciplinas ({len(questions)} questões)"
    else:
        title = f"Simulado personalizado · Todas as disciplinas ({len(questions)} questões)"
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

        try:
            option_images_dict = json.loads(q.option_images) if q.option_images else {}
            if not isinstance(option_images_dict, dict):
                option_images_dict = {}
        except Exception:
            option_images_dict = {}

        is_latex = bool(q.latex_support) or ('$$' in q.statement or '\\frac' in q.statement)

        questions_list.append(QuestionSchema(
            id=q.id,
            numero_questao=str(idx),
            statement=q.statement,
            options=options_dict,
            correct_answer=q.correct_answer,
            subject=q.subject or "Geral",
            images=secure_exam_image_urls(exam.id, images_list),
            option_images=secure_exam_option_image_urls(exam.id, option_images_dict),
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
