"""DocumentProfile construction and deterministic fingerprinting."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from statistics import median, pstdev
from typing import Any, Iterable, Mapping, Optional

from ..model import BBox, DocumentModel, PhysicalElement
from .models import ClusterSummary, PageLayout, ZoneDetection


FINGERPRINT_FEATURES = (
    "column_count",
    "column_center_1",
    "column_center_2",
    "column_center_3",
    "median_body_font_norm",
    "header_zone_height",
    "footer_zone_height",
    "alignment_cluster_ratio",
    "line_spacing_median",
    "line_spacing_p90",
    "ocr_ratio",
    "image_density",
    "drawing_density",
    "spanning_ratio",
    "page_aspect_ratio",
    "scan_quality",
)


@dataclass
class DocumentProfile:
    page_size_stats: dict[str, Any] = field(default_factory=dict)
    column_models: list[dict[str, Any]] = field(default_factory=list)
    dominant_fonts: list[dict[str, Any]] = field(default_factory=list)
    style_clusters: list[dict[str, Any]] = field(default_factory=list)

    header_zone: Optional[BBox] = None
    footer_zone: Optional[BBox] = None

    reading_order_mode: str = "SINGLE_COLUMN"

    question_header_signature: Optional[dict[str, Any]] = None
    option_signature: Optional[dict[str, Any]] = None
    subject_signature: Optional[dict[str, Any]] = None

    ocr_ratio: float = 0.0
    scan_quality: float = 0.0

    fingerprint: list[float] = field(default_factory=list)
    fingerprint_version: str = "layout-profile-v1"
    fingerprint_features: tuple[str, ...] = FINGERPRINT_FEATURES

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "page_size_stats": self.page_size_stats,
            "column_models": self.column_models,
            "dominant_fonts": self.dominant_fonts,
            "style_clusters": self.style_clusters,
            "header_zone": self.header_zone.to_dict() if self.header_zone else None,
            "footer_zone": self.footer_zone.to_dict() if self.footer_zone else None,
            "reading_order_mode": self.reading_order_mode,
            "question_header_signature": self.question_header_signature,
            "option_signature": self.option_signature,
            "subject_signature": self.subject_signature,
            "ocr_ratio": self.ocr_ratio,
            "scan_quality": self.scan_quality,
            "fingerprint": list(self.fingerprint),
            "fingerprint_version": self.fingerprint_version,
            "fingerprint_features": list(self.fingerprint_features),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DocumentProfile":
        return cls(
            page_size_stats=dict(value.get("page_size_stats") or {}),
            column_models=[dict(item) for item in value.get("column_models", [])],
            dominant_fonts=[dict(item) for item in value.get("dominant_fonts", [])],
            style_clusters=[dict(item) for item in value.get("style_clusters", [])],
            header_zone=(
                BBox.from_dict(value["header_zone"])
                if value.get("header_zone")
                else None
            ),
            footer_zone=(
                BBox.from_dict(value["footer_zone"])
                if value.get("footer_zone")
                else None
            ),
            reading_order_mode=str(value.get("reading_order_mode", "SINGLE_COLUMN")),
            question_header_signature=value.get("question_header_signature"),
            option_signature=value.get("option_signature"),
            subject_signature=value.get("subject_signature"),
            ocr_ratio=float(value.get("ocr_ratio", 0.0)),
            scan_quality=float(value.get("scan_quality", 0.0)),
            fingerprint=[float(item) for item in value.get("fingerprint", [])],
            fingerprint_version=str(value.get("fingerprint_version", "layout-profile-v1")),
            fingerprint_features=tuple(
                value.get("fingerprint_features", FINGERPRINT_FEATURES)
            ),
        )

    @classmethod
    def from_json(cls, value: str) -> "DocumentProfile":
        return cls.from_dict(json.loads(value))


def build_document_profile(
    document: DocumentModel,
    page_layouts: list[PageLayout],
    zones: ZoneDetection,
    *,
    style_clusters: list[ClusterSummary],
    alignment_clusters: list[ClusterSummary],
    fingerprint_version: str = "layout-profile-v1",
) -> DocumentProfile:
    page_size_stats = _page_size_stats(document)
    column_models = _aggregate_columns(page_layouts)
    dominant_fonts = _dominant_fonts(document, zones)
    ocr_ratio, scan_quality = _ocr_and_scan_quality(document)
    line_spacing_median, line_spacing_p90 = _line_spacing(document, page_layouts)
    image_density, drawing_density = _visual_density(document)
    spanning_ratio = _spanning_ratio(page_layouts)
    alignment_ratio = len(alignment_clusters) / max(len(_text_elements(document)), 1)
    modes = [page.reading_order.mode for page in page_layouts]
    reading_mode = _dominant_mode(modes)

    dominant_column_count = _dominant_column_count(page_layouts)
    centers = [
        float(item.get("center_x_norm", 0.0))
        for item in column_models[:3]
    ]
    centers.extend([0.0] * (3 - len(centers)))
    median_body_font = _median_body_font(document, zones)
    header_height = float(zones.header_zone.ny1) if zones.header_zone else 0.0
    footer_height = (
        1.0 - float(zones.footer_zone.ny0) if zones.footer_zone else 0.0
    )
    aspect = float(page_size_stats.get("aspect_ratio_median", 0.0))
    fingerprint = [
        float(dominant_column_count),
        centers[0],
        centers[1],
        centers[2],
        median_body_font,
        header_height,
        footer_height,
        float(alignment_ratio),
        line_spacing_median,
        line_spacing_p90,
        ocr_ratio,
        image_density,
        drawing_density,
        spanning_ratio,
        aspect,
        scan_quality,
    ]
    fingerprint = [
        round(value, 8) if math.isfinite(value) else 0.0
        for value in fingerprint
    ]

    return DocumentProfile(
        page_size_stats=page_size_stats,
        column_models=column_models,
        dominant_fonts=dominant_fonts,
        style_clusters=[cluster.to_dict() for cluster in style_clusters],
        header_zone=zones.header_zone,
        footer_zone=zones.footer_zone,
        reading_order_mode=reading_mode,
        ocr_ratio=round(ocr_ratio, 8),
        scan_quality=round(scan_quality, 8),
        fingerprint=fingerprint,
        fingerprint_version=fingerprint_version,
    )


def _text_elements(document: DocumentModel) -> list[PhysicalElement]:
    return [
        element
        for page in document.pages
        for element in page.elements
        if element.kind == "text"
    ]


def _page_size_stats(document: DocumentModel) -> dict[str, Any]:
    widths = [float(page.width) for page in document.pages]
    heights = [float(page.height) for page in document.pages]
    aspects = [width / max(height, 1e-9) for width, height in zip(widths, heights)]
    return {
        "page_count": len(document.pages),
        "width_median": round(median(widths), 8) if widths else 0.0,
        "height_median": round(median(heights), 8) if heights else 0.0,
        "width_std": round(pstdev(widths), 8) if len(widths) > 1 else 0.0,
        "height_std": round(pstdev(heights), 8) if len(heights) > 1 else 0.0,
        "aspect_ratio_median": round(median(aspects), 8) if aspects else 0.0,
    }


def _aggregate_columns(page_layouts: list[PageLayout]) -> list[dict[str, Any]]:
    by_index: dict[int, list[Any]] = {}
    for page in page_layouts:
        for column in page.columns:
            by_index.setdefault(column.index, []).append(column)
    result: list[dict[str, Any]] = []
    for index in sorted(by_index):
        columns = by_index[index]
        result.append(
            {
                "index": index,
                "center_x_norm": round(median(item.center_x_norm for item in columns), 8),
                "x0_norm": round(median(item.x0_norm for item in columns), 8),
                "x1_norm": round(median(item.x1_norm for item in columns), 8),
                "width_norm": round(median(item.width_norm for item in columns), 8),
                "weight": round(median(item.weight for item in columns), 8),
                "pages_present": len(columns),
            }
        )
    return result


def _dominant_column_count(page_layouts: list[PageLayout]) -> int:
    counts: dict[int, int] = {}
    for page in page_layouts:
        count = len(page.columns)
        counts[count] = counts.get(count, 0) + 1
    return max(counts, key=lambda item: (counts[item], -item), default=1)


def _dominant_mode(modes: list[str]) -> str:
    counts: dict[str, int] = {}
    for mode in modes:
        counts[mode] = counts.get(mode, 0) + 1
    return max(counts, key=lambda item: (counts[item], item), default="SINGLE_COLUMN")


def _dominant_fonts(
    document: DocumentModel,
    zones: ZoneDetection,
) -> list[dict[str, Any]]:
    counts: dict[tuple[Any, ...], int] = {}
    for element in _text_elements(document):
        if element.id in zones.element_roles:
            continue
        key = (
            element.font_family or "",
            round(float(element.font_size or 0.0), 2),
            bool(element.bold),
            bool(element.italic),
        )
        counts[key] = counts.get(key, 0) + 1
    total = max(sum(counts.values()), 1)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    return [
        {
            "font_family": key[0],
            "font_size": key[1],
            "bold": key[2],
            "italic": key[3],
            "count": count,
            "ratio": round(count / total, 8),
        }
        for key, count in ordered
    ]


def _median_body_font(document: DocumentModel, zones: ZoneDetection) -> float:
    sizes = [
        float(element.font_size) / max(float(document.pages[element.page_index].height), 1e-9)
        for element in _text_elements(document)
        if element.font_size is not None and element.id not in zones.element_roles
    ]
    return round(median(sizes), 8) if sizes else 0.0


def _ocr_and_scan_quality(document: DocumentModel) -> tuple[float, float]:
    text = _text_elements(document)
    total_chars = sum(len(element.text or "") for element in text)
    ocr_chars = sum(
        len(element.text or "") for element in text if element.source == "ocr"
    )
    ocr_ratio = ocr_chars / max(total_chars, 1)
    page_scores: list[float] = []
    for page in document.pages:
        page_text = [element for element in page.elements if element.kind == "text"]
        if not page_text:
            page_scores.append(0.0)
            continue
        confidence = [
            float(element.source_confidence)
            for element in page_text
            if element.source == "ocr"
        ]
        page_scores.append(sum(confidence) / len(confidence) if confidence else 1.0)
    return float(ocr_ratio), float(sum(page_scores) / max(len(page_scores), 1))


def _line_spacing(
    document: DocumentModel,
    page_layouts: list[PageLayout],
) -> tuple[float, float]:
    gaps: list[float] = []
    for page_layout in page_layouts:
        page = document.pages[page_layout.page_index]
        physical = {element.id: element for element in page.elements}
        for column in range(len(page_layout.columns)):
            ordered = [
                element_id
                for element_id in page_layout.reading_order.sequence
                if next(
                    (
                        layout.column_id
                        for layout in page_layout.elements
                        if layout.element_id == element_id
                    ),
                    None,
                )
                == column
            ]
            for left_id, right_id in zip(ordered[:-1], ordered[1:]):
                left, right = physical[left_id], physical[right_id]
                gap = float(right.bbox.ny0) - float(left.bbox.ny1)
                if gap >= 0.0:
                    gaps.append(gap)
    if not gaps:
        return 0.0, 0.0
    ordered = sorted(gaps)
    p90_index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.90)))
    return round(float(median(ordered)), 8), round(float(ordered[p90_index]), 8)


def _visual_density(document: DocumentModel) -> tuple[float, float]:
    image_density: list[float] = []
    drawing_density: list[float] = []
    for page in document.pages:
        page_area = max(float(page.width) * float(page.height), 1e-9)
        image_density.append(
            sum(max(0.0, element.bbox.width * element.bbox.height) for element in page.elements if element.kind == "image")
            / page_area
        )
        drawing_density.append(
            sum(max(0.0, element.bbox.width * element.bbox.height) for element in page.elements if element.kind == "drawing")
            / page_area
        )
    return (
        round(float(sum(image_density) / max(len(image_density), 1)), 8),
        round(float(sum(drawing_density) / max(len(drawing_density), 1)), 8),
    )


def _spanning_ratio(page_layouts: list[PageLayout]) -> float:
    total = sum(len(page.elements) for page in page_layouts)
    spanning = sum(
        sum(1 for element in page.elements if element.is_spanning)
        for page in page_layouts
    )
    return spanning / max(total, 1)

