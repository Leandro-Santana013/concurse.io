import os
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

from models.database import init_db
from routes.api_v1 import api_v1_router

load_dotenv()

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Arquivos de Mídia Estáticos
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# 2. Roteadores da API V1
app.include_router(api_v1_router)

@app.get("/health")
def healthcheck():
    return {
        "status": "healthy",
        "service": "concurse.io FastAPI",
        "version": "2.0.0"
    }

# 3. Montagem do Frontend React (SPA)
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="frontend_assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
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
