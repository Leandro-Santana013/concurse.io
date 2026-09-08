"""Structural pipeline entry points for the staged PDF migration.

The application still calls the legacy parser. These functions are explicit
opt-in analysis helpers and do not change production ingestion behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .candidates import StructuralAnalysis, StructuralAnalyzer
from .diagnostics import export_page_model_debug
from .layout import LayoutAnalysis, LayoutAnalyzer
from .model import DocumentModel
from .physical import PhysicalExtractor
from .question_ast import ExamDocumentNode, QuestionASTBuilder
from .renderer import render_legacy_document
from .shadow import StructuralShadowResult, run_structural_shadow
from .solver import ConstraintSolver, DocumentParseConfidence, SequenceSolution
from .trace import build_structural_trace


@dataclass
class StructuralSemanticResult:
    """Opt-in Phase-4 result kept separate from the legacy application path."""

    document: DocumentModel
    analysis: StructuralAnalysis
    solution: SequenceSolution
    ast: ExamDocumentNode
    legacy_questions: list[dict[str, Any]]
    layout_family: Any = None
    ml_models_used: list[str] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)

    @property
    def questions(self) -> list[dict[str, Any]]:
        return self.legacy_questions

    @property
    def confidence(self) -> DocumentParseConfidence:
        return self.solution.confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document.to_dict(),
            "analysis": self.analysis.to_dict(),
            "solution": self.solution.to_dict(),
            "ast": self.ast.to_dict(),
            "questions": list(self.legacy_questions),
            "layout_family": (
                self.layout_family.to_dict()
                if hasattr(self.layout_family, "to_dict")
                else self.layout_family
            ),
            "ml_models_used": list(self.ml_models_used),
            "trace": dict(self.trace),
        }


def extract_physical_document(
    pdf_bytes_or_path: Any,
    *,
    source: Optional[str] = None,
    exam_id: Optional[int | str] = None,
    debug_export: bool = False,
    artifacts_dir: str | Path = "artifacts/debug",
    extractor: Optional[PhysicalExtractor] = None,
) -> DocumentModel:
    """Extract a physical document and optionally write its debug JSON."""

    model = (extractor or PhysicalExtractor()).extract(
        pdf_bytes_or_path,
        source=source,
    )
    if debug_export:
        export_page_model_debug(
            model,
            artifacts_dir=artifacts_dir,
            exam_id=exam_id,
        )
    return model


def analyze_layout(
    document: DocumentModel,
    *,
    analyzer: Optional[LayoutAnalyzer] = None,
) -> LayoutAnalysis:
    """Analyze a previously extracted POM and return its layout profile."""

    return (analyzer or LayoutAnalyzer()).analyze(document)


def extract_and_analyze_layout(
    pdf_bytes_or_path: Any,
    *,
    source: Optional[str] = None,
    extractor: Optional[PhysicalExtractor] = None,
    analyzer: Optional[LayoutAnalyzer] = None,
    exam_id: Optional[int | str] = None,
    debug_export: bool = False,
    artifacts_dir: str | Path = "artifacts/debug",
) -> LayoutAnalysis:
    """Opt-in POM -> LayoutAnalyzer -> DocumentProfile helper."""

    document = extract_physical_document(
        pdf_bytes_or_path,
        source=source,
        extractor=extractor,
        exam_id=exam_id,
        debug_export=debug_export,
        artifacts_dir=artifacts_dir,
    )
    return analyze_layout(document, analyzer=analyzer)


def analyze_structure(
    document: DocumentModel,
    *,
    analyzer: Optional[StructuralAnalyzer] = None,
    layout_analysis: Optional[LayoutAnalysis] = None,
    legacy_metadata: Optional[dict[str, Any]] = None,
    candidate_classifier: Any = None,
    ml_enabled: Optional[bool] = None,
    legacy_evidence_provider: Any = None,
) -> StructuralAnalysis:
    """Run the opt-in Phase-3 candidate/graph/region analysis."""

    resolved_analyzer = analyzer or StructuralAnalyzer(
        candidate_classifier=candidate_classifier,
        ml_enabled=ml_enabled,
        legacy_evidence_provider=legacy_evidence_provider,
    )
    return resolved_analyzer.analyze(
        document,
        layout_analysis=layout_analysis,
        legacy_metadata=legacy_metadata,
    )


def extract_and_analyze_structure(
    pdf_bytes_or_path: Any,
    *,
    source: Optional[str] = None,
    extractor: Optional[PhysicalExtractor] = None,
    analyzer: Optional[StructuralAnalyzer] = None,
    exam_id: Optional[int | str] = None,
    debug_export: bool = False,
    artifacts_dir: str | Path = "artifacts/debug",
    legacy_metadata: Optional[dict[str, Any]] = None,
    candidate_classifier: Any = None,
    ml_enabled: Optional[bool] = None,
    legacy_evidence_provider: Any = None,
) -> StructuralAnalysis:
    """Convenience entry point for POM -> profile -> Phase-3 trace."""

    document = extract_physical_document(
        pdf_bytes_or_path,
        source=source,
        extractor=extractor,
        exam_id=exam_id,
        debug_export=debug_export,
        artifacts_dir=artifacts_dir,
    )
    return analyze_structure(
        document,
        analyzer=analyzer,
        legacy_metadata=legacy_metadata,
        candidate_classifier=candidate_classifier,
        ml_enabled=ml_enabled,
        legacy_evidence_provider=legacy_evidence_provider,
    )


def solve_structure(
    document: DocumentModel,
    analysis: Optional[StructuralAnalysis] = None,
    *,
    answer_key: Any = None,
    legacy_questions: Optional[list[dict[str, Any]]] = None,
    solver: Optional[ConstraintSolver] = None,
) -> SequenceSolution:
    """Solve an existing Phase-3 analysis without invoking the legacy parser."""

    resolved_analysis = analysis or analyze_structure(document)
    return (solver or ConstraintSolver()).solve(
        resolved_analysis,
        document=document,
        answer_key=answer_key,
        legacy_questions=legacy_questions,
    )


def analyze_and_render_structure(
    document: DocumentModel,
    *,
    analysis: Optional[StructuralAnalysis] = None,
    answer_key: Any = None,
    legacy_questions: Optional[list[dict[str, Any]]] = None,
    solver: Optional[ConstraintSolver] = None,
    ast_builder: Optional[QuestionASTBuilder] = None,
    candidate_classifier: Any = None,
    ml_enabled: Optional[bool] = None,
    layout_family: Any = None,
    legacy_adapter_used: Optional[str] = None,
    ml_models_used: Optional[list[str]] = None,
    legacy_evidence_provider: Any = None,
) -> StructuralSemanticResult:
    """Run Phase 3 -> solver -> AST -> compatibility renderer."""

    resolved_analysis = analysis or analyze_structure(
        document,
        candidate_classifier=candidate_classifier,
        ml_enabled=ml_enabled,
        legacy_evidence_provider=legacy_evidence_provider,
    )
    resolved_solver = solver or ConstraintSolver()
    solution = resolved_solver.solve(
        resolved_analysis,
        document=document,
        answer_key=answer_key,
        legacy_questions=legacy_questions,
    )
    ast = (ast_builder or QuestionASTBuilder()).build(
        document,
        resolved_analysis,
        solution,
        answer_key=answer_key,
        legacy_questions=legacy_questions,
    )
    trace = build_structural_trace(
        resolved_analysis,
        solution,
        layout_family=layout_family,
        legacy_adapter_used=legacy_adapter_used,
        ml_models_used=ml_models_used,
    )
    return StructuralSemanticResult(
        document=document,
        analysis=resolved_analysis,
        solution=solution,
        ast=ast,
        legacy_questions=render_legacy_document(ast),
        layout_family=layout_family,
        ml_models_used=list(ml_models_used or []),
        trace=trace,
    )


def extract_and_render_structure(
    pdf_bytes_or_path: Any,
    *,
    source: Optional[str] = None,
    answer_key: Any = None,
    legacy_questions: Optional[list[dict[str, Any]]] = None,
    extractor: Optional[PhysicalExtractor] = None,
    analyzer: Optional[StructuralAnalyzer] = None,
    solver: Optional[ConstraintSolver] = None,
    ast_builder: Optional[QuestionASTBuilder] = None,
    exam_id: Optional[int | str] = None,
    debug_export: bool = False,
    artifacts_dir: str | Path = "artifacts/debug",
    candidate_classifier: Any = None,
    ml_enabled: Optional[bool] = None,
    layout_family: Any = None,
    legacy_adapter_used: Optional[str] = None,
    ml_models_used: Optional[list[str]] = None,
    legacy_evidence_provider: Any = None,
) -> StructuralSemanticResult:
    """Convenience helper for opt-in Phase-4 semantic extraction."""

    document = extract_physical_document(
        pdf_bytes_or_path,
        source=source,
        extractor=extractor,
        exam_id=exam_id,
        debug_export=debug_export,
        artifacts_dir=artifacts_dir,
    )
    analysis = analyze_structure(
        document,
        analyzer=analyzer,
        candidate_classifier=candidate_classifier,
        ml_enabled=ml_enabled,
        legacy_evidence_provider=legacy_evidence_provider,
    )
    return analyze_and_render_structure(
        document,
        analysis=analysis,
        answer_key=answer_key,
        legacy_questions=legacy_questions,
        solver=solver,
        ast_builder=ast_builder,
        candidate_classifier=candidate_classifier,
        ml_enabled=ml_enabled,
        layout_family=layout_family,
        legacy_adapter_used=legacy_adapter_used,
        ml_models_used=ml_models_used,
    )


def run_shadow_pipeline(*args: Any, **kwargs: Any) -> StructuralShadowResult:
    """Named pipeline alias; the returned ``user_result`` is always legacy."""

    return run_structural_shadow(*args, **kwargs)
