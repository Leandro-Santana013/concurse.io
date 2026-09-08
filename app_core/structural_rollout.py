"""Compatibility import for the application structural-rollout seam."""

from services.pdf_pipeline.structural.ingestion import (
    STRUCTURAL_TRACE_DIR_ENV,
    StructuralRolloutOutcome,
    merge_structural_questions,
    run_structural_rollout,
)

__all__ = [
    "STRUCTURAL_TRACE_DIR_ENV",
    "StructuralRolloutOutcome",
    "merge_structural_questions",
    "run_structural_rollout",
]
