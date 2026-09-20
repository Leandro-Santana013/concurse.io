"""Normalização e entrega de mídia privada vinculada a uma prova."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from models.database import Exam, get_db, resolve_exam_questions
from routes.api_v1.user_context import get_accessible_exam_or_404, get_current_user
from services.object_storage import ObjectStorageError, get_object, question_object_key
from services.object_storage import exam_pdf_object_key


PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTION_MEDIA_DIR = (PROJECT_ROOT / "static" / "images" / "questions").resolve()
PDF_DIR = (PROJECT_ROOT / "pdfs").resolve()
LEGACY_QUESTION_MEDIA_PREFIX = "/static/images/questions/"
router = APIRouter()


def question_media_filename(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = unquote(urlparse(raw).path).replace("\\", "/")
    if path.startswith(LEGACY_QUESTION_MEDIA_PREFIX):
        filename = path[len(LEGACY_QUESTION_MEDIA_PREFIX):]
    elif path.startswith(LEGACY_QUESTION_MEDIA_PREFIX.lstrip("/")):
        filename = path[len(LEGACY_QUESTION_MEDIA_PREFIX) - 1:]
    else:
        return None
    if not filename or Path(filename).name != filename or filename in {".", ".."}:
        return None
    return filename


def secure_exam_image_urls(exam_id: int, images: list[str] | None) -> list[str] | None:
    if not images:
        return None
    secured: list[str] = []
    for image in images:
        filename = question_media_filename(image)
        if filename:
            secured.append(f"/api/v1/exams/{int(exam_id)}/media/{quote(filename, safe='')}")
        else:
            secured.append(str(image))
    return secured or None


def secure_exam_option_image_urls(
    exam_id: int,
    option_images: dict[str, list[str]] | None,
) -> dict[str, list[str]] | None:
    """Aplica a mesma autorização de mídia às imagens por alternativa."""

    if not isinstance(option_images, dict):
        return None
    secured: dict[str, list[str]] = {}
    for label, images in option_images.items():
        key = str(label or '').strip().upper()
        if not key:
            continue
        values = images if isinstance(images, list) else [images]
        secured_values = secure_exam_image_urls(
            exam_id,
            [str(value) for value in values if value not in (None, '')],
        )
        if secured_values:
            secured[key] = secured_values
    return secured or None


def resolve_question_media_path(filename: str) -> Path | None:
    normalized = unquote(str(filename or "").strip())
    if not normalized or Path(normalized).name != normalized or normalized in {".", ".."}:
        return None
    candidate = (QUESTION_MEDIA_DIR / normalized).resolve()
    if candidate.parent != QUESTION_MEDIA_DIR or not candidate.is_file():
        return None
    return candidate


def _question_image_values(raw_images: object) -> list[str]:
    if raw_images in (None, ""):
        return []
    decoded = raw_images
    if isinstance(raw_images, str):
        try:
            decoded = json.loads(raw_images)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = raw_images
    if isinstance(decoded, str):
        return [decoded]
    if isinstance(decoded, list):
        return [str(value) for value in decoded if value not in (None, "")]
    return []


def _question_option_image_values(raw_option_images: object) -> list[str]:
    if raw_option_images in (None, ""):
        return []
    decoded = raw_option_images
    if isinstance(raw_option_images, str):
        try:
            decoded = json.loads(raw_option_images)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(decoded, dict):
        return []
    values: list[str] = []
    for images in decoded.values():
        values.extend(_question_image_values(images))
    return values


def exam_references_question_media(db: Session, exam: Exam, filename: str) -> bool:
    questions, _is_generated_session = resolve_exam_questions(db, exam)
    return any(
        question_media_filename(image) == filename
        for question in questions
        for image in [
            *_question_image_values(question.images),
            *_question_option_image_values(getattr(question, 'option_images', None)),
        ]
    )


@router.get("/exams/{exam_id}/media/{filename}", include_in_schema=False)
def get_exam_question_media(
    exam_id: int,
    filename: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Entrega apenas arquivos referenciados por uma prova acessível ao usuário."""
    exam = get_accessible_exam_or_404(db, user_id=current_user.id, exam_id=exam_id)
    normalized_filename = unquote(str(filename or "").strip())
    if not exam_references_question_media(db, exam, normalized_filename):
        raise HTTPException(status_code=404, detail="Mídia da prova não encontrada.")

    # Object Storage is the canonical media plane in production.  The local
    # file is retained as a development/fallback path so an existing database
    # can be migrated gradually without breaking old exams.
    try:
        remote = get_object(question_object_key(normalized_filename))
    except (ObjectStorageError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="O armazenamento de mídia está temporariamente indisponível.",
        ) from exc
    if remote is not None:
        headers = {"Cache-Control": "private, no-store"}
        if remote.etag:
            headers["ETag"] = remote.etag
        return Response(remote.content, media_type=remote.content_type, headers=headers)

    media_path = resolve_question_media_path(normalized_filename)
    if media_path is None:
        raise HTTPException(status_code=404, detail="Mídia da prova não encontrada.")
    return FileResponse(media_path, headers={"Cache-Control": "private, no-store"})


@router.get("/exams/{exam_id}/pdf/{kind}", include_in_schema=False)
def get_exam_pdf(
    exam_id: int,
    kind: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Entrega o caderno ou gabarito por uma rota autorizada.

    O nome canônico no Object Storage é ``exams/{id}/{kind}.pdf``.  O arquivo
    local é mantido como fallback durante a migração dos artefatos existentes.
    """

    exam = get_accessible_exam_or_404(db, user_id=current_user.id, exam_id=exam_id)
    try:
        object_key = exam_pdf_object_key(exam.id, kind)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="PDF da prova não encontrado.") from exc

    try:
        remote = get_object(object_key)
    except ObjectStorageError as exc:
        raise HTTPException(
            status_code=503,
            detail="O armazenamento de provas está temporariamente indisponível.",
        ) from exc
    if remote is not None:
        headers = {"Cache-Control": "private, no-store"}
        if remote.etag:
            headers["ETag"] = remote.etag
        return Response(remote.content, media_type="application/pdf", headers=headers)

    suffix = "prova" if kind.strip().lower() == "prova" else "gab"
    local_path = (PDF_DIR / f"{int(exam.id)}_{suffix}.pdf").resolve()
    if local_path.parent != PDF_DIR or not local_path.is_file():
        raise HTTPException(status_code=404, detail="PDF da prova não encontrado.")
    return FileResponse(local_path, media_type="application/pdf", headers={"Cache-Control": "private, no-store"})
