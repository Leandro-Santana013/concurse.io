"""Serializable records produced by Phase 3."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Mapping, Optional

from ..model import BBox
from .features import FeatureSchemaV1, FeatureVector


@dataclass
class Candidate:
    """A scored structural hypothesis with decomposable evidence."""

    id: str
    type: str
    score: float
    evidence: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_element_ids: list[str] = field(default_factory=list)
    features: Optional[FeatureVector] = None
    page_index: Optional[int] = None
    bbox: Optional[BBox] = None
    score_breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def candidate_id(self) -> str:
        return self.id

    @property
    def candidate_type(self) -> str:
        return self.type

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "score": float(self.score),
            "evidence": dict(sorted(self.evidence.items())),
            "metadata": self.metadata,
            "source_element_ids": list(self.source_element_ids),
            "features": self.features.to_dict() if self.features else None,
            "page_index": self.page_index,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "score_breakdown": dict(sorted(self.score_breakdown.items())),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Candidate":
        return cls(
            id=str(value["id"]),
            type=str(value["type"]),
            score=float(value.get("score", 0.0)),
            evidence={str(k): float(v) for k, v in (value.get("evidence") or {}).items()},
            metadata=dict(value.get("metadata") or {}),
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            features=(
                FeatureVector.from_dict(value["features"])
                if value.get("features")
                else None
            ),
            page_index=(int(value["page_index"]) if value.get("page_index") is not None else None),
            bbox=BBox.from_dict(value["bbox"]) if value.get("bbox") else None,
            score_breakdown={
                str(k): float(v)
                for k, v in (value.get("score_breakdown") or {}).items()
            },
        )


@dataclass
class CandidateDetection:
    """Typed candidate collections returned by :class:`CandidateDetector`."""

    question_headers: list[Candidate] = field(default_factory=list)
    option_groups: list[Candidate] = field(default_factory=list)
    subjects: list[Candidate] = field(default_factory=list)
    contexts: list[Candidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def candidates(self) -> list[Candidate]:
        return [
            *self.question_headers,
            *self.option_groups,
            *self.subjects,
            *self.contexts,
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question_headers": [item.to_dict() for item in self.question_headers],
            "option_groups": [item.to_dict() for item in self.option_groups],
            "subjects": [item.to_dict() for item in self.subjects],
            "contexts": [item.to_dict() for item in self.contexts],
            "warnings": list(self.warnings),
        }


@dataclass
class PageSegment:
    """The portion of a question region that belongs to one PDF page."""

    page_index: int
    element_ids: list[str] = field(default_factory=list)
    bbox: Optional[BBox] = None
    start_order: Optional[int] = None
    end_order: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_index": self.page_index,
            "element_ids": list(self.element_ids),
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "start_order": self.start_order,
            "end_order": self.end_order,
        }


@dataclass
class ImageOwnership:
    """Geometric ownership decision for one visual element."""

    image_element_id: str
    question_candidate_id: str
    score: float
    evidence: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_element_id": self.image_element_id,
            "question_candidate_id": self.question_candidate_id,
            "score": float(self.score),
            "evidence": dict(sorted(self.evidence.items())),
            "metadata": self.metadata,
        }


@dataclass
class QuestionRegion:
    """Preliminary region bounded by consecutive question candidates."""

    id: str
    question_candidate_id: str
    question_number: Optional[int]
    segments: list[PageSegment] = field(default_factory=list)
    content_element_ids: list[str] = field(default_factory=list)
    option_candidate_ids: list[str] = field(default_factory=list)
    context_candidate_ids: list[str] = field(default_factory=list)
    image_element_ids: list[str] = field(default_factory=list)
    image_ownership: list[ImageOwnership] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question_candidate_id": self.question_candidate_id,
            "question_number": self.question_number,
            "segments": [item.to_dict() for item in self.segments],
            "content_element_ids": list(self.content_element_ids),
            "option_candidate_ids": list(self.option_candidate_ids),
            "context_candidate_ids": list(self.context_candidate_ids),
            "image_element_ids": list(self.image_element_ids),
            "image_ownership": [item.to_dict() for item in self.image_ownership],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QuestionRegion":
        return cls(
            id=str(value["id"]),
            question_candidate_id=str(value["question_candidate_id"]),
            question_number=(
                int(value["question_number"])
                if value.get("question_number") is not None
                else None
            ),
            segments=[
                PageSegment(
                    page_index=int(item["page_index"]),
                    element_ids=[str(element_id) for element_id in item.get("element_ids", [])],
                    bbox=BBox.from_dict(item["bbox"]) if item.get("bbox") else None,
                    start_order=item.get("start_order"),
                    end_order=item.get("end_order"),
                )
                for item in value.get("segments", [])
            ],
            content_element_ids=[str(item) for item in value.get("content_element_ids", [])],
            option_candidate_ids=[str(item) for item in value.get("option_candidate_ids", [])],
            context_candidate_ids=[str(item) for item in value.get("context_candidate_ids", [])],
            image_element_ids=[str(item) for item in value.get("image_element_ids", [])],
            image_ownership=[
                ImageOwnership(
                    image_element_id=str(item["image_element_id"]),
                    question_candidate_id=str(item["question_candidate_id"]),
                    score=float(item.get("score", 0.0)),
                    evidence={str(k): float(v) for k, v in (item.get("evidence") or {}).items()},
                    metadata=dict(item.get("metadata") or {}),
                )
                for item in value.get("image_ownership", [])
            ],
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass
class ContextBlock:
    """A shared physical context that can apply to multiple questions."""

    id: str
    source_element_ids: list[str] = field(default_factory=list)
    applies_to_candidate_ids: list[str] = field(default_factory=list)
    question_numbers: list[int] = field(default_factory=list)
    text: str = ""
    score: float = 0.0
    evidence: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_element_ids": list(self.source_element_ids),
            "applies_to_candidate_ids": list(self.applies_to_candidate_ids),
            "question_numbers": list(self.question_numbers),
            "text": self.text,
            "score": float(self.score),
            "evidence": dict(sorted(self.evidence.items())),
        }


@dataclass
class StructuralAnalysis:
    """Complete, opt-in Phase-3 output and its inspectable diagnostics."""

    pipeline_version: str
    document_profile: Any
    question_candidates: list[Candidate]
    option_candidates: list[Candidate]
    subject_candidates: list[Candidate]
    context_candidates: list[Candidate]
    context_blocks: list[ContextBlock]
    graph: Any
    question_regions: list[QuestionRegion]
    image_ownership: list[ImageOwnership]
    warnings: list[str] = field(default_factory=list)
    layout_analysis: Any = None

    @property
    def candidates(self) -> list[Candidate]:
        return [
            *self.question_candidates,
            *self.option_candidates,
            *self.subject_candidates,
            *self.context_candidates,
        ]

    def trace(self) -> dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "feature_schema_version": 1,
            "feature_schema": FeatureSchemaV1.to_dict(),
            "document_profile": self.document_profile.to_dict(),
            "question_candidates": [item.to_dict() for item in self.question_candidates],
            "option_candidates": [item.to_dict() for item in self.option_candidates],
            "subject_candidates": [item.to_dict() for item in self.subject_candidates],
            "context_candidates": [item.to_dict() for item in self.context_candidates],
            "context_blocks": [item.to_dict() for item in self.context_blocks],
            "graph_stats": self.graph.stats(),
            "question_regions": [item.to_dict() for item in self.question_regions],
            "image_ownership": [item.to_dict() for item in self.image_ownership],
            "warnings": list(self.warnings),
        }

    def to_dict(self) -> dict[str, Any]:
        value = self.trace()
        value["graph"] = self.graph.to_dict()
        return value

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)
