import os
import sys
import logging
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from dotenv import load_dotenv

from models.database import init_db
from routes.api_v1 import api_v1_router

load_dotenv()


class _OAuthAccessLogFilter(logging.Filter):
    """Impede que código/state OAuth apareçam no access log do Uvicorn."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            path = args[2]
            if isinstance(path, str) and path.startswith("/api/v1/auth/google/callback?"):
                args[2] = "/api/v1/auth/google/callback?[REDACTED]"
                record.args = tuple(args)
        return True


logging.getLogger("uvicorn.access").addFilter(_OAuthAccessLogFilter())


def _cors_origins():
    configured = os.environ.get("CORS_ORIGINS", "")
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    os.makedirs('static/images/questions', exist_ok=True)
    os.makedirs('pdfs', exist_ok=True)
    print("[concurse.io] FastAPI ASGI inicializado com sucesso!", flush=True)
    yield
    print("[concurse.io] FastAPI desligado.", flush=True)

app = FastAPI(
    title="concurse.io API",
    description="API assíncrona de alta performance para busca, leitura de PDFs e plataforma de simulados de concursos.",
    version="2.0.0",
    lifespan=lifespan
)


def _env_flag(name: str, default: bool = False) -> bool:
    configured = os.environ.get(name)
    if configured is None:
        return default
    return configured.strip().lower() in {"1", "true", "yes", "on"}


def _is_https_request(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    return request.url.scheme == "https" or forwarded_proto == "https"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    is_https = _is_https_request(request)
    if _env_flag("FORCE_HTTPS") and not is_https:
        secure_url = request.url.replace(scheme="https")
        return RedirectResponse(str(secure_url), status_code=307)

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith("/api/v1/auth"):
        response.headers["Cache-Control"] = "no-store"
    if is_https:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Roteadores da API V1 (a mídia de provas é entregue por rota autenticada)
app.include_router(api_v1_router)

@app.get("/health")
def healthcheck():
    return {
        "status": "healthy",
        "service": "concurse.io FastAPI",
        "version": "2.0.0"
    }

# 2. Montagem do Frontend React (SPA)
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="frontend_assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith(("api/", "docs", "openapi.json", "static/")):
            return JSONResponse(status_code=404, content={"error": "Not Found"})
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return JSONResponse(status_code=404, content={"error": "Frontend build not found"})
else:
    @app.get("/")
    def root_fallback():
        return {
            "name": "concurse.io API V2",
            "docs_url": "/docs",
            "status": "Backend running. Run 'npm run dev' inside frontend/ for development."
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fastapi_app:app", host="0.0.0.0", port=8000, reload=True)
