"""Reproducible inventory of legacy rule families, separate from visual clusters.

Bank aliases document historical associations; they are not evidence that a
new PDF has a particular layout or answer format. No parser routing is changed.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from ..formatters.banca_clusterizer import BANCA_MAPPING, PROFILES, BancaFamily
from .registry import LEGACY_RULES


CATALOG_SCHEMA_VERSION = 1
_SOURCE = "services.pdf_pipeline.formatters.banca_clusterizer"
_NAMES = {
    BancaFamily.STANDARD_ACADEMIC: "Acadêmica padrão",
    BancaFamily.TRUE_FALSE_ITEM: "Itens de certo ou errado",
    BancaFamily.MUNICIPAL_PREFIXED: "Municipal com prefixos",
    BancaFamily.UNIVERSAL: "Universal (fallback)",
}


def normalize_family_alias(value: str) -> str:
    """Normalize accents, punctuation and case without substring matching."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def build_legacy_family_catalog() -> dict[str, Any]:
    """Capture actual patterns and their provenance without claiming PDF QA."""
    alias_families: dict[str, set[BancaFamily]] = {}
    for alias, family in BANCA_MAPPING.items():
        alias_families.setdefault(normalize_family_alias(alias), set()).add(family)

    families = []
    for family in BancaFamily:
        aliases = sorted(alias for alias, mapped in BANCA_MAPPING.items() if mapped == family)
        profile = dict(PROFILES[family])
        families.append({
            "family_id": f"legacy-{family.value.lower().replace('_', '-')}",
            "legacy_family": family.value,
            "name": _NAMES[family],
            "status": "imported_from_legacy",
            "validation_status": "pending_pdf_validation",
            "validated_reference_exam_ids": [],
            "is_fallback": family == BancaFamily.UNIVERSAL,
            "aliases": aliases,
            "normalized_aliases": sorted({normalize_family_alias(alias) for alias in aliases}),
            "patterns": {"header": profile["header"], "options": profile["options"]},
            "legacy_confidence_threshold": profile["confidence_threshold"],
            "source_references": [f"{_SOURCE}.BANCA_MAPPING", f"{_SOURCE}.PROFILES[{family.value}]"],
        })

    rules = []
    for rule in LEGACY_RULES:
        matches = sorted({
            family.value
            for signal in rule.signals
            for family in alias_families.get(normalize_family_alias(signal), set())
        })
        rules.append({
            "rule_id": rule.name,
            "signals": list(rule.signals),
            "candidate_family_ids": [f"legacy-{value.lower().replace('_', '-')}" for value in matches],
            "association_basis": "exact_normalized_signal_in_legacy_mapping" if matches else "unmapped",
            "source_modules": list(rule.source_modules),
            "notes": rule.notes,
        })

    content = {"families": families, "legacy_rules": rules}
    revision = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_kind": "legacy_rule_families",
        "content_sha256": revision,
        "usage": "Historical rule inventory; validate current PDF evidence before applying a family.",
        **content,
    }
