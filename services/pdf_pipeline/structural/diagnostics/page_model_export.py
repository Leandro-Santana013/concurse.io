"""Optional JSON export for inspecting physical extraction locally."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Optional

from ..model import DocumentModel


def _safe_component(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "unknown"))
    return text.strip("._") or "unknown"


def export_page_model_debug(
    document: DocumentModel,
    *,
    artifacts_dir: str | Path = "artifacts/debug",
    exam_id: Optional[int | str] = None,
) -> Path:
    """Write artifacts/debug/{exam_id}/page_model.json and return its path."""

    output_path = (
        Path(artifacts_dir)
        / _safe_component(exam_id)
        / "page_model.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document.to_json() + chr(10), encoding="utf-8")
    return output_path
