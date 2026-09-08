"""Optional Phase-5 dataset, classifier and registry seams."""

from .classifier import (
    MODEL_VERSION,
    CandidateClassifierTrainer,
    FeatureSchemaMismatchError,
    ModelMetadata,
    ModelTrainingError,
    TrainedCandidateClassifier,
    train_candidate_classifier,
)
from .dataset import (
    DATASET_VERSION,
    ConsistencyReport,
    DatasetSplits,
    ExamLabelInput,
    GroupFold,
    GroupKFoldSplitter,
    ReliableDatasetBuilder,
    WeakLabelDataset,
    WeakLabelRecord,
    build_weak_label_dataset,
)
from .registry import ModelRegistry, ModelRegistryEntry, RegistryEntry, REGISTRY_VERSION

__all__ = [
    "DATASET_VERSION",
    "MODEL_VERSION",
    "REGISTRY_VERSION",
    "ConsistencyReport",
    "DatasetSplits",
    "ExamLabelInput",
    "GroupFold",
    "GroupKFoldSplitter",
    "ReliableDatasetBuilder",
    "WeakLabelDataset",
    "WeakLabelRecord",
    "build_weak_label_dataset",
    "CandidateClassifierTrainer",
    "FeatureSchemaMismatchError",
    "ModelMetadata",
    "ModelTrainingError",
    "TrainedCandidateClassifier",
    "train_candidate_classifier",
    "ModelRegistry",
    "ModelRegistryEntry",
    "RegistryEntry",
]

