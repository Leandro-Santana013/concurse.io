"""Optional, CPU-friendly candidate classifiers.

The first model is intentionally binary and explainable.  Importing this
module does not import scikit-learn; the dependency is loaded only when a
caller explicitly trains or loads a model.  This is what keeps the geometric
structural pipeline usable with ``STRUCTURAL_ML_ENABLED=false``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from ..candidates.features import FEATURE_SCHEMA_VERSION, QUESTION_HEADER_FEATURES
from ..candidates.models import Candidate
from .dataset import DatasetSplits, WeakLabelDataset, WeakLabelRecord


MODEL_VERSION = "candidate-classifier-v1"


class FeatureSchemaMismatchError(ValueError):
    """Raised when a serialized model cannot consume current features."""


class ModelTrainingError(ValueError):
    """Raised for an unusable or non-reproducible training corpus."""


@dataclass(frozen=True)
class ModelMetadata:
    model_version: str = MODEL_VERSION
    feature_schema_version: int = FEATURE_SCHEMA_VERSION
    training_dataset_version: str = "weak-label-v1"
    metrics: Mapping[str, float] = field(default_factory=dict)
    created_at: str = ""
    estimator_name: str = "LogisticRegression"
    target: str = "QUESTION_HEADER"
    feature_names: tuple[str, ...] = QUESTION_HEADER_FEATURES

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(
                self,
                "created_at",
                datetime.now(timezone.utc).isoformat(),
            )
        object.__setattr__(self, "feature_names", tuple(self.feature_names))

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "feature_schema_version": self.feature_schema_version,
            "training_dataset_version": self.training_dataset_version,
            "metrics": dict(self.metrics),
            "created_at": self.created_at,
            "estimator_name": self.estimator_name,
            "target": self.target,
            "feature_names": list(self.feature_names),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ModelMetadata":
        return cls(
            model_version=str(value.get("model_version", MODEL_VERSION)),
            feature_schema_version=int(value.get("feature_schema_version", 0)),
            training_dataset_version=str(value.get("training_dataset_version", "")),
            metrics={str(key): float(item) for key, item in (value.get("metrics") or {}).items()},
            created_at=str(value.get("created_at", "")),
            estimator_name=str(value.get("estimator_name", "LogisticRegression")),
            target=str(value.get("target", "QUESTION_HEADER")),
            feature_names=tuple(value.get("feature_names") or QUESTION_HEADER_FEATURES),
        )


@dataclass
class TrainedCandidateClassifier:
    """A fitted estimator plus the metadata required to use it safely."""

    estimator: Any
    metadata: ModelMetadata

    def __post_init__(self) -> None:
        _assert_schema(self.metadata.feature_schema_version, FEATURE_SCHEMA_VERSION)
        if tuple(self.metadata.feature_names) != tuple(QUESTION_HEADER_FEATURES):
            raise FeatureSchemaMismatchError(
                "candidate classifier feature names do not match the current schema"
            )

    @property
    def model_version(self) -> str:
        return self.metadata.model_version

    @property
    def feature_schema_version(self) -> int:
        return self.metadata.feature_schema_version

    def predict_proba(
        self,
        values: Candidate | WeakLabelRecord | Mapping[str, float] | Sequence[float],
    ) -> float:
        vector = _vector(values, self.metadata.feature_names)
        probabilities = self.estimator.predict_proba([vector])
        classes = list(getattr(self.estimator, "classes_", (0, 1)))
        if 1 not in classes:
            return 0.0
        return _clamp(float(probabilities[0][classes.index(1)]))

    def score_candidate(self, candidate: Candidate) -> float:
        return self.predict_proba(candidate)

    def predict(self, values: Candidate | WeakLabelRecord | Mapping[str, float] | Sequence[float]) -> int:
        return int(self.predict_proba(values) >= 0.5)

    def save(self, path: str | Path) -> Path:
        _require_ml_dependencies()
        import joblib

        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"metadata": self.metadata.to_dict(), "estimator": self.estimator},
            output,
        )
        return output

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        expected_feature_schema_version: int = FEATURE_SCHEMA_VERSION,
    ) -> "TrainedCandidateClassifier":
        _require_ml_dependencies()
        import joblib

        payload = joblib.load(Path(path))
        metadata = ModelMetadata.from_dict(payload.get("metadata") or {})
        _assert_schema(metadata.feature_schema_version, expected_feature_schema_version)
        return cls(estimator=payload["estimator"], metadata=metadata)


class CandidateClassifierTrainer:
    """Train and evaluate the baseline with exam-group isolation."""

    def __init__(
        self,
        *,
        random_state: int = 0,
        model_version: str = MODEL_VERSION,
        feature_schema_version: int = FEATURE_SCHEMA_VERSION,
    ) -> None:
        _assert_schema(feature_schema_version, FEATURE_SCHEMA_VERSION)
        self.random_state = int(random_state)
        self.model_version = str(model_version)
        self.feature_schema_version = int(feature_schema_version)

    def train(
        self,
        dataset: WeakLabelDataset,
        *,
        splits: Optional[DatasetSplits] = None,
        estimator: str = "logistic",
    ) -> TrainedCandidateClassifier:
        _require_ml_dependencies()
        records = list(splits.train if splits is not None else dataset.records)
        if not records:
            raise ModelTrainingError("cannot train candidate classifier with no records")
        labels = {record.label for record in records}
        if labels != {0, 1}:
            raise ModelTrainingError(
                "candidate classifier needs both QUESTION_HEADER and NOT_QUESTION_HEADER labels"
            )
        estimator_name = _estimator_name(estimator)
        metrics = self._evaluate(dataset, splits=splits, estimator=estimator)
        fitted = _make_estimator(estimator, self.random_state)
        fitted.fit(
            [record.vector(QUESTION_HEADER_FEATURES) for record in records],
            [record.label for record in records],
        )
        metadata = ModelMetadata(
            model_version=self.model_version,
            feature_schema_version=self.feature_schema_version,
            training_dataset_version=dataset.version,
            metrics=metrics,
            estimator_name=estimator_name,
        )
        return TrainedCandidateClassifier(estimator=fitted, metadata=metadata)

    def compare(
        self,
        dataset: WeakLabelDataset,
        *,
        splits: Optional[DatasetSplits] = None,
    ) -> dict[str, Any]:
        """Compare optional HistGradientBoosting without making it mandatory."""

        results: dict[str, Any] = {}
        for name in ("logistic", "hist_gradient_boosting"):
            try:
                model = self.train(dataset, splits=splits, estimator=name)
            except (ModelTrainingError, ValueError) as exc:
                results[name] = {"available": False, "reason": str(exc)}
                continue
            results[name] = {
                "available": True,
                "metadata": model.metadata.to_dict(),
            }
        available = {
            name: value
            for name, value in results.items()
            if value.get("available")
        }
        if available:
            recommended = max(
                available,
                key=lambda name: (
                    float(available[name]["metadata"]["metrics"].get("full_exam_success_rate", 0.0)),
                    float(available[name]["metadata"]["metrics"].get("f1", 0.0)),
                    1 if name == "logistic" else 0,
                ),
            )
            results["recommended"] = recommended
        return results

    def _evaluate(
        self,
        dataset: WeakLabelDataset,
        *,
        splits: Optional[DatasetSplits],
        estimator: str,
    ) -> dict[str, float]:
        if splits is not None:
            train = list(splits.train)
            test = list(splits.validation)
            model = _make_estimator(estimator, self.random_state)
            model.fit(
                [record.vector(QUESTION_HEADER_FEATURES) for record in train],
                [record.label for record in train],
            )
            predictions = _predict(model, test)
            return _classification_metrics(test, predictions)

        from .dataset import GroupKFoldSplitter

        folds = GroupKFoldSplitter(n_splits=3).kfold(dataset)
        all_records: list[WeakLabelRecord] = []
        all_predictions: list[int] = []
        for fold in folds:
            if {record.label for record in fold.train} != {0, 1}:
                continue
            model = _make_estimator(estimator, self.random_state)
            model.fit(
                [record.vector(QUESTION_HEADER_FEATURES) for record in fold.train],
                [record.label for record in fold.train],
            )
            all_records.extend(fold.test)
            all_predictions.extend(_predict(model, fold.test))
        if not all_records:
            return {
                "accuracy": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
                "full_exam_success_rate": 0.0,
            }
        return _classification_metrics(all_records, all_predictions)


def train_candidate_classifier(
    dataset: WeakLabelDataset,
    *,
    splits: Optional[DatasetSplits] = None,
    estimator: str = "logistic",
    random_state: int = 0,
) -> TrainedCandidateClassifier:
    return CandidateClassifierTrainer(random_state=random_state).train(
        dataset,
        splits=splits,
        estimator=estimator,
    )


def _make_estimator(name: str, random_state: int) -> Any:
    from sklearn.linear_model import LogisticRegression

    normalized = str(name).strip().lower()
    if normalized in {"logistic", "logisticregression", "lr"}:
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        return Pipeline(
            [
                ("scale", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=500,
                        random_state=random_state,
                        class_weight="balanced",
                    ),
                ),
            ]
        )
    if normalized in {"hist_gradient_boosting", "histgradientboosting", "hgb"}:
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(
            max_iter=100,
            learning_rate=0.08,
            max_leaf_nodes=15,
            random_state=random_state,
        )
    raise ValueError(f"unknown candidate classifier {name!r}")


def _estimator_name(name: str) -> str:
    return "HistGradientBoostingClassifier" if str(name).lower().startswith("hist") else "LogisticRegression"


def _predict(model: Any, records: Sequence[WeakLabelRecord]) -> list[int]:
    if not records:
        return []
    return [int(value) for value in model.predict([record.vector(QUESTION_HEADER_FEATURES) for record in records])]


def _classification_metrics(records: Sequence[WeakLabelRecord], predictions: Sequence[int]) -> dict[str, float]:
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    truth = [record.label for record in records]
    groups: dict[str, list[tuple[int, int]]] = {}
    for record, prediction in zip(records, predictions):
        groups.setdefault(record.exam_id, []).append((record.label, int(prediction)))
    full_exam = sum(all(label == prediction for label, prediction in pairs) for pairs in groups.values()) / max(len(groups), 1)
    return {
        "accuracy": float(accuracy_score(truth, predictions)),
        "precision": float(precision_score(truth, predictions, zero_division=0)),
        "recall": float(recall_score(truth, predictions, zero_division=0)),
        "f1": float(f1_score(truth, predictions, zero_division=0)),
        "full_exam_success_rate": float(full_exam),
    }


def _vector(
    value: Candidate | WeakLabelRecord | Mapping[str, float] | Sequence[float],
    feature_names: Sequence[str],
) -> list[float]:
    if isinstance(value, Candidate):
        if value.features is not None:
            mapping: Mapping[str, float] = value.features.values
        else:
            mapping = value.evidence
        return [_finite_float(mapping.get(name, 0.0)) for name in feature_names]
    if isinstance(value, WeakLabelRecord):
        return [_finite_float(value.features.get(name, 0.0)) for name in feature_names]
    if isinstance(value, Mapping):
        return [_finite_float(value.get(name, 0.0)) for name in feature_names]
    values = list(value)
    if len(values) != len(feature_names):
        raise FeatureSchemaMismatchError(
            f"feature vector length {len(values)} != schema length {len(feature_names)}"
        )
    return [_finite_float(item) for item in values]


def _assert_schema(actual: int, expected: int) -> None:
    if int(actual) != int(expected):
        raise FeatureSchemaMismatchError(
            f"feature schema mismatch: model={actual}, runtime={expected}"
        )


def _require_ml_dependencies() -> None:
    try:
        import sklearn  # noqa: F401
        import joblib  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised without extras
        raise RuntimeError(
            "Optional structural ML requires scikit-learn and joblib; "
            "geometry and constraints remain available without them"
        ) from exc


def _clamp(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _finite_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0
