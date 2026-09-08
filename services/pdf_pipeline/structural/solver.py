"""Global constraint solving and localized recovery for Phase 4.

The solver is deliberately independent from the legacy question parser.  Its
public seam is ``ConstraintSolver.solve``: callers provide the Phase-3
structural analysis and may provide answer-key/legacy evidence, while the
implementation returns an auditable global sequence and a decomposable
confidence record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Iterable, Mapping, Optional, Sequence

from .candidates.features import FeatureVector, QUESTION_HEADER_FEATURES
from .candidates.graph import EdgeType
from .candidates.models import Candidate, QuestionRegion, StructuralAnalysis
from .model import BBox, DocumentModel, PhysicalElement


@dataclass(frozen=True)
class ConfidenceWeights:
    """Weights for the final confidence aggregation."""

    header: float = 0.25
    sequence: float = 0.25
    option: float = 0.15
    image: float = 0.10
    answer_key: float = 0.15
    structural: float = 0.10

    def to_dict(self) -> dict[str, float]:
        return {
            "header": self.header,
            "sequence": self.sequence,
            "option": self.option,
            "image": self.image,
            "answer_key": self.answer_key,
            "structural": self.structural,
        }


@dataclass(frozen=True)
class ConfidenceThresholds:
    """Configurable gates used only for diagnostics, never hard rejection."""

    header: float = 0.55
    sequence: float = 0.70
    option: float = 0.50
    image: float = 0.50
    answer_key: float = 0.80
    overall: float = 0.60

    def to_dict(self) -> dict[str, float]:
        return {
            "header": self.header,
            "sequence": self.sequence,
            "option": self.option,
            "image": self.image,
            "answer_key": self.answer_key,
            "overall": self.overall,
        }


@dataclass(frozen=True)
class SolverConfig:
    """All tunable constraint and recovery values live here.

    The defaults are intentionally conservative.  In particular, recovery is
    bounded by a local gap and never lowers the detector threshold globally.
    """

    sequence_step_reward: float = 1.20
    sequence_gap_penalty: float = 0.16
    backward_jump_penalty: float = 0.80
    duplicate_number_penalty: float = 1.10
    impossible_jump_penalty: float = 0.55
    layout_consistency_weight: float = 0.45
    option_support_weight: float = 0.35
    answer_key_support_weight: float = 0.28
    legacy_support_weight: float = 0.12
    explicit_header_bonus: float = 0.14
    non_explicit_header_penalty: float = 0.04
    start_number_bonus: float = 0.32
    end_number_bonus: float = 0.12
    max_sequence_jump: int = 8
    min_selected_candidate_score: float = 0.16
    recovery_enabled: bool = True
    recovery_min_score: float = 0.42
    recovery_max_gap: int = 3
    recovery_max_elements: int = 80
    recovery_exact_number_weight: float = 0.40
    recovery_locality_weight: float = 0.24
    recovery_style_weight: float = 0.16
    recovery_legacy_weight: float = 0.10
    recovery_ocr_weight: float = 0.10
    recovery_legacy_only_score: float = 0.43
    expected_option_counts: tuple[int, ...] = (4, 5)
    confidence_weights: ConfidenceWeights = field(default_factory=ConfidenceWeights)
    confidence_thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    missing_answer_key_confidence: float = 0.50

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence_step_reward": self.sequence_step_reward,
            "sequence_gap_penalty": self.sequence_gap_penalty,
            "backward_jump_penalty": self.backward_jump_penalty,
            "duplicate_number_penalty": self.duplicate_number_penalty,
            "impossible_jump_penalty": self.impossible_jump_penalty,
            "layout_consistency_weight": self.layout_consistency_weight,
            "option_support_weight": self.option_support_weight,
            "answer_key_support_weight": self.answer_key_support_weight,
            "legacy_support_weight": self.legacy_support_weight,
            "explicit_header_bonus": self.explicit_header_bonus,
            "non_explicit_header_penalty": self.non_explicit_header_penalty,
            "start_number_bonus": self.start_number_bonus,
            "end_number_bonus": self.end_number_bonus,
            "max_sequence_jump": self.max_sequence_jump,
            "min_selected_candidate_score": self.min_selected_candidate_score,
            "recovery_enabled": self.recovery_enabled,
            "recovery_min_score": self.recovery_min_score,
            "recovery_max_gap": self.recovery_max_gap,
            "recovery_max_elements": self.recovery_max_elements,
            "recovery_exact_number_weight": self.recovery_exact_number_weight,
            "recovery_locality_weight": self.recovery_locality_weight,
            "recovery_style_weight": self.recovery_style_weight,
            "recovery_legacy_weight": self.recovery_legacy_weight,
            "recovery_ocr_weight": self.recovery_ocr_weight,
            "recovery_legacy_only_score": self.recovery_legacy_only_score,
            "expected_option_counts": list(self.expected_option_counts),
            "confidence_weights": self.confidence_weights.to_dict(),
            "confidence_thresholds": self.confidence_thresholds.to_dict(),
            "missing_answer_key_confidence": self.missing_answer_key_confidence,
        }


@dataclass(frozen=True)
class AnswerKeyEvidence:
    """Normalized official-answer-key evidence used by the solver.

    It supports mappings (``{1: "A"}``), ordered answer sequences and the
    answer-key result objects already used by the application.  It never
    creates a question candidate by itself.
    """

    answers: Mapping[int, str] = field(default_factory=dict)
    expected_count: Optional[int] = None
    source: Optional[str] = None
    declared_coverage: Optional[float] = None

    def __post_init__(self) -> None:
        normalized: dict[int, str] = {}
        for raw_number, raw_answer in dict(self.answers or {}).items():
            try:
                number = int(raw_number)
            except (TypeError, ValueError):
                continue
            if number <= 0:
                continue
            normalized[number] = str(raw_answer or "").strip().upper()
        object.__setattr__(self, "answers", normalized)
        expected = self.expected_count
        if expected is None and normalized:
            numbers = sorted(normalized)
            expected = max(numbers) if numbers == list(range(1, max(numbers) + 1)) else len(numbers)
        object.__setattr__(self, "expected_count", int(expected) if expected else None)

    @classmethod
    def from_value(
        cls,
        value: Any = None,
        *,
        expected_count: Optional[int] = None,
        source: Optional[str] = None,
    ) -> "AnswerKeyEvidence":
        if isinstance(value, cls):
            if expected_count is None and source is None:
                return value
            return cls(
                answers=value.answers,
                expected_count=expected_count or value.expected_count,
                source=source or value.source,
                declared_coverage=value.declared_coverage,
            )
        answers: Any = value
        declared_coverage: Optional[float] = None
        if value is not None and not isinstance(value, Mapping):
            possible = getattr(value, "answers", None)
            if possible is not None:
                answers = possible
            declared_coverage = _optional_float(
                getattr(value, "coverage", None)
                or getattr(value, "coverage_pct", None)
                or getattr(value, "gabarito_coverage", None)
            )
            expected_count = expected_count or _optional_int(
                getattr(value, "expected_count", None)
                or getattr(value, "question_count", None)
            )
        if answers is None:
            normalized: dict[int, str] = {}
        elif isinstance(answers, Mapping):
            normalized = dict(answers)
        elif isinstance(answers, (list, tuple)):
            normalized = {index: item for index, item in enumerate(answers, start=1)}
        else:
            normalized = {}
        return cls(
            answers=normalized,
            expected_count=expected_count,
            source=source,
            declared_coverage=declared_coverage,
        )

    @property
    def available(self) -> bool:
        return bool(self.answers)

    @property
    def coverage(self) -> float:
        if self.declared_coverage is not None:
            value = self.declared_coverage
            return max(0.0, min(1.0, value / 100.0 if value > 1.0 else value))
        if not self.answers or not self.expected_count:
            return 0.0
        return max(0.0, min(1.0, len(self.answers) / self.expected_count))

    def supports(self, number: Optional[int]) -> float:
        return 1.0 if number is not None and int(number) in self.answers else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "answers": {str(k): v for k, v in sorted(self.answers.items())},
            "expected_count": self.expected_count,
            "source": self.source,
            "coverage": self.coverage,
        }


@dataclass
class DocumentParseConfidence:
    """Decomposable confidence for a solved document."""

    header_confidence: float = 0.0
    sequence_confidence: float = 0.0
    option_confidence: float = 0.0
    image_confidence: float = 0.0
    answer_key_coverage: float = 0.0
    overall: float = 0.0
    structural_confidence: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "header_confidence",
            "sequence_confidence",
            "option_confidence",
            "image_confidence",
            "answer_key_coverage",
            "overall",
            "structural_confidence",
        ):
            setattr(self, name, _clamp(getattr(self, name)))

    @classmethod
    def from_components(
        cls,
        *,
        header_confidence: float,
        sequence_confidence: float,
        option_confidence: float,
        image_confidence: float,
        answer_key_coverage: float,
        structural_confidence: float,
        weights: ConfidenceWeights,
    ) -> "DocumentParseConfidence":
        values = {
            "header_confidence": _clamp(header_confidence),
            "sequence_confidence": _clamp(sequence_confidence),
            "option_confidence": _clamp(option_confidence),
            "image_confidence": _clamp(image_confidence),
            "answer_key_coverage": _clamp(answer_key_coverage),
            "structural_confidence": _clamp(structural_confidence),
        }
        total_weight = sum(weights.to_dict().values()) or 1.0
        values["overall"] = (
            values["header_confidence"] * weights.header
            + values["sequence_confidence"] * weights.sequence
            + values["option_confidence"] * weights.option
            + values["image_confidence"] * weights.image
            + values["answer_key_coverage"] * weights.answer_key
            + values["structural_confidence"] * weights.structural
        ) / total_weight
        return cls(**values)

    def to_dict(self) -> dict[str, float]:
        return {
            "header_confidence": self.header_confidence,
            "sequence_confidence": self.sequence_confidence,
            "option_confidence": self.option_confidence,
            "image_confidence": self.image_confidence,
            "answer_key_coverage": self.answer_key_coverage,
            "structural_confidence": self.structural_confidence,
            "overall": self.overall,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DocumentParseConfidence":
        return cls(
            header_confidence=float(value.get("header_confidence", 0.0)),
            sequence_confidence=float(value.get("sequence_confidence", 0.0)),
            option_confidence=float(value.get("option_confidence", 0.0)),
            image_confidence=float(value.get("image_confidence", 0.0)),
            answer_key_coverage=float(value.get("answer_key_coverage", 0.0)),
            structural_confidence=float(value.get("structural_confidence", 0.0)),
            overall=float(value.get("overall", 0.0)),
        )


@dataclass
class ConstraintViolation:
    """An explicit, serializable rule violation."""

    rule: str
    message: str
    candidate_ids: list[str] = field(default_factory=list)
    penalty: float = 0.0
    severity: str = "warning"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "message": self.message,
            "candidate_ids": list(self.candidate_ids),
            "penalty": float(self.penalty),
            "severity": self.severity,
            "metadata": self.metadata,
        }


@dataclass
class SequenceSolution:
    """Global sequence selected by the constraint solver."""

    selected_candidates: list[Candidate] = field(default_factory=list)
    recovered_candidates: list[Candidate] = field(default_factory=list)
    discarded_candidates: list[Candidate] = field(default_factory=list)
    score: float = 0.0
    transition_scores: list[float] = field(default_factory=list)
    violations: list[ConstraintViolation] = field(default_factory=list)
    missing_numbers: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: DocumentParseConfidence = field(default_factory=DocumentParseConfidence)
    answer_key: AnswerKeyEvidence = field(default_factory=AnswerKeyEvidence)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def sequence(self) -> list[Candidate]:
        return self.selected_candidates

    @property
    def ordered_candidates(self) -> list[Candidate]:
        return self.selected_candidates

    @property
    def printed_numbers(self) -> list[int]:
        return [
            number
            for candidate in self.selected_candidates
            if (number := _candidate_number(candidate)) is not None
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_candidates": [item.to_dict() for item in self.selected_candidates],
            "recovered_candidates": [item.to_dict() for item in self.recovered_candidates],
            "discarded_candidates": [item.to_dict() for item in self.discarded_candidates],
            "score": self.score,
            "transition_scores": list(self.transition_scores),
            "violations": [item.to_dict() for item in self.violations],
            "missing_numbers": list(self.missing_numbers),
            "warnings": list(self.warnings),
            "confidence": self.confidence.to_dict(),
            "answer_key": self.answer_key.to_dict(),
            "metadata": self.metadata,
        }


class RecoveryPass:
    """Localized recovery adapter used by :class:`ConstraintSolver`."""

    def __init__(self, config: Optional[SolverConfig] = None) -> None:
        self.config = config or SolverConfig()

    def recover(
        self,
        number: int,
        *,
        selected: Sequence[Candidate],
        all_candidates: Sequence[Candidate],
        document: Optional[DocumentModel],
        analysis: StructuralAnalysis,
        legacy_questions: Optional[Sequence[Mapping[str, Any]]] = None,
        legacy_recovery_provider: Any = None,
    ) -> tuple[Optional[Candidate], dict[str, Any]]:
        order_map = _document_order_map(analysis, document)
        lower = [item for item in selected if (_candidate_number(item) or 0) < number]
        upper = [item for item in selected if (_candidate_number(item) or 10**9) > number]
        lower_order = max((order_map.get(_source_id(item), -1) for item in lower), default=-1)
        upper_order = min((order_map.get(_source_id(item), 10**9) for item in upper), default=10**9)

        existing = [
            candidate
            for candidate in all_candidates
            if _candidate_number(candidate) == number
            and candidate.id not in {item.id for item in selected}
        ]
        ranked: list[tuple[float, Candidate, dict[str, Any]]] = []
        for candidate in existing:
            candidate_order = order_map.get(_source_id(candidate), _candidate_order(candidate))
            if lower_order <= candidate_order <= upper_order:
                locality = 1.0
            else:
                locality = 0.35
            score = self._recovery_score(
                exact=1.0,
                locality=locality,
                style=_style_recovery_score(candidate, selected),
                legacy=_legacy_recovery_score(candidate),
                ocr=_candidate_ocr_score(candidate, document),
            )
            ranked.append(
                (
                    score,
                    _mark_recovered(candidate, score, "existing_candidate"),
                    {
                        "source": "existing_candidate",
                        "locality": locality,
                        "score": score,
                    },
                )
            )

        if document is not None:
            physical = [
                element
                for page in document.pages
                for element in page.elements
                if element.kind == "text" and str(element.text or "").strip()
            ]
            physical.sort(key=lambda item: order_map.get(item.id, _physical_order(item)))
            considered = 0
            for element in physical:
                if considered >= self.config.recovery_max_elements:
                    break
                parsed = _isolated_number(element.text)
                if parsed != number:
                    continue
                element_order = order_map.get(element.id, _physical_order(element))
                if not lower_order <= element_order <= upper_order:
                    continue
                considered += 1
                candidate = self._candidate_from_element(element, number, selected)
                score = self._recovery_score(
                    exact=1.0,
                    locality=1.0,
                    style=_element_style_recovery_score(element, selected, document),
                    legacy=_legacy_text_score(element.text),
                    ocr=float(element.source == "ocr"),
                )
                candidate.score = round(score, 8)
                candidate.score_breakdown["localized_recovery"] = score
                ranked.append(
                    (
                        score,
                        candidate,
                        {
                            "source": "physical_element",
                            "element_id": element.id,
                            "locality": 1.0,
                            "score": score,
                        },
                    )
                )

        if ranked:
            score, candidate, trace = max(
                ranked,
                key=lambda item: (item[0], -_candidate_order(item[1]), item[1].id),
            )
            if score >= self.config.recovery_min_score:
                return candidate, trace

        if legacy_recovery_provider is not None:
            region = next(
                (
                    item
                    for item in analysis.question_regions
                    if item.question_number == number
                ),
                None,
            )
            try:
                recovered = legacy_recovery_provider.recover_question(region, number)
            except Exception as exc:
                recovered = None
                provider_error = type(exc).__name__
            else:
                provider_error = None
            candidate = _candidate_from_legacy_recovery(
                recovered,
                number,
                self.config.recovery_legacy_only_score,
            )
            if candidate is not None:
                trace = {
                    "source": "legacy_recovery_provider",
                    "score": candidate.score,
                }
                if provider_error:
                    trace["provider_error"] = provider_error
                return candidate, trace

        for legacy_question in legacy_questions or []:
            raw_number = legacy_question.get("numero_questao")
            try:
                if int(str(raw_number).strip()) != number:
                    continue
            except (TypeError, ValueError):
                continue
            candidate = Candidate(
                id=f"recovered-question-header:legacy:{number}",
                type="QUESTION_HEADER",
                score=self.config.recovery_legacy_only_score,
                evidence={"legacy_recovery": 1.0},
                metadata={
                    "question_number": number,
                    "recovered": True,
                    "recovery_source": "legacy_adapter",
                    "legacy_question": dict(legacy_question),
                    "reading_index": upper_order if upper_order < 10**9 else lower_order,
                },
                source_element_ids=[],
                page_index=None,
                bbox=None,
                score_breakdown={"legacy_recovery": self.config.recovery_legacy_only_score},
            )
            return candidate, {
                "source": "legacy_adapter",
                "score": self.config.recovery_legacy_only_score,
            }
        return None, {"source": "not_found", "score": 0.0}

    def _recovery_score(
        self,
        *,
        exact: float,
        locality: float,
        style: float,
        legacy: float,
        ocr: float,
    ) -> float:
        return _clamp(
            self.config.recovery_exact_number_weight * exact
            + self.config.recovery_locality_weight * locality
            + self.config.recovery_style_weight * style
            + self.config.recovery_legacy_weight * legacy
            + self.config.recovery_ocr_weight * ocr
        )

    def _candidate_from_element(
        self,
        element: PhysicalElement,
        number: int,
        selected: Sequence[Candidate],
    ) -> Candidate:
        feature_values = {name: 0.0 for name in QUESTION_HEADER_FEATURES}
        feature_values.update(
            {
                "content.is_integer": 1.0,
                "content.integer_value_norm": min(1.0, number / 200.0),
                "content.has_question_token": float(bool(re.search(r"\b(?:questao|item|q)\b", element.text or "", re.I))),
                "content.regex_score": 0.90,
                "content.text_length": float(len(element.text or "")),
                "geometry.x0": float(element.bbox.nx0),
                "geometry.y0": float(element.bbox.ny0),
                "geometry.width": float(element.bbox.nx1 - element.bbox.nx0),
                "geometry.height": float(element.bbox.ny1 - element.bbox.ny0),
                "style.bold": float(element.bold),
                "style.font_size_body_ratio": 1.0,
                "sequence.prev_numeric_delta": 1.0,
                "sequence.next_numeric_delta": 1.0,
            }
        )
        return Candidate(
            id=f"recovered-question-header:{element.id}",
            type="QUESTION_HEADER",
            score=0.0,
            evidence={
                "numeric": 1.0,
                "regex": 0.90,
                "localized_recovery": 1.0,
            },
            metadata={
                "question_number": number,
                "line_text": str(element.text or "").strip(),
                "reading_index": _physical_order(element),
                "explicit_question_token": bool(re.search(r"\b(?:questao|item|q)\b", element.text or "", re.I)),
                "recovered": True,
                "recovery_source": "physical_element",
            },
            source_element_ids=[element.id],
            features=FeatureVector(values=feature_values),
            page_index=element.page_index,
            bbox=element.bbox,
            score_breakdown={},
        )


class ConstraintSolver:
    """Select the best global question sequence and recover local gaps."""

    def __init__(self, config: Optional[SolverConfig] = None) -> None:
        self.config = config or SolverConfig()
        self.recovery = RecoveryPass(self.config)

    def solve(
        self,
        analysis: StructuralAnalysis,
        *,
        document: Optional[DocumentModel] = None,
        answer_key: Any = None,
        legacy_questions: Optional[Sequence[Mapping[str, Any]]] = None,
        legacy_evidence: Optional[Mapping[int, float]] = None,
        legacy_recovery_provider: Any = None,
    ) -> SequenceSolution:
        """Return a globally scored sequence, never mutate ``analysis``.

        ``answer_key`` is evidence only.  A number present in it without a
        physical or localized candidate becomes a warning, not a fabricated
        question.
        """

        answer = AnswerKeyEvidence.from_value(answer_key)
        candidates = [
            candidate
            for candidate in analysis.question_candidates
            if _candidate_number(candidate) is not None
            and candidate.score >= self.config.min_selected_candidate_score
        ]
        order_map = _document_order_map(analysis, document)
        candidates.sort(key=lambda item: (_candidate_order(item, order_map), item.id))

        violations: list[ConstraintViolation] = []
        unique_candidates, duplicate_violations = self._deduplicate(
            candidates,
            order_map,
            analysis=analysis,
            answer_key=answer,
            legacy_evidence=legacy_evidence,
        )
        violations.extend(duplicate_violations)
        selected, discarded, transitions, score = self._dynamic_sequence(
            unique_candidates,
            analysis=analysis,
            answer_key=answer,
            order_map=order_map,
            legacy_evidence=legacy_evidence,
        )

        selected, overlap_violations = self._resolve_region_overlaps(
            selected,
            analysis.question_regions,
        )
        violations.extend(overlap_violations)
        numeric_answer_sequence = self._answer_key_sequence(
            unique_candidates,
            analysis=analysis,
            answer_key=answer,
            legacy_evidence=legacy_evidence,
        )
        numeric_ordering = bool(
            answer.available
            and len(answer.answers) >= 2
            and len(numeric_answer_sequence) >= 2
        )
        if numeric_ordering:
            # A complete/large answer-key sequence is global evidence.  It
            # can justify a physical inversion caused by columns, while the
            # key still cannot create a missing physical question.
            selected = numeric_answer_sequence
            violations.append(
                ConstraintViolation(
                    rule="reading_order",
                    message="Numeric sequence was selected globally with answer-key support; physical inversions remain traceable",
                    candidate_ids=[item.id for item in selected],
                    penalty=0.0,
                    severity="info",
                    metadata={"justification": "answer_key_global_sequence"},
                )
            )
            selected, numeric_overlap_violations = self._resolve_region_overlaps(
                selected,
                analysis.question_regions,
            )
            violations.extend(numeric_overlap_violations)
            score = sum(
                self._base_candidate_score(item, analysis, answer, legacy_evidence)
                for item in selected
            ) + self.config.sequence_step_reward * max(0, len(selected) - 1)
        discarded = [candidate for candidate in candidates if candidate.id not in {item.id for item in selected}]

        missing = self._missing_numbers(selected, answer)
        recovered: list[Candidate] = []
        recovery_trace: list[dict[str, Any]] = []
        warnings: list[str] = []
        if self.config.recovery_enabled:
            for number in missing:
                candidate, trace = self.recovery.recover(
                    number,
                    selected=selected,
                    all_candidates=candidates,
                    document=document,
                    analysis=analysis,
                    legacy_questions=legacy_questions,
                    legacy_recovery_provider=legacy_recovery_provider,
                )
                recovery_trace.append({"number": number, **trace})
                if candidate is None:
                    warnings.append(f"recovery_not_found:{number}")
                    violations.append(
                        ConstraintViolation(
                            rule="localized_recovery",
                            message=f"Q{number} is supported by sequence/gabarito evidence but no local candidate was found",
                            candidate_ids=[],
                            penalty=0.0,
                            severity="warning",
                            metadata={"question_number": number},
                        )
                    )
                    continue
                if number not in {_candidate_number(item) for item in selected}:
                    recovered.append(candidate)
                    selected.append(candidate)
        selected = self._sort_sequence(selected, order_map, numeric=numeric_ordering)

        selected_numbers = self._numbers(selected)
        if answer.available:
            missing_answer_numbers = sorted(set(answer.answers) - set(selected_numbers))
            if missing_answer_numbers:
                warnings.append("answer_key_without_candidate")
                violations.append(
                    ConstraintViolation(
                        rule="answer_key_support",
                        message="Official answer-key entries did not create questions",
                        candidate_ids=[],
                        penalty=0.0,
                        severity="warning",
                        metadata={"numbers": missing_answer_numbers},
                    )
                )
        if not selected:
            warnings.append("no_solved_question_sequence")

        confidence = self._confidence(
            selected,
            analysis=analysis,
            answer_key=answer,
            violations=violations,
        )
        for metric, threshold in (
            ("header", self.config.confidence_thresholds.header),
            ("sequence", self.config.confidence_thresholds.sequence),
            ("option", self.config.confidence_thresholds.option),
            ("image", self.config.confidence_thresholds.image),
            ("answer_key", self.config.confidence_thresholds.answer_key),
            ("overall", self.config.confidence_thresholds.overall),
        ):
            value = confidence.overall if metric == "overall" else getattr(
                confidence,
                f"{metric}_confidence" if metric != "answer_key" else "answer_key_coverage",
            )
            if answer.available or metric != "answer_key":
                if value < threshold:
                    warnings.append(f"low_confidence:{metric}")
        return SequenceSolution(
            selected_candidates=selected,
            recovered_candidates=recovered,
            discarded_candidates=discarded,
            score=round(score, 8),
            transition_scores=transitions,
            violations=violations,
            missing_numbers=[number for number in missing if number not in {_candidate_number(item) for item in recovered}],
            warnings=warnings,
            confidence=confidence,
            answer_key=answer,
            metadata={
                "solver_version": "constraint-solver-v1",
                "score_formula": {
                    "candidate_score": "candidate_score",
                    "sequence_score": "sequence_score",
                    "layout_consistency": "layout_consistency_weight * layout_consistency",
                    "option_support": "option_support_weight * option_support",
                    "answer_key_support": "answer_key_support_weight * answer_key_support",
                    "legacy_support": "legacy_support_weight * legacy_support",
                    "penalties": [
                        "overlap_penalty",
                        "backward_jump_penalty",
                        "impossible_jump_penalty",
                    ],
                },
                "recovery": recovery_trace,
                "config": self.config.to_dict(),
            },
        )

    def _deduplicate(
        self,
        candidates: Sequence[Candidate],
        order_map: Mapping[str, int],
        *,
        analysis: StructuralAnalysis,
        answer_key: AnswerKeyEvidence,
        legacy_evidence: Optional[Mapping[int, float]],
    ) -> tuple[list[Candidate], list[ConstraintViolation]]:
        groups: dict[int, list[Candidate]] = {}
        for candidate in candidates:
            number = _candidate_number(candidate)
            if number is not None:
                groups.setdefault(number, []).append(candidate)
        unique: list[Candidate] = []
        violations: list[ConstraintViolation] = []
        for number, group in groups.items():
            winner = max(
                group,
                key=lambda item: (
                    self._base_candidate_score(item, analysis, answer_key, legacy_evidence),
                    item.score,
                    -_candidate_order(item, order_map),
                    item.id,
                ),
            )
            unique.append(winner)
            if len(group) > 1:
                violations.append(
                    ConstraintViolation(
                        rule="unique_printed_number",
                        message=f"Multiple physical candidates share printed number {number}; strongest evidence selected",
                        candidate_ids=[item.id for item in group],
                        penalty=self.config.duplicate_number_penalty,
                        severity="warning",
                        metadata={"question_number": number, "selected": winner.id},
                    )
                )
        unique.sort(key=lambda item: (_candidate_order(item, order_map), item.id))
        return unique, violations

    def _answer_key_sequence(
        self,
        candidates: Sequence[Candidate],
        *,
        analysis: StructuralAnalysis,
        answer_key: AnswerKeyEvidence,
        legacy_evidence: Optional[Mapping[int, float]],
    ) -> list[Candidate]:
        if not answer_key.answers:
            return []
        by_number: dict[int, list[Candidate]] = {}
        for candidate in candidates:
            number = _candidate_number(candidate)
            if number is not None and number in answer_key.answers:
                by_number.setdefault(number, []).append(candidate)
        selected: list[Candidate] = []
        for number in sorted(answer_key.answers):
            group = by_number.get(number, [])
            if not group:
                continue
            selected.append(
                max(
                    group,
                    key=lambda item: (
                        self._base_candidate_score(item, analysis, answer_key, legacy_evidence)
                        + self._header_quality_bonus(item),
                        item.score,
                        -_candidate_order(item),
                        item.id,
                    ),
                )
            )
        return selected

    def _dynamic_sequence(
        self,
        candidates: Sequence[Candidate],
        *,
        analysis: StructuralAnalysis,
        answer_key: AnswerKeyEvidence,
        order_map: Mapping[str, int],
        legacy_evidence: Optional[Mapping[int, float]],
    ) -> tuple[list[Candidate], list[Candidate], list[float], float]:
        if not candidates:
            return [], [], [], 0.0
        base_scores = [
            self._base_candidate_score(candidate, analysis, answer_key, legacy_evidence)
            for candidate in candidates
        ]
        dp = list(base_scores)
        previous = [-1] * len(candidates)
        transitions = [0.0] * len(candidates)
        expected_start = min(answer_key.answers) if answer_key.answers else None
        for index, candidate in enumerate(candidates):
            number = _candidate_number(candidate)
            if expected_start is not None and number == expected_start:
                dp[index] += self.config.start_number_bonus
            for prior_index in range(index):
                prior = candidates[prior_index]
                transition = self._transition_score(
                    prior,
                    candidate,
                    analysis=analysis,
                    order_map=order_map,
                )
                value = dp[prior_index] + transition + base_scores[index]
                if value > dp[index]:
                    dp[index] = value
                    previous[index] = prior_index
                    transitions[index] = transition
        end_index = max(
            range(len(candidates)),
            key=lambda index: (
                dp[index]
                + (self.config.end_number_bonus if answer_key.answers and _candidate_number(candidates[index]) == max(answer_key.answers) else 0.0),
                -index,
            ),
        )
        selected_indices: list[int] = []
        cursor = end_index
        while cursor >= 0:
            selected_indices.append(cursor)
            cursor = previous[cursor]
        selected_indices.reverse()
        selected = [candidates[index] for index in selected_indices]
        discarded = [candidate for index, candidate in enumerate(candidates) if index not in set(selected_indices)]
        selected_transitions = [transitions[index] for index in selected_indices if transitions[index] != 0.0]
        return selected, discarded, selected_transitions, dp[end_index]

    def _base_candidate_score(
        self,
        candidate: Candidate,
        analysis: Optional[StructuralAnalysis],
        answer_key: AnswerKeyEvidence,
        legacy_evidence: Optional[Mapping[int, float]] = None,
    ) -> float:
        number = _candidate_number(candidate)
        option_support = self._option_support(candidate, analysis)
        answer_support = answer_key.supports(number)
        legacy_support = max(
            float(candidate.evidence.get("legacy_bank_header_match", 0.0)),
            float(candidate.evidence.get("legacy_bank_rule_score", 0.0)),
            float((legacy_evidence or {}).get(number or -1, 0.0)),
        )
        return (
            float(candidate.score)
            + self._header_quality_bonus(candidate)
            + self.config.option_support_weight * option_support
            + self.config.answer_key_support_weight * answer_support
            + self.config.legacy_support_weight * legacy_support
        )

    def _transition_score(
        self,
        prior: Candidate,
        current: Candidate,
        *,
        analysis: StructuralAnalysis,
        order_map: Mapping[str, int],
    ) -> float:
        prior_number = _candidate_number(prior)
        current_number = _candidate_number(current)
        if prior_number is None or current_number is None:
            return -self.config.impossible_jump_penalty
        difference = current_number - prior_number
        if difference == 1:
            sequence_score = self.config.sequence_step_reward
        elif difference > 1:
            sequence_score = -self.config.sequence_gap_penalty * (difference - 1)
        elif difference == 0:
            sequence_score = -self.config.duplicate_number_penalty
        else:
            sequence_score = -self.config.backward_jump_penalty * abs(difference)
        if difference > self.config.max_sequence_jump:
            sequence_score -= self.config.impossible_jump_penalty
        prior_order = _candidate_order(prior, order_map)
        current_order = _candidate_order(current, order_map)
        layout_consistency = 1.0 if current_order >= prior_order else -1.0
        if _same_column(prior, current, analysis):
            layout_consistency += 0.20
        if _graph_has_relation(
            analysis,
            prior,
            current,
            {EdgeType.NEXT_READING_BLOCK.value, EdgeType.BELOW.value, EdgeType.SAME_COLUMN.value},
        ):
            layout_consistency += 0.20
        if _overlapping_candidates(prior, current):
            layout_consistency -= 1.0
        return sequence_score + self.config.layout_consistency_weight * layout_consistency

    def _option_support(
        self,
        candidate: Candidate,
        analysis: Optional[StructuralAnalysis],
    ) -> float:
        if analysis is None:
            return float(candidate.evidence.get("options_below", 0.0))
        region = next(
            (item for item in analysis.question_regions if item.question_candidate_id == candidate.id),
            None,
        )
        if region is None:
            return float(candidate.evidence.get("options_below", 0.0))
        option_by_id = {item.id: item for item in analysis.option_candidates}
        groups = [option_by_id[item] for item in region.option_candidate_ids if item in option_by_id]
        if not groups:
            return float(candidate.evidence.get("options_below", 0.0))
        count = max(int(group.metadata.get("count", 0)) for group in groups)
        expected = self._expected_option_counts(analysis)
        if count in expected:
            return 1.0
        if count in {2, 3}:
            return 0.55
        return 0.25

    def _expected_option_counts(self, analysis: StructuralAnalysis) -> tuple[int, ...]:
        profile = getattr(analysis, "document_profile", None)
        signature = getattr(profile, "option_signature", None) or {}
        inferred = signature.get("dominant_counts") or signature.get("counts") or ()
        values: list[int] = []
        if isinstance(inferred, Mapping):
            values = [int(key) for key in inferred if str(key).isdigit()]
        elif isinstance(inferred, (list, tuple, set)):
            values = [int(item) for item in inferred if str(item).isdigit()]
        return tuple(values) or self.config.expected_option_counts

    def _resolve_region_overlaps(
        self,
        selected: Sequence[Candidate],
        regions: Sequence[QuestionRegion],
    ) -> tuple[list[Candidate], list[ConstraintViolation]]:
        by_candidate = {region.question_candidate_id: region for region in regions}
        resolved = list(selected)
        violations: list[ConstraintViolation] = []
        changed = True
        while changed:
            changed = False
            for index, left in enumerate(list(resolved)):
                left_region = by_candidate.get(left.id)
                if left_region is None:
                    continue
                for right in list(resolved[index + 1 :]):
                    right_region = by_candidate.get(right.id)
                    if right_region is None or not _regions_overlap(left_region, right_region):
                        continue
                    loser = right if left.score >= right.score else left
                    winner = left if loser is right else right
                    if loser in resolved:
                        resolved.remove(loser)
                    violations.append(
                        ConstraintViolation(
                            rule="region_non_overlap",
                            message="Overlapping question regions cannot both belong to the solved sequence",
                            candidate_ids=[left.id, right.id],
                            penalty=self.config.impossible_jump_penalty,
                            severity="warning",
                            metadata={"selected": winner.id, "discarded": loser.id},
                        )
                    )
                    changed = True
                    break
                if changed:
                    break
        return resolved, violations

    def _missing_numbers(
        self,
        selected: Sequence[Candidate],
        answer_key: AnswerKeyEvidence,
    ) -> list[int]:
        numbers = self._numbers(selected)
        if len(numbers) < 2 and not answer_key.answers:
            return []
        missing: set[int] = set()
        for prior, current in zip(numbers[:-1], numbers[1:]):
            if 1 < current - prior <= self.config.recovery_max_gap:
                missing.update(range(prior + 1, current))
        if answer_key.answers:
            missing.update(
                number
                for number in answer_key.answers
                if number not in numbers
                and (not numbers or min(numbers) - self.config.recovery_max_gap <= number <= max(numbers) + self.config.recovery_max_gap)
            )
        return sorted(missing)

    def _sort_sequence(
        self,
        selected: Sequence[Candidate],
        order_map: Mapping[str, int],
        *,
        numeric: bool = False,
    ) -> list[Candidate]:
        if numeric:
            return sorted(
                selected,
                key=lambda item: (
                    _candidate_number(item) is None,
                    _candidate_number(item) if _candidate_number(item) is not None else 10**9,
                    item.id,
                ),
            )
        return sorted(
            selected,
            key=lambda item: (
                _candidate_order(item, order_map),
                _candidate_number(item) is None,
                _candidate_number(item) if _candidate_number(item) is not None else 10**9,
                item.id,
            ),
        )

    def _numbers(self, candidates: Sequence[Candidate]) -> list[int]:
        return [number for candidate in candidates if (number := _candidate_number(candidate)) is not None]

    def _header_quality_bonus(self, candidate: Candidate) -> float:
        explicit = bool(candidate.metadata.get("explicit_question_token"))
        return (
            self.config.explicit_header_bonus
            if explicit
            else -self.config.non_explicit_header_penalty
        )

    def _confidence(
        self,
        selected: Sequence[Candidate],
        *,
        analysis: StructuralAnalysis,
        answer_key: AnswerKeyEvidence,
        violations: Sequence[ConstraintViolation],
    ) -> DocumentParseConfidence:
        if not selected:
            return DocumentParseConfidence()
        header = sum(float(item.score) for item in selected) / len(selected)
        numbers = self._numbers(selected)
        adjacent = [
            current - prior == 1
            for prior, current in zip(numbers[:-1], numbers[1:])
        ]
        sequence = sum(adjacent) / len(adjacent) if adjacent else 1.0
        option_values = [self._option_support(item, analysis) for item in selected]
        option = sum(option_values) / len(option_values) if option_values else 0.5
        owned = {
            item.question_candidate_id: item.score
            for item in analysis.image_ownership
        }
        image_values = [owned.get(item.id, 1.0) for item in selected]
        image = sum(image_values) / len(image_values) if image_values else 1.0
        if answer_key.available:
            answer_coverage = len(set(numbers) & set(answer_key.answers)) / max(
                answer_key.expected_count or len(answer_key.answers),
                1,
            )
        else:
            answer_coverage = self.config.missing_answer_key_confidence
        structural = 1.0 - min(1.0, len(violations) / max(len(selected), 1))
        return DocumentParseConfidence.from_components(
            header_confidence=header,
            sequence_confidence=sequence,
            option_confidence=option,
            image_confidence=image,
            answer_key_coverage=answer_coverage,
            structural_confidence=structural,
            weights=self.config.confidence_weights,
        )


# Descriptive aliases make the seam easy to discover for callers and tests.
ConstraintSolverConfig = SolverConfig
ConstraintSolveResult = SequenceSolution


def solve_constraints(
    analysis: StructuralAnalysis,
    *,
    solver: Optional[ConstraintSolver] = None,
    document: Optional[DocumentModel] = None,
    answer_key: Any = None,
    legacy_questions: Optional[Sequence[Mapping[str, Any]]] = None,
    legacy_evidence: Optional[Mapping[int, float]] = None,
) -> SequenceSolution:
    return (solver or ConstraintSolver()).solve(
        analysis,
        document=document,
        answer_key=answer_key,
        legacy_questions=legacy_questions,
        legacy_evidence=legacy_evidence,
    )


def _candidate_number(candidate: Candidate) -> Optional[int]:
    raw = candidate.metadata.get("question_number")
    if raw is None:
        raw = re.search(r"(?:^|:)(\d{1,3})", candidate.id)
        raw = raw.group(1) if raw else None
    try:
        number = int(raw)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _candidate_order(
    candidate: Candidate,
    order_map: Optional[Mapping[str, int]] = None,
) -> int:
    if candidate.source_element_ids and order_map:
        values = [order_map.get(item) for item in candidate.source_element_ids if item in order_map]
        if values:
            return min(values)
    raw = candidate.metadata.get("reading_index")
    try:
        return int(raw)
    except (TypeError, ValueError):
        pass
    page = candidate.page_index if candidate.page_index is not None else 0
    y = candidate.bbox.ny0 if candidate.bbox else 0.0
    x = candidate.bbox.nx0 if candidate.bbox else 0.0
    return int(page * 1_000_000 + y * 10_000 + x * 100)


def _source_id(candidate: Candidate) -> str:
    return candidate.source_element_ids[0] if candidate.source_element_ids else candidate.id


def _document_order_map(
    analysis: StructuralAnalysis,
    document: Optional[DocumentModel],
) -> dict[str, int]:
    result: dict[str, int] = {}
    cursor = 0
    layout = getattr(analysis, "layout_analysis", None)
    if layout is not None:
        for page in sorted(layout.pages, key=lambda item: item.page_index):
            for element_id in page.reading_order.sequence:
                result.setdefault(element_id, cursor)
                cursor += 1
    if document is not None:
        for page in sorted(document.pages, key=lambda item: item.page_index):
            for element in sorted(page.elements, key=_physical_order):
                result.setdefault(element.id, cursor)
                cursor += 1
    for candidate in analysis.question_candidates:
        for element_id in candidate.source_element_ids:
            result.setdefault(element_id, _candidate_order(candidate))
    return result


def _physical_order(element: PhysicalElement) -> int:
    return int(
        element.page_index * 1_000_000
        + float(element.bbox.ny0) * 10_000
        + float(element.bbox.nx0) * 100
    )


def _same_column(
    left: Candidate,
    right: Candidate,
    analysis: StructuralAnalysis,
) -> bool:
    layout = getattr(analysis, "layout_analysis", None)
    if layout is None:
        return False
    by_id = {
        item.element_id: item
        for page in layout.pages
        for item in page.elements
    }
    left_columns = {
        by_id[item].column_id
        for item in left.source_element_ids
        if item in by_id and by_id[item].column_id is not None
    }
    right_columns = {
        by_id[item].column_id
        for item in right.source_element_ids
        if item in by_id and by_id[item].column_id is not None
    }
    return bool(left_columns and right_columns and left_columns & right_columns)


def _graph_has_relation(
    analysis: StructuralAnalysis,
    prior: Candidate,
    current: Candidate,
    relations: set[str],
) -> bool:
    graph = getattr(analysis, "graph", None)
    if graph is None:
        return False
    current_ids = set(current.source_element_ids)
    for source_id in prior.source_element_ids:
        for edge in graph.edges_by_source.get(source_id, []):
            if edge.relation in relations and edge.target in current_ids:
                return True
    return False


def _overlapping_candidates(left: Candidate, right: Candidate) -> bool:
    if left.page_index is None or right.page_index is None or left.page_index != right.page_index:
        return False
    if left.bbox is None or right.bbox is None:
        return bool(set(left.source_element_ids) & set(right.source_element_ids))
    return _bbox_overlap(left.bbox, right.bbox) > 0.20


def _regions_overlap(left: QuestionRegion, right: QuestionRegion) -> bool:
    if set(left.content_element_ids) & set(right.content_element_ids):
        return True
    left_boxes = [segment.bbox for segment in left.segments if segment.bbox]
    right_boxes = [segment.bbox for segment in right.segments if segment.bbox]
    return any(_bbox_overlap(first, second) > 0.35 for first in left_boxes for second in right_boxes)


def _bbox_overlap(left: BBox, right: BBox) -> float:
    x_overlap = max(0.0, min(left.nx1, right.nx1) - max(left.nx0, right.nx0))
    y_overlap = max(0.0, min(left.ny1, right.ny1) - max(left.ny0, right.ny0))
    intersection = x_overlap * y_overlap
    smaller = min(max(left.width * left.height, 1e-9), max(right.width * right.height, 1e-9))
    return intersection / smaller


def _isolated_number(text: Any) -> Optional[int]:
    normalized = str(text or "").strip()
    match = re.match(
        r"^(?:(?:quest(?:ao|ão)|item|q)\s*0*)?\(?0*(\d{1,3})\)?(?:\s*[\.:;\)\-])?\s*$",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None
    number = int(match.group(1))
    return number if number > 0 else None


def _mark_recovered(candidate: Candidate, score: float, source: str) -> Candidate:
    metadata = dict(candidate.metadata)
    metadata.update({"recovered": True, "recovery_source": source})
    return Candidate(
        id=f"recovered-question-header:{candidate.id}",
        type=candidate.type,
        score=round(score, 8),
        evidence=dict(candidate.evidence),
        metadata=metadata,
        source_element_ids=list(candidate.source_element_ids),
        features=candidate.features,
        page_index=candidate.page_index,
        bbox=candidate.bbox,
        score_breakdown={**candidate.score_breakdown, "localized_recovery": score},
    )


def _style_recovery_score(candidate: Candidate, selected: Sequence[Candidate]) -> float:
    if not selected:
        return 0.5
    value = candidate.evidence.get("same_style_cluster")
    if value is not None:
        return _clamp(float(value))
    bold = bool(candidate.features and candidate.features.get("style.bold", 0.0) >= 0.5)
    selected_bold = [
        bool(item.features and item.features.get("style.bold", 0.0) >= 0.5)
        for item in selected
    ]
    return 1.0 if selected_bold and bold == (sum(selected_bold) >= len(selected_bold) / 2.0) else 0.35


def _element_style_recovery_score(
    element: PhysicalElement,
    selected: Sequence[Candidate],
    document: DocumentModel,
) -> float:
    if not selected:
        return 0.5
    selected_sizes = [
        item.features.get("style.font_size_body_ratio", 1.0)
        for item in selected
        if item.features is not None
    ]
    median_size = sorted(selected_sizes)[len(selected_sizes) // 2] if selected_sizes else 1.0
    body_sizes = [
        float(other.font_size)
        for page in document.pages
        for other in page.elements
        if other.kind == "text" and other.font_size is not None
    ]
    body = sorted(body_sizes)[len(body_sizes) // 2] if body_sizes else float(element.font_size or 1.0)
    ratio = float(element.font_size or body) / max(body, 1e-9)
    return _clamp(1.0 - abs(ratio - median_size) / 1.5)


def _legacy_recovery_score(candidate: Candidate) -> float:
    return max(
        float(candidate.evidence.get("legacy_bank_header_match", 0.0)),
        float(candidate.evidence.get("legacy_bank_rule_score", 0.0)),
    )


def _legacy_text_score(text: Any) -> float:
    return 1.0 if re.search(r"\b(?:quest(?:ao|ão)|item|q)\b", str(text or ""), re.I) else 0.35


def _candidate_ocr_score(candidate: Candidate, document: Optional[DocumentModel]) -> float:
    if document is None:
        return 0.0
    source_ids = set(candidate.source_element_ids)
    return max(
        (float(element.source == "ocr") for page in document.pages for element in page.elements if element.id in source_ids),
        default=0.0,
    )


def _optional_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clamp(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _candidate_from_legacy_recovery(
    value: Any,
    number: int,
    default_score: float,
) -> Optional[Candidate]:
    """Normalize an adapter recovery payload without fabricating geometry."""

    if value is None:
        return None
    if isinstance(value, Candidate):
        value.metadata = {
            **value.metadata,
            "question_number": number,
            "recovered": True,
            "recovery_source": "legacy_recovery_provider",
        }
        value.score = max(float(value.score), float(default_score))
        return value
    if not isinstance(value, Mapping):
        return None
    payload = dict(value)
    raw_candidate = payload.get("candidate")
    if isinstance(raw_candidate, Candidate):
        return _candidate_from_legacy_recovery(raw_candidate, number, default_score)
    metadata = dict(payload.get("metadata") or {})
    metadata.update(
        {
            "question_number": number,
            "recovered": True,
            "recovery_source": "legacy_recovery_provider",
        }
    )
    source_ids = [str(item) for item in payload.get("source_element_ids", [])]
    score = float(payload.get("score", default_score))
    evidence = {"legacy_recovery": 1.0}
    evidence.update(
        {
            str(key): float(raw_value)
            for key, raw_value in (payload.get("evidence") or {}).items()
            if _is_number(raw_value)
        }
    )
    return Candidate(
        id=str(payload.get("id", f"recovered-question:legacy-provider:{number}")),
        type="QUESTION_HEADER",
        score=max(score, default_score),
        evidence=evidence,
        metadata=metadata,
        source_element_ids=source_ids,
        page_index=payload.get("page_index"),
        bbox=BBox.from_dict(payload["bbox"]) if payload.get("bbox") else None,
        score_breakdown={"legacy_recovery": max(score, default_score)},
    )
