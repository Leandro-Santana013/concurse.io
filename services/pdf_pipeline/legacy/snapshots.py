"""Stable JSON snapshots for the current legacy question schema."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


def _get(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _snapshot_question(question: Any) -> dict[str, Any]:
    options = _get(question, "options", "opcoes", default={})
    images = _get(question, "images", default=None)
    return {
        "numero_questao": _get(question, "numero_questao", default=None),
        "question_index": _get(question, "question_index", default=None),
        "statement": _get(question, "statement", "enunciado", default=""),
        "options": deepcopy(options),
        "images": deepcopy(images),
        "subject": _get(question, "subject", "disciplina", default=None),
        "correct_answer": _get(
            question,
            "correct_answer",
            "resposta",
            default=None,
        ),
    }


def build_legacy_snapshot(
    questions: Iterable[Any],
    *,
    source: Optional[str] = None,
    adapter_name: str = "hybrid_extractor",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pipeline": "legacy",
        "adapter": adapter_name,
        "source": source,
        "questions": [_snapshot_question(question) for question in questions],
    }


def write_legacy_snapshot(
    path: str | Path,
    questions: Iterable[Any],
    *,
    source: Optional[str] = None,
    adapter_name: str = "hybrid_extractor",
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = build_legacy_snapshot(
        questions,
        source=source,
        adapter_name=adapter_name,
    )
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + chr(10),
        encoding="utf-8",
    )
    return output_path
