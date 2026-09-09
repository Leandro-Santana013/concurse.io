"""Document-level container and JSON serialization for the POM."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Optional

from .page_objects import PageModel


@dataclass
class DocumentModel:
    """A physical PDF document before layout or semantic interpretation."""

    pages: list[PageModel] = field(default_factory=list)
    source: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": self.source,
            "page_count": self.page_count,
            "pages": [page.to_dict() for page in self.pages],
            "metadata": self.metadata,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DocumentModel":
        return cls(
            pages=[PageModel.from_dict(item) for item in value.get("pages", [])],
            source=value.get("source"),
            metadata=dict(value.get("metadata") or {}),
        )

    @classmethod
    def from_json(cls, value: str) -> "DocumentModel":
        return cls.from_dict(json.loads(value))
