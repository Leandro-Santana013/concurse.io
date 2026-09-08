"""Small, explicit registry for versioned optional models."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Optional

from ..candidates.features import FEATURE_SCHEMA_VERSION
from .classifier import FeatureSchemaMismatchError, TrainedCandidateClassifier


REGISTRY_VERSION = 1


@dataclass(frozen=True)
class RegistryEntry:
    version: str
    path: str
    feature_schema: str
    model_version: Optional[str] = None
    training_dataset_version: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "version": self.version,
            "path": self.path,
            "feature_schema": self.feature_schema,
        }
        if self.model_version is not None:
            value["model_version"] = self.model_version
        if self.training_dataset_version is not None:
            value["training_dataset_version"] = self.training_dataset_version
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RegistryEntry":
        return cls(
            version=str(value.get("version", "")),
            path=str(value.get("path", "")),
            feature_schema=str(value.get("feature_schema", "")),
            model_version=value.get("model_version"),
            training_dataset_version=value.get("training_dataset_version"),
        )


class ModelRegistry:
    """Manifest-backed registry with a schema compatibility gate."""

    def __init__(self, manifest_path: str | Path, *, runtime_feature_schema: int = FEATURE_SCHEMA_VERSION) -> None:
        self.manifest_path = Path(manifest_path)
        self.runtime_feature_schema = int(runtime_feature_schema)
        self.entries: dict[str, RegistryEntry] = {}

    def register(
        self,
        name: str,
        *,
        path: str | Path,
        version: str = "1",
        feature_schema: int | str = FEATURE_SCHEMA_VERSION,
        model_version: Optional[str] = None,
        training_dataset_version: Optional[str] = None,
    ) -> RegistryEntry:
        entry = RegistryEntry(
            version=str(version),
            path=str(path),
            feature_schema=str(feature_schema),
            model_version=model_version,
            training_dataset_version=training_dataset_version,
        )
        self.entries[str(name)] = entry
        return entry

    def get(self, name: str) -> RegistryEntry:
        try:
            return self.entries[str(name)]
        except KeyError as exc:
            raise KeyError(f"model {name!r} is not registered") from exc

    def save(self, path: str | Path | None = None) -> Path:
        output = Path(path) if path is not None else self.manifest_path
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "registry_version": REGISTRY_VERSION,
            "candidate_classifier": self.entries.get("candidate_classifier", RegistryEntry("", "", "")).to_dict()
            if "candidate_classifier" in self.entries
            else None,
            "layout_clusterer": self.entries.get("layout_clusterer", RegistryEntry("", "", "")).to_dict()
            if "layout_clusterer" in self.entries
            else None,
        }
        for name, entry in sorted(self.entries.items()):
            payload[name] = entry.to_dict()
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return output

    @classmethod
    def load(cls, path: str | Path, *, runtime_feature_schema: int = FEATURE_SCHEMA_VERSION) -> "ModelRegistry":
        manifest_path = Path(path)
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        registry = cls(manifest_path, runtime_feature_schema=runtime_feature_schema)
        for name, value in payload.items():
            if name == "registry_version" or not isinstance(value, Mapping):
                continue
            if not value.get("path"):
                continue
            registry.entries[str(name)] = RegistryEntry.from_dict(value)
        return registry

    def resolve(self, name: str, *, expected_feature_schema: Optional[int] = None) -> Path:
        entry = self.get(name)
        expected = self.runtime_feature_schema if expected_feature_schema is None else int(expected_feature_schema)
        try:
            actual = int(entry.feature_schema)
        except (TypeError, ValueError) as exc:
            raise FeatureSchemaMismatchError(
                f"invalid feature schema in registry for {name!r}: {entry.feature_schema!r}"
            ) from exc
        if actual != expected:
            raise FeatureSchemaMismatchError(
                f"registry feature schema mismatch for {name!r}: model={actual}, runtime={expected}"
            )
        path = Path(entry.path)
        if not path.is_absolute():
            path = self.manifest_path.parent / path
        return path

    def load_candidate_classifier(
        self,
        *,
        name: str = "candidate_classifier",
        expected_feature_schema: Optional[int] = None,
    ) -> TrainedCandidateClassifier:
        path = self.resolve(name, expected_feature_schema=expected_feature_schema)
        return TrainedCandidateClassifier.load(
            path,
            expected_feature_schema_version=(
                self.runtime_feature_schema
                if expected_feature_schema is None
                else int(expected_feature_schema)
            ),
        )

    def load_layout_clusterer(
        self,
        *,
        name: str = "layout_clusterer",
        expected_feature_schema: Optional[int] = None,
    ) -> Any:
        """Load the JSON family model through the same schema gate."""

        path = self.resolve(name, expected_feature_schema=expected_feature_schema)
        from ..layout_families import LayoutFamilyModel

        return LayoutFamilyModel.load(path)

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_version": REGISTRY_VERSION,
            **{name: entry.to_dict() for name, entry in sorted(self.entries.items())},
        }


ModelRegistryEntry = RegistryEntry
