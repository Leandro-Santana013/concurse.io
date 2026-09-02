import os

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from models.database import Exam, User, UserExam, get_db
from app_security import identifier_lookup_values
from services.auth import SESSION_COOKIE, read_session_token


def _dev_bypass_enabled() -> bool:
    return os.environ.get("AUTH_DEV_BYPASS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_or_create_dev_user(db: Session) -> User:
    identifiers = identifier_lookup_values("default_dev_user")
    user = db.query(User).filter(User.google_subject_hash.in_(identifiers)).first()
    if user is None:
        user = User(
            google_id="default_dev_user",
            email="dev@concurse.io",
            name="Concurseiro Dev",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_accessible_exam_or_404(db: Session, *, user_id: int, exam_id: int) -> Exam:
    """Oculta a existência de provas fora da biblioteca/propriedade do usuário."""
    exam = db.get(Exam, int(exam_id))
    if exam is None:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")

    is_legacy_owner = exam.user_id == int(user_id)
    is_in_library = db.get(UserExam, (int(user_id), int(exam_id))) is not None
    if not is_legacy_owner and not is_in_library:
        raise HTTPException(status_code=404, detail="Prova não encontrada.")
    return exam


def require_admin_user(current_user: User) -> User:
    """Bloqueia operações globais salvo allowlist explícita e fechada por padrão."""
    configured_ids = {
        int(raw_id)
        for raw_id in os.environ.get("APP_ADMIN_USER_IDS", "").split(",")
        if raw_id.strip().isdigit()
    }
    if current_user.id not in configured_ids:
        raise HTTPException(status_code=403, detail="Operação administrativa não autorizada.")
    return current_user


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Resolve o usuário por injeção de teste ou cookie de sessão assinado."""
    state_user = getattr(request.state, "user", None)
    state_user_id = getattr(request.state, "user_id", None)
    scope_user = request.scope.get("user")

    candidate_id = state_user_id
    if candidate_id is None and state_user is not None:
        candidate_id = getattr(state_user, "id", None)
    if candidate_id is None and scope_user is not None:
        candidate_id = getattr(scope_user, "id", None)
    if candidate_id is None:
        candidate_id = read_session_token(request.cookies.get(SESSION_COOKIE))

    if candidate_id is not None:
        try:
            user_id = int(candidate_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=401, detail="Usuário autenticado inválido.")

        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Usuário autenticado não encontrado.")
        return user

    if _dev_bypass_enabled():
        return _get_or_create_dev_user(db)

    raise HTTPException(
        status_code=401,
        detail="Faça login para continuar.",
        headers={"WWW-Authenticate": "Cookie"},
    )
