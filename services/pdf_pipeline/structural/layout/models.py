"""Serializable results produced by the phase-2 layout analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Optional

from ..model import BBox


@dataclass
class GutterCandidate:
    x0_norm: float
    x1_norm: float
    score: float
    persistence: float
    source: str = "text_layer"

    @property
    def width_norm(self) -> float:
        return self.x1_norm - self.x0_norm

    def to_dict(self) -> dict[str, Any]:
        return {
            "x0_norm": self.x0_norm,
            "x1_norm": self.x1_norm,
            "width_norm": self.width_norm,
            "score": self.score,
            "persistence": self.persistence,
            "source": self.source,
        }


@dataclass
class GutterEvidence:
    page_index: int
    candidates: list[GutterCandidate] = field(default_factory=list)
    projection: list[float] = field(default_factory=list)
    raster_projection: list[float] = field(default_factory=list)
    occupied_intervals: list[list[float]] = field(default_factory=list)
    source: str = "text_layer"
    used_raster: bool = False
    raster_dpi: Optional[int] = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_index": self.page_index,
            "candidates": [item.to_dict() for item in self.candidates],
            "projection": self.projection,
            "raster_projection": self.raster_projection,
            "occupied_intervals": self.occupied_intervals,
            "source": self.source,
            "used_raster": self.used_raster,
            "raster_dpi": self.raster_dpi,
            "diagnostics": self.diagnostics,
        }


@dataclass
class ColumnModel:
    index: int
    center_x_norm: float
    x0_norm: float
    x1_norm: float
    width_norm: float
    weight: float
    sample_count: int
    bic: Optional[float] = None
    bic_gain: float = 0.0
    gutter_score: float = 0.0
    gutter_validated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "center_x_norm": self.center_x_norm,
            "x0_norm": self.x0_norm,
            "x1_norm": self.x1_norm,
            "width_norm": self.width_norm,
            "weight": self.weight,
            "sample_count": self.sample_count,
            "bic": self.bic,
            "bic_gain": self.bic_gain,
            "gutter_score": self.gutter_score,
            "gutter_validated": self.gutter_validated,
        }


@dataclass
class ClusterSummary:
    cluster_id: int
    element_ids: list[str]
    centroid: dict[str, float]
    is_noise: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "element_ids": list(self.element_ids),
            "centroid": dict(self.centroid),
            "is_noise": self.is_noise,
        }


@dataclass
class ElementLayout:
    element_id: str
    page_index: int
    column_id: Optional[int] = None
    is_spanning: bool = False
    roles: list[str] = field(default_factory=list)
    alignment_cluster_id: Optional[int] = None
    style_cluster_id: Optional[int] = None
    order_index: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "page_index": self.page_index,
            "column_id": self.column_id,
            "is_spanning": self.is_spanning,
            "roles": list(self.roles),
            "alignment_cluster_id": self.alignment_cluster_id,
            "style_cluster_id": self.style_cluster_id,
            "order_index": self.order_index,
        }


@dataclass
class ReadingOrder:
    mode: str
    sequence: list[str]
    next_reading_block: dict[str, Optional[str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "sequence": list(self.sequence),
            "next_reading_block": dict(self.next_reading_block),
        }


@dataclass
class PageLayout:
    page_index: int
    columns: list[ColumnModel]
    gutter: GutterEvidence
    elements: list[ElementLayout]
    reading_order: ReadingOrder
    column_diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_index": self.page_index,
            "columns": [item.to_dict() for item in self.columns],
            "gutter": self.gutter.to_dict(),
            "elements": [item.to_dict() for item in self.elements],
            "reading_order": self.reading_order.to_dict(),
            "column_diagnostics": self.column_diagnostics,
        }


@dataclass
class ZoneDetection:
    header_zone: Optional[BBox] = None
    footer_zone: Optional[BBox] = None
    element_roles: dict[str, list[str]] = field(default_factory=dict)
    repeated_groups: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "header_zone": self.header_zone.to_dict() if self.header_zone else None,
            "footer_zone": self.footer_zone.to_dict() if self.footer_zone else None,
            "element_roles": self.element_roles,
            "repeated_groups": self.repeated_groups,
        }


@dataclass
class LayoutAnalysis:
    pages: list[PageLayout]
    document_profile: Any
    zones: ZoneDetection

    @property
    def profile(self) -> Any:
        """Short alias for callers that only need the DocumentProfile."""

        return self.document_profile

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "pages": [page.to_dict() for page in self.pages],
            "zones": self.zones.to_dict(),
            "document_profile": self.document_profile.to_dict(),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )
