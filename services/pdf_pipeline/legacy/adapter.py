"""A narrow seam around the existing hybrid parser.

The current repository does not contain independent Dataprev, IBAM or IDCAP
question parser functions. Their rules are distributed across the hybrid
extractor, layout detector, media extractor, banca family patterns and
gabarito services. This adapter records that reality without moving or
rewriting those rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Any, Dict, List, Mapping, Optional, Protocol


@dataclass(frozen=True)
class LegacyParserContext:
    """Inputs needed to invoke the legacy parser without changing its contract."""

    declared_banca: Optional[str] = None
    text_excerpt: str = ""
    exam_id: Optional[int] = None
    extract_images: bool = True
    gabarito_override: Optional[str] = None
    force_ocr: bool = False
    layout_config: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def parse_kwargs(self) -> dict[str, Any]:
        return {
            "exam_id": self.exam_id,
            "extract_images": self.extract_images,
            "gabarito_override": self.gabarito_override,
            "force_ocr": self.force_ocr,
            "layout_config": self.layout_config,
        }


class LegacyParserAdapter(Protocol):
    """Interface shared by the current parser and future legacy adapters."""

    name: str

    def supports(self, context: LegacyParserContext) -> float:
        """Return a confidence in [0, 1] for the supplied document context."""

    def parse(
        self,
        pdf: Any,
        context: LegacyParserContext,
    ) -> List[Dict[str, Any]]:
        """Return the existing question dictionary schema."""


class HybridLegacyParserAdapter:
    """Adapter for the unchanged services.pdf_pipeline.hybrid_extractor parser."""

    name = "hybrid_extractor"

    def supports(self, context: LegacyParserContext) -> float:
        return 0.10

    def parse(
        self,
        pdf: Any,
        context: Optional[LegacyParserContext] = None,
    ) -> List[Dict[str, Any]]:
        from services.pdf_pipeline.hybrid_extractor import parse_exam_document

        resolved_context = context or LegacyParserContext()
        return parse_exam_document(pdf, **resolved_context.parse_kwargs())


@dataclass(frozen=True)
class LegacyRule:
    """Inventory entry for a legacy rule family, not a new parser implementation."""

    name: str
    signals: tuple[str, ...]
    source_modules: tuple[str, ...]
    notes: str


def _normalize_signal(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]", "", normalized.upper())


class BancaLegacyParserAdapter:
    """Named bank adapter that delegates to the unchanged hybrid parser."""

    def __init__(
        self,
        rule: LegacyRule,
        delegate: Optional[HybridLegacyParserAdapter] = None,
    ) -> None:
        self.rule = rule
        self.delegate = delegate or HybridLegacyParserAdapter()
        self.name = rule.name

    @property
    def source_modules(self) -> tuple[str, ...]:
        return self.rule.source_modules

    def supports(self, context: LegacyParserContext) -> float:
        haystack = _normalize_signal(
            " ".join(
                [
                    context.declared_banca or "",
                    context.text_excerpt,
                ]
            )
        )
        if any(_normalize_signal(signal) in haystack for signal in self.rule.signals):
            return 0.95
        return 0.0

    def parse(
        self,
        pdf: Any,
        context: Optional[LegacyParserContext] = None,
    ) -> List[Dict[str, Any]]:
        return self.delegate.parse(pdf, context or LegacyParserContext())
