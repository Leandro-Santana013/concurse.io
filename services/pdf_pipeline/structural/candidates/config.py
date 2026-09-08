"""Configuration for the opt-in Phase-3 structural interpretation layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..layout.config import LayoutAnalyzerConfig


@dataclass(frozen=True)
class CandidateScoreWeights:
    """Centralized, explainable weights for question-header scoring.

    The first seven weights are the initial proposal from the architecture
    plan. The small legacy bonus is deliberately capped so a bank-specific
    rule can add evidence without becoming the deciding signal.
    """

    numeric: float = 0.15
    sequential: float = 0.20
    same_alignment: float = 0.15
    same_style_cluster: float = 0.10
    options_below: float = 0.20
    regex: float = 0.10
    vertical_structure: float = 0.10
    legacy_bonus: float = 0.05

    def to_dict(self) -> dict[str, float]:
        return {
            "numeric": self.numeric,
            "sequential": self.sequential,
            "same_alignment": self.same_alignment,
            "same_style_cluster": self.same_style_cluster,
            "options_below": self.options_below,
            "regex": self.regex,
            "vertical_structure": self.vertical_structure,
            "legacy_bonus": self.legacy_bonus,
        }


@dataclass(frozen=True)
class CandidateDetectorConfig:
    """Thresholds for candidate discovery, not final semantic decisions."""

    feature_schema_version: int = 1
    max_question_number: int = 200
    min_question_header_score: float = 0.30
    explicit_question_min_score: float = 0.18
    max_header_body_gap_norm: float = 0.42
    max_option_gap_norm: float = 0.065
    max_option_group_size: int = 5
    min_option_group_size: int = 2
    min_unlabelled_option_group_size: int = 4
    max_context_source_elements: int = 80
    context_min_body_chars: int = 25
    max_subject_line_chars: int = 100
    weights: CandidateScoreWeights = field(default_factory=CandidateScoreWeights)


@dataclass(frozen=True)
class GraphConfig:
    """Local-neighborhood limits used to keep graph construction sparse."""

    spatial_grid_size: int = 32
    max_neighbors_per_bucket: int = 12
    max_alignment_neighbors: int = 8
    near_radius_norm: float = 0.11


@dataclass(frozen=True)
class RegionConfig:
    """Question-region and image-ownership scoring parameters."""

    exclude_header_footer_noise: bool = True
    min_image_ownership_score: float = 0.22
    inside_region_weight: float = 0.45
    same_column_weight: float = 0.20
    nearest_statement_weight: float = 0.15
    trigger_word_weight: float = 0.10
    crossing_next_question_penalty: float = 0.20
    header_footer_penalty: float = 0.35
    max_region_fallback_gap_norm: float = 0.18


@dataclass(frozen=True)
class StructuralAnalyzerConfig:
    """Public configuration for the Phase-3 deep module."""

    layout: LayoutAnalyzerConfig = field(default_factory=LayoutAnalyzerConfig)
    candidates: CandidateDetectorConfig = field(default_factory=CandidateDetectorConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    regions: RegionConfig = field(default_factory=RegionConfig)
    pipeline_version: str = "structural-v1"

