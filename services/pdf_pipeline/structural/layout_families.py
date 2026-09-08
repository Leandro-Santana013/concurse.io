"""Bank-agnostic layout-family clustering and priors.

Families are learned from ``DocumentProfile.fingerprint`` only.  A bank name
may be useful to report benchmark slices, but it never participates in the
cluster features or the family identity.  The resulting family is a prior;
the current PDF's geometry and candidates remain authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from statistics import mean
from typing import Any, Iterable, Mapping, Optional, Sequence

from .layout.profile import DocumentProfile


LAYOUT_FAMILY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LayoutFamilyConfig:
    algorithm: str = "auto"
    eps: float = 1.25
    min_samples: int = 2
    max_assignment_distance: float = 3.5
    random_state: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "eps": self.eps,
            "min_samples": self.min_samples,
            "max_assignment_distance": self.max_assignment_distance,
            "random_state": self.random_state,
        }


@dataclass
class LayoutFamilyPriors:
    expected_column_count: Optional[int] = None
    question_header_style_prior: dict[str, Any] = field(default_factory=dict)
    option_style_prior: dict[str, Any] = field(default_factory=dict)
    likely_reading_order: str = "UNKNOWN"
    known_noise_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_column_count": self.expected_column_count,
            "question_header_style_prior": dict(self.question_header_style_prior),
            "option_style_prior": dict(self.option_style_prior),
            "likely_reading_order": self.likely_reading_order,
            "known_noise_patterns": list(self.known_noise_patterns),
        }


@dataclass
class LayoutFamily:
    family_id: str
    member_ids: list[str] = field(default_factory=list)
    centroid: list[float] = field(default_factory=list)
    priors: LayoutFamilyPriors = field(default_factory=LayoutFamilyPriors)
    sample_count: int = 0
    is_noise: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "member_ids": list(self.member_ids),
            "centroid": list(self.centroid),
            "priors": self.priors.to_dict(),
            "sample_count": self.sample_count,
            "is_noise": self.is_noise,
        }


@dataclass(frozen=True)
class LayoutFamilyAssignment:
    document_id: Optional[str]
    family_id: str
    confidence: float
    distance: Optional[float]
    is_noise: bool
    priors: LayoutFamilyPriors

    @property
    def layout_family(self) -> Optional[str]:
        return None if self.is_noise else self.family_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "family_id": self.family_id,
            "layout_family": self.layout_family,
            "confidence": self.confidence,
            "distance": self.distance,
            "is_noise": self.is_noise,
            "priors": self.priors.to_dict(),
        }


class LayoutFamilyModel:
    """Cluster document fingerprints and expose only soft layout priors."""

    def __init__(self, config: Optional[LayoutFamilyConfig] = None) -> None:
        self.config = config or LayoutFamilyConfig()
        self.families: dict[str, LayoutFamily] = {}
        self.assignments: dict[str, LayoutFamilyAssignment] = {}
        self.algorithm_used: Optional[str] = None
        self.fingerprint_version: Optional[str] = None
        self._mean: list[float] = []
        self._scale: list[float] = []

    def fit(
        self,
        profiles: Sequence[DocumentProfile],
        *,
        document_ids: Optional[Sequence[str]] = None,
    ) -> "LayoutFamilyModel":
        if not profiles:
            self.families = {}
            self.assignments = {}
            self.algorithm_used = None
            return self
        ids = [str(item) for item in (document_ids or range(len(profiles)))]
        if len(ids) != len(profiles):
            raise ValueError("document_ids must have one entry per DocumentProfile")
        versions = {str(profile.fingerprint_version) for profile in profiles}
        if len(versions) != 1:
            raise ValueError("all profiles in a layout-family model need one fingerprint version")
        self.fingerprint_version = versions.pop()
        matrix = [_profile_vector(profile) for profile in profiles]
        dimensions = {len(vector) for vector in matrix}
        if len(dimensions) != 1 or not next(iter(dimensions), 0):
            raise ValueError("profiles must expose equally sized non-empty fingerprints")
        normalized = _standardize(matrix)
        self._mean = normalized[1]
        self._scale = normalized[2]
        points = normalized[0]
        labels, algorithm = self._cluster(points)
        self.algorithm_used = algorithm
        self.families = {}
        self.assignments = {}
        for label in sorted(set(labels)):
            member_indices = [index for index, value in enumerate(labels) if value == label]
            is_noise = int(label) < 0
            family_id = "noise" if is_noise else f"layout-family-{int(label) + 1}"
            centroid = _centroid([points[index] for index in member_indices])
            priors = _build_priors([profiles[index] for index in member_indices])
            family = LayoutFamily(
                family_id=family_id,
                member_ids=[ids[index] for index in member_indices],
                centroid=centroid,
                priors=priors,
                sample_count=len(member_indices),
                is_noise=is_noise,
            )
            self.families[family_id] = family
            for index in member_indices:
                distance = _distance(points[index], centroid)
                self.assignments[ids[index]] = LayoutFamilyAssignment(
                    document_id=ids[index],
                    family_id=family_id,
                    confidence=0.0 if is_noise else _distance_confidence(distance, self.config.max_assignment_distance),
                    distance=distance,
                    is_noise=is_noise,
                    priors=priors,
                )
        return self

    def fit_predict(
        self,
        profiles: Sequence[DocumentProfile],
        *,
        document_ids: Optional[Sequence[str]] = None,
    ) -> dict[str, LayoutFamilyAssignment]:
        self.fit(profiles, document_ids=document_ids)
        return dict(self.assignments)

    def predict(
        self,
        profile: DocumentProfile,
        *,
        document_id: Optional[str] = None,
    ) -> LayoutFamilyAssignment:
        if not self.families:
            return LayoutFamilyAssignment(
                document_id=document_id,
                family_id="noise",
                confidence=0.0,
                distance=None,
                is_noise=True,
                priors=LayoutFamilyPriors(),
            )
        vector = _profile_vector(profile)
        if self.fingerprint_version and str(profile.fingerprint_version) != self.fingerprint_version:
            raise ValueError(
                f"layout fingerprint version mismatch: model={self.fingerprint_version}, profile={profile.fingerprint_version}"
            )
        standardized = [
            (value - self._mean[index]) / self._scale[index]
            for index, value in enumerate(vector)
        ]
        candidates = [family for family in self.families.values() if not family.is_noise]
        if not candidates:
            noise_family = self.families.get("noise")
            return LayoutFamilyAssignment(
                document_id=document_id,
                family_id="noise",
                confidence=0.0,
                distance=None,
                is_noise=True,
                priors=noise_family.priors if noise_family else LayoutFamilyPriors(),
            )
        family = min(candidates, key=lambda item: _distance(standardized, item.centroid))
        distance = _distance(standardized, family.centroid)
        is_noise = distance > self.config.max_assignment_distance
        if is_noise:
            noise_family = self.families.get("noise")
            return LayoutFamilyAssignment(
                document_id=document_id,
                family_id="noise",
                confidence=0.0,
                distance=distance,
                is_noise=True,
                priors=noise_family.priors if noise_family else LayoutFamilyPriors(),
            )
        return LayoutFamilyAssignment(
            document_id=document_id,
            family_id=family.family_id,
            confidence=_distance_confidence(distance, self.config.max_assignment_distance),
            distance=distance,
            is_noise=False,
            priors=family.priors,
        )

    def priors_for(self, profile: DocumentProfile) -> LayoutFamilyPriors:
        return self.predict(profile).priors

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LAYOUT_FAMILY_SCHEMA_VERSION,
            "config": self.config.to_dict(),
            "algorithm_used": self.algorithm_used,
            "fingerprint_version": self.fingerprint_version,
            "mean": list(self._mean),
            "scale": list(self._scale),
            "families": {key: value.to_dict() for key, value in sorted(self.families.items())},
        }

    def save(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return output

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)

    @classmethod
    def load(cls, path: str | Path) -> "LayoutFamilyModel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_json(cls, value: str) -> "LayoutFamilyModel":
        return cls.from_dict(json.loads(value))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LayoutFamilyModel":
        model = cls(
            LayoutFamilyConfig(**dict(value.get("config") or {}))
        )
        model.algorithm_used = value.get("algorithm_used")
        model.fingerprint_version = value.get("fingerprint_version")
        model._mean = [float(item) for item in value.get("mean", [])]
        model._scale = [float(item) for item in value.get("scale", [])]
        for family_id, item in (value.get("families") or {}).items():
            priors_value = item.get("priors") or {}
            priors = LayoutFamilyPriors(
                expected_column_count=priors_value.get("expected_column_count"),
                question_header_style_prior=dict(priors_value.get("question_header_style_prior") or {}),
                option_style_prior=dict(priors_value.get("option_style_prior") or {}),
                likely_reading_order=str(priors_value.get("likely_reading_order", "UNKNOWN")),
                known_noise_patterns=[str(pattern) for pattern in priors_value.get("known_noise_patterns", [])],
            )
            model.families[str(family_id)] = LayoutFamily(
                family_id=str(item.get("family_id", family_id)),
                member_ids=[str(member) for member in item.get("member_ids", [])],
                centroid=[float(number) for number in item.get("centroid", [])],
                priors=priors,
                sample_count=int(item.get("sample_count", 0)),
                is_noise=bool(item.get("is_noise", False)),
            )
        return model

    def _cluster(self, points: Sequence[Sequence[float]]) -> tuple[list[int], str]:
        algorithm = str(self.config.algorithm).strip().lower()
        if algorithm in {"auto", "hdbscan"}:
            try:
                from sklearn.cluster import HDBSCAN

                clusterer = HDBSCAN(
                    min_cluster_size=max(2, self.config.min_samples),
                    min_samples=self.config.min_samples,
                    copy=False,
                )
                return [int(item) for item in clusterer.fit_predict(points)], "HDBSCAN"
            except ImportError:
                try:
                    import hdbscan  # type: ignore

                    clusterer = hdbscan.HDBSCAN(
                        min_cluster_size=max(2, self.config.min_samples),
                        min_samples=self.config.min_samples,
                    )
                    return [int(item) for item in clusterer.fit_predict(points)], "HDBSCAN"
                except ImportError:
                    if algorithm == "hdbscan":
                        algorithm = "dbscan"
            except Exception:
                algorithm = "dbscan"
        if algorithm != "dbscan":
            algorithm = "dbscan"
        from sklearn.cluster import DBSCAN

        clusterer = DBSCAN(
            eps=float(self.config.eps),
            min_samples=int(self.config.min_samples),
        )
        return [int(item) for item in clusterer.fit_predict(points)], "DBSCAN"


LayoutFamilyClusterer = LayoutFamilyModel


def build_layout_families(
    profiles: Sequence[DocumentProfile],
    *,
    document_ids: Optional[Sequence[str]] = None,
    config: Optional[LayoutFamilyConfig] = None,
) -> LayoutFamilyModel:
    return LayoutFamilyModel(config).fit(profiles, document_ids=document_ids)


def _profile_vector(profile: DocumentProfile) -> list[float]:
    values = [float(value) for value in profile.fingerprint]
    if not values:
        raise ValueError("DocumentProfile has no fingerprint")
    return [value if math.isfinite(value) else 0.0 for value in values]


def _standardize(matrix: Sequence[Sequence[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    dimensions = len(matrix[0])
    mean_values = [sum(row[index] for row in matrix) / len(matrix) for index in range(dimensions)]
    scales = []
    for index in range(dimensions):
        variance = sum((row[index] - mean_values[index]) ** 2 for row in matrix) / max(len(matrix), 1)
        scales.append(math.sqrt(variance) or 1.0)
    normalized = [
        [(row[index] - mean_values[index]) / scales[index] for index in range(dimensions)]
        for row in matrix
    ]
    return normalized, mean_values, scales


def _centroid(points: Sequence[Sequence[float]]) -> list[float]:
    if not points:
        return []
    return [sum(row[index] for row in points) / len(points) for index in range(len(points[0]))]


def _distance(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(left, right)))


def _distance_confidence(distance: float, maximum: float) -> float:
    if maximum <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - distance / maximum))


def _build_priors(profiles: Sequence[DocumentProfile]) -> LayoutFamilyPriors:
    columns = [int(round(profile.fingerprint[0])) for profile in profiles if profile.fingerprint]
    column_count = max(set(columns), key=lambda value: (columns.count(value), -value)) if columns else None
    modes = [str(profile.reading_order_mode or "UNKNOWN") for profile in profiles]
    reading_order = max(set(modes), key=lambda value: (modes.count(value), value)) if modes else "UNKNOWN"
    header_prior = _merge_signature([profile.question_header_signature for profile in profiles])
    option_prior = _merge_signature([profile.option_signature for profile in profiles])
    noise_patterns = sorted(
        {
            str(cluster.get("cluster_id"))
            for profile in profiles
            for cluster in profile.style_clusters
            if cluster.get("is_noise")
        }
    )
    return LayoutFamilyPriors(
        expected_column_count=column_count,
        question_header_style_prior=header_prior,
        option_style_prior=option_prior,
        likely_reading_order=reading_order,
        known_noise_patterns=noise_patterns,
    )


def _merge_signature(values: Iterable[Optional[Mapping[str, Any]]]) -> dict[str, Any]:
    usable = [dict(value) for value in values if isinstance(value, Mapping)]
    if not usable:
        return {}
    keys = sorted({str(key) for value in usable for key in value})
    result: dict[str, Any] = {}
    for key in keys:
        numeric = [float(value[key]) for value in usable if _is_number(value.get(key))]
        if numeric:
            result[key] = round(mean(numeric), 8)
        else:
            counts: dict[str, int] = {}
            for value in usable:
                if key in value:
                    text = str(value[key])
                    counts[text] = counts.get(text, 0) + 1
            if counts:
                result[key] = max(counts, key=lambda item: (counts[item], item))
    return result


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False
