"""Confidence policy for choosing structural, legacy or quarantine results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence


class ArbitrationStatus(str, Enum):
    STRUCTURAL = "STRUCTURAL"
    LEGACY = "LEGACY"
    QUARANTINE = "QUARANTINE"


@dataclass(frozen=True)
class ArbiterConfig:
    structural_high: float = 0.80
    structural_medium: float = 0.55
    legacy_high: float = 0.75
    concordance_bonus: float = 0.08

    def to_dict(self) -> dict[str, float]:
        return {
            "structural_high": self.structural_high,
            "structural_medium": self.structural_medium,
            "legacy_high": self.legacy_high,
            "concordance_bonus": self.concordance_bonus,
        }


@dataclass
class ArbitrationDecision:
    status: ArbitrationStatus
    result: Optional[list[dict[str, Any]]]
    source: str
    confidence: float
    reason: str
    concordant: bool = False
    quarantined: bool = False
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def selected_result(self) -> Optional[list[dict[str, Any]]]:
        return self.result

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "result": self.result,
            "source": self.source,
            "confidence": self.confidence,
            "reason": self.reason,
            "concordant": self.concordant,
            "quarantined": self.quarantined,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


class ResultArbiter:
    """Apply the rollout policy without fabricating a result."""

    def __init__(self, config: Optional[ArbiterConfig] = None) -> None:
        self.config = config or ArbiterConfig()

    def arbitrate(
        self,
        *,
        legacy_result: Optional[Sequence[Mapping[str, Any]]],
        structural_result: Optional[Sequence[Mapping[str, Any]]],
        structural_confidence: Any = 0.0,
        legacy_confidence: Optional[float] = None,
        structural_failed: bool = False,
        diff: Any = None,
    ) -> ArbitrationDecision:
        legacy = [dict(item) for item in (legacy_result or [])]
        structural = [dict(item) for item in (structural_result or [])]
        structural_score = _confidence_value(structural_confidence)
        legacy_score = (
            _clamp(float(legacy_confidence))
            if legacy_confidence is not None
            else _legacy_confidence(legacy)
        )
        concordant = bool(structural and legacy and _semantically_concordant(legacy, structural))
        differs = _diff_has_differences(diff)

        if structural and not structural_failed and structural_score >= self.config.structural_high:
            if differs:
                return ArbitrationDecision(
                    status=ArbitrationStatus.QUARANTINE,
                    result=legacy,
                    source="quarantine",
                    confidence=structural_score,
                    reason="structural_high_legacy_divergent",
                    concordant=concordant,
                    quarantined=True,
                    warnings=["manual_review_required", "structural_diff_requires_gate"],
                    metadata={"legacy_confidence": legacy_score, "diff": _diff_value(diff)},
                )
            return ArbitrationDecision(
                status=ArbitrationStatus.STRUCTURAL,
                result=structural,
                source="structural",
                confidence=structural_score,
                reason="structural_high",
                concordant=concordant,
                metadata={"legacy_confidence": legacy_score},
            )

        if structural and not structural_failed and structural_score >= self.config.structural_medium:
            if concordant and not differs:
                return ArbitrationDecision(
                    status=ArbitrationStatus.STRUCTURAL,
                    result=structural,
                    source="structural",
                    confidence=_clamp(structural_score + self.config.concordance_bonus),
                    reason="structural_medium_legacy_concordant",
                    concordant=True,
                    metadata={"legacy_confidence": legacy_score},
                )
            return ArbitrationDecision(
                status=ArbitrationStatus.QUARANTINE,
                result=legacy,
                source="quarantine",
                confidence=structural_score,
                reason="structural_medium_legacy_divergent",
                quarantined=True,
                warnings=["manual_review_required", "structural_diff_requires_gate"]
                if differs
                else ["manual_review_required"],
                metadata={"legacy_confidence": legacy_score, "diff": _diff_value(diff)},
            )

        if legacy and legacy_score >= self.config.legacy_high:
            return ArbitrationDecision(
                status=ArbitrationStatus.LEGACY,
                result=legacy,
                source="legacy",
                confidence=legacy_score,
                reason="structural_low_legacy_high" if structural else "structural_unavailable_legacy_high",
                concordant=concordant,
                metadata={"structural_confidence": structural_score},
            )

        return ArbitrationDecision(
            status=ArbitrationStatus.QUARANTINE,
            result=legacy,
            source="quarantine",
            confidence=max(structural_score, legacy_score),
            reason="both_low_or_structural_failure",
            concordant=concordant,
            quarantined=True,
            warnings=["manual_review_required", "no_result_promoted"],
            metadata={
                "structural_confidence": structural_score,
                "legacy_confidence": legacy_score,
            },
        )

    resolve = arbitrate


StructuralResultArbiter = ResultArbiter


def _confidence_value(value: Any) -> float:
    if isinstance(value, (int, float)):
        return _clamp(float(value))
    if isinstance(value, Mapping):
        return _clamp(value.get("overall", value.get("confidence", 0.0)))
    return _clamp(getattr(value, "overall", getattr(value, "confidence", 0.0)))


def _legacy_confidence(questions: Sequence[Mapping[str, Any]]) -> float:
    if not questions:
        return 0.0
    raw_numbers = [item.get("numero_questao", item.get("printed_number")) for item in questions]
    numbers: list[int] = []
    for raw in raw_numbers:
        try:
            numbers.append(int(raw))
        except (TypeError, ValueError):
            continue
    unique = len(numbers) == len(set(numbers)) and len(numbers) == len(questions)
    ordered = numbers == sorted(numbers)
    score = 0.45
    score += 0.30 if unique else 0.0
    score += 0.20 if ordered else 0.0
    score += 0.05 if any(item.get("enunciado", item.get("statement")) for item in questions) else 0.0
    return _clamp(score)


def _semantically_concordant(
    legacy: Sequence[Mapping[str, Any]],
    structural: Sequence[Mapping[str, Any]],
) -> bool:
    if _numbers(legacy) != _numbers(structural):
        return False
    for left, right in zip(legacy, structural):
        left_options = left.get("opcoes", left.get("options", {})) or {}
        right_options = right.get("opcoes", right.get("options", {})) or {}
        if sorted(str(key).upper() for key in left_options) != sorted(str(key).upper() for key in right_options):
            return False
    return True


def _numbers(questions: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(item.get("numero_questao", item.get("printed_number", ""))) for item in questions]


def _diff_value(diff: Any) -> Any:
    if diff is None:
        return None
    if isinstance(diff, Mapping):
        return dict(diff)
    return getattr(diff, "changed_fields", None)


def _diff_has_differences(diff: Any) -> bool:
    if diff is None:
        return False
    if isinstance(diff, Mapping):
        if "has_differences" in diff:
            return bool(diff["has_differences"])
        return bool(diff.get("changed_fields"))
    return bool(getattr(diff, "has_differences", bool(getattr(diff, "changed_fields", ()))) )


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
