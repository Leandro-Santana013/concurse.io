"""Metrics and split-aware benchmark reporting for the structural rollout."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence


BENCHMARK_VERSION = "phase5-benchmark-v1"


@dataclass(frozen=True)
class BenchmarkCase:
    exam_id: str
    expected_numbers: Sequence[int]
    structural_result: Sequence[Mapping[str, Any]]
    legacy_result: Optional[Sequence[Mapping[str, Any]]] = None
    expected_options: Optional[Mapping[int | str, Sequence[str] | Mapping[str, Any]]] = None
    expected_image_ownership: Optional[Mapping[str, str | int]] = None
    predicted_image_ownership: Optional[Mapping[str, str | int]] = None
    banca: Optional[str] = None
    layout_family: Optional[str] = None
    split: str = "holdout"
    development_modified: bool = False


@dataclass
class ExamBenchmarkMetrics:
    exam_id: str
    question_detection_precision: float
    question_detection_recall: float
    option_extraction_accuracy: Optional[float]
    image_ownership_accuracy: Optional[float]
    question_ordering_accuracy: float
    full_exam_success: bool
    zero_modification_success: bool
    predicted_count: int
    expected_count: int
    changed_fields_vs_legacy: list[str] = field(default_factory=list)
    banca: Optional[str] = None
    layout_family: Optional[str] = None
    split: str = "holdout"

    def to_dict(self) -> dict[str, Any]:
        return {
            "exam_id": self.exam_id,
            "question_detection_precision": self.question_detection_precision,
            "question_detection_recall": self.question_detection_recall,
            "option_extraction_accuracy": self.option_extraction_accuracy,
            "image_ownership_accuracy": self.image_ownership_accuracy,
            "question_ordering_accuracy": self.question_ordering_accuracy,
            "full_exam_success": self.full_exam_success,
            "zero_modification_success": self.zero_modification_success,
            "predicted_count": self.predicted_count,
            "expected_count": self.expected_count,
            "changed_fields_vs_legacy": list(self.changed_fields_vs_legacy),
            "banca": self.banca,
            "layout_family": self.layout_family,
            "split": self.split,
        }


@dataclass
class BenchmarkReport:
    cases: list[ExamBenchmarkMetrics] = field(default_factory=list)
    version: str = BENCHMARK_VERSION

    @property
    def question_detection_precision(self) -> float:
        return _average(item.question_detection_precision for item in self.cases)

    @property
    def question_detection_recall(self) -> float:
        return _average(item.question_detection_recall for item in self.cases)

    @property
    def option_extraction_accuracy(self) -> float:
        return _average(item.option_extraction_accuracy for item in self.cases if item.option_extraction_accuracy is not None)

    @property
    def image_ownership_accuracy(self) -> float:
        return _average(item.image_ownership_accuracy for item in self.cases if item.image_ownership_accuracy is not None)

    @property
    def question_ordering_accuracy(self) -> float:
        return _average(item.question_ordering_accuracy for item in self.cases)

    @property
    def full_exam_success_rate(self) -> float:
        return _average(item.full_exam_success for item in self.cases)

    @property
    def zero_modification_success_rate(self) -> float:
        return _average(item.zero_modification_success for item in self.cases)

    @property
    def generalization_rate(self) -> float:
        holdout = [item for item in self.cases if item.split.upper() == "HOLDOUT"]
        return _average(item.zero_modification_success for item in holdout)

    @property
    def full_exam_success(self) -> float:
        return self.full_exam_success_rate

    def by_banca(self) -> dict[str, dict[str, float]]:
        return self._grouped(lambda item: item.banca or "UNKNOWN")

    def by_layout_family(self) -> dict[str, dict[str, float]]:
        return self._grouped(lambda item: item.layout_family or "noise/unknown")

    def holdout_metrics(self) -> dict[str, float]:
        holdout = [item for item in self.cases if item.split.upper() == "HOLDOUT"]
        return _summary(holdout)

    def legacy_vs_structural(self) -> dict[str, Any]:
        return {
            "cases": len(self.cases),
            "cases_with_changes": sum(bool(item.changed_fields_vs_legacy) for item in self.cases),
            "changed_fields": sorted({field for item in self.cases for field in item.changed_fields_vs_legacy}),
            "structural_full_exam_success_rate": self.full_exam_success_rate,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "benchmark_version": self.version,
            "metrics": {
                "question_detection_precision": self.question_detection_precision,
                "question_detection_recall": self.question_detection_recall,
                "option_extraction_accuracy": self.option_extraction_accuracy,
                "image_ownership_accuracy": self.image_ownership_accuracy,
                "question_ordering_accuracy": self.question_ordering_accuracy,
                "full_exam_success_rate": self.full_exam_success_rate,
                "zero_modification_success_rate": self.zero_modification_success_rate,
                "generalization_rate": self.generalization_rate,
            },
            "by_banca": self.by_banca(),
            "by_layout_family": self.by_layout_family(),
            "holdout": self.holdout_metrics(),
            "legacy_vs_structural": self.legacy_vs_structural(),
            "cases": [item.to_dict() for item in self.cases],
        }

    def _grouped(self, key_fn: Any) -> dict[str, dict[str, float]]:
        groups: dict[str, list[ExamBenchmarkMetrics]] = {}
        for item in self.cases:
            groups.setdefault(str(key_fn(item)), []).append(item)
        return {key: _summary(value) for key, value in sorted(groups.items())}


def evaluate_exam(case: BenchmarkCase) -> ExamBenchmarkMetrics:
    expected = [int(number) for number in case.expected_numbers]
    predicted = [_number(item) for item in case.structural_result]
    predicted = [number for number in predicted if number is not None]
    expected_set = set(expected)
    predicted_set = set(predicted)
    true_positive = len(expected_set & predicted_set)
    precision = true_positive / max(len(predicted_set), 1)
    recall = true_positive / max(len(expected_set), 1)
    ordering = _ordering_accuracy(expected, predicted)
    options = _option_accuracy(case.expected_options, case.structural_result)
    image_accuracy = _image_accuracy(case.expected_image_ownership, case.predicted_image_ownership)
    full_success = (
        precision == 1.0
        and recall == 1.0
        and ordering == 1.0
        and (options is None or options == 1.0)
        and (image_accuracy is None or image_accuracy == 1.0)
    )
    changed_fields = _changed_fields(case.legacy_result, case.structural_result)
    return ExamBenchmarkMetrics(
        exam_id=str(case.exam_id),
        question_detection_precision=precision,
        question_detection_recall=recall,
        option_extraction_accuracy=options,
        image_ownership_accuracy=image_accuracy,
        question_ordering_accuracy=ordering,
        full_exam_success=full_success,
        zero_modification_success=bool(full_success and not case.development_modified),
        predicted_count=len(predicted),
        expected_count=len(expected),
        changed_fields_vs_legacy=changed_fields,
        banca=case.banca,
        layout_family=case.layout_family,
        split=case.split,
    )


def run_benchmark(cases: Iterable[BenchmarkCase]) -> BenchmarkReport:
    return BenchmarkReport(cases=[evaluate_exam(case) for case in cases])


def compare_legacy_structural_metrics(
    legacy_result: Sequence[Mapping[str, Any]],
    structural_result: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    changed = _changed_fields(legacy_result, structural_result)
    return {
        "changed_fields": changed,
        "legacy_count": len(legacy_result or []),
        "structural_count": len(structural_result or []),
        "question_order_equal": _numbers(legacy_result) == _numbers(structural_result),
    }


def _option_accuracy(
    expected: Optional[Mapping[int | str, Sequence[str] | Mapping[str, Any]]],
    actual: Sequence[Mapping[str, Any]],
) -> Optional[float]:
    if expected is None:
        return None
    actual_by_number = {_number(item): item for item in actual}
    matches = 0
    total = 0
    for raw_number, expected_options in expected.items():
        number = int(raw_number)
        total += 1
        item = actual_by_number.get(number)
        if item is None:
            continue
        options = item.get("opcoes", item.get("options", {})) or {}
        expected_keys = set(str(key).upper() for key in (expected_options.keys() if isinstance(expected_options, Mapping) else expected_options))
        actual_keys = set(str(key).upper() for key in options)
        matches += int(expected_keys == actual_keys)
    return matches / max(total, 1)


def _image_accuracy(
    expected: Optional[Mapping[str, str | int]],
    actual: Optional[Mapping[str, str | int]],
) -> Optional[float]:
    if expected is None:
        return None
    if actual is None:
        return 0.0
    return sum(str(actual.get(key)) == str(value) for key, value in expected.items()) / max(len(expected), 1)


def _ordering_accuracy(expected: Sequence[int], actual: Sequence[int]) -> float:
    if not expected:
        return 1.0 if not actual else 0.0
    return sum(left == right for left, right in zip(expected, actual)) / max(len(expected), len(actual), 1)


def _changed_fields(
    legacy: Optional[Sequence[Mapping[str, Any]]],
    structural: Sequence[Mapping[str, Any]],
) -> list[str]:
    if legacy is None:
        return []
    changed: list[str] = []
    if len(legacy) != len(structural):
        changed.append("question_count")
    if _numbers(legacy) != _numbers(structural):
        changed.append("question_order")
    if _option_keys(legacy) != _option_keys(structural):
        changed.append("option_keys")
    if _image_counts(legacy) != _image_counts(structural):
        changed.append("image_count")
    return changed


def _summary(items: Sequence[ExamBenchmarkMetrics]) -> dict[str, float]:
    return {
        "question_detection_precision": _average(item.question_detection_precision for item in items),
        "question_detection_recall": _average(item.question_detection_recall for item in items),
        "option_extraction_accuracy": _average(item.option_extraction_accuracy for item in items if item.option_extraction_accuracy is not None),
        "image_ownership_accuracy": _average(item.image_ownership_accuracy for item in items if item.image_ownership_accuracy is not None),
        "question_ordering_accuracy": _average(item.question_ordering_accuracy for item in items),
        "full_exam_success_rate": _average(item.full_exam_success for item in items),
        "zero_modification_success_rate": _average(item.zero_modification_success for item in items),
    }


def _average(values: Iterable[Any]) -> float:
    values = [float(value) for value in values]
    return sum(values) / len(values) if values else 0.0


def _number(item: Mapping[str, Any]) -> Optional[int]:
    raw = item.get("numero_questao", item.get("printed_number"))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _numbers(items: Sequence[Mapping[str, Any]]) -> list[int]:
    return [number for item in items if (number := _number(item)) is not None]


def _option_keys(items: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    return [sorted(str(key).upper() for key in (item.get("opcoes", item.get("options", {})) or {})) for item in items]


def _image_counts(items: Sequence[Mapping[str, Any]]) -> list[int]:
    return [len(item.get("images") or []) for item in items]

