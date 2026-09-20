"""Optional Oracle Object Storage adapter used by the authenticated API.

The desktop and mobile clients never receive OCI API keys.  They continue to
call the concurse.io API, which checks the user's library before reading or
writing an object.  This module is deliberately optional so local development
and the existing local-media tests keep working when OCI is not configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote


class ObjectStorageError(RuntimeError):
    """Base error for a configured but unavailable Object Storage backend."""


class ObjectStorageNotConfigured(ObjectStorageError):
    """Raised when OCI credentials or bucket settings are incomplete."""


@dataclass(frozen=True)
class ObjectStorageSettings:
    namespace: str
    bucket: str
    region: str
    tenancy: str
    user: str
    fingerprint: str
    private_key: str
    private_key_passphrase: str | None
    question_prefix: str

    @classmethod
    def from_environment(cls) -> "ObjectStorageSettings":
        """Read server-only OCI settings from environment variables.

        ``OCI_OBJECT_STORAGE_*`` is the preferred namespace.  The shorter
        aliases are accepted so the same settings can be used with OCI CLI
        deployments without copying the private key into the client builds.
        """

        def value(*names: str) -> str:
            for name in names:
                configured = os.environ.get(name, "").strip()
                if configured:
                    return configured
            return ""

        private_key = value(
            "OCI_OBJECT_STORAGE_PRIVATE_KEY",
            "OCI_PRIVATE_KEY",
        )
        private_key_file = value(
            "OCI_OBJECT_STORAGE_PRIVATE_KEY_FILE",
            "OCI_PRIVATE_KEY_FILE",
        )
        if not private_key and private_key_file:
            try:
                private_key = Path(private_key_file).expanduser().read_text(encoding="utf-8")
            except OSError as exc:
                raise ObjectStorageError(
                    "Não foi possível ler OCI_OBJECT_STORAGE_PRIVATE_KEY_FILE."
                ) from exc
        # Docker/secret stores commonly encode newlines as the two characters
        # ``\\n``.  Normalize them only on the server, never in the app bundle.
        private_key = private_key.replace("\\n", "\n")

        question_prefix = value("OCI_OBJECT_STORAGE_QUESTION_PREFIX") or "questions"
        return cls(
            namespace=value("OCI_OBJECT_STORAGE_NAMESPACE", "OCI_NAMESPACE"),
            bucket=value("OCI_OBJECT_STORAGE_BUCKET", "OCI_BUCKET"),
            region=value("OCI_OBJECT_STORAGE_REGION", "OCI_REGION") or "sa-saopaulo-1",
            tenancy=value("OCI_OBJECT_STORAGE_TENANCY", "OCI_TENANCY"),
            user=value("OCI_OBJECT_STORAGE_USER", "OCI_USER"),
            fingerprint=value("OCI_OBJECT_STORAGE_FINGERPRINT", "OCI_FINGERPRINT"),
            private_key=private_key,
            private_key_passphrase=(
                value(
                    "OCI_OBJECT_STORAGE_PRIVATE_KEY_PASSPHRASE",
                    "OCI_PRIVATE_KEY_PASSPHRASE",
                )
                or None
            ),
            question_prefix=question_prefix.strip("/"),
        )

    @property
    def configured(self) -> bool:
        return all(
            (
                self.namespace,
                self.bucket,
                self.region,
                self.tenancy,
                self.user,
                self.fingerprint,
                self.private_key,
            )
        )


@dataclass(frozen=True)
class StoredObject:
    content: bytes
    content_type: str
    etag: str | None = None


def _safe_filename(filename: str) -> str:
    normalized = unquote(str(filename or "").strip()).replace("\\", "/").lstrip("/")
    if not normalized or "/" in normalized or normalized in {".", ".."}:
        raise ValueError("Nome de mídia inválido.")
    return normalized


def question_object_key(filename: str, settings: ObjectStorageSettings | None = None) -> str:
    """Return the stable object key for a legacy question image filename."""

    settings = settings or ObjectStorageSettings.from_environment()
    return f"{settings.question_prefix}/{_safe_filename(filename)}"


def exam_pdf_object_key(exam_id: int, kind: str = "prova") -> str:
    """Return the canonical key used for an exam PDF or answer key PDF."""

    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in {"prova", "gabarito"}:
        raise ValueError("O tipo do PDF deve ser 'prova' ou 'gabarito'.")
    return f"exams/{int(exam_id)}/{normalized_kind}.pdf"


def object_storage_configured() -> bool:
    return ObjectStorageSettings.from_environment().configured


@lru_cache(maxsize=1)
def _client_for_settings(settings: ObjectStorageSettings) -> Any:
    if not settings.configured:
        raise ObjectStorageNotConfigured(
            "Object Storage não configurado; use a mídia local ou preencha os segredos OCI no servidor."
        )
    try:
        import oci  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised in deployment only
        raise ObjectStorageError(
            "O SDK OCI não está instalado. Adicione o pacote 'oci' ao ambiente da API."
        ) from exc

    config = {
        "user": settings.user,
        "tenancy": settings.tenancy,
        "region": settings.region,
        "fingerprint": settings.fingerprint,
        # Signer accepts the PEM content directly; no key is shipped to apps.
        "key_content": settings.private_key,
    }
    signer = oci.signer.Signer(
        tenancy=settings.tenancy,
        user=settings.user,
        fingerprint=settings.fingerprint,
        private_key_file_location=None,
        pass_phrase=settings.private_key_passphrase,
        private_key_content=settings.private_key,
    )
    return oci.object_storage.ObjectStorageClient(config, signer=signer)


def _read_body(data: Any) -> bytes:
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    content = getattr(data, "content", None)
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    reader = getattr(data, "read", None)
    if callable(reader):
        value = reader()
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
    raise ObjectStorageError("A resposta do Object Storage não contém bytes legíveis.")


def get_object(object_key: str) -> StoredObject | None:
    """Read an object, returning ``None`` for a normal OCI 404."""

    settings = ObjectStorageSettings.from_environment()
    if not settings.configured:
        return None
    try:
        client = _client_for_settings(settings)
        response = client.get_object(
            namespace_name=settings.namespace,
            bucket_name=settings.bucket,
            object_name=object_key,
        )
    except Exception as exc:  # SDK type is optional until deployment
        if getattr(exc, "status", None) == 404:
            return None
        if isinstance(exc, ObjectStorageError):
            raise
        raise ObjectStorageError("Falha ao ler o objeto no Oracle Object Storage.") from exc

    headers = getattr(response, "headers", {}) or {}
    content_type = headers.get("content-type") or mimetypes.guess_type(object_key)[0]
    return StoredObject(
        content=_read_body(getattr(response, "data", response)),
        content_type=content_type or "application/octet-stream",
        etag=headers.get("etag"),
    )


def put_object(
    object_key: str,
    content: bytes,
    *,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    """Upload an object from the trusted API/ingestion process."""

    settings = ObjectStorageSettings.from_environment()
    if not settings.configured:
        raise ObjectStorageNotConfigured("Object Storage não está configurado no servidor.")
    try:
        client = _client_for_settings(settings)
        client.put_object(
            namespace_name=settings.namespace,
            bucket_name=settings.bucket,
            object_name=object_key,
            put_object_body=BytesIO(content),
            content_type=content_type or mimetypes.guess_type(object_key)[0] or "application/octet-stream",
            opc_meta=metadata or {},
        )
    except Exception as exc:  # SDK type is optional until deployment
        if isinstance(exc, ObjectStorageError):
            raise
        raise ObjectStorageError("Falha ao gravar o objeto no Oracle Object Storage.") from exc


def put_file(
    object_key: str,
    path: str | Path,
    *,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    """Upload a local artifact without loading the complete file in RAM."""

    settings = ObjectStorageSettings.from_environment()
    if not settings.configured:
        raise ObjectStorageNotConfigured("Object Storage não está configurado no servidor.")
    source = Path(path)
    try:
        size = source.stat().st_size
        stream = source.open("rb")
    except OSError as exc:
        raise ObjectStorageError("Não foi possível abrir o artefato para upload.") from exc

    try:
        client = _client_for_settings(settings)
        client.put_object(
            namespace_name=settings.namespace,
            bucket_name=settings.bucket,
            object_name=object_key,
            put_object_body=stream,
            content_length=size,
            content_type=content_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream",
            opc_meta=metadata or {},
        )
    except Exception as exc:  # SDK type is optional until deployment
        if isinstance(exc, ObjectStorageError):
            raise
        raise ObjectStorageError("Falha ao gravar o artefato no Oracle Object Storage.") from exc
    finally:
        stream.close()
