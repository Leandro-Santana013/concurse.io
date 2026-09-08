"""Versioned feature schema used by structural candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping


FEATURE_SCHEMA_VERSION = 1

QUESTION_HEADER_FEATURES = (
    "content.is_integer",
    "content.integer_value_norm",
    "content.has_question_token",
    "content.regex_score",
    "content.text_length",
    "content.uppercase_ratio",
    "content.digit_ratio",
    "geometry.x0",
    "geometry.y0",
    "geometry.width",
    "geometry.height",
    "geometry.column",
    "style.font_size_body_ratio",
    "style.bold",
    "style.italic",
    "style.cluster_frequency",
    "sequence.prev_numeric_delta",
    "sequence.next_numeric_delta",
    "sequence.reading_distance",
    "context.gap_before",
    "context.gap_after",
    "context.option_group_below",
    "context.body_below",
    "context.header_footer_penalty",
    "profile.header_style_similarity",
    "profile.question_x_similarity",
    "legacy.bank_rule_score",
)

FEATURE_SCHEMA = {
    "feature_schema_version": FEATURE_SCHEMA_VERSION,
    "QUESTION_HEADER": list(QUESTION_HEADER_FEATURES),
}


class FeatureSchemaV1:
    """Formal schema metadata kept stable for serialized traces."""

    version = FEATURE_SCHEMA_VERSION
    question_header = QUESTION_HEADER_FEATURES

    @classmethod
    def to_dict(cls) -> dict[str, Any]:
        return {
            "feature_schema_version": cls.version,
            "QUESTION_HEADER": list(cls.question_header),
        }


@dataclass
class FeatureVector:
    """A finite, serializable feature vector tied to a schema version."""

    values: dict[str, float] = field(default_factory=dict)
    schema_version: int = FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.values = {
            str(name): _finite_float(value)
            for name, value in self.values.items()
        }
        missing = [name for name in QUESTION_HEADER_FEATURES if name not in self.values]
        for name in missing:
            self.values[name] = 0.0

    def get(self, name: str, default: float = 0.0) -> float:
        return float(self.values.get(name, default))

    def __getitem__(self, name: str) -> float:
        return self.get(name)

    def __contains__(self, name: object) -> bool:
        return str(name) in self.values

    def __iter__(self):
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def keys(self):
        return self.values.keys()

    def items(self):
        return self.values.items()

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_schema_version": int(self.schema_version),
            "features": dict(sorted(self.values.items())),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FeatureVector":
        return cls(
            values=dict(value.get("features") or {}),
            schema_version=int(value.get("feature_schema_version", FEATURE_SCHEMA_VERSION)),
        )


def _finite_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if result == result and abs(result) != float("inf") else 0.0
