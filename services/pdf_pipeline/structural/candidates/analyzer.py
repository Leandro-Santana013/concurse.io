"""Orchestration seam for Phase 3: candidates -> graph -> regions."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Optional

from ..layout.analyzer import LayoutAnalyzer
from ..layout.models import LayoutAnalysis
from ..model import DocumentModel
from .config import StructuralAnalyzerConfig
from .detector import CandidateDetector
from .graph import DocumentGraphBuilder
from .legacy import LegacyEvidenceProvider
from .models import Candidate, CandidateDetection, StructuralAnalysis
from .regions import QuestionRegionBuilder


class StructuralAnalyzer:
    """Deep public interface for the Phase-3 structural pipeline.

    ``analyze`` is intentionally opt-in. It consumes the physical document
    and Phase-2 profile, then returns diagnostics rather than changing the
    production parser, API payloads or database schema.
    """

    def __init__(
        self,
        config: Optional[StructuralAnalyzerConfig] = None,
        *,
        layout_analyzer: Optional[LayoutAnalyzer] = None,
        candidate_detector: Optional[CandidateDetector] = None,
        graph_builder: Optional[DocumentGraphBuilder] = None,
        region_builder: Optional[QuestionRegionBuilder] = None,
        candidate_classifier: Any = None,
        ml_enabled: Optional[bool] = None,
        legacy_evidence_provider: Any = None,
    ) -> None:
        self.config = config or StructuralAnalyzerConfig()
        self.layout_analyzer = layout_analyzer or LayoutAnalyzer(self.config.layout)
        self.candidate_detector = candidate_detector or CandidateDetector(
            self.config.candidates,
            legacy_evidence_provider=legacy_evidence_provider,
        )
        self.graph_builder = graph_builder or DocumentGraphBuilder(self.config.graph)
        self.region_builder = region_builder or QuestionRegionBuilder(self.config.regions)
        self.candidate_classifier = candidate_classifier
        self.ml_enabled = ml_enabled

    def analyze(
        self,
        document: DocumentModel,
        *,
        layout_analysis: Optional[LayoutAnalysis] = None,
        legacy_metadata: Optional[Mapping[str, Any]] = None,
    ) -> StructuralAnalysis:
        resolved_layout = layout_analysis or self.layout_analyzer.analyze(document)
        detection = self.candidate_detector.detect(
            document,
            resolved_layout,
            legacy_metadata=legacy_metadata,
        )
        detection = self._apply_optional_ml(detection)
        graph = self.graph_builder.build(document, resolved_layout, detection)
        regions = self.region_builder.build(
            document,
            resolved_layout,
            detection,
            graph,
        )
        context_blocks = list(self.region_builder.last_context_blocks)
        warnings = [*detection.warnings]
        if not regions and detection.question_headers:
            warnings.append("question_regions_not_built")
        if any(not region.segments for region in regions):
            warnings.append("question_region_without_page_segment")
        return StructuralAnalysis(
            pipeline_version=self.config.pipeline_version,
            document_profile=resolved_layout.profile,
            question_candidates=detection.question_headers,
            option_candidates=detection.option_groups,
            subject_candidates=detection.subjects,
            context_candidates=detection.contexts,
            context_blocks=context_blocks,
            graph=graph,
            question_regions=regions,
            image_ownership=list(self.region_builder.last_image_ownership),
            warnings=warnings,
            layout_analysis=resolved_layout,
        )

    def _apply_optional_ml(self, detection: CandidateDetection) -> CandidateDetection:
        """Blend an optional model into candidate scores without making it required."""

        enabled = self.ml_enabled
        if enabled is None:
            from ..rollout import structural_ml_enabled

            enabled = structural_ml_enabled()
        if not enabled:
            return detection
        if self.candidate_classifier is None:
            detection.warnings.append("ml_enabled_without_candidate_model")
            return detection
        updated: list[Candidate] = []
        for candidate in detection.question_headers:
            try:
                if hasattr(self.candidate_classifier, "score_candidate"):
                    probability = float(self.candidate_classifier.score_candidate(candidate))
                else:
                    probability = float(self.candidate_classifier.predict_proba(candidate))
            except Exception as exc:
                detection.warnings.append(f"ml_candidate_scoring_failed:{type(exc).__name__}")
                updated.append(candidate)
                continue
            probability = max(0.0, min(1.0, probability))
            evidence = dict(candidate.evidence)
            evidence["ml_candidate_probability"] = probability
            breakdown = dict(candidate.score_breakdown)
            breakdown["ml_candidate_probability"] = 0.25 * probability
            metadata = dict(candidate.metadata)
            metadata["ml_candidate_classifier"] = getattr(
                getattr(self.candidate_classifier, "metadata", None),
                "model_version",
                "candidate-classifier",
            )
            updated.append(
                replace(
                    candidate,
                    score=round(min(1.0, 0.75 * float(candidate.score) + 0.25 * probability), 8),
                    evidence=evidence,
                    metadata=metadata,
                    score_breakdown=breakdown,
                )
            )
        detection.question_headers = updated
        return detection


# Descriptive alias for callers that prefer the pipeline's output name.
CandidateGraphAnalyzer = StructuralAnalyzer


def analyze_structure(
    document: DocumentModel,
    *,
    analyzer: Optional[StructuralAnalyzer] = None,
    layout_analysis: Optional[LayoutAnalysis] = None,
    legacy_metadata: Optional[Mapping[str, Any]] = None,
    candidate_classifier: Any = None,
    ml_enabled: Optional[bool] = None,
    legacy_evidence_provider: Any = None,
) -> StructuralAnalysis:
    """Analyze an extracted document through the Phase-3 opt-in seam."""

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
