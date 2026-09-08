"""Structural reading-order sequences for single and multi-column pages."""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Optional

from ..model import PageModel, PhysicalElement
from .models import ColumnModel, ElementLayout, ReadingOrder


def build_reading_order(
    page: PageModel,
    elements: list[ElementLayout],
    columns: list[ColumnModel],
    *,
    topology_hint: Optional[str] = None,
    requested_mode: str = "AUTO",
    line_bucket_factor: float = 1.25,
) -> ReadingOrder:
    """Return IDs and NEXT_READING_BLOCK links, never a flattened text string."""

    element_map = {item.element_id: item for item in elements}
    physical_map = {item.id: item for item in page.elements}
    if len(columns) <= 1:
        mode = "SINGLE_COLUMN"
    else:
        requested = str(requested_mode or "AUTO").upper()
        hinted = str(topology_hint or "").upper()
        mode = (
            requested
            if requested in {"N_ORDER", "Z_ORDER"}
            else hinted
            if hinted in {"N_ORDER", "Z_ORDER"}
            else "N_ORDER"
        )

    if mode == "Z_ORDER":
        sequence = _z_order(page, elements, physical_map, line_bucket_factor)
    elif mode == "N_ORDER":
        sequence = _n_order(page, elements, columns, physical_map)
    else:
        sequence = _single_order(elements, physical_map)

    # Keep any element not reached by a geometry branch, including unusual
    # zero-sized records, so the structural result remains lossless.
    sequence.extend(
        item.element_id for item in elements if item.element_id not in sequence
    )
    for index, element_id in enumerate(sequence):
        if element_id in element_map:
            element_map[element_id].order_index = index
    links = {
        element_id: sequence[index + 1] if index + 1 < len(sequence) else None
        for index, element_id in enumerate(sequence)
    }
    return ReadingOrder(mode=mode, sequence=sequence, next_reading_block=links)


def _single_order(
    elements: list[ElementLayout],
    physical_map: Mapping[str, PhysicalElement],
) -> list[str]:
    return [
        item.element_id
        for item in sorted(
            elements,
            key=lambda item: _vertical_key(physical_map[item.element_id]),
        )
    ]


def _z_order(
    page: PageModel,
    elements: list[ElementLayout],
    physical_map: Mapping[str, PhysicalElement],
    line_bucket_factor: float,
) -> list[str]:
    median_height = _median_height(page)
    bucket = max(0.002, median_height * max(0.5, line_bucket_factor))
    return [
        item.element_id
        for item in sorted(
            elements,
            key=lambda item: (
                round(float(physical_map[item.element_id].bbox.ny0) / bucket),
                float(physical_map[item.element_id].bbox.nx0),
                float(physical_map[item.element_id].bbox.ny1),
                item.element_id,
            ),
        )
    ]


def _n_order(
    page: PageModel,
    elements: list[ElementLayout],
    columns: list[ColumnModel],
    physical_map: Mapping[str, PhysicalElement],
) -> list[str]:
    by_column: dict[int, list[ElementLayout]] = defaultdict(list)
    spanning: list[ElementLayout] = []
    for item in elements:
        if item.is_spanning or item.column_id is None:
            spanning.append(item)
        else:
            by_column[item.column_id].append(item)
    for column_items in by_column.values():
        column_items.sort(key=lambda item: _vertical_key(physical_map[item.element_id]))
    spanning.sort(key=lambda item: _vertical_key(physical_map[item.element_id]))

    sequence: list[str] = []
    consumed: set[str] = set()
    for span in spanning:
        span_y = float(physical_map[span.element_id].bbox.ny0)
        for column in sorted(columns, key=lambda item: item.index):
            for element in by_column.get(column.index, []):
                if element.element_id in consumed:
                    continue
                if float(physical_map[element.element_id].bbox.ny0) < span_y:
                    sequence.append(element.element_id)
                    consumed.add(element.element_id)
        sequence.append(span.element_id)
        consumed.add(span.element_id)

    for column in sorted(columns, key=lambda item: item.index):
        for element in by_column.get(column.index, []):
            if element.element_id not in consumed:
                sequence.append(element.element_id)
                consumed.add(element.element_id)
    return sequence


def _vertical_key(element: PhysicalElement) -> tuple[float, float, float, str]:
    return (
        float(element.bbox.ny0),
        float(element.bbox.nx0),
        float(element.bbox.ny1),
        element.id,
    )


def _median_height(page: PageModel) -> float:
    heights = sorted(
        float(element.bbox.height) / max(float(page.height), 1e-9)
        for element in page.elements
        if element.bbox.height > 0
    )
    if not heights:
        return 0.01
    middle = len(heights) // 2
    return heights[middle] if len(heights) % 2 else (heights[middle - 1] + heights[middle]) / 2.0

