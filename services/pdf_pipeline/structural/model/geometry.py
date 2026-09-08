"""Geometry primitives for the physical PDF model."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


@dataclass(frozen=True)
class BBox:
    """A PDF rectangle with absolute and page-normalized coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float
    nx0: float
    ny0: float
    nx1: float
    ny1: float

    def __post_init__(self) -> None:
        values = (
            self.x0,
            self.y0,
            self.x1,
            self.y1,
            self.nx0,
            self.ny0,
            self.nx1,
            self.ny1,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("BBox coordinates must be finite numbers")
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("BBox maximum coordinates must not precede minimum coordinates")
        if self.nx1 < self.nx0 or self.ny1 < self.ny0:
            raise ValueError(
                "Normalized BBox maximum coordinates must not precede minimum coordinates"
            )

    @classmethod
    def from_absolute(
        cls,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
        page_width: float,
        page_height: float,
    ) -> "BBox":
        if page_width <= 0 or page_height <= 0:
            raise ValueError("Page dimensions must be positive")
        return cls(
            x0=float(x0),
            y0=float(y0),
            x1=float(x1),
            y1=float(y1),
            nx0=float(x0) / float(page_width),
            ny0=float(y0) / float(page_height),
            nx1=float(x1) / float(page_width),
            ny1=float(y1) / float(page_height),
        )

    @classmethod
    def from_rect(cls, rect: Any, page_width: float, page_height: float) -> "BBox":
        return cls.from_absolute(
            rect.x0,
            rect.y0,
            rect.x1,
            rect.y1,
            page_width,
            page_height,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BBox":
        return cls(
            x0=float(value["x0"]),
            y0=float(value["y0"]),
            x1=float(value["x1"]),
            y1=float(value["y1"]),
            nx0=float(value["nx0"]),
            ny0=float(value["ny0"]),
            nx1=float(value["nx1"]),
            ny1=float(value["ny1"]),
        )

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    def to_dict(self) -> dict[str, float]:
        return {
            "x0": self.x0,
            "y0": self.y0,
            "x1": self.x1,
            "y1": self.y1,
            "nx0": self.nx0,
            "ny0": self.ny0,
            "nx1": self.nx1,
            "ny1": self.ny1,
        }
