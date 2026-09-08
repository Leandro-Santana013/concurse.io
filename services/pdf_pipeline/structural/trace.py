"""Inspectable Phase-5 trace assembly."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .candidates.models import StructuralAnalysis
from .solver import SequenceSolution


TRACE_VERSION = "structural-trace-v1"


def build_structural_trace(
    analysis: StructuralAnalysis,
    solution: SequenceSolution,
    *,
    layout_family: Any = None,
    legacy_adapter_used: Optional[str] = None,
    ml_models_used: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Return the layer-oriented diagnostic shape required by the rollout."""

    profile = analysis.document_profile
    family_value = (
        layout_family.to_dict()
        if hasattr(layout_family, "to_dict")
        else layout_family
    )
    trace = {
        "pipeline_version": TRACE_VERSION,
        "feature_schema_version": 1,
        "document_profile": profile.to_dict() if hasattr(profile, "to_dict") else profile,
        "layout_family": family_value,
        "question_candidates": [item.to_dict() for item in analysis.question_candidates],
        "option_candidates": [item.to_dict() for item in analysis.option_candidates],
        "selected_sequence": [item.to_dict() for item in solution.selected_candidates],
        "question_regions": [item.to_dict() for item in analysis.question_regions],
        "recoveries": [item.to_dict() for item in solution.recovered_candidates],
        "legacy_adapter_used": legacy_adapter_used,
        "ml_models_used": list(ml_models_used or []),
        "confidence": solution.confidence.to_dict(),
        "warnings": [*(analysis.warnings or []), *(solution.warnings or []), *(warnings or [])],
    }
    return trace


def trace_for_shadow_result(result: Any) -> Mapping[str, Any]:
    return dict(getattr(result, "trace", {}) or {})

