"""Opt-in structural PDF pipeline components."""

from .model import BBox, DocumentModel, PageModel, PhysicalElement
from .physical import PhysicalExtractor
from .layout import (
    ClusterSummary,
    ColumnConfig,
    ColumnModel,
    DBSCANConfig,
    DocumentProfile,
    ElementLayout,
    GutterCandidate,
    GutterConfig,
    GutterEvidence,
    LayoutAnalysis,
    LayoutAnalyzer,
    LayoutAnalyzerConfig,
    PageLayout,
    ReadingOrder,
    ZoneConfig,
    ZoneDetection,
)

__all__ = [
    "BBox", "DocumentModel", "PageModel", "PhysicalElement", "PhysicalExtractor",
    "LayoutAnalyzer", "LayoutAnalyzerConfig", "GutterConfig", "ColumnConfig",
    "DBSCANConfig", "ZoneConfig", "DocumentProfile", "LayoutAnalysis",
    "PageLayout", "ColumnModel", "GutterCandidate", "GutterEvidence",
    "ElementLayout", "ReadingOrder", "ClusterSummary", "ZoneDetection",
]
