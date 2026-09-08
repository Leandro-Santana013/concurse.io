"""Semantic Question AST for the Phase-4 structural pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Mapping, Optional, Sequence

from .candidates.models import Candidate, ContextBlock, QuestionRegion, StructuralAnalysis
from .model import BBox, DocumentModel, PhysicalElement
from .solver import AnswerKeyEvidence, DocumentParseConfidence, SequenceSolution


AST_SCHEMA_VERSION = 1
AST_VERSION = "question-ast-v1"


@dataclass
class ASTNode:
    """Common trace surface shared by every semantic node."""

    source_element_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def _base_dict(self, node_type: str) -> dict[str, Any]:
        return {
            "node_type": node_type,
            "source_element_ids": list(self.source_element_ids),
            "metadata": self.metadata,
        }


@dataclass
class QuestionHeaderNode(ASTNode):
    printed_number: Optional[str] = None
    text: str = ""
    confidence: float = 0.0
    candidate_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._base_dict("QuestionHeaderNode"),
            "printed_number": self.printed_number,
            "text": self.text,
            "confidence": float(self.confidence),
            "candidate_id": self.candidate_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QuestionHeaderNode":
        return cls(
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            metadata=dict(value.get("metadata") or {}),
            printed_number=value.get("printed_number"),
            text=str(value.get("text", "")),
            confidence=float(value.get("confidence", 0.0)),
            candidate_id=value.get("candidate_id"),
        )


@dataclass
class StatementNode(ASTNode):
    text: str = ""
    page_indices: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._base_dict("StatementNode"),
            "text": self.text,
            "page_indices": list(self.page_indices),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "StatementNode":
        return cls(
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            metadata=dict(value.get("metadata") or {}),
            text=str(value.get("text", "")),
            page_indices=[int(item) for item in value.get("page_indices", [])],
        )


@dataclass
class FigureNode(ASTNode):
    bbox: Optional[BBox] = None
    alt_text: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._base_dict("FigureNode"),
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "alt_text": self.alt_text,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FigureNode":
        return cls(
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            metadata=dict(value.get("metadata") or {}),
            bbox=BBox.from_dict(value["bbox"]) if value.get("bbox") else None,
            alt_text=value.get("alt_text"),
        )


@dataclass
class TableNode(ASTNode):
    text: str = ""
    bbox: Optional[BBox] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._base_dict("TableNode"),
            "text": self.text,
            "bbox": self.bbox.to_dict() if self.bbox else None,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TableNode":
        return cls(
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            metadata=dict(value.get("metadata") or {}),
            text=str(value.get("text", "")),
            bbox=BBox.from_dict(value["bbox"]) if value.get("bbox") else None,
        )


@dataclass
class OptionNode(ASTNode):
    key: str = ""
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._base_dict("OptionNode"),
            "key": self.key,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OptionNode":
        return cls(
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            metadata=dict(value.get("metadata") or {}),
            key=str(value.get("key", "")),
            text=str(value.get("text", "")),
        )


@dataclass
class OptionGroupNode(ASTNode):
    options: list[OptionNode] = field(default_factory=list)
    confidence: float = 0.0
    marker_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._base_dict("OptionGroupNode"),
            "options": [item.to_dict() for item in self.options],
            "confidence": float(self.confidence),
            "marker_types": list(self.marker_types),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "OptionGroupNode":
        return cls(
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            metadata=dict(value.get("metadata") or {}),
            options=[OptionNode.from_dict(item) for item in value.get("options", [])],
            confidence=float(value.get("confidence", 0.0)),
            marker_types=[str(item) for item in value.get("marker_types", [])],
        )


@dataclass
class ContextNode(ASTNode):
    context_id: str = ""
    text: str = ""
    applies_to_question_numbers: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._base_dict("ContextNode"),
            "context_id": self.context_id,
            "text": self.text,
            "applies_to_question_numbers": list(self.applies_to_question_numbers),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ContextNode":
        return cls(
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            metadata=dict(value.get("metadata") or {}),
            context_id=str(value.get("context_id", "")),
            text=str(value.get("text", "")),
            applies_to_question_numbers=[
                int(item) for item in value.get("applies_to_question_numbers", [])
            ],
        )


@dataclass
class QuestionNode(ASTNode):
    canonical_index: int = 0
    printed_number: Optional[str] = None
    header: Optional[QuestionHeaderNode] = None
    question_header: Optional[QuestionHeaderNode] = None
    statement_nodes: list[StatementNode] = field(default_factory=list)
    option_group: Optional[OptionGroupNode] = None
    figures: list[FigureNode] = field(default_factory=list)
    tables: list[TableNode] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    subject: Optional[str] = None
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    answer: Optional[str] = None
    region_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.header is None and self.question_header is not None:
            self.header = self.question_header
        if self.question_header is None:
            self.question_header = self.header

    @property
    def statements(self) -> list[StatementNode]:
        return self.statement_nodes

    @property
    def source_refs(self) -> list[str]:
        return self.source_element_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._base_dict("QuestionNode"),
            "canonical_index": self.canonical_index,
            "printed_number": self.printed_number,
            "header": self.header.to_dict() if self.header else None,
            "statement_nodes": [item.to_dict() for item in self.statement_nodes],
            "option_group": self.option_group.to_dict() if self.option_group else None,
            "figures": [item.to_dict() for item in self.figures],
            "tables": [item.to_dict() for item in self.tables],
            "context_refs": list(self.context_refs),
            "subject": self.subject,
            "confidence": float(self.confidence),
            "evidence": self.evidence,
            "answer": self.answer,
            "region_id": self.region_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QuestionNode":
        return cls(
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            metadata=dict(value.get("metadata") or {}),
            canonical_index=int(value.get("canonical_index", 0)),
            printed_number=value.get("printed_number"),
            header=QuestionHeaderNode.from_dict(value["header"]) if value.get("header") else None,
            question_header=(
                QuestionHeaderNode.from_dict(value["question_header"])
                if value.get("question_header")
                else None
            ),
            statement_nodes=[
                StatementNode.from_dict(item) for item in value.get("statement_nodes", [])
            ],
            option_group=(
                OptionGroupNode.from_dict(value["option_group"])
                if value.get("option_group")
                else None
            ),
            figures=[FigureNode.from_dict(item) for item in value.get("figures", [])],
            tables=[TableNode.from_dict(item) for item in value.get("tables", [])],
            context_refs=[str(item) for item in value.get("context_refs", [])],
            subject=value.get("subject"),
            confidence=float(value.get("confidence", 0.0)),
            evidence=dict(value.get("evidence") or {}),
            answer=value.get("answer"),
            region_id=value.get("region_id"),
        )


@dataclass
class ExamDocumentNode(ASTNode):
    contexts: list[ContextNode] = field(default_factory=list)
    questions: list[QuestionNode] = field(default_factory=list)
    source: Optional[str] = None
    confidence: Optional[DocumentParseConfidence] = None
    pipeline_version: str = AST_VERSION

    @property
    def context_nodes(self) -> list[ContextNode]:
        return self.contexts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": AST_SCHEMA_VERSION,
            "ast_version": AST_VERSION,
            **self._base_dict("ExamDocumentNode"),
            "contexts": [item.to_dict() for item in self.contexts],
            "questions": [item.to_dict() for item in self.questions],
            "source": self.source,
            "confidence": self.confidence.to_dict() if self.confidence else None,
            "pipeline_version": self.pipeline_version,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExamDocumentNode":
        return cls(
            source_element_ids=[str(item) for item in value.get("source_element_ids", [])],
            metadata=dict(value.get("metadata") or {}),
            contexts=[ContextNode.from_dict(item) for item in value.get("contexts", [])],
            questions=[QuestionNode.from_dict(item) for item in value.get("questions", [])],
            source=value.get("source"),
            confidence=(
                DocumentParseConfidence.from_dict(value["confidence"])
                if value.get("confidence")
                else None
            ),
            pipeline_version=str(value.get("pipeline_version", AST_VERSION)),
        )

    @classmethod
    def from_json(cls, value: str) -> "ExamDocumentNode":
        return cls.from_dict(json.loads(value))


class QuestionASTBuilder:
    """Build the semantic AST from a solved structural analysis."""

    def build(
        self,
        document: DocumentModel,
        analysis: StructuralAnalysis,
        solution: SequenceSolution,
        *,
        answer_key: Any = None,
        legacy_questions: Optional[Sequence[Mapping[str, Any]]] = None,
    ) -> ExamDocumentNode:
        physical = {
            element.id: element
            for page in document.pages
            for element in page.elements
        }
        order = _order_map(analysis, document)
        regions = {region.question_candidate_id: region for region in analysis.question_regions}
        options = {candidate.id: candidate for candidate in analysis.option_candidates}
        subjects = list(analysis.subject_candidates)
        legacy_by_number = _legacy_by_number(legacy_questions)
        answer = AnswerKeyEvidence.from_value(answer_key or solution.answer_key)

        context_blocks, context_aliases = _coalesce_context_blocks(analysis.context_blocks)
        contexts = [
            ContextNode(
                context_id=block.id,
                source_element_ids=list(block.source_element_ids),
                text=block.text,
                applies_to_question_numbers=list(block.question_numbers),
                metadata={
                    "score": block.score,
                    "evidence": dict(block.evidence),
                    "applies_to_candidate_ids": list(block.applies_to_candidate_ids),
                },
            )
            for block in context_blocks
        ]
        questions: list[QuestionNode] = []
        all_source_ids: set[str] = set()
        for canonical_index, candidate in enumerate(solution.selected_candidates, start=1):
            number = _candidate_number(candidate)
            region = regions.get(candidate.id) or _region_by_number(regions.values(), number)
            content_ids = self._content_ids(
                candidate,
                region,
                solution.selected_candidates,
                order,
                physical,
            )
            header_ids = set(candidate.source_element_ids)
            question_contexts = [
                block
                for block in context_blocks
                if candidate.id in block.applies_to_candidate_ids
                or (number is not None and number in block.question_numbers)
            ]
            context_ids = {
                source_id
                for block in question_contexts
                for source_id in block.source_element_ids
            }
            option_candidates = [
                item
                for item in analysis.option_candidates
                if (
                    region is not None
                    and item.id in region.option_candidate_ids
                )
                or bool(set(item.source_element_ids) & set(content_ids))
            ]
            option_ids = {
                source_id
                for item in option_candidates
                for source_id in item.source_element_ids
            }
            subject_candidates = [
                item
                for item in subjects
                if _is_semantic_subject_candidate(item)
                if bool(set(item.source_element_ids) & set(content_ids))
                or _candidate_order(item, order) <= _candidate_order(candidate, order)
            ]
            subject = _nearest_subject(subject_candidates, candidate, order)
            statement_elements = [
                physical[element_id]
                for element_id in content_ids
                if element_id in physical
                and physical[element_id].kind == "text"
                and element_id not in header_ids
                and element_id not in option_ids
                and element_id not in context_ids
                and not _is_subject_source(element_id, subject_candidates)
                and str(physical[element_id].text or "").strip()
            ]
            statement_nodes = self._statement_nodes(statement_elements, candidate)
            option_group = self._option_group(option_candidates, physical)
            if option_group is None:
                option_group = self._legacy_option_group(legacy_by_number.get(number))

            figures = self._figures(candidate, region, content_ids, physical, analysis)
            tables = self._tables(content_ids, physical)
            legacy_question = legacy_by_number.get(number)
            if not statement_nodes and legacy_question:
                statement_nodes = [
                    StatementNode(
                        text=str(legacy_question.get("enunciado") or "").strip(),
                        metadata={"legacy_fallback": True},
                    )
                ]
            if not statement_nodes:
                statement_nodes = [StatementNode(text="", metadata={"empty_statement": True})]

            answer_value = answer.answers.get(number) if number is not None else None
            if not answer_value and legacy_question:
                answer_value = str(legacy_question.get("resposta") or "").strip().upper() or None
            source_parts: list[Any] = [*candidate.source_element_ids]
            source_parts.extend(item.source_element_ids for item in statement_nodes)
            if option_group:
                source_parts.extend(item.source_element_ids for item in option_group.options)
            source_parts.extend(item.source_element_ids for item in figures)
            source_parts.extend(item.source_element_ids for item in tables)
            source_ids = _unique(source_parts)
            all_source_ids.update(source_ids)
            question = QuestionNode(
                source_element_ids=source_ids,
                metadata={
                    "candidate_id": candidate.id,
                    "recovered": bool(candidate.metadata.get("recovered")),
                    "recovery_source": candidate.metadata.get("recovery_source"),
                    "option_candidate_ids": [item.id for item in option_candidates],
                    "source_trace": {
                        "header": list(candidate.source_element_ids),
                        "content": list(content_ids),
                    },
                },
                canonical_index=canonical_index,
                printed_number=str(number) if number is not None else None,
                header=QuestionHeaderNode(
                    source_element_ids=list(candidate.source_element_ids),
                    text=str(candidate.metadata.get("line_text") or ""),
                    printed_number=str(number) if number is not None else None,
                    confidence=float(candidate.score),
                    candidate_id=candidate.id,
                    metadata={"evidence": dict(candidate.evidence)},
                ),
                statement_nodes=statement_nodes,
                option_group=option_group,
                figures=figures,
                tables=tables,
                context_refs=[block.id for block in question_contexts],
                subject=subject,
                confidence=float(candidate.score),
                evidence={
                    **candidate.evidence,
                    "score_breakdown": dict(candidate.score_breakdown),
                    "solver_recovered": bool(candidate.metadata.get("recovered")),
                },
                answer=answer_value,
                region_id=region.id if region else None,
            )
            questions.append(question)

        return ExamDocumentNode(
            source_element_ids=sorted(all_source_ids),
            metadata={
                "solver": solution.metadata,
                "warnings": list(solution.warnings),
                "violations": [item.to_dict() for item in solution.violations],
                "answer_key": answer.to_dict(),
            },
            contexts=contexts,
            questions=questions,
            source=document.source,
            confidence=solution.confidence,
            pipeline_version=AST_VERSION,
        )

    def _content_ids(
        self,
        candidate: Candidate,
        region: Optional[QuestionRegion],
        selected: Sequence[Candidate],
        order: Mapping[str, int],
        physical: Mapping[str, PhysicalElement],
    ) -> list[str]:
        if region is not None and region.content_element_ids:
            return list(region.content_element_ids)
        source_ids = list(candidate.source_element_ids)
        if not source_ids:
            return []
        start = min(order.get(item, 10**9) for item in source_ids)
        following = [
            min((order.get(item, 10**9) for item in other.source_element_ids), default=10**9)
            for other in selected
            if other.id != candidate.id
            and min((order.get(item, 10**9) for item in other.source_element_ids), default=10**9) > start
        ]
        end = min(following, default=10**9)
        return [
            element_id
            for element_id in sorted(physical, key=lambda item: order.get(item, 10**9))
            if start <= order.get(element_id, 10**9) < end
        ]

    def _statement_nodes(
        self,
        elements: Sequence[PhysicalElement],
        candidate: Candidate,
    ) -> list[StatementNode]:
        if not elements:
            return []
        text = "\n".join(str(element.text or "").strip() for element in elements).strip()
        return [
            StatementNode(
                source_element_ids=[element.id for element in elements],
                text=text,
                page_indices=sorted({element.page_index for element in elements}),
                metadata={"cross_page": len({element.page_index for element in elements}) > 1},
            )
        ]

    def _option_group(
        self,
        candidates: Sequence[Candidate],
        physical: Mapping[str, PhysicalElement],
    ) -> Optional[OptionGroupNode]:
        if not candidates:
            return None
        candidate = max(candidates, key=lambda item: (item.score, item.id))
        labels = [str(item) for item in candidate.metadata.get("labels", [])]
        marker_types = [str(item) for item in candidate.metadata.get("marker_types", [])]
        options: list[OptionNode] = []
        for index, element_id in enumerate(candidate.source_element_ids):
            element = physical.get(element_id)
            if element is None or element.kind != "text":
                continue
            label, content = _option_label_and_text(element.text, labels, index)
            options.append(
                OptionNode(
                    source_element_ids=[element.id],
                    key=label,
                    text=content,
                    metadata={"marker_type": marker_types[index] if index < len(marker_types) else None},
                )
            )
        if not options and labels:
            options = [OptionNode(key=label, text="") for label in labels]
        return OptionGroupNode(
            source_element_ids=list(candidate.source_element_ids),
            options=options,
            confidence=float(candidate.score),
            marker_types=marker_types,
            metadata={
                "candidate_id": candidate.id,
                "evidence": dict(candidate.evidence),
            },
        )

    def _legacy_option_group(
        self,
        legacy_question: Optional[Mapping[str, Any]],
    ) -> Optional[OptionGroupNode]:
        if not legacy_question:
            return None
        raw_options = legacy_question.get("opcoes") or legacy_question.get("options") or {}
        if not isinstance(raw_options, Mapping) or not raw_options:
            return None
        options = [
            OptionNode(key=str(key), text=str(value or "").strip(), metadata={"legacy_fallback": True})
            for key, value in raw_options.items()
        ]
        return OptionGroupNode(
            options=options,
            confidence=0.45,
            metadata={"legacy_fallback": True},
        )

    def _figures(
        self,
        candidate: Candidate,
        region: Optional[QuestionRegion],
        content_ids: Sequence[str],
        physical: Mapping[str, PhysicalElement],
        analysis: StructuralAnalysis,
    ) -> list[FigureNode]:
        owned = {
            item.image_element_id: item
            for item in analysis.image_ownership
            if item.question_candidate_id == candidate.id
        }
        image_ids = set(region.image_element_ids if region else ()) | set(owned)
        image_ids &= set(content_ids) | set(owned)
        result: list[FigureNode] = []
        for element_id in content_ids:
            element = physical.get(element_id)
            if element is None or element.kind not in {"image", "drawing"} or element_id not in image_ids:
                continue
            evidence = owned.get(element_id)
            result.append(
                FigureNode(
                    source_element_ids=[element.id],
                    bbox=element.bbox,
                    alt_text=str(element.metadata.get("alt_text") or "") or None,
                    metadata={
                        "kind": element.kind,
                        "ownership": evidence.to_dict() if evidence else None,
                    },
                )
            )
        return result

    def _tables(
        self,
        content_ids: Sequence[str],
        physical: Mapping[str, PhysicalElement],
    ) -> list[TableNode]:
        return [
            TableNode(
                source_element_ids=[element.id],
                text=str(element.text or element.metadata.get("text") or "").strip(),
                bbox=element.bbox,
                metadata=dict(element.metadata),
            )
            for element_id in content_ids
            if (element := physical.get(element_id)) is not None and element.kind == "table"
        ]


QuestionAST = ExamDocumentNode


def build_question_ast(
    document: DocumentModel,
    analysis: StructuralAnalysis,
    solution: SequenceSolution,
    *,
    answer_key: Any = None,
    legacy_questions: Optional[Sequence[Mapping[str, Any]]] = None,
    builder: Optional[QuestionASTBuilder] = None,
) -> ExamDocumentNode:
    return (builder or QuestionASTBuilder()).build(
        document,
        analysis,
        solution,
        answer_key=answer_key,
        legacy_questions=legacy_questions,
    )


def _candidate_number(candidate: Candidate) -> Optional[int]:
    try:
        raw = candidate.metadata.get("question_number")
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _order_map(analysis: StructuralAnalysis, document: DocumentModel) -> dict[str, int]:
    result: dict[str, int] = {}
    cursor = 0
    layout = getattr(analysis, "layout_analysis", None)
    if layout is not None:
        for page in sorted(layout.pages, key=lambda item: item.page_index):
            for element_id in page.reading_order.sequence:
                result.setdefault(element_id, cursor)
                cursor += 1
    for page in sorted(document.pages, key=lambda item: item.page_index):
        for element in sorted(page.elements, key=lambda item: (item.bbox.ny0, item.bbox.nx0, item.id)):
            result.setdefault(element.id, cursor)
            cursor += 1
    return result


def _candidate_order(candidate: Candidate, order: Mapping[str, int]) -> int:
    values = [order[item] for item in candidate.source_element_ids if item in order]
    if values:
        return min(values)
    try:
        return int(candidate.metadata.get("reading_index", 10**9))
    except (TypeError, ValueError):
        return 10**9


def _region_by_number(
    regions: Sequence[QuestionRegion],
    number: Optional[int],
) -> Optional[QuestionRegion]:
    if number is None:
        return None
    return next((region for region in regions if region.question_number == number), None)


def _legacy_by_number(
    questions: Optional[Sequence[Mapping[str, Any]]],
) -> dict[Optional[int], Mapping[str, Any]]:
    result: dict[Optional[int], Mapping[str, Any]] = {}
    for question in questions or []:
        raw = question.get("numero_questao") or question.get("printed_number")
        try:
            number = int(str(raw).strip())
        except (TypeError, ValueError):
            number = None
        result[number] = question
    return result


def _nearest_subject(
    candidates: Sequence[Candidate],
    question: Candidate,
    order: Mapping[str, int],
) -> Optional[str]:
    if not candidates:
        return None
    before = [
        item
        for item in candidates
        if _candidate_order(item, order) <= _candidate_order(question, order)
    ]
    chosen = max(before or list(candidates), key=lambda item: _candidate_order(item, order))
    return str(chosen.metadata.get("subject") or chosen.metadata.get("line_text") or "").strip() or None


def _is_subject_source(element_id: str, candidates: Sequence[Candidate]) -> bool:
    return any(element_id in candidate.source_element_ids for candidate in candidates)


def _is_semantic_subject_candidate(candidate: Candidate) -> bool:
    """Avoid treating every classifier-labelled body line as a heading."""

    pattern_score = float(candidate.evidence.get("legacy_subject_pattern", 0.0))
    explicit = str(candidate.metadata.get("line_text") or "").strip()
    return pattern_score >= 0.50 or bool(
        re.match(r"^(?:disciplina|materia|conhecimentos?)\s*[:\-]", explicit, re.I)
    )


def _coalesce_context_blocks(
    blocks: Sequence[ContextBlock],
) -> tuple[list[ContextBlock], dict[str, str]]:
    """Keep one shared semantic context when detector evidence overlaps."""

    canonical: list[ContextBlock] = []
    aliases: dict[str, str] = {}
    for block in blocks:
        existing = next(
            (
                item
                for item in canonical
                if set(item.source_element_ids) & set(block.source_element_ids)
                or set(item.question_numbers) & set(block.question_numbers)
            ),
            None,
        )
        if existing is None:
            canonical.append(
                ContextBlock(
                    id=block.id,
                    source_element_ids=list(block.source_element_ids),
                    applies_to_candidate_ids=list(block.applies_to_candidate_ids),
                    question_numbers=list(block.question_numbers),
                    text=block.text,
                    score=block.score,
                    evidence=dict(block.evidence),
                )
            )
            aliases[block.id] = block.id
            continue
        aliases[block.id] = existing.id
        existing.source_element_ids = _unique(
            [existing.source_element_ids, block.source_element_ids]
        )
        existing.applies_to_candidate_ids = _unique(
            [existing.applies_to_candidate_ids, block.applies_to_candidate_ids]
        )
        existing.question_numbers = sorted(
            {
                *existing.question_numbers,
                *block.question_numbers,
            }
        )
        if len(block.text) > len(existing.text) and _looks_like_context_marker(block.text):
            existing.text = block.text
        existing.score = max(existing.score, block.score)
        existing.evidence.update(block.evidence)
    return canonical, aliases


def _looks_like_context_marker(text: str) -> bool:
    return bool(re.search(r"\b(?:texto|leia|considere|instru[cç]ao|com base)\b", text, re.I))


def _option_label_and_text(
    raw_text: Any,
    labels: Sequence[str],
    index: int,
) -> tuple[str, str]:
    text = str(raw_text or "").strip()
    match = re.match(
        r"^\s*(?:(?P<label>[A-Ea-e])\s*(?:\(\s*\)|[\.\-:;\)])|\(\s*(?P<paren>[A-Ea-e])\s*\)|\[\s*(?P<bracket>[A-Ea-e])\s*\])\s*",
        text,
    )
    if match:
        label = (match.group("label") or match.group("paren") or match.group("bracket")).upper()
        return label, text[match.end() :].strip()
    marker_match = re.match(r"^\s*(?:[\u2610\u2611\u25a1\u25a2\u25a3\u25cb\u25cf\u2022\u00b7\u25e6\u25aa\u25ab\-])\s*", text)
    if marker_match:
        return (labels[index] if index < len(labels) else chr(ord("A") + index)), text[marker_match.end() :].strip()
    return (labels[index] if index < len(labels) else chr(ord("A") + index)), text


def _unique(values: Sequence[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            for nested in value:
                if nested and str(nested) not in result:
                    result.append(str(nested))
        elif value and str(value) not in result:
            result.append(str(value))
    return result
