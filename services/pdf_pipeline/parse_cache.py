"""Cache local, determinístico e reversível para resultados do parser legado.

O cache guarda somente o payload já produzido pelo parser. A chave inclui o
hash do PDF, a configuração relevante e a versão explícita do contrato. Nunca
é usado para aceitar uma saída parcial: entradas inválidas ou imagens ausentes
simplesmente provocam um novo processamento.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PARSE_CACHE_VERSION = "legacy-parse-cache-v2"


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "off", "no"}


def cache_enabled() -> bool:
    return _env_flag("PDF_PARSE_CACHE_ENABLED", default=True)


def _cache_dir() -> Path:
    configured = os.getenv("PDF_PARSE_CACHE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(tempfile.gettempdir()) / "concurseio_pdf_pipeline"


def cache_directory() -> Path:
    """Diretório comum para caches derivados do mesmo PDF."""
    return _cache_dir()


def _read_source_bytes(source: Any) -> Optional[bytes]:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, (str, os.PathLike)):
        try:
            return Path(source).read_bytes()
        except (OSError, TypeError, ValueError):
            return None
    return None


def prepare_parse_source(
    source: Any,
    *,
    exam_id: Optional[int],
    extract_images: bool,
    gabarito_override: Optional[str],
    force_ocr: bool,
    layout_config: Optional[Any],
) -> Tuple[Any, Optional[str]]:
    """Retorna uma fonte estável e a chave do cache, quando possível."""
    if not cache_enabled():
        return source, None

    pdf_bytes = _read_source_bytes(source)
    if pdf_bytes is None:
        return source, None

    layout_payload: Dict[str, Any] = {}
    if layout_config is not None:
        try:
            layout_payload = dict(vars(layout_config))
        except TypeError:
            layout_payload = {"repr": repr(layout_config)}

    key_payload = {
        "cache_version": PARSE_CACHE_VERSION,
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "exam_id": exam_id,
        "extract_images": bool(extract_images),
        "force_ocr": bool(force_ocr),
        "gabarito_override_sha256": (
            hashlib.sha256(gabarito_override.encode("utf-8")).hexdigest()
            if gabarito_override is not None
            else None
        ),
        "layout_config": layout_payload,
    }
    serialized = json.dumps(key_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cache_key = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return pdf_bytes, cache_key


def _cache_path(cache_key: str) -> Path:
    return _cache_dir() / f"{cache_key}.json"


def _image_payload_is_available(questions: List[Dict[str, Any]]) -> bool:
    """Não aceita cache se algum recorte persistido foi removido."""
    root = Path.cwd()

    def image_values_are_available(values: Any) -> bool:
        if values in (None, ""):
            return True
        normalized = values if isinstance(values, list) else [values]
        for image in normalized:
            if not isinstance(image, str):
                return False
            if image.startswith(("http://", "https://")):
                continue
            relative = image.split("?", 1)[0].lstrip("/\\")
            if not relative or not (root / Path(relative)).is_file():
                return False
        return True

    for question in questions:
        if not image_values_are_available(question.get("images")):
            return False
        option_images = question.get("option_images")
        if option_images in (None, ""):
            continue
        if not isinstance(option_images, dict):
            return False
        for images in option_images.values():
            if not image_values_are_available(images):
                return False
    return True


def load_parse_cache(cache_key: Optional[str]) -> Optional[Tuple[List[Dict[str, Any]], int]]:
    if not cache_key or not cache_enabled():
        return None

    try:
        payload = json.loads(_cache_path(cache_key).read_text(encoding="utf-8"))
        if payload.get("cache_version") != PARSE_CACHE_VERSION:
            return None
        questions = payload.get("questions")
        pages = payload.get("pages")
        if not isinstance(questions, list) or not isinstance(pages, int) or pages < 0:
            return None
        if not all(isinstance(question, dict) for question in questions):
            return None
        if not _image_payload_is_available(questions):
            return None
        return questions, pages
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def save_parse_cache(
    cache_key: Optional[str],
    questions: List[Dict[str, Any]],
    *,
    pages: int,
) -> None:
    if not cache_key or not cache_enabled() or not isinstance(questions, list) or not questions:
        return

    cache_dir = _cache_dir()
    temp_path: Optional[Path] = None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_version": PARSE_CACHE_VERSION,
            "pages": int(pages),
            "questions": questions,
        }
        target = _cache_path(cache_key)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=cache_dir,
            prefix=f".{cache_key}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
        temp_path = None
    except (OSError, TypeError, ValueError):
        # Cache é uma otimização: falhar ao gravá-lo nunca falha a ingestão.
        pass
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
