"""Runtime roles for preserved legacy bank adapters.

Dataprev, IBAM, IDCAP and the other named entries still delegate to the
existing hybrid parser.  This module gives them three explicit roles at the
structural seam: bounded evidence, localized recovery, and full fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Optional, Protocol

from .candidates.legacy import LegacyEvidenceProvider
from .model import DocumentModel
from ..legacy.adapter import LegacyParserAdapter, LegacyParserContext


class LegacyEvidenceRole(Protocol):
    def legacy_bank_header_match(self, candidate_or_text: Any) -> float: ...

    def legacy_option_pattern(self, text: str) -> float: ...

    def legacy_subject_pattern(self, text: str) -> float: ...


class LegacyRecoveryRole(Protocol):
    def recover_question(self, region: Any, expected_number: int) -> Any: ...


class LegacyFallbackRole(Protocol):
    def parse(self, pdf: Any, context: LegacyParserContext) -> list[dict[str, Any]]: ...


class LegacyRuntimeEvidenceProvider:
    """Expose old rules as named, bounded numeric evidence."""

    def __init__(
        self,
        adapter: LegacyParserAdapter,
        *,
        document: Optional[DocumentModel] = None,
        context: Optional[LegacyParserContext] = None,
    ) -> None:
        self.adapter = adapter
        self.context = context or LegacyParserContext()
        self.document = document
        self._provider = (
            LegacyEvidenceProvider(document, metadata=self.context.metadata)
            if document is not None
            else None
        )

    def legacy_bank_header_match(self, candidate_or_text: Any) -> float:
        text = _candidate_text(candidate_or_text)
        method = getattr(self.adapter, "legacy_bank_header_match", None)
        if callable(method):
            try:
                return _clamp(method(text, self.context))
            except TypeError:
                return _clamp(method(text))
        if self._provider is not None:
            evidence = self._provider.header_evidence(text)
            return _clamp(
                max(
                    evidence.get("legacy_bank_header_match", 0.0),
                    evidence.get("legacy_bank_rule_count", 0.0),
                )
            )
        return _clamp(float(self.adapter.supports(self.context)))

    def legacy_option_pattern(self, text: str) -> float:
        method = getattr(self.adapter, "legacy_option_pattern", None)
        if callable(method):
            return _clamp(method(text))
        if self._provider is not None:
            return _clamp(self._provider.option_evidence(text).get("legacy_option_pattern", 0.0))
        return 1.0 if re.match(r"^\s*[A-Ea-e][\.)\-:]", str(text or "")) else 0.0

    def legacy_subject_pattern(self, text: str) -> float:
        method = getattr(self.adapter, "legacy_subject_pattern", None)
        if callable(method):
            return _clamp(method(text))
        if self._provider is not None:
            return _clamp(self._provider.subject_evidence(text).get("legacy_subject_pattern", 0.0))
        return 0.0

    def evidence(self, candidate_or_text: Any) -> dict[str, float]:
        text = _candidate_text(candidate_or_text)
        return {
            "legacy_bank_header_match": self.legacy_bank_header_match(candidate_or_text),
            "legacy_option_pattern": self.legacy_option_pattern(text),
            "legacy_subject_pattern": self.legacy_subject_pattern(text),
        }

    # CandidateDetector-compatible aliases keep the adapter role at the
    # structural seam without changing the detector's existing interface.
    def header_evidence(self, text: str) -> dict[str, float]:
        score = self.legacy_bank_header_match(text)
        return {
            "legacy_bank_header_match": score,
            "legacy_bank_rule_count": score,
        }

    def option_evidence(self, text: str) -> dict[str, float]:
        score = self.legacy_option_pattern(text)
        return {
            "legacy_option_pattern": score,
            "legacy_option_count_norm": score,
        }

    def subject_evidence(self, text: str) -> dict[str, float]:
        score = self.legacy_subject_pattern(text)
        return {
            "legacy_subject_pattern": score,
            "legacy_subject_classifier": score,
        }

    def context_evidence(self, text: str) -> dict[str, float]:
        """Expose bounded context signals expected by the candidate detector."""

        if self._provider is not None:
            return self._provider.context_evidence(text)
        return {
            "legacy_context_pattern": 0.0,
            "legacy_context_question_range": 0.0,
            "legacy_context_extractor": 0.0,
        }


class LegacyRuntimeRecoveryProvider:
    """Call an adapter's optional local recovery hook, if it has one."""

    def __init__(self, adapter: LegacyParserAdapter) -> None:
        self.adapter = adapter

    def recover_question(self, region: Any, expected_number: int) -> Any:
        method = getattr(self.adapter, "recover_question", None)
        if not callable(method):
            return None
        return method(region, expected_number)


class LegacyRuntimeFallbackProvider:
    """Keep the unchanged parser behind the final fallback seam."""

    def __init__(self, adapter: LegacyParserAdapter) -> None:
        self.adapter = adapter

    def parse(self, pdf: Any, context: LegacyParserContext) -> list[dict[str, Any]]:
        return list(self.adapter.parse(pdf, context) or [])


@dataclass
class LegacyAdapterRoles:
    adapter: LegacyParserAdapter
    evidence: LegacyRuntimeEvidenceProvider
    recovery: LegacyRuntimeRecoveryProvider
    fallback: LegacyRuntimeFallbackProvider

    @property
    def adapter_name(self) -> str:
        return str(self.adapter.name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter_name,
            "roles": ["evidence", "recovery", "fallback"],
        }


def build_legacy_adapter_roles(
    adapter: LegacyParserAdapter,
    *,
    document: Optional[DocumentModel] = None,
    context: Optional[LegacyParserContext] = None,
) -> LegacyAdapterRoles:
    return LegacyAdapterRoles(
        adapter=adapter,
        evidence=LegacyRuntimeEvidenceProvider(adapter, document=document, context=context),
        recovery=LegacyRuntimeRecoveryProvider(adapter),
        fallback=LegacyRuntimeFallbackProvider(adapter),
    )


def _candidate_text(candidate_or_text: Any) -> str:
    if isinstance(candidate_or_text, str):
        return candidate_or_text
    if isinstance(candidate_or_text, Mapping):
        return str(candidate_or_text.get("line_text") or candidate_or_text.get("text") or "")
    metadata = getattr(candidate_or_text, "metadata", {}) or {}
    return str(metadata.get("line_text") or getattr(candidate_or_text, "text", "") or "")


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
