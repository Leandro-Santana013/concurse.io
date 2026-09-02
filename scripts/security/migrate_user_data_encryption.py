"""Audita e aplica a migração criptográfica dos usuários com backup cifrado.

Uso:
    python scripts/security/migrate_user_data_encryption.py
    python scripts/security/migrate_user_data_encryption.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app_security import encrypt_user_data  # noqa: E402


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        value = f"sqlite:///{(PROJECT_ROOT / 'concurse.db').as_posix()}"
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql://", 1)
    return value


def _snapshot_users(engine) -> list[dict]:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return []
    available = {column["name"] for column in inspector.get_columns("users")}
    columns = [name for name in ("id", "google_id", "email", "name", "picture") if name in available]
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(
            f"SELECT {', '.join(columns)} FROM users ORDER BY id"
        )).mappings().all()]


def _write_encrypted_backup(rows: list[dict]) -> Path:
    backup_dir = PROJECT_ROOT / ".codex-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"users-pre-encryption-{timestamp}.json.enc"
    payload = json.dumps(
        {"version": 1, "created_at": timestamp, "users": rows},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    encrypted = encrypt_user_data(payload, "migration-backup")
    if not encrypted:
        raise RuntimeError("Não foi possível criar o backup criptografado.")
    destination.write_text(encrypted, encoding="utf-8")
    return destination


def _verify(engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            "total": int(connection.execute(text("SELECT COUNT(*) FROM users")).scalar() or 0),
            "raw_google_ids": int(connection.execute(text(
                "SELECT COUNT(*) FROM users WHERE google_id NOT LIKE :pattern"
            ), {"pattern": "hmac:v1:%"}).scalar() or 0),
            "raw_emails": int(connection.execute(text(
                "SELECT COUNT(*) FROM users WHERE email NOT LIKE :pattern"
            ), {"pattern": "private+%@users.invalid"}).scalar() or 0),
            "encrypted_emails": int(connection.execute(text(
                "SELECT COUNT(*) FROM users WHERE email_encrypted LIKE :pattern"
            ), {"pattern": "enc:v1:%"}).scalar() or 0),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migração de dados pessoais para AES-GCM.")
    parser.add_argument("--apply", action="store_true", help="Cria backup cifrado e aplica a migração.")
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    audit_engine = create_engine(_database_url(), pool_pre_ping=True)
    rows = _snapshot_users(audit_engine)
    columns = {column["name"] for column in inspect(audit_engine).get_columns("users")}
    missing = sorted({"email_encrypted", "name_encrypted", "picture_encrypted"} - columns)
    print(f"Usuários encontrados: {len(rows)}")
    print(f"Colunas pendentes: {', '.join(missing) if missing else 'nenhuma'}")
    if not args.apply:
        audit_engine.dispose()
        print("Auditoria concluída; use --apply para migrar.")
        return 0

    backup_path = _write_encrypted_backup(rows)
    print(f"Backup criptografado criado: {backup_path}")
    audit_engine.dispose()

    from models import database as database_module

    database_module.init_db()
    verification = _verify(database_module.engine)
    print(f"Usuários verificados: {verification['total']}")
    print(f"Identificadores brutos restantes: {verification['raw_google_ids']}")
    print(f"E-mails brutos restantes: {verification['raw_emails']}")
    print(f"E-mails criptografados: {verification['encrypted_emails']}")
    return 0 if (
        verification["raw_google_ids"] == 0
        and verification["raw_emails"] == 0
        and verification["encrypted_emails"] == verification["total"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
