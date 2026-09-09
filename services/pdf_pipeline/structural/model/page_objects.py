"""Page Object Model records for physical PDF elements."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Optional

from .geometry import BBox


ElementKind = Literal["text", "image", "drawing", "table", "marker"]
ElementSource = Literal["pdf_text", "ocr", "raster", "vector"]


@dataclass
class PhysicalElement:
    """One physical item extracted from a page.

    This record intentionally contains no question/header regular expression
    state. Ownership and semantic roles belong to later phases.
    """

    id: str
    page_index: int
    kind: ElementKind
    bbox: BBox
    text: Optional[str] = None
    font_family: Optional[str] = None
    font_size: Optional[float] = None
    bold: bool = False
    italic: bool = False
    flags: Optional[int] = None
    source: ElementSource = "pdf_text"
    source_confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.source_confidence) <= 1.0:
            raise ValueError("source_confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "page_index": self.page_index,
            "kind": self.kind,
            "bbox": self.bbox.to_dict(),
            "text": self.text,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "flags": self.flags,
            "source": self.source,
            "source_confidence": self.source_confidence,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PhysicalElement":
        return cls(
            id=str(value["id"]),
            page_index=int(value["page_index"]),
            kind=value["kind"],
            bbox=BBox.from_dict(value["bbox"]),
            text=value.get("text"),
            font_family=value.get("font_family"),
            font_size=(
                float(value["font_size"])
                if value.get("font_size") is not None
                else None
            ),
            bold=bool(value.get("bold", False)),
            italic=bool(value.get("italic", False)),
            flags=int(value["flags"]) if value.get("flags") is not None else None,
            source=value.get("source", "pdf_text"),
            source_confidence=float(value.get("source_confidence", 1.0)),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass
class PageModel:
    """All physical elements and page-level facts for one PDF page."""

    page_index: int
    width: float
    height: float
    elements: list[PhysicalElement] = field(default_factory=list)
    raster_features: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_index": self.page_index,
            "width": self.width,
            "height": self.height,
            "elements": [element.to_dict() for element in self.elements],
            "raster_features": self.raster_features,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PageModel":
        return cls(
            page_index=int(value["page_index"]),
            width=float(value["width"]),
            height=float(value["height"]),
            elements=[
                PhysicalElement.from_dict(item)
                for item in value.get("elements", [])
            ],
            raster_features=dict(value.get("raster_features") or {}),
        )
