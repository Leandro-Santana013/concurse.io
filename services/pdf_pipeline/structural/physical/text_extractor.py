"""PyMuPDF text-span extraction without semantic question parsing."""

from __future__ import annotations

from typing import Any

import fitz

from ..model import BBox, PhysicalElement


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def extract_text_elements(page: fitz.Page, page_index: int) -> list[PhysicalElement]:
    """Return one physical element per PyMuPDF text span.

    The block/line/span coordinates remain available in the stable element ID
    and metadata. No regular expression is used to identify a question.
    """

    page_width = float(page.rect.width)
    page_height = float(page.rect.height)
    text_page = page.get_text("dict")
    elements: list[PhysicalElement] = []

    for block_index, block in enumerate(text_page.get("blocks", [])):
        if block.get("type") != 0:
            continue
        for line_index, line in enumerate(block.get("lines", [])):
            line_bbox = line.get("bbox")
            for span_index, span in enumerate(line.get("spans", [])):
                if "bbox" not in span:
                    continue
                text = span.get("text")
                if text is None or text == "":
                    continue

                flags = int(span.get("flags", 0) or 0)
                font_family = span.get("font")
                font_name = str(font_family or "").lower()
                bbox = BBox.from_absolute(
                    *span["bbox"],
                    page_width=page_width,
                    page_height=page_height,
                )
                metadata = {
                    "block_index": block_index,
                    "line_index": line_index,
                    "span_index": span_index,
                    "line_bbox": list(line_bbox) if line_bbox else None,
                    "color": span.get("color"),
                    "origin": list(span["origin"]) if span.get("origin") else None,
                }
                elements.append(
                    PhysicalElement(
                        id=f"p{page_index}-b{block_index}-l{line_index}-s{span_index}",
                        page_index=page_index,
                        kind="text",
                        bbox=bbox,
                        text=str(text),
                        font_family=str(font_family) if font_family is not None else None,
                        font_size=_as_float(span.get("size")),
                        bold=bool(flags & 16) or "bold" in font_name or "black" in font_name,
                        italic=bool(flags & 2) or "italic" in font_name or "oblique" in font_name,
                        flags=flags,
                        source="pdf_text",
                        source_confidence=1.0,
                        metadata=metadata,
                    )
                )
    return elements


def native_text_statistics(elements: list[PhysicalElement]) -> dict[str, int]:
    """Summarize the native text layer without changing its contents."""

    text_elements = [element for element in elements if element.kind == "text"]
    return {
        "element_count": len(text_elements),
        "character_count": sum(len(element.text or "") for element in text_elements),
    }
