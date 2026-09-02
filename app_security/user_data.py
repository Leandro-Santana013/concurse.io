"""Criptografia autenticada e índices cegos para dados pessoais.

O servidor precisa ler nome/e-mail para entregar a aplicação, então este módulo
protege esses campos em repouso. O identificador do Google é transformado em um
índice HMAC determinístico: ele continua pesquisável sem guardar o valor bruto.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Iterable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ENCRYPTED_PREFIX = "enc:v1:"
IDENTIFIER_PREFIX = "hmac:v1:"
MINIMUM_SECRET_BYTES = 24


class UserDataCryptoError(RuntimeError):
    """Configuração ausente ou dado criptografado inválido."""


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _configured_secrets() -> tuple[bytes, ...]:
    """Retorna chave ativa e chaves anteriores para rotação sem perda de dados."""
    explicit_active = os.environ.get("USER_DATA_ENCRYPTION_KEY", "")
    explicit_previous = os.environ.get("USER_DATA_ENCRYPTION_KEY_PREVIOUS", "")
    session_fallback = os.environ.get("SESSION_SECRET") or os.environ.get("FLASK_SECRET_KEY") or ""

    raw_values = _unique(
        [explicit_active]
        + explicit_previous.split(",")
        + [session_fallback]
    )
    if not raw_values:
        raise UserDataCryptoError(
            "Configure USER_DATA_ENCRYPTION_KEY ou SESSION_SECRET antes de acessar dados pessoais."
        )

    encoded = tuple(value.encode("utf-8") for value in raw_values)
    if len(encoded[0]) < MINIMUM_SECRET_BYTES:
        raise UserDataCryptoError(
            "USER_DATA_ENCRYPTION_KEY/SESSION_SECRET precisa ter pelo menos 24 bytes."
        )
    return encoded


def _derive(master: bytes, purpose: bytes) -> bytes:
    return hmac.new(master, b"concurse.io\x00" + purpose, hashlib.sha256).digest()


def _key_id(master: bytes) -> str:
    return hashlib.sha256(b"concurse.io:key-id\x00" + master).hexdigest()[:12]


def _encryption_key(master: bytes) -> bytes:
    return _derive(master, b"user-data:aes-gcm:v1")


def _identifier_key(master: bytes) -> bytes:
    return _derive(master, b"google-sub:hmac:v1")


def _aad(field: str) -> bytes:
    normalized = str(field or "unknown").strip().lower()
    return f"concurse.io:user-data:{normalized}:v1".encode("utf-8")


def is_encrypted_user_data(value: object) -> bool:
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def is_encrypted_with_active_key(value: object) -> bool:
    if not is_encrypted_user_data(value):
        return False
    remainder = str(value)[len(ENCRYPTED_PREFIX):]
    stored_key_id = remainder.split(":", 1)[0]
    return stored_key_id == _key_id(_configured_secrets()[0])


def encrypt_user_data(value: object, field: str) -> str | None:
    if value is None:
        return None
    plaintext = str(value)
    if not plaintext:
        return None

    master = _configured_secrets()[0]
    nonce = os.urandom(12)
    ciphertext = AESGCM(_encryption_key(master)).encrypt(
        nonce,
        plaintext.encode("utf-8"),
        _aad(field),
    )
    return f"{ENCRYPTED_PREFIX}{_key_id(master)}:{_b64encode(nonce + ciphertext)}"


def decrypt_user_data(value: object, field: str) -> str | None:
    if value is None:
        return None
    encoded = str(value)
    if not encoded:
        return ""
    if not is_encrypted_user_data(encoded):
        return encoded

    try:
        remainder = encoded[len(ENCRYPTED_PREFIX):]
        stored_key_id, payload = remainder.split(":", 1)
        packed = _b64decode(payload)
        nonce, ciphertext = packed[:12], packed[12:]
        if len(nonce) != 12 or not ciphertext:
            raise ValueError("payload incompleto")
    except (TypeError, ValueError) as exc:
        raise UserDataCryptoError("Formato de dado pessoal criptografado inválido.") from exc

    secrets = _configured_secrets()
    ordered = sorted(secrets, key=lambda secret: _key_id(secret) != stored_key_id)
    for master in ordered:
        if _key_id(master) != stored_key_id:
            continue
        try:
            plaintext = AESGCM(_encryption_key(master)).decrypt(
                nonce,
                ciphertext,
                _aad(field),
            )
            return plaintext.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError):
            break
    raise UserDataCryptoError("Não foi possível autenticar o dado pessoal criptografado.")


def is_protected_identifier(value: object) -> bool:
    return isinstance(value, str) and value.startswith(IDENTIFIER_PREFIX)


def _protect_identifier_with(master: bytes, value: str) -> str:
    digest = hmac.new(
        _identifier_key(master),
        value.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return f"{IDENTIFIER_PREFIX}{_key_id(master)}:{_b64encode(digest)}"


def protect_identifier(value: object) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise UserDataCryptoError("Identificador de usuário vazio.")
    if is_protected_identifier(normalized):
        return normalized
    return _protect_identifier_with(_configured_secrets()[0], normalized)


def identifier_lookup_values(value: object) -> tuple[str, ...]:
    """Gera índices para a chave ativa, chaves antigas e linha legada em texto puro."""
    normalized = str(value or "").strip()
    if not normalized:
        return ()
    if is_protected_identifier(normalized):
        return (normalized,)
    protected = [_protect_identifier_with(master, normalized) for master in _configured_secrets()]
    return _unique(protected + [normalized])


def pseudonymous_email(value: object) -> str:
    normalized = str(value or "").strip().casefold()
    if not normalized:
        normalized = "unknown"
    master = _configured_secrets()[0]
    digest = hmac.new(
        _derive(master, b"email-placeholder:hmac:v1"),
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:28]
    return f"private+{digest}@users.invalid"


def is_pseudonymous_email(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized.startswith("private+") and normalized.endswith("@users.invalid")
