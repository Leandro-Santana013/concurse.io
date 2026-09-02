import os
import tempfile
from pathlib import Path


_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"concurse-pytest-{os.getpid()}.db"

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB_PATH.as_posix()}")
os.environ.setdefault("SESSION_SECRET", "pytest-session-secret-with-at-least-32-bytes")
os.environ.setdefault("USER_DATA_ENCRYPTION_KEY", "pytest-user-data-key-with-at-least-32-bytes")
os.environ.setdefault("AUTH_DEV_BYPASS", "false")


def pytest_sessionfinish(session, exitstatus):
    for suffix in ("", "-shm", "-wal", "-journal"):
        candidate = Path(f"{_TEST_DB_PATH}{suffix}")
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass
