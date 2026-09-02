import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app_security import (
    UserDataCryptoError,
    decrypt_user_data,
    encrypt_user_data,
    identifier_lookup_values,
    protect_identifier,
)
from models.database import User
from models import database as database_module


def test_user_data_uses_authenticated_encryption(monkeypatch):
    monkeypatch.setenv("USER_DATA_ENCRYPTION_KEY", "active-user-data-key-with-more-than-32-bytes")
    monkeypatch.delenv("USER_DATA_ENCRYPTION_KEY_PREVIOUS", raising=False)

    ciphertext = encrypt_user_data("pessoa@example.com", "email")

    assert ciphertext.startswith("enc:v1:")
    assert "pessoa@example.com" not in ciphertext
    assert decrypt_user_data(ciphertext, "email") == "pessoa@example.com"

    payload_start = ciphertext.rfind(":") + 1
    tamper_index = payload_start + 5
    replacement = "A" if ciphertext[tamper_index] != "A" else "B"
    tampered = ciphertext[:tamper_index] + replacement + ciphertext[tamper_index + 1:]
    with pytest.raises(UserDataCryptoError):
        decrypt_user_data(tampered, "email")


def test_key_rotation_keeps_old_ciphertext_readable(monkeypatch):
    old_key = "old-user-data-key-with-more-than-32-bytes"
    new_key = "new-user-data-key-with-more-than-32-bytes"
    monkeypatch.setenv("USER_DATA_ENCRYPTION_KEY", old_key)
    old_ciphertext = encrypt_user_data("Pessoa", "name")
    old_identifier = protect_identifier("google-subject")

    monkeypatch.setenv("USER_DATA_ENCRYPTION_KEY", new_key)
    monkeypatch.setenv("USER_DATA_ENCRYPTION_KEY_PREVIOUS", old_key)

    assert decrypt_user_data(old_ciphertext, "name") == "Pessoa"
    candidates = identifier_lookup_values("google-subject")
    assert old_identifier in candidates
    assert protect_identifier("google-subject") in candidates


def test_user_model_never_places_plain_pii_in_legacy_columns(monkeypatch):
    monkeypatch.setenv("USER_DATA_ENCRYPTION_KEY", "model-user-data-key-with-more-than-32-bytes")
    user = User(
        google_id="google-sub-123",
        email="pessoa@example.com",
        name="Pessoa Estudante",
        picture="https://example.test/avatar.png",
    )

    assert user.google_subject_hash.startswith("hmac:v1:")
    assert user._email_legacy.startswith("private+")
    assert user._email_legacy != "pessoa@example.com"
    assert user._name_legacy is None
    assert user._picture_legacy is None
    assert user._email_encrypted.startswith("enc:v1:")
    assert user.email == "pessoa@example.com"
    assert user.name == "Pessoa Estudante"
    assert user.picture == "https://example.test/avatar.png"


def test_legacy_user_rows_are_backfilled_idempotently(monkeypatch):
    monkeypatch.setenv("USER_DATA_ENCRYPTION_KEY", "migration-user-data-key-with-more-than-32-bytes")
    legacy_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with legacy_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, google_id VARCHAR(200) NOT NULL UNIQUE, "
            "email VARCHAR(200) NOT NULL, name VARCHAR(200), picture VARCHAR(500))"
        ))
        connection.execute(text(
            "INSERT INTO users (id, google_id, email, name, picture) "
            "VALUES (1, 'legacy-google-id', 'legacy@example.com', 'Legacy', "
            "'https://example.test/legacy.png')"
        ))

    monkeypatch.setattr(database_module, "engine", legacy_engine)
    database_module._ensure_user_security_columns()
    assert database_module._migrate_user_security_rows() == 1
    assert database_module._migrate_user_security_rows() == 0

    with legacy_engine.connect() as connection:
        row = connection.execute(text(
            "SELECT google_id, email, name, picture, email_encrypted, "
            "name_encrypted, picture_encrypted FROM users WHERE id = 1"
        )).mappings().one()

    assert row["google_id"].startswith("hmac:v1:")
    assert row["email"].startswith("private+")
    assert row["name"] is None
    assert row["picture"] is None
    assert decrypt_user_data(row["email_encrypted"], "email") == "legacy@example.com"
    assert decrypt_user_data(row["name_encrypted"], "name") == "Legacy"
    assert decrypt_user_data(row["picture_encrypted"], "picture") == "https://example.test/legacy.png"
    legacy_engine.dispose()
