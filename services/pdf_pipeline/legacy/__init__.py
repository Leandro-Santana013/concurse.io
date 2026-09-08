"""Adapters and regression snapshots for the current PDF parser."""

from .adapter import (
    BancaLegacyParserAdapter,
    HybridLegacyParserAdapter,
    LegacyParserAdapter,
    LegacyParserContext,
    LegacyRule,
)
from .registry import LegacyParserRegistry, build_default_legacy_registry
from .snapshots import build_legacy_snapshot, write_legacy_snapshot

__all__ = [
    "BancaLegacyParserAdapter",
    "HybridLegacyParserAdapter",
    "LegacyParserAdapter",
    "LegacyParserContext",
    "LegacyRule",
    "LegacyParserRegistry",
    "build_default_legacy_registry",
    "build_legacy_snapshot",
    "write_legacy_snapshot",
]
