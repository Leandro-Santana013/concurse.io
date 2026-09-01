import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from models.database import Exam, ExamSource, Question, UserExam


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "referrer",
}


def normalize_source_url(raw_url: str) -> str:
    """Normaliza URLs e caminhos locais sem remover parâmetros funcionais."""
    value = str(raw_url or "").strip()
    if not value:
        return ""

    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname.lower().rstrip(".")
        try:
            port = parsed.port
        except ValueError:
            port = None
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            netloc = f"{hostname}:{port}"
        else:
            netloc = hostname

        path = re.sub(r"/{2,}", "/", parsed.path or "/")
        if path != "/":
            path = path.rstrip("/")

        query_items = [
            (key, item_value)
            for key, item_value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
        ]
        query = urlencode(sorted(query_items))
        return urlunsplit((scheme, netloc, path, query, ""))

    clean_local = value.replace("file:///", "").replace("file://", "")
    return os.path.normcase(os.path.abspath(os.path.normpath(clean_local)))


def source_key(raw_url: str) -> str:
    normalized = normalize_source_url(raw_url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _question_count(db: Session, exam_id: int) -> int:
    return int(
        db.query(func.count(Question.id))
        .filter(Question.exam_id == exam_id)
        .scalar()
        or 0
    )


def is_exam_ready(db: Session, exam: Exam) -> bool:
    return exam.status == "Aprovada" and _question_count(db, exam.id) >= 5


def is_exam_processing(exam: Exam) -> bool:
    progress = exam.progress or 0
    return exam.status == "Processando" and 0 < progress < 100


def get_user_exam_ids(db: Session, user_id: int) -> set[int]:
    """Inclui vínculos novos e o proprietário legado para compatibilidade."""
    linked_ids = {
        row[0]
        for row in db.query(UserExam.exam_id)
        .filter(UserExam.user_id == user_id)
        .all()
    }
    linked_ids.update(
        row[0]
        for row in db.query(Exam.id)
        .filter(Exam.user_id == user_id)
        .all()
    )
    return linked_ids


def _best_legacy_exam(db: Session, normalized_url: str) -> Optional[Exam]:
    candidates = [
        exam
        for exam in db.query(Exam).filter(Exam.source_url.isnot(None)).all()
        if normalize_source_url(exam.source_url or "") == normalized_url
    ]
    if not candidates:
        return None

    def rank(exam: Exam) -> tuple[int, int, int, int]:
        question_count = _question_count(db, exam.id)
        return (
            int(exam.status == "Aprovada" and question_count >= 5),
            int(is_exam_processing(exam)),
            question_count,
            -exam.id,
        )

    return max(candidates, key=rank)


def _add_source_alias(db: Session, exam_id: int, raw_url: str) -> ExamSource:
    identity = ExamSource(
        source_key=source_key(raw_url),
        source_url=str(raw_url).strip()[:500],
        exam_id=exam_id,
        created_at=_now(),
    )
    db.add(identity)
    return identity


def register_exam_source_alias(db: Session, exam_id: int, raw_url: str) -> int:
    """Registra uma URL resolvida pelo worker sem sobrescrever outro canônico."""
    key = source_key(raw_url)
    existing = db.get(ExamSource, key)
    if existing is not None:
        return existing.exam_id

    try:
        _add_source_alias(db, exam_id, raw_url)
        db.commit()
        return exam_id
    except (IntegrityError, OperationalError):
        db.rollback()
        existing = db.get(ExamSource, key)
        return existing.exam_id if existing is not None else exam_id


@dataclass
class ExamClaim:
    exam: Exam
    should_process: bool
    reused: bool
    already_in_library: bool


def claim_exam_for_user(
    db: Session,
    *,
    user_id: int,
    raw_url: str,
    title: str,
    gabarito_url: Optional[str] = None,
    force_reprocess: bool = False,
) -> ExamClaim:
    """Obtém uma prova canônica e cria uma única associação por usuário."""
    normalized_url = normalize_source_url(raw_url)
    key = source_key(raw_url)

    for attempt in range(5):
        try:
            identity = (
                db.query(ExamSource)
                .filter(ExamSource.source_key == key)
                .with_for_update()
                .first()
            )
            exam = db.get(Exam, identity.exam_id) if identity is not None else None
            if identity is not None and exam is None:
                db.delete(identity)
                db.flush()
                identity = None
            created_exam = False

            if exam is None:
                exam = _best_legacy_exam(db, normalized_url)
                if exam is None:
                    exam = Exam(
                        title=(title or "Nova Prova de Concurso")[:300],
                        source_url=str(raw_url).strip()[:500],
                        gabarito_url=(gabarito_url[:500] if gabarito_url else None),
                        status="Processando",
                        progress=5,
                        progress_message="Iniciando download e processamento...",
                        user_id=user_id,
                    )
                    db.add(exam)
                    db.flush()
                    created_exam = True
                _add_source_alias(db, exam.id, raw_url)

            library_entry = (
                db.query(UserExam)
                .filter(
                    UserExam.user_id == user_id,
                    UserExam.exam_id == exam.id,
                )
                .first()
            )
            already_in_library = library_entry is not None or (
                not created_exam and exam.user_id == user_id
            )

            if library_entry is None:
                db.add(UserExam(
                    user_id=user_id,
                    exam_id=exam.id,
                    created_at=_now(),
                ))

            ready = is_exam_ready(db, exam)
            processing = is_exam_processing(exam)
            should_process = created_exam or force_reprocess or (not ready and not processing)

            if should_process:
                exam.status = "Processando"
                exam.progress = 5
                exam.progress_message = (
                    "Iniciando download e processamento..."
                    if created_exam
                    else "Reiniciando processamento..."
                )
                exam.error_type = None
                if created_exam or not exam.title or exam.title.startswith("Nova Prova"):
                    exam.title = (title or "Nova Prova de Concurso")[:300]
                if gabarito_url and (created_exam or not exam.gabarito_url):
                    exam.gabarito_url = gabarito_url[:500]

            db.commit()
            db.refresh(exam)
            return ExamClaim(
                exam=exam,
                should_process=should_process,
                reused=not created_exam,
                already_in_library=already_in_library,
            )
        except (IntegrityError, OperationalError):
            db.rollback()
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))

    raise RuntimeError("Não foi possível obter a prova canônica.")


def link_ready_exam_to_user(
    db: Session,
    *,
    user_id: int,
    exam_id: int,
) -> tuple[Exam, bool]:
    """Cria somente o vínculo de biblioteca para uma prova já processada."""
    exam = db.get(Exam, exam_id)
    if exam is None:
        raise LookupError("Prova não encontrada.")
    if not is_exam_ready(db, exam):
        raise ValueError("A prova ainda não está processada e aprovada.")

    existing = db.get(UserExam, (user_id, exam_id))
    already_in_library = existing is not None or exam.user_id == user_id
    if existing is not None:
        return exam, True

    try:
        db.add(UserExam(
            user_id=user_id,
            exam_id=exam_id,
            created_at=_now(),
        ))
        db.commit()
        db.refresh(exam)
        return exam, already_in_library
    except IntegrityError:
        db.rollback()
        existing = db.get(UserExam, (user_id, exam_id))
        if existing is None:
            raise
        exam = db.get(Exam, exam_id)
        return exam, True


def prepare_search_results_for_user(
    db: Session,
    cards: Iterable[Dict[str, Any]],
    user_id: int,
) -> List[Dict[str, Any]]:
    """Oculta itens já adicionados e marca provas prontas para reutilização."""
    card_list = [dict(card) for card in cards if card.get("url")]
    if not card_list:
        return []

    keys = {source_key(str(card["url"])) for card in card_list}
    identities = (
        db.query(ExamSource)
        .filter(ExamSource.source_key.in_(keys))
        .all()
    )
    exams_by_key = {
        identity.source_key: identity.exam
        for identity in identities
        if identity.exam is not None
    }

    unresolved_keys = keys.difference(exams_by_key)
    if unresolved_keys:
        for card in card_list:
            key = source_key(str(card["url"]))
            if key not in unresolved_keys or key in exams_by_key:
                continue
            legacy_exam = _best_legacy_exam(db, normalize_source_url(str(card["url"])))
            if legacy_exam is not None:
                exams_by_key[key] = legacy_exam

    user_exam_ids = get_user_exam_ids(db, user_id)
    exam_ids = {exam.id for exam in exams_by_key.values()}
    question_counts = dict(
        db.query(Question.exam_id, func.count(Question.id))
        .filter(Question.exam_id.in_(exam_ids))
        .group_by(Question.exam_id)
        .all()
    ) if exam_ids else {}

    prepared: List[Dict[str, Any]] = []
    seen_exam_ids: set[int] = set()
    seen_source_keys: set[str] = set()

    for card in card_list:
        key = source_key(str(card["url"]))
        exam = exams_by_key.get(key)
        if exam is not None:
            if exam.id in user_exam_ids or exam.id in seen_exam_ids:
                continue
            seen_exam_ids.add(exam.id)
            ready = exam.status == "Aprovada" and int(question_counts.get(exam.id, 0)) >= 5
            card.update({
                "id": exam.id,
                "title": exam.title or card.get("title") or "Prova de Concurso",
                "status": exam.status or "Pendente",
                "reuse_available": ready,
                "has_gabarito_link": bool(exam.has_official_answers or card.get("gabarito_url")),
            })
        else:
            if key in seen_source_keys:
                continue
            seen_source_keys.add(key)
            card.update({
                "id": None,
                "status": card.get("status") or "Pendente",
                "reuse_available": False,
            })
        prepared.append(card)

    return prepared
