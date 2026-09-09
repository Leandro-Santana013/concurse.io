"""Minimal opt-in flags for structural components.

The structural pipeline is diagnostic-only until the explicit rollout phase.
This module deliberately defaults every optional capability to disabled.
"""

import os


STRUCTURAL_ML_ENABLED_ENV = "STRUCTURAL_ML_ENABLED"


def structural_ml_enabled() -> bool:
    return os.getenv(STRUCTURAL_ML_ENABLED_ENV, "0").strip().lower() in {
        "1", "true", "yes", "on"
    }


__all__ = ["STRUCTURAL_ML_ENABLED_ENV", "structural_ml_enabled"]
