"""Identidade estável para imagens de provas.

As questões continuam armazenando as referências legadas (por exemplo,
``/static/images/questions/foo.png``). Este módulo cria uma camada de
identidade por conteúdo para a sincronização entre dispositivos e para uma
futura distribuição P2P: o nome local do arquivo não é usado como identidade
da imagem.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, unquote, urlparse


LEGACY_QUESTION_MEDIA_PREFIX = "/static/images/questions/"
ASSET_ID_PREFIX = "sha256:"
UNRESOLVED_ASSET_PREFIX = "ref:"


def asset_id_from_bytes(data: bytes) -> str:
    """Retorna o identificador content-addressed de um blob."""

    return f"{ASSET_ID_PREFIX}{hashlib.sha256(data).hexdigest()}"


def asset_id_from_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Calcula o identificador SHA-256 sem carregar uma imagem inteira na RAM."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return f"{ASSET_ID_PREFIX}{digest.hexdigest()}"


def question_media_filename(value: object) -> str | None:
    """Extrai somente o nome de um caminho de mídia legado seguro."""

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


def _decode_images(raw: object) -> list[str]:
    if raw in (None, ""):
        return []
    decoded: Any = raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = raw
    if isinstance(decoded, str):
        return [decoded]
    if isinstance(decoded, list):
        return [str(value) for value in decoded if value not in (None, "")]
    return []


def _decode_option_images(raw: object) -> dict[str, list[str]]:
    if raw in (None, ""):
        return {}
    decoded: Any = raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    if not isinstance(decoded, dict):
        return {}
    result: dict[str, list[str]] = {}
    for label, images in decoded.items():
        values = images if isinstance(images, list) else [images]
        result[str(label).strip().upper()] = [
            str(value) for value in values if value not in (None, "")
        ]
    return result


def _safe_media_path(media_root: Path, filename: str) -> Path | None:
    root = media_root.resolve()
    candidate = (root / filename).resolve()
    if candidate.parent != root or not candidate.is_file():
        return None
    return candidate


def build_exam_asset_manifest(
    exam_id: int,
    questions: Iterable[Any],
    *,
    media_root: Path,
) -> dict[str, Any]:
    """Monta o manifesto de imagens de uma prova.

    Cada arquivo disponível recebe um `sha256:` estável. Referências antigas
    cujo arquivo ainda não está no volume são mantidas com um ID `ref:` e
    `available=false`, permitindo que uma futura sincronização as repare sem
    quebrar a prova atual.
    """

    entries: dict[str, dict[str, Any]] = {}
    for question in questions:
        question_id = int(getattr(question, "id", 0) or 0)
        body_images = _decode_images(getattr(question, "images", None))
        option_images = _decode_option_images(getattr(question, "option_images", None))

        references: list[tuple[str, int, str | None]] = [
            ("body", index, None) for index, value in enumerate(body_images)
        ]
        references.extend(
            (f"option:{label}", index, label)
            for label, values in option_images.items()
            for index, value in enumerate(values)
        )
        all_values = body_images + [value for values in option_images.values() for value in values]
        for (slot, index, option_key), raw_value in zip(references, all_values):
            filename = question_media_filename(raw_value)
            if filename is None:
                continue
            path = _safe_media_path(media_root, filename)
            if path is not None:
                asset_id = asset_id_from_file(path)
                available = True
                size = path.stat().st_size
                content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            else:
                asset_id = f"{UNRESOLVED_ASSET_PREFIX}{hashlib.sha256(filename.encode('utf-8')).hexdigest()}"
                available = False
                size = None
                content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

            entry = entries.setdefault(
                asset_id,
                {
                    "asset_id": asset_id,
                    "filename": filename,
                    "media_url": f"/api/v1/exams/{int(exam_id)}/media/{quote(filename, safe='')}",
                    "size": size,
                    "content_type": content_type,
                    "available": available,
                    "references": [],
                },
            )
            entry["references"].append({
                "question_id": question_id,
                "slot": slot,
                "index": index,
                "option_key": option_key,
            })

    assets = sorted(entries.values(), key=lambda item: item["asset_id"])
    for asset in assets:
        asset["references"] = sorted(
            asset["references"],
            key=lambda item: (item["question_id"], item["slot"], item["index"]),
        )
    canonical = json.dumps(assets, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    manifest_id = asset_id_from_bytes(canonical.encode("utf-8"))
    return {
        "exam_id": int(exam_id),
        "manifest_id": manifest_id,
        "assets": assets,
    }


def library_version(payload: Any) -> str:
    """Calcula uma versão determinística para uma biblioteca de usuário."""

    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return asset_id_from_bytes(canonical.encode("utf-8"))
