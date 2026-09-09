"""Redacted structural diagnostics safe for persistence and observability."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from .candidates.models import StructuralAnalysis
from .solver import SequenceSolution


TRACE_VERSION = "structural-trace-v2-redacted"
_SENSITIVE_KEYS = {
    "text", "line_text", "enunciado", "statement", "resposta", "answer",
    "options", "opcoes", "raw_text", "content", "source_text", "alt_text",
}


def build_structural_trace(
    analysis: StructuralAnalysis,
    solution: SequenceSolution,
    *,
    layout_family: Any = None,
    legacy_adapter_used: Optional[str] = None,
    ml_models_used: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build an audit trace with structure and metrics, never PDF content."""
    profile = analysis.document_profile
    trace = {
        "pipeline_version": TRACE_VERSION,
        "feature_schema_version": 1,
        "document_profile": profile.to_dict() if hasattr(profile, "to_dict") else {},
        "layout_family": _safe_layout_family(layout_family),
        "question_candidates": [_candidate_trace(item) for item in analysis.question_candidates],
        "option_candidates": [_candidate_trace(item) for item in analysis.option_candidates],
        "selected_sequence": [_candidate_trace(item) for item in solution.selected_candidates],
        "question_regions": [_region_trace(item) for item in analysis.question_regions],
        "recoveries": [_candidate_trace(item) for item in solution.recovered_candidates],
        "graph_stats": analysis.graph.stats() if hasattr(analysis.graph, "stats") else {},
        "legacy_adapter_used": legacy_adapter_used,
        "ml_models_used": list(ml_models_used or []),
        "confidence": solution.confidence.to_dict(),
        "warnings": [*(analysis.warnings or []), *(solution.warnings or []), *(warnings or [])],
    }
    return trace


def trace_for_shadow_result(result: Any) -> Mapping[str, Any]:
    return dict(getattr(result, "trace", {}) or {})


def _candidate_trace(candidate: Any) -> dict[str, Any]:
    metadata = getattr(candidate, "metadata", {}) or {}
    safe_metadata = {
        str(key): value
        for key, value in metadata.items()
        if str(key).lower() not in _SENSITIVE_KEYS
    }
    safe_metadata.pop("line_text", None)
    return {
        "id": str(getattr(candidate, "id", "")),
        "type": str(getattr(candidate, "type", "")),
        "score": float(getattr(candidate, "score", 0.0) or 0.0),
        "page_index": getattr(candidate, "page_index", None),
        "source_element_ids": list(getattr(candidate, "source_element_ids", []) or []),
        "metadata": safe_metadata,
        "evidence": dict(getattr(candidate, "evidence", {}) or {}),
        "score_breakdown": dict(getattr(candidate, "score_breakdown", {}) or {}),
    }


def _region_trace(region: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(region, "id", "")),
        "question_candidate_id": str(getattr(region, "question_candidate_id", "")),
        "question_number": getattr(region, "question_number", None),
        "segment_count": len(getattr(region, "segments", []) or []),
        "content_element_count": len(getattr(region, "content_element_ids", []) or []),
        "option_candidate_count": len(getattr(region, "option_candidate_ids", []) or []),
        "context_candidate_count": len(getattr(region, "context_candidate_ids", []) or []),
        "image_element_count": len(getattr(region, "image_element_ids", []) or []),
        "image_ownership_count": len(getattr(region, "image_ownership", []) or []),
        "cross_page": bool((getattr(region, "metadata", {}) or {}).get("cross_page", False)),
    }


def _safe_layout_family(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        allowed = {"family_id", "family_name", "confidence", "model_version"}
        return {key: value[key] for key in allowed if key in value}
    safe = {}
    for key in ("family_id", "family_name", "confidence", "model_version"):
        if hasattr(value, key):
            safe[key] = getattr(value, key)
    return safe or None
