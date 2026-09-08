"""Non-destructive repeated header and footer detection."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Optional

from ..model import BBox, DocumentModel, PhysicalElement
from .config import ZoneConfig
from .models import ZoneDetection


@dataclass
class _ZoneItem:
    element: PhysicalElement
    role: str
    page_width: float
    page_height: float
    canonical_text: str
    style_key: tuple[Any, ...]


@dataclass
class _ZoneGroup:
    role: str
    items: list[_ZoneItem] = field(default_factory=list)

    @property
    def pages(self) -> set[int]:
        return {item.element.page_index for item in self.items}


def detect_repeated_zones(
    document: DocumentModel,
    *,
    config: Optional[ZoneConfig] = None,
) -> ZoneDetection:
    """Mark repeated top/bottom visual material while retaining every element."""

    cfg = config or ZoneConfig()
    groups: list[_ZoneGroup] = []
    for item in _candidate_items(document, cfg):
        group = _find_group(groups, item, cfg)
        if group is None:
            group = _ZoneGroup(role=item.role)
            groups.append(group)
        group.items.append(item)

    min_pages = max(1, int(cfg.min_repeat_pages))
    min_fraction = float(cfg.min_repeat_fraction)
    accepted = [
        group
        for group in groups
        if len(group.pages) >= min_pages
        and len(group.pages) / max(document.page_count, 1) >= min_fraction
    ]

    roles: dict[str, list[str]] = {}
    repeated_groups: list[dict[str, Any]] = []
    accepted_by_role: dict[str, list[_ZoneGroup]] = {"HEADER_NOISE": [], "FOOTER_NOISE": []}
    for group in accepted:
        accepted_by_role[group.role].append(group)
        for item in group.items:
            element_roles = roles.setdefault(item.element.id, [])
            if group.role not in element_roles:
                element_roles.append(group.role)
        representative = group.items[0]
        repeated_groups.append(
            {
                "role": group.role,
                "canonical_text": representative.canonical_text,
                "pages": sorted(group.pages),
                "element_ids": [item.element.id for item in group.items],
                "frequency": len(group.pages) / max(document.page_count, 1),
                "style": {
                    "font_family": representative.element.font_family,
                    "font_size": representative.element.font_size,
                    "bold": representative.element.bold,
                    "italic": representative.element.italic,
                },
            }
        )

    return ZoneDetection(
        header_zone=_union_zone(accepted_by_role["HEADER_NOISE"]),
        footer_zone=_union_zone(accepted_by_role["FOOTER_NOISE"]),
        element_roles={key: sorted(value) for key, value in roles.items()},
        repeated_groups=sorted(
            repeated_groups,
            key=lambda item: (item["role"], item["canonical_text"]),
        ),
    )


def _candidate_items(document: DocumentModel, config: ZoneConfig) -> list[_ZoneItem]:
    items: list[_ZoneItem] = []
    for page in document.pages:
        for element in page.elements:
            if element.kind != "text" or not (element.text or "").strip():
                continue
            if element.bbox.ny0 <= config.header_max_y:
                role = "HEADER_NOISE"
            elif element.bbox.ny1 >= config.footer_min_y:
                role = "FOOTER_NOISE"
            else:
                continue
            items.append(
                _ZoneItem(
                    element=element,
                    role=role,
                    page_width=page.width,
                    page_height=page.height,
                    canonical_text=_canonicalize(element.text or ""),
                    style_key=(
                        (element.font_family or "").lower(),
                        round(float(element.font_size or 0.0), 1),
                        bool(element.bold),
                        bool(element.italic),
                    ),
                )
            )
    return items


def _find_group(
    groups: list[_ZoneGroup],
    item: _ZoneItem,
    config: ZoneConfig,
) -> Optional[_ZoneGroup]:
    for group in groups:
        if group.role != item.role or not group.items:
            continue
        representative = group.items[0]
        if abs(
            float(representative.element.bbox.ny0) - float(item.element.bbox.ny0)
        ) > config.position_tolerance:
            continue
        if abs(
            float(representative.element.bbox.nx0) - float(item.element.bbox.nx0)
        ) > config.x_tolerance:
            continue
        text_similarity = SequenceMatcher(
            None,
            representative.canonical_text,
            item.canonical_text,
        ).ratio()
        same_text = (
            representative.canonical_text == item.canonical_text
            or text_similarity >= config.text_similarity_threshold
        )
        same_style = representative.style_key == item.style_key
        if same_text or (same_style and text_similarity >= 0.55):
            return group
    return None


def _canonicalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower()
    normalized = re.sub(r"\d+", "#", normalized)
    normalized = re.sub(r"[^\w#]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _union_zone(groups: list[_ZoneGroup]) -> Optional[BBox]:
    if not groups:
        return None
    items = [item for group in groups for item in group.items]
    if not items:
        return None
    reference = items[0]
    nx0 = min(float(item.element.bbox.nx0) for item in items)
    ny0 = min(float(item.element.bbox.ny0) for item in items)
    nx1 = max(float(item.element.bbox.nx1) for item in items)
    ny1 = max(float(item.element.bbox.ny1) for item in items)
    return BBox.from_absolute(
        nx0 * reference.page_width,
        ny0 * reference.page_height,
        nx1 * reference.page_width,
        ny1 * reference.page_height,
        reference.page_width,
        reference.page_height,
    )

