from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from models.database import User, get_db


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Resolve o usuário autenticado injetado pela aplicação, com fallback local."""
    state_user = getattr(request.state, "user", None)
    state_user_id = getattr(request.state, "user_id", None)
    scope_user = request.scope.get("user")

    candidate_id = state_user_id
    if candidate_id is None and state_user is not None:
        candidate_id = getattr(state_user, "id", None)
    if candidate_id is None and scope_user is not None:
        candidate_id = getattr(scope_user, "id", None)

    if candidate_id is not None:
        try:
            user_id = int(candidate_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=401, detail="Usuário autenticado inválido.")

        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Usuário autenticado não encontrado.")
        return user

    user = db.query(User).order_by(User.id.asc()).first()
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
