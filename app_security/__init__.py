"""Primitivas de segurança independentes da camada HTTP e do banco."""

from .user_data import (
    UserDataCryptoError,
    decrypt_user_data,
    encrypt_user_data,
    identifier_lookup_values,
    is_encrypted_with_active_key,
    is_encrypted_user_data,
    is_pseudonymous_email,
    is_protected_identifier,
    protect_identifier,
    pseudonymous_email,
)

__all__ = [
    "UserDataCryptoError",
    "decrypt_user_data",
    "encrypt_user_data",
    "identifier_lookup_values",
    "is_encrypted_with_active_key",
    "is_encrypted_user_data",
    "is_pseudonymous_email",
    "is_protected_identifier",
    "protect_identifier",
    "pseudonymous_email",
]
