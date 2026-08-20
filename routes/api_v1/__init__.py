from fastapi import APIRouter
from .exam_api import router as exam_router
from .search_api import router as search_router
from .stats_api import router as stats_router
from .auth_api import router as auth_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(exam_router, tags=["Exams"])
api_v1_router.include_router(search_router, tags=["Search & Ingestion"])
api_v1_router.include_router(stats_router, tags=["Stats & Analytics"])
api_v1_router.include_router(auth_router, tags=["Auth & Profile"])
