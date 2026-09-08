"""Reliable weak-label datasets for the optional structural ML layer.

The dataset seam is deliberately independent from the legacy parser.  A
legacy result becomes a training label only after a complete, internally
consistent answer key (or an explicit curated validation) has been supplied.
This keeps a convenient parser output from silently becoming ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import re
from typing import Any, Iterable, Mapping, Optional, Sequence

from ..candidates.features import FeatureVector, QUESTION_HEADER_FEATURES
from ..candidates.models import Candidate
from ..solver import AnswerKeyEvidence


DATASET_VERSION = "weak-label-v1"


@dataclass(frozen=True)
class ConsistencyReport:
    """Audit result for one legacy exam output."""

    reliable: bool
    reasons: tuple[str, ...] = ()
    question_numbers: tuple[int, ...] = ()
    answer_key_numbers: tuple[int, ...] = ()
    answer_key_coverage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "reliable": self.reliable,
            "reasons": list(self.reasons),
            "question_numbers": list(self.question_numbers),
            "answer_key_numbers": list(self.answer_key_numbers),
            "answer_key_coverage": self.answer_key_coverage,
        }


@dataclass(frozen=True)
class WeakLabelRecord:
    """One candidate label tied to an exam group.

    ``exam_id`` is the mandatory grouping key.  Layout family is descriptive
    metadata and is never used as a substitute for the group identity.
    """

    exam_id: str
    candidate_id: str
    label: int
    features: Mapping[str, float]
    layout_family: Optional[str] = None
    source: str = "legacy+complete_gabarito"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "exam_id", str(self.exam_id))
        object.__setattr__(self, "candidate_id", str(self.candidate_id))
        object.__setattr__(self, "label", int(bool(self.label)))
        object.__setattr__(
            self,
            "features",
            {str(name): _finite_float(value) for name, value in self.features.items()},
        )

    def vector(self, feature_names: Sequence[str] = QUESTION_HEADER_FEATURES) -> list[float]:
        return [float(self.features.get(name, 0.0)) for name in feature_names]

    def to_dict(self) -> dict[str, Any]:
        return {
            "exam_id": self.exam_id,
            "candidate_id": self.candidate_id,
            "label": self.label,
            "features": dict(sorted(self.features.items())),
            "layout_family": self.layout_family,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass
class WeakLabelDataset:
    """Serializable records accepted by the model trainer."""

    records: list[WeakLabelRecord] = field(default_factory=list)
    version: str = DATASET_VERSION
    rejected_exams: dict[str, ConsistencyReport] = field(default_factory=dict)

    @property
    def exam_ids(self) -> tuple[str, ...]:
        return tuple(sorted({record.exam_id for record in self.records}))

    @property
    def groups(self) -> list[str]:
        return [record.exam_id for record in self.records]

    @property
    def labels(self) -> list[int]:
        return [record.label for record in self.records]

    def matrix(self, feature_names: Sequence[str] = QUESTION_HEADER_FEATURES) -> list[list[float]]:
        return [record.vector(feature_names) for record in self.records]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.version,
            "records": [record.to_dict() for record in self.records],
            "rejected_exams": {
                key: value.to_dict() for key, value in sorted(self.rejected_exams.items())
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "WeakLabelDataset":
        rejected = {
            str(key): ConsistencyReport(
                reliable=bool(item.get("reliable", False)),
                reasons=tuple(str(reason) for reason in item.get("reasons", [])),
                question_numbers=tuple(int(number) for number in item.get("question_numbers", [])),
                answer_key_numbers=tuple(int(number) for number in item.get("answer_key_numbers", [])),
                answer_key_coverage=float(item.get("answer_key_coverage", 0.0)),
            )
            for key, item in (value.get("rejected_exams") or {}).items()
        }
        return cls(
            records=[
                WeakLabelRecord(
                    exam_id=item["exam_id"],
                    candidate_id=item["candidate_id"],
                    label=int(item.get("label", 0)),
                    features=dict(item.get("features") or {}),
                    layout_family=item.get("layout_family"),
                    source=str(item.get("source", "legacy+complete_gabarito")),
                    metadata=dict(item.get("metadata") or {}),
                )
                for item in value.get("records", [])
            ],
            version=str(value.get("dataset_version", DATASET_VERSION)),
            rejected_exams=rejected,
        )


@dataclass(frozen=True)
class ExamLabelInput:
    """Input required to derive weak labels for one exam."""

    exam_id: str
    legacy_questions: Sequence[Mapping[str, Any]]
    candidates: Sequence[Candidate]
    answer_key: Any
    layout_family: Optional[str] = None
    source: Optional[str] = None
    expected_count: Optional[int] = None
    curated: bool = False


class ReliableDatasetBuilder:
    """Build weak labels while rejecting unverified legacy outputs."""

    def __init__(
        self,
        *,
        min_answer_key_coverage: float = 1.0,
        allow_curated_without_answer_key: bool = False,
        dataset_version: str = DATASET_VERSION,
    ) -> None:
        self.min_answer_key_coverage = float(min_answer_key_coverage)
        self.allow_curated_without_answer_key = bool(allow_curated_without_answer_key)
        self.dataset_version = str(dataset_version)

    def validate_exam(
        self,
        legacy_questions: Sequence[Mapping[str, Any]],
        answer_key: Any,
        *,
        expected_count: Optional[int] = None,
        curated: bool = False,
    ) -> ConsistencyReport:
        questions = list(legacy_questions or [])
        answer = AnswerKeyEvidence.from_value(answer_key, expected_count=expected_count)
        numbers = [_question_number(item) for item in questions]
        valid_numbers = [number for number in numbers if number is not None]
        reasons: list[str] = []
        if not questions:
            reasons.append("legacy_result_empty")
        if len(valid_numbers) != len(set(valid_numbers)):
            reasons.append("legacy_duplicate_question_number")
        if any(number is None for number in numbers):
            reasons.append("legacy_question_number_missing")

        if not answer.available:
            if not (curated and self.allow_curated_without_answer_key):
                reasons.append("complete_answer_key_required")
        elif answer.coverage < self.min_answer_key_coverage:
            reasons.append("answer_key_incomplete")

        answer_numbers = sorted(int(number) for number in answer.answers)
        question_numbers = sorted(set(valid_numbers))
        if answer.available and question_numbers != answer_numbers:
            reasons.append("legacy_answer_key_number_mismatch")
        if expected_count is not None and len(question_numbers) != int(expected_count):
            reasons.append("legacy_expected_count_mismatch")

        if answer.available:
            for question in questions:
                number = _question_number(question)
                legacy_answer = _question_answer(question)
                if number is None or not legacy_answer:
                    continue
                expected_answer = str(answer.answers.get(number, "")).strip().upper()
                if expected_answer and legacy_answer.strip().upper() != expected_answer:
                    reasons.append(f"legacy_answer_mismatch:{number}")

        return ConsistencyReport(
            reliable=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            question_numbers=tuple(question_numbers),
            answer_key_numbers=tuple(answer_numbers),
            answer_key_coverage=answer.coverage,
        )

    def build(self, exams: Iterable[ExamLabelInput | Mapping[str, Any]]) -> WeakLabelDataset:
        dataset = WeakLabelDataset(version=self.dataset_version)
        for raw_exam in exams:
            exam = _coerce_exam_input(raw_exam)
            report = self.validate_exam(
                exam.legacy_questions,
                exam.answer_key,
                expected_count=exam.expected_count,
                curated=exam.curated,
            )
            if not report.reliable:
                dataset.rejected_exams[str(exam.exam_id)] = report
                continue
            positive_numbers = set(report.question_numbers)
            question_candidates = [
                candidate
                for candidate in exam.candidates
                if candidate.type == "QUESTION_HEADER"
            ]
            candidate_numbers = {
                number
                for candidate in question_candidates
                if (number := _candidate_number(candidate)) is not None
            }
            missing_candidate_numbers = sorted(positive_numbers - candidate_numbers)
            if missing_candidate_numbers:
                dataset.rejected_exams[str(exam.exam_id)] = replace(
                    report,
                    reliable=False,
                    reasons=tuple(
                        [
                            *report.reasons,
                            "candidate_question_number_missing:"
                            + ",".join(str(number) for number in missing_candidate_numbers),
                        ]
                    ),
                )
                continue

            canonical_ids = _canonical_question_candidate_ids(
                question_candidates,
                positive_numbers,
            )
            for candidate in question_candidates:
                number = _candidate_number(candidate)
                features = _candidate_features(candidate)
                dataset.records.append(
                    WeakLabelRecord(
                        exam_id=str(exam.exam_id),
                        candidate_id=candidate.id,
                        label=int(candidate.id in canonical_ids),
                        features=features,
                        layout_family=exam.layout_family,
                        source=exam.source or "legacy+complete_gabarito",
                        metadata={
                            "question_number": number,
                            "label_validation": "complete_answer_key+canonical_candidate",
                        },
                    )
                )
        return dataset

    def add_exam(self, dataset: WeakLabelDataset, exam: ExamLabelInput | Mapping[str, Any]) -> WeakLabelDataset:
        """Convenience method that preserves the same reject-on-inconsistency policy."""

        result = self.build([exam])
        dataset.records.extend(result.records)
        dataset.rejected_exams.update(result.rejected_exams)
        dataset.version = self.dataset_version
        return dataset


@dataclass(frozen=True)
class GroupFold:
    """One leakage-safe GroupKFold partition."""

    train: tuple[WeakLabelRecord, ...]
    test: tuple[WeakLabelRecord, ...]
    train_groups: tuple[str, ...]
    test_groups: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_groups": list(self.train_groups),
            "test_groups": list(self.test_groups),
            "train_size": len(self.train),
            "test_size": len(self.test),
        }


@dataclass(frozen=True)
class DatasetSplits:
    train: tuple[WeakLabelRecord, ...]
    validation: tuple[WeakLabelRecord, ...]
    holdout: tuple[WeakLabelRecord, ...]
    train_groups: tuple[str, ...]
    validation_groups: tuple[str, ...]
    holdout_groups: tuple[str, ...]

    def assert_no_leakage(self) -> None:
        groups = [set(self.train_groups), set(self.validation_groups), set(self.holdout_groups)]
        if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
            raise AssertionError("exam groups leaked across train/validation/holdout")

    def to_dict(self) -> dict[str, Any]:
        return {
            "train_groups": list(self.train_groups),
            "validation_groups": list(self.validation_groups),
            "holdout_groups": list(self.holdout_groups),
            "train_size": len(self.train),
            "validation_size": len(self.validation),
            "holdout_size": len(self.holdout),
        }


class GroupKFoldSplitter:
    """Deterministic GroupKFold wrapper with explicit exam holdout support."""

    def __init__(self, *, n_splits: int = 3, validation_fold: int = 0) -> None:
        self.n_splits = int(n_splits)
        self.validation_fold = int(validation_fold)

    def kfold(
        self,
        dataset: WeakLabelDataset,
        *,
        group_by: str = "exam_id",
    ) -> list[GroupFold]:
        if not dataset.records:
            return []
        from sklearn.model_selection import GroupKFold

        grouping = [
            record.exam_id
            if group_by == "exam_id"
            else (record.layout_family or record.exam_id)
            for record in dataset.records
        ]
        if group_by not in {"exam_id", "layout_family"}:
            raise ValueError("group_by must be 'exam_id' or 'layout_family'")
        unique_groups = sorted(set(grouping))
        n_splits = min(self.n_splits, len(unique_groups))
        if n_splits < 2:
            raise ValueError("GroupKFold requires at least two distinct exam_id groups")
        if not 0 <= self.validation_fold < n_splits:
            raise ValueError("validation_fold must be within the GroupKFold range")
        rows = list(range(len(dataset.records)))
        groups = grouping
        result: list[GroupFold] = []
        for train_indices, test_indices in GroupKFold(n_splits=n_splits).split(rows, dataset.labels, groups):
            train = tuple(dataset.records[index] for index in train_indices)
            test = tuple(dataset.records[index] for index in test_indices)
            result.append(
                GroupFold(
                    train=train,
                    test=test,
                    train_groups=tuple(sorted({grouping[index] for index in train_indices})),
                    test_groups=tuple(sorted({grouping[index] for index in test_indices})),
                )
            )
        return result

    def kfold_by_layout_family(self, dataset: WeakLabelDataset) -> list[GroupFold]:
        """Stricter evaluation where a complete visual family is held out."""

        return self.kfold(dataset, group_by="layout_family")

    def split(
        self,
        dataset: WeakLabelDataset,
        *,
        holdout_groups: Optional[Iterable[str]] = None,
        validation_groups: Optional[Iterable[str]] = None,
    ) -> DatasetSplits:
        all_groups = sorted(set(dataset.groups))
        if holdout_groups is None and len(all_groups) >= 3:
            # A deterministic default keeps TRAIN/VALIDATION/HOLDOUT separate
            # even when a caller does not provide a manifest split.
            holdout = {all_groups[-1]}
        else:
            holdout = {str(group) for group in (holdout_groups or ())}
        remaining = [record for record in dataset.records if record.exam_id not in holdout]
        if not remaining:
            raise ValueError("holdout removed every record from the dataset")
        remaining_dataset = WeakLabelDataset(records=remaining, version=dataset.version)
        if validation_groups is not None:
            validation = {str(group) for group in validation_groups}
            train = [record for record in remaining if record.exam_id not in validation]
            valid = [record for record in remaining if record.exam_id in validation]
        else:
            folds = self.kfold(remaining_dataset)
            fold = folds[self.validation_fold]
            train = list(fold.train)
            valid = list(fold.test)
        if not train or not valid:
            raise ValueError("train and validation must both contain at least one exam group")
        result = DatasetSplits(
            train=tuple(train),
            validation=tuple(valid),
            holdout=tuple(record for record in dataset.records if record.exam_id in holdout),
            train_groups=tuple(sorted({record.exam_id for record in train})),
            validation_groups=tuple(sorted({record.exam_id for record in valid})),
            holdout_groups=tuple(sorted({record.exam_id for record in dataset.records if record.exam_id in holdout})),
        )
        result.assert_no_leakage()
        return result


def build_weak_label_dataset(
    exams: Iterable[ExamLabelInput | Mapping[str, Any]],
    *,
    min_answer_key_coverage: float = 1.0,
) -> WeakLabelDataset:
    return ReliableDatasetBuilder(
        min_answer_key_coverage=min_answer_key_coverage,
    ).build(exams)


def _coerce_exam_input(value: ExamLabelInput | Mapping[str, Any]) -> ExamLabelInput:
    if isinstance(value, ExamLabelInput):
        return value
    return ExamLabelInput(
        exam_id=str(value["exam_id"]),
        legacy_questions=list(value.get("legacy_questions") or value.get("questions") or []),
        candidates=list(value.get("candidates") or []),
        answer_key=value.get("answer_key"),
        layout_family=value.get("layout_family"),
        source=value.get("source"),
        expected_count=value.get("expected_count"),
        curated=bool(value.get("curated", False)),
    )


def _candidate_features(candidate: Candidate) -> dict[str, float]:
    if candidate.features is not None:
        return {
            name: float(candidate.features.get(name, 0.0))
            for name in QUESTION_HEADER_FEATURES
        }
    return {
        name: float(candidate.evidence.get(name, 0.0))
        for name in QUESTION_HEADER_FEATURES
    }


def _candidate_number(candidate: Candidate) -> Optional[int]:
    raw = candidate.metadata.get("question_number")
    try:
        number = int(raw)
        return number if number > 0 else None
    except (TypeError, ValueError):
        match = re.search(r"\b(\d{1,3})\b", str(candidate.metadata.get("line_text", "")))
        return int(match.group(1)) if match else None


def _canonical_question_candidate_ids(
    candidates: Sequence[Candidate],
    positive_numbers: set[int],
) -> set[str]:
    """Select one physical header per validated number.

    Two-column PDFs often expose the same printed number once as a real header
    and again as an isolated numeric line in the body.  Treating every
    occurrence as positive removes the negative class from real corpora.  The
    detector's explicit question-token evidence wins, followed by its score.
    """

    grouped: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        number = _candidate_number(candidate)
        if number in positive_numbers:
            grouped.setdefault(number, []).append(candidate)

    selected: set[str] = set()
    for values in grouped.values():
        winner = max(values, key=_candidate_rank)
        selected.add(winner.id)
    return selected


def _candidate_rank(candidate: Candidate) -> tuple[float, float, float]:
    evidence = candidate.features.values if candidate.features is not None else candidate.evidence
    line_text = str(candidate.metadata.get("line_text", "")).strip().lower()
    has_question_token = float(evidence.get("content.has_question_token", 0.0))
    explicit_token = float("quest" in line_text or "item" in line_text)
    return (max(has_question_token, explicit_token), float(candidate.score), float(evidence.get("content.regex_score", 0.0)))


def _question_number(question: Mapping[str, Any]) -> Optional[int]:
    raw = question.get("numero_questao", question.get("printed_number"))
    try:
        number = int(str(raw).strip())
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None


def _question_answer(question: Mapping[str, Any]) -> str:
    return str(question.get("resposta", question.get("correct_answer", "")) or "").strip()


def _finite_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if result == result and abs(result) != float("inf") else 0.0
