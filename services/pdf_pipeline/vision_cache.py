"""Cache retomável das linhas OCR por página."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .parse_cache import cache_directory, cache_enabled


VISION_CACHE_VERSION = "vision-ocr-cache-v1"


def _cache_path(document_sha256: str, dpi: int, page_index: int) -> Path:
    identity = f"{VISION_CACHE_VERSION}:{document_sha256}:{int(dpi)}:{int(page_index)}"
    key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return cache_directory() / "vision_pages" / f"{key}.json"


def load_page_ocr_cache(
    document_sha256: Optional[str],
    *,
    dpi: int,
    page_index: int,
) -> Optional[List[Dict[str, Any]]]:
    if not document_sha256 or not cache_enabled():
        return None

    try:
        payload = json.loads(_cache_path(document_sha256, dpi, page_index).read_text(encoding="utf-8"))
        if payload.get("cache_version") != VISION_CACHE_VERSION:
            return None
        lines = payload.get("lines")
        if not isinstance(lines, list) or not all(isinstance(line, dict) for line in lines):
            return None
        return lines
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_page_ocr_cache(
    document_sha256: Optional[str],
    *,
    dpi: int,
    page_index: int,
    lines: List[Dict[str, Any]],
) -> None:
    if not document_sha256 or not cache_enabled() or not isinstance(lines, list):
        return

    target_dir = cache_directory() / "vision_pages"
    temp_path: Optional[Path] = None
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "cache_version": VISION_CACHE_VERSION,
            "dpi": int(dpi),
            "page_index": int(page_index),
            "lines": lines,
        }
        target = _cache_path(document_sha256, dpi, page_index)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_dir,
            prefix=".vision-",
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
        # O cache não pode interromper a extração principal.
        pass
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
