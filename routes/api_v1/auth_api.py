from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.database import get_db, User

router = APIRouter()

@router.get("/auth/me")
def get_current_user_profile(db: Session = Depends(get_db)):
    """Retorna o perfil do usuário logado."""
    user = db.query(User).first()
    if not user:
        user = User(google_id="default_dev_user", email="dev@concurse.io", name="Concurseiro Dev")
        db.add(user)
        db.commit()
        db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name or "Concurseiro",
        "picture": user.picture or "",
        "is_authenticated": True
    }
