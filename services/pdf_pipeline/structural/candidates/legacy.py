"""Adapters exposing legacy parser rules as non-authoritative evidence."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping, Optional

from ..model import DocumentModel
from ...fallbacks.subject_classifier import SUBJECT_REGEX, format_subject_title
try:
    from ...legacy.registry import LEGACY_RULES
except ImportError:  # legacy adapters are optional in this isolated phase
    LEGACY_RULES = ()


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().upper()


class LegacyEvidenceProvider:
    """Use existing parser rules without invoking or changing production parsing.

    The provider intentionally returns small, bounded signals. A caller can
    inspect which legacy rule fired, but the bank name is never used as the
    primary classifier for a physical candidate.
    """

    def __init__(
        self,
        document: DocumentModel,
        *,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.document = document
        merged_metadata = dict(document.metadata or {})
        merged_metadata.update(dict(metadata or {}))
        self.metadata = merged_metadata
        self.document_text = "\n".join(
            str(element.text or "")
            for page in document.pages
            for element in page.elements
            if element.kind == "text"
        )
        normalized_metadata = " ".join(
            _normalize(value)
            for key, value in self.metadata.items()
            if key in {"bank", "banca", "declared_banca", "exam_title", "title"}
        )
        self.bank_context = _normalize(f"{normalized_metadata} {self.document_text[:12000]}")

    def header_evidence(self, text: str) -> dict[str, float]:
        explicit = bool(re.search(r"\b(?:QUEST[A-ZÃÃ]O|ITEM|Q)\b", _normalize(text)))
        matched_rules = [
            rule.name
            for rule in LEGACY_RULES
            if any(_normalize(signal) in self.bank_context for signal in rule.signals)
        ]
        score = 1.0 if explicit and matched_rules else 0.0
        return {
            "legacy_bank_header_match": score,
            "legacy_bank_rule_count": min(1.0, len(matched_rules) / 2.0),
        }

    def option_evidence(self, text: str) -> dict[str, float]:
        """Turn the current A-E extractor into a label signal only."""

        try:
            from ...hybrid_extractor import extract_options_from_chunk

            options, _ = extract_options_from_chunk(text)
            count = len(options or {})
        except Exception:
            count = 0
        return {
            "legacy_option_pattern": 1.0 if count >= 2 else 0.0,
            "legacy_option_count_norm": min(1.0, count / 5.0),
        }

    def subject_evidence(self, text: str) -> dict[str, float]:
        stripped = str(text or "").strip()
        regex_match = bool(SUBJECT_REGEX.fullmatch(stripped))
        classified = ""
        if stripped and len(stripped) <= 120:
            try:
                classified = str(format_subject_title(stripped) or "")
            except Exception:
                classified = ""
        classifier_match = bool(classified and _normalize(classified) != "GERAL")
        return {
            "legacy_subject_pattern": 1.0 if regex_match else 0.0,
            "legacy_subject_classifier": 1.0 if classifier_match else 0.0,
        }

    def context_evidence(self, text: str) -> dict[str, float]:
        normalized = _normalize(text)
        marker = bool(
            re.search(
                r"\b(?:TEXTO|INSTRUCAO|LEIA|CONSIDERE|COM BASE|PARA RESPONDER|QUESTOES)\b",
                normalized,
            )
        )
        range_marker = bool(re.search(r"\bQUESTOES?\b.*\d", normalized))
        legacy_extractor_match = False
        try:
            from ...layout.layout_detector import extract_context_blocks

            legacy_extractor_match = bool(extract_context_blocks(str(text or "")))
        except Exception:
            legacy_extractor_match = False
        return {
            "legacy_context_pattern": 1.0 if marker else 0.0,
            "legacy_context_question_range": 1.0 if range_marker else 0.0,
            "legacy_context_extractor": 1.0 if legacy_extractor_match else 0.0,
        }
