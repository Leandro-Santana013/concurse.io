"""Phase-3 candidate, graph and question-region modules."""

from .analyzer import CandidateGraphAnalyzer, StructuralAnalyzer, analyze_structure
from .config import (
    CandidateDetectorConfig,
    CandidateScoreWeights,
    GraphConfig,
    RegionConfig,
    StructuralAnalyzerConfig,
)
from .detector import CandidateDetector
from .features import (
    FEATURE_SCHEMA_VERSION,
    FEATURE_SCHEMA,
    QUESTION_HEADER_FEATURES,
    FeatureSchemaV1,
    FeatureVector,
)
from .graph import (
    DocumentGraph,
    DocumentGraphBuilder,
    EdgeType,
    GraphEdge,
    GraphNode,
)
from .legacy import LegacyEvidenceProvider
from .models import (
    Candidate,
    CandidateDetection,
    ContextBlock,
    ImageOwnership,
    PageSegment,
    QuestionRegion,
    StructuralAnalysis,
)
from .regions import QuestionRegionBuilder

__all__ = [
    "StructuralAnalyzer",
    "CandidateGraphAnalyzer",
    "analyze_structure",
    "StructuralAnalyzerConfig",
    "CandidateDetectorConfig",
    "CandidateScoreWeights",
    "GraphConfig",
    "RegionConfig",
    "CandidateDetector",
    "LegacyEvidenceProvider",
    "FEATURE_SCHEMA_VERSION",
    "FEATURE_SCHEMA",
    "QUESTION_HEADER_FEATURES",
    "FeatureSchemaV1",
    "FeatureVector",
    "Candidate",
    "CandidateDetection",
    "ContextBlock",
    "ImageOwnership",
    "PageSegment",
    "QuestionRegion",
    "StructuralAnalysis",
    "DocumentGraph",
    "DocumentGraphBuilder",
    "GraphNode",
    "GraphEdge",
    "EdgeType",
    "QuestionRegionBuilder",
]
