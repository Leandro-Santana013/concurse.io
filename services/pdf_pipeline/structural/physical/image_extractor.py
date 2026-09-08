"""Raster image extraction for the physical page model."""

from __future__ import annotations

import fitz

from ..model import BBox, PhysicalElement


def _rounded_rect(value) -> tuple[int, int, int, int]:
    coordinates = (
        (value.x0, value.y0, value.x1, value.y1)
        if hasattr(value, "x0")
        else tuple(value)
    )
    return tuple(round(float(coordinate) / 10) for coordinate in coordinates)


def _same_bbox(left: BBox, right: BBox, tolerance: float = 0.5) -> bool:
    return all(
        abs(a - b) <= tolerance
        for a, b in (
            (left.x0, right.x0),
            (left.y0, right.y0),
            (left.x1, right.x1),
            (left.y1, right.y1),
        )
    )


def extract_image_elements(
    page: fitz.Page,
    page_index: int,
    *,
    watermark_rects: set[tuple[int, int, int, int]] | None = None,
) -> list[PhysicalElement]:
    """Represent image blocks and image placements without assigning ownership."""

    page_width = float(page.rect.width)
    page_height = float(page.rect.height)
    elements: list[PhysicalElement] = []

    try:
        page_dict = page.get_text("dict")
    except Exception:
        page_dict = {}

    for block_index, block in enumerate(page_dict.get("blocks", [])):
        if block.get("type") != 1 or "bbox" not in block:
            continue
        is_repeated_layout_artifact = (
            _rounded_rect(block["bbox"]) in (watermark_rects or set())
        )
        bbox = BBox.from_absolute(
            *block["bbox"],
            page_width=page_width,
            page_height=page_height,
        )
        elements.append(
            PhysicalElement(
                id=f"p{page_index}-img-block{block_index}",
                page_index=page_index,
                kind="image",
                bbox=bbox,
                source="raster",
                source_confidence=1.0,
                metadata={
                    "block_index": block_index,
                    "xref": block.get("xref"),
                    "width": block.get("width"),
                    "height": block.get("height"),
                    "source_representation": "page.get_text(dict)",
                    "is_repeated_layout_artifact": is_repeated_layout_artifact,
                },
            )
        )

    try:
        image_infos = page.get_images(full=True)
    except Exception:
        image_infos = []

    for image_index, image_info in enumerate(image_infos):
        xref = image_info[0] if image_info else None
        try:
            placements = page.get_image_rects(xref) if xref is not None else []
        except Exception:
            placements = []
        for placement_index, rect in enumerate(placements):
            bbox = BBox.from_rect(rect, page_width, page_height)
            if any(_same_bbox(bbox, element.bbox) for element in elements):
                continue
            elements.append(
                PhysicalElement(
                    id=f"p{page_index}-img{image_index}-{placement_index}",
                    page_index=page_index,
                    kind="image",
                    bbox=bbox,
                    source="raster",
                    source_confidence=1.0,
                    metadata={
                        "xref": xref,
                        "image_index": image_index,
                        "placement_index": placement_index,
                        "source_representation": "page.get_images",
                        "is_repeated_layout_artifact": (
                            _rounded_rect(rect) in (watermark_rects or set())
                        ),
                    },
                )
            )
    return elements
