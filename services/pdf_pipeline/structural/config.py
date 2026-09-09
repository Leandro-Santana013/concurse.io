"""Configuration shared by the staged PDF pipeline migration."""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional


PIPELINE_MODE_ENV = "PDF_PIPELINE_MODE"
LEGACY_PIPELINE_MODE_ENV = "STRUCTURAL_PIPELINE_MODE"


class PipelineMode(str, Enum):
    """Available rollout modes.

    ``LEGACY_ONLY`` remains the application default. Phase 5 wires
    ``STRUCTURAL_SHADOW`` and confidence-gated ``STRUCTURAL_PREFERRED``
    through the explicit rollout runner; legacy fallback remains available.
    """

    LEGACY_ONLY = "LEGACY_ONLY"
    STRUCTURAL_SHADOW = "STRUCTURAL_SHADOW"
    STRUCTURAL_PREFERRED = "STRUCTURAL_PREFERRED"
    STRUCTURAL_ONLY = "STRUCTURAL_ONLY"

    @classmethod
    def from_value(cls, value: "PipelineMode | str") -> "PipelineMode":
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().upper()
        try:
            return cls(normalized)
        except ValueError as exc:
            choices = ", ".join(mode.value for mode in cls)
            raise ValueError(
                f"Invalid PDF pipeline mode {value!r}; expected one of: {choices}"
            ) from exc


def get_pipeline_mode(value: Optional[str] = None) -> PipelineMode:
    """Read the configured mode, defaulting safely to legacy-only."""

    raw_value = value
    if raw_value is None:
        raw_value = os.getenv(PIPELINE_MODE_ENV)
    if raw_value is None:
        raw_value = os.getenv(LEGACY_PIPELINE_MODE_ENV)
    if raw_value is None or not str(raw_value).strip():
        return PipelineMode.LEGACY_ONLY
    return PipelineMode.from_value(raw_value)
