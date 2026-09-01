from fastapi import APIRouter, Depends

from routes.api_v1.user_context import get_current_user

router = APIRouter()

@router.get("/auth/me")
def get_current_user_profile(current_user=Depends(get_current_user)):
    """Retorna o perfil do usuário logado."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name or "Concurseiro",
        "picture": current_user.picture or "",
        "is_authenticated": True
    }
