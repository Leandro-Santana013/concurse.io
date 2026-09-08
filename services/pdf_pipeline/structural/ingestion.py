"""Application seam for the opt-in structural PDF rollout.

The ingestion worker remains responsible for the legacy persistence contract.
This module keeps rollout policy, trace persistence and structural adoption in
one small interface so shadow execution cannot accidentally change the normal
path.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .arbiter import ArbitrationStatus
from .config import PipelineMode, get_pipeline_mode
from .shadow import StructuralShadowResult, run_structural_shadow


STRUCTURAL_TRACE_DIR_ENV = "STRUCTURAL_TRACE_DIR"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StructuralRolloutOutcome:
    """Result of one opt-in structural observation at the ingestion seam."""

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
        return bool(decision is not None and decision.status is ArbitrationStatus.STRUCTURAL)

    @property
    def quarantined(self) -> bool:
        decision = self.result.arbitration if self.result is not None else None
        return bool(decision is not None and decision.status is ArbitrationStatus.QUARANTINE)

    @property
    def selected_result(self) -> Optional[list[dict[str, Any]]]:
        if self.result is None:
            return None
        decision = self.result.arbitration
        if decision is not None and decision.selected_result is not None:
            return [dict(item) for item in decision.selected_result]
        return None


def run_structural_rollout(
    pdf: Any,
    *,
    legacy_questions: Sequence[Mapping[str, Any]],
    answer_key: Any,
    exam_id: int | str,
    source: Optional[str] = None,
    mode: PipelineMode | str | None = None,
    extract_images: bool = False,
    ml_enabled: Optional[bool] = None,
) -> StructuralRolloutOutcome:
    """Execute the structural observer without changing legacy-only behavior."""

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
    except Exception as exc:  # pragma: no cover - defensive application seam
        logger.exception("Structural rollout failed for exam %s", exam_id)
        return StructuralRolloutOutcome(
            mode=resolved_mode,
            error=f"{type(exc).__name__}:{exc}",
        )

    trace_path = _write_trace(exam_id, result)
    logger.info(
        "Structural rollout exam=%s mode=%s metrics=%s errors=%s trace=%s",
        exam_id,
        resolved_mode.value,
        result.metrics,
        result.errors,
        trace_path,
    )
    return StructuralRolloutOutcome(
        mode=resolved_mode,
        result=result,
        trace_path=trace_path,
    )


def merge_structural_questions(
    legacy_questions: Sequence[Mapping[str, Any]],
    structural_questions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Adopt a promoted structural result while preserving legacy fallbacks."""

    legacy = [dict(item) for item in legacy_questions]
    structural = [dict(item) for item in structural_questions]
    if not structural:
        return legacy

    by_number = {
        _question_number(item): item
        for item in legacy
        if _question_number(item) is not None
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
    raw_directory = os.getenv(STRUCTURAL_TRACE_DIR_ENV, "").strip()
    if not raw_directory:
        return None

    output = Path(raw_directory) / f"exam-{exam_id}.json"
    temporary = output.with_suffix(output.suffix + ".tmp")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exam_id": str(exam_id),
            "mode": result.mode.value,
            "metrics": result.metrics,
            "errors": list(result.errors),
            "diff": result.diff.to_dict() if result.diff else None,
            "arbitration": result.arbitration.to_dict() if result.arbitration else None,
            "trace": dict(result.trace),
            "ml_models_used": list(result.ml_models_used),
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
        return str(output)
    except Exception as exc:  # diagnostics must never fail ingestion
        logger.warning("Could not persist structural trace for exam %s: %s", exam_id, exc)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return None


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
