"""Opt-in structural candidate and alternative detection."""

from .config import CandidateDetectorConfig, CandidateScoreWeights
from .detector import CandidateDetector
from .features import FEATURE_SCHEMA, FEATURE_SCHEMA_VERSION, FeatureSchemaV1, FeatureVector
from .legacy import LegacyEvidenceProvider
from .models import Candidate, CandidateDetection

__all__ = [
    "CandidateDetector", "CandidateDetectorConfig", "CandidateScoreWeights",
    "LegacyEvidenceProvider", "FEATURE_SCHEMA", "FEATURE_SCHEMA_VERSION",
    "FeatureSchemaV1", "FeatureVector", "Candidate", "CandidateDetection",
]
