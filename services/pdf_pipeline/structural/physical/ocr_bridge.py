"""Small adapter around the existing RapidOCR integration."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Optional

import fitz

from ..model import BBox, PhysicalElement


OCRReader = Callable[[fitz.Page, int], Sequence[Mapping[str, Any]]]


def _rapidocr_engine():
    from services.pdf_pipeline.media.diagram_cropper import get_rapidocr_engine

    return get_rapidocr_engine()


def read_ocr_lines(
    page: fitz.Page,
    dpi: int = 150,
    *,
    engine: Optional[Callable[..., Any]] = None,
) -> list[dict[str, Any]]:
    """Read OCR boxes and convert pixel coordinates back to PDF points."""

    engine = engine or _rapidocr_engine()
    if not engine:
        return []

    try:
        pixmap = page.get_pixmap(dpi=dpi, alpha=False)
        result = engine(pixmap.tobytes("png"))
        raw_lines = result[0] if isinstance(result, tuple) else result
    except Exception:
        return []

    if not raw_lines:
        return []

    scale_x = float(page.rect.width) / float(pixmap.width)
    scale_y = float(page.rect.height) / float(pixmap.height)
    lines: list[dict[str, Any]] = []
    for item in raw_lines:
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        image_bbox, text, score = item[0], item[1], item[2]
        if not text or not str(text).strip():
            continue
        try:
            confidence = float(score)
            points = list(image_bbox)
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
        except (TypeError, ValueError, IndexError):
            continue
        lines.append(
            {
                "bbox": (
                    min(xs) * scale_x,
                    min(ys) * scale_y,
                    max(xs) * scale_x,
                    max(ys) * scale_y,
                ),
                "text": str(text).strip(),
                "confidence": max(0.0, min(1.0, confidence)),
            }
        )
    return lines


def extract_ocr_elements(
    page: fitz.Page,
    page_index: int,
    *,
    dpi: int = 150,
    reader: Optional[OCRReader] = None,
    reason: str = "degraded_native_text",
) -> list[PhysicalElement]:
    """Create OCR-sourced elements while retaining their confidence."""

    lines = list(reader(page, dpi)) if reader is not None else read_ocr_lines(page, dpi)
    page_width = float(page.rect.width)
    page_height = float(page.rect.height)
    elements: list[PhysicalElement] = []

    for line_index, line in enumerate(lines):
        bbox_value = line.get("bbox")
        if bbox_value is None:
            try:
                bbox_value = (
                    line["x0"],
                    line["y0"],
                    line["x1"],
                    line["y1"],
                )
            except KeyError:
                continue
        text = line.get("text")
        if text is None or not str(text).strip():
            continue
        raw_confidence = line.get("confidence", line.get("score", 0.0))
        try:
            confidence = max(0.0, min(1.0, float(raw_confidence)))
        except (TypeError, ValueError):
            confidence = 0.0
        elements.append(
            PhysicalElement(
                id=f"p{page_index}-ocr{line_index}",
                page_index=page_index,
                kind="text",
                bbox=BBox.from_absolute(
                    *bbox_value,
                    page_width=page_width,
                    page_height=page_height,
                ),
                text=str(text).strip(),
                source="ocr",
                source_confidence=confidence,
                metadata={
                    "ocr_line_index": line_index,
                    "dpi": dpi,
                    "engine": "rapidocr-onnxruntime" if reader is None else "injected",
                    "fallback_reason": reason,
                },
            )
        )
    return elements
