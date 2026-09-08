"""Feature flags and explicit gradual-rollout configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Optional

from .config import PipelineMode, get_pipeline_mode


STRUCTURAL_ML_ENABLED_ENV = "STRUCTURAL_ML_ENABLED"
STRUCTURAL_ML_MODEL_REGISTRY_ENV = "STRUCTURAL_ML_MODEL_REGISTRY"
STRUCTURAL_ROLLOUT_PERCENT_ENV = "STRUCTURAL_ROLLOUT_PERCENT"


@dataclass(frozen=True)
class MLRuntimeConfig:
    enabled: bool = False
    registry_path: Optional[str] = None
    model_name: str = "candidate_classifier"
    feature_schema_version: int = 1

    @classmethod
    def from_env(cls) -> "MLRuntimeConfig":
        return cls(
            enabled=_env_bool(STRUCTURAL_ML_ENABLED_ENV, False),
            registry_path=os.getenv(STRUCTURAL_ML_MODEL_REGISTRY_ENV) or None,
            model_name=os.getenv("STRUCTURAL_ML_MODEL_NAME", "candidate_classifier"),
            feature_schema_version=int(os.getenv("STRUCTURAL_ML_FEATURE_SCHEMA_VERSION", "1")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "registry_path": self.registry_path,
            "model_name": self.model_name,
            "feature_schema_version": self.feature_schema_version,
        }


@dataclass(frozen=True)
class RolloutConfig:
    mode: PipelineMode = PipelineMode.LEGACY_ONLY
    ml: MLRuntimeConfig = MLRuntimeConfig()
    rollout_percent: float = 0.0
    preserve_legacy_fallback: bool = True

    @classmethod
    def from_env(cls, *, mode: PipelineMode | str | None = None) -> "RolloutConfig":
        resolved_mode = get_pipeline_mode(mode.value if isinstance(mode, PipelineMode) else mode)
        raw_percent = os.getenv(STRUCTURAL_ROLLOUT_PERCENT_ENV, "0")
        try:
            percent = max(0.0, min(100.0, float(raw_percent)))
        except ValueError:
            percent = 0.0
        return cls(
            mode=resolved_mode,
            ml=MLRuntimeConfig.from_env(),
            rollout_percent=percent,
            preserve_legacy_fallback=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "ml": self.ml.to_dict(),
            "rollout_percent": self.rollout_percent,
            "preserve_legacy_fallback": self.preserve_legacy_fallback,
        }

    @property
    def structural_preferred(self) -> bool:
        return self.mode in {PipelineMode.STRUCTURAL_PREFERRED, PipelineMode.STRUCTURAL_ONLY}


def structural_ml_enabled(value: Optional[bool] = None) -> bool:
    if value is not None:
        return bool(value)
    return MLRuntimeConfig.from_env().enabled


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "sim"}

