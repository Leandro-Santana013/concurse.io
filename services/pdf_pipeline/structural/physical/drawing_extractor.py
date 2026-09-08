"""Extraction of vector drawing records from a PyMuPDF page."""

from __future__ import annotations

from typing import Any

import fitz

from ..model import BBox, PhysicalElement


def _rounded_rect(rect) -> tuple[int, int, int, int]:
    return (
        round(float(rect.x0) / 10),
        round(float(rect.y0) / 10),
        round(float(rect.x1) / 10),
        round(float(rect.y1) / 10),
    )


def extract_drawing_elements(
    page: fitz.Page,
    page_index: int,
    *,
    watermark_rects: set[tuple[int, int, int, int]] | None = None,
) -> list[PhysicalElement]:
    page_width = float(page.rect.width)
    page_height = float(page.rect.height)
    elements: list[PhysicalElement] = []

    try:
        drawings = page.get_drawings()
    except Exception:
        drawings = []

    for drawing_index, drawing in enumerate(drawings):
        rect = drawing.get("rect")
        if rect is None:
            continue
        metadata: dict[str, Any] = {
            "drawing_index": drawing_index,
            "item_count": len(drawing.get("items") or []),
            "type": drawing.get("type"),
            "width": drawing.get("width"),
            "stroke_opacity": drawing.get("stroke_opacity"),
            "fill_opacity": drawing.get("fill_opacity"),
            "is_repeated_layout_artifact": (
                _rounded_rect(rect) in (watermark_rects or set())
            ),
        }
        elements.append(
            PhysicalElement(
                id=f"p{page_index}-d{drawing_index}",
                page_index=page_index,
                kind="drawing",
                bbox=BBox.from_rect(rect, page_width, page_height),
                source="vector",
                source_confidence=1.0,
                metadata=metadata,
            )
        )
    return elements
