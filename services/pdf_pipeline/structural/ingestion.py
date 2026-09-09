"""Application seam for the opt-in structural PDF rollout.

The ingestion worker remains responsible for the legacy persistence contract.
This module contains the rollout policy, redacted trace persistence and the
single explicit point at which a promoted structural result may be adopted.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Optional, Sequence

from .arbiter import ArbitrationStatus
from .config import PipelineMode, get_pipeline_mode
from .shadow import StructuralShadowResult, run_structural_shadow


STRUCTURAL_TRACE_DIR_ENV = "STRUCTURAL_TRACE_DIR"
_SENSITIVE_KEYS = {
    "text",
    "line_text",
    "enunciado",
    "statement",
    "resposta",
    "answer",
    "options",
    "opcoes",
    "raw_text",
    "source_text",
    "content",
    "alt_text",
}


@dataclass(frozen=True)
class StructuralRolloutOutcome:
    """Outcome of one structural observation at the ingestion seam."""

    mode: PipelineMode
    result: Optional[StructuralShadowResult] = None
    trace_path: Optional[str] = None
    error: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return self.mode is not PipelineMode.LEGACY_ONLY

    @property
    def promoted(self) -> bool:
        decision = self.result.arbitration if self.result is not None else None
        return bool(
            decision is not None
            and decision.status is ArbitrationStatus.STRUCTURAL
            and self.result.structural_result
        )

    @property
    def quarantined(self) -> bool:
        decision = self.result.arbitration if self.result is not None else None
        return bool(decision is not None and decision.status is ArbitrationStatus.QUARANTINE)

    @property
    def selected_result(self) -> Optional[list[dict[str, Any]]]:
        if self.result is None or self.result.arbitration is None:
            return None
        selected = self.result.arbitration.selected_result
        return [dict(item) for item in selected] if selected is not None else None


def run_structural_rollout(
    pdf: Any,
    *,
    legacy_questions: Sequence[Mapping[str, Any]],
    answer_key: Any,
    exam_id: int | str,
    source: Optional[str] = None,
    mode: PipelineMode | str | None = None,
    extract_images: bool = True,
    ml_enabled: Optional[bool] = None,
) -> StructuralRolloutOutcome:
    """Run the structural observer without changing legacy-only behavior.

    The function deliberately catches all structural/diagnostic failures. The
    caller can therefore keep the legacy result as the only user-visible
    result even when the experimental pipeline is enabled.
    """

    resolved_mode = get_pipeline_mode(
        mode.value if isinstance(mode, PipelineMode) else mode
    )
    if resolved_mode is PipelineMode.LEGACY_ONLY:
        return StructuralRolloutOutcome(mode=resolved_mode)

    try:
        result = run_structural_shadow(
            pdf,
            mode=resolved_mode,
            legacy_result=legacy_questions,
            answer_key=answer_key,
            source=source,
            exam_id=exam_id,
            extract_images=extract_images,
            ml_enabled=ml_enabled,
        )
    except Exception as exc:  # pragma: no cover - final application guard
        return StructuralRolloutOutcome(
            mode=resolved_mode,
            error=f"{type(exc).__name__}",
        )

    trace_path = _write_trace(exam_id, result)
    return StructuralRolloutOutcome(
        mode=resolved_mode,
        result=result,
        trace_path=trace_path,
    )


def merge_structural_questions(
    legacy_questions: Sequence[Mapping[str, Any]],
    structural_questions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Adopt a promoted result while retaining safe legacy fallbacks.

    This helper is only called after arbitration has promoted the structural
    result. Empty structural values never erase a known legacy value, and an
    absent answer is never converted into a fabricated option.
    """

    legacy = [dict(item) for item in legacy_questions]
    structural = [dict(item) for item in structural_questions]
    if not structural:
        return legacy

    by_number = {
        number: item
        for item in legacy
        if (number := _question_number(item)) is not None
    }
    merged: list[dict[str, Any]] = []
    for item in structural:
        number = _question_number(item)
        base = dict(by_number.get(number, {})) if number is not None else {}
        if not base:
            base = dict(item)
        else:
            for field in (
                "numero_questao",
                "enunciado",
                "opcoes",
                "resposta",
                "disciplina",
                "images",
                "latex_support",
                "question_index",
            ):
                value = item.get(field)
                if _usable_structural_value(field, value):
                    base[field] = value
        merged.append(base)
    return merged or legacy


def _write_trace(exam_id: int | str, result: StructuralShadowResult) -> Optional[str]:
    """Persist only redacted structural diagnostics, atomically, if configured."""

    raw_directory = os.getenv(STRUCTURAL_TRACE_DIR_ENV, "").strip()
    if not raw_directory:
        return None

    safe_exam_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(exam_id)).strip("._") or "unknown"
    output = Path(raw_directory) / f"exam-{safe_exam_id}.json"
    temporary = output.with_suffix(output.suffix + ".tmp")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "exam_id": str(exam_id),
            "mode": result.mode.value,
            "metrics": _redact(result.metrics),
            "errors": [str(item) for item in result.errors],
            "diff": _redact(result.diff.to_dict()) if result.diff else None,
            "arbitration": _decision_summary(result),
            "trace": _redact(result.trace),
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, output)
        return str(output)
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _decision_summary(result: StructuralShadowResult) -> Optional[dict[str, Any]]:
    decision = result.arbitration
    if decision is None:
        return None
    return {
        "status": decision.status.value,
        "source": decision.source,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "concordant": decision.concordant,
        "quarantined": decision.quarantined,
        "warnings": list(decision.warnings),
        "metadata": _redact(decision.metadata),
    }


def _redact(value: Any, key: Optional[str] = None) -> Any:
    """Recursively remove content-bearing keys from diagnostic payloads."""

    if key is not None and key.casefold() in _SENSITIVE_KEYS:
        return "[redacted]"
    if isinstance(value, Mapping):
        return {
            str(name): _redact(item, str(name))
            for name, item in value.items()
            if str(name).casefold() not in _SENSITIVE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _question_number(value: Mapping[str, Any]) -> Optional[int]:
    raw = value.get("numero_questao", value.get("printed_number"))
    try:
        number = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _usable_structural_value(field: str, value: Any) -> bool:
    if value is None or value == "":
        return False
    if field in {"opcoes", "images"} and not value:
        return False
    if field == "images" and isinstance(value, list) and all(
        str(item).startswith("source:") for item in value
    ):
        return False
    return True
