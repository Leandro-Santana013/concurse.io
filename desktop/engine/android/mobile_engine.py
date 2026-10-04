"""Android entry point for the same processing API shipped on desktop.

Only the working database lives here. The frontend reads the central library
and submits the finished extraction to Supabase and the media gateway.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path


_android_context = None


def run(data_dir: str, supabase_url: str, publishable_key: str, android_context=None) -> None:
    global _android_context
    _android_context = android_context
    data_root = Path(data_dir).resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    key_path = data_root / ".engine-key"
    if not key_path.exists():
        # The Android app-private directory prevents other apps from reading it.
        with key_path.open("x", encoding="ascii") as stream:
            stream.write(secrets.token_urlsafe(48))
    os.environ.update({
        "CONCURSE_DATA_ROOT": str(data_root),
        "DATABASE_URL": f"sqlite:///{(data_root / 'processing.db').as_posix()}",
        "AUTH_DEV_BYPASS": "false",
        "SESSION_SECRET": key_path.read_text(encoding="ascii"),
        "SUPABASE_URL": supabase_url,
        "SUPABASE_PUBLISHABLE_KEY": publishable_key,
        "CORS_ORIGINS": "http://tauri.localhost,https://tauri.localhost",
        "CONCURSE_EMBEDDED_ANDROID": "1",
    })
    os.environ["USER_DATA_ENCRYPTION_KEY"] = os.environ["SESSION_SECRET"]
    os.environ["OMP_NUM_THREADS"] = "2"
    os.chdir(data_root)
    import uvicorn
    from fastapi_app import app

    uvicorn.run(app, host="127.0.0.1", port=45873, loop="asyncio", http="h11",
                log_level="warning", access_log=False)


def processing_started() -> None:
    from java import jclass
    jclass("io.concurse.desktop.ProcessingService").begin(_android_context)


def processing_finished() -> None:
    from java import jclass
    jclass("io.concurse.desktop.ProcessingService").end(_android_context)
