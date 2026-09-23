"""FastAPI local embutida no aplicativo desktop.

O processo usa o mesmo banco, worker e pipeline OCR do projeto, mas grava tudo
na pasta de dados do aplicativo. Ele não depende de uma API FastAPI externa.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_SUPABASE_URL = "https://pvojiokewtteroaraykk.supabase.co"
# This is a publishable client key, not a service-role secret.
DEFAULT_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_B_5ggWu2WVGYsi02iyN1Ng_HBBRBW9F"


def _repository_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path.cwd())).resolve()
    return Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=45873)
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args()

    data_root = Path(args.data_dir).expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    os.environ["CONCURSE_DATA_ROOT"] = str(data_root)
    os.environ["DATABASE_URL"] = f"sqlite:///{(data_root / 'concurse-desktop.db').as_posix()}"
    os.environ["AUTH_DEV_BYPASS"] = os.environ.get("CONCURSE_LOCAL_AUTH_DEV_BYPASS", "false")
    os.environ.setdefault("SUPABASE_URL", DEFAULT_SUPABASE_URL)
    os.environ.setdefault("SUPABASE_PUBLISHABLE_KEY", DEFAULT_SUPABASE_PUBLISHABLE_KEY)
    os.environ.setdefault("SESSION_SECRET", "concurse-desktop-local-session-2026")
    os.environ.setdefault("USER_DATA_ENCRYPTION_KEY", os.environ["SESSION_SECRET"])
    os.environ["CORS_ORIGINS"] = ",".join(
        {
            "http://tauri.localhost",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }
    )
    os.chdir(data_root)

    root = _repository_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import uvicorn
    from fastapi_app import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
