"""Safe shadow execution and structural-versus-legacy metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Any, Callable, Mapping, Optional, Sequence

from .arbiter import ArbitrationDecision, ResultArbiter
from .config import PipelineMode, get_pipeline_mode
from .model import DocumentModel
from .physical import PhysicalExtractor
from .question_ast import ExamDocumentNode, QuestionASTBuilder
from .renderer import render_legacy_document
from .rollout import RolloutConfig, should_sample_structural, structural_ml_enabled
from .solver import AnswerKeyEvidence, ConstraintSolver, SequenceSolution
from .trace import build_structural_trace


@dataclass(frozen=True)
class LegacyParserContext:
    exam_id: Optional[int] = None
    extract_images: bool = True
    declared_banca: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class StructuralMetric:
    legacy: Any
    structural: Any
    equal: bool
    delta: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "legacy": self.legacy,
            "structural": self.structural,
            "equal": self.equal,
            "delta": self.delta,
        }


@dataclass
class StructuralDiff:
    question_count: StructuralMetric
    question_order: StructuralMetric
    printed_numbers: StructuralMetric
    option_count: StructuralMetric
    option_keys: StructuralMetric
    image_count: StructuralMetric
    image_ownership: StructuralMetric
    subject: StructuralMetric
    answer_key_coverage: StructuralMetric
    changed_fields: list[str] = field(default_factory=list)

    @property
    def has_differences(self) -> bool:
        return bool(self.changed_fields)

    @property
    def difference_count(self) -> int:
        return len(self.changed_fields)

    def to_dict(self) -> dict[str, Any]:
        return {
            name: getattr(self, name).to_dict()
            for name in (
                "question_count", "question_order", "printed_numbers", "option_count",
                "option_keys", "image_count", "image_ownership", "subject",
                "answer_key_coverage",
            )
        } | {
            "changed_fields": list(self.changed_fields),
            "has_differences": self.has_differences,
            "difference_count": self.difference_count,
        }


@dataclass
class StructuralShadowResult:
    mode: PipelineMode
    legacy_result: list[dict[str, Any]]
    structural_result: Optional[list[dict[str, Any]]] = None
    structural_analysis: Any = None
    solution: Optional[SequenceSolution] = None
    ast: Optional[ExamDocumentNode] = None
    diff: Optional[StructuralDiff] = None
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    arbitration: Optional[ArbitrationDecision] = None
    trace: dict[str, Any] = field(default_factory=dict)

    @property
    def user_result(self) -> list[dict[str, Any]]:
        if (
            self.mode in {PipelineMode.STRUCTURAL_PREFERRED, PipelineMode.STRUCTURAL_ONLY}
            and self.arbitration is not None
            and self.arbitration.status.value == "STRUCTURAL"
            and self.arbitration.result is not None
        ):
            return [dict(item) for item in self.arbitration.result]
        return [dict(item) for item in self.legacy_result]

    @property
    def structural_failed(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "legacy_result": list(self.legacy_result),
            "structural_result": self.structural_result,
            "structural_analysis": dict(self.trace) if self.structural_analysis else None,
            "solution": self.solution.to_dict() if self.solution else None,
            "ast": self.ast.to_dict() if self.ast else None,
            "diff": self.diff.to_dict() if self.diff else None,
            "metrics": dict(self.metrics),
            "errors": list(self.errors),
            "arbitration": self.arbitration.to_dict() if self.arbitration else None,
            "trace": dict(self.trace),
        }


def compare_legacy_structural(
    legacy_questions: Sequence[Mapping[str, Any]],
    structural_questions: Sequence[Mapping[str, Any]],
    *,
    answer_key: Any = None,
    image_ownership: Optional[Mapping[str, Any] | Sequence[Any]] = None,
) -> StructuralDiff:
    legacy = list(legacy_questions or [])
    structural = list(structural_questions or [])
    answer = AnswerKeyEvidence.from_value(answer_key)
    metrics = {
        "question_count": _metric(len(legacy), len(structural)),
        "question_order": _metric(_numbers(legacy), _numbers(structural)),
        "printed_numbers": _metric(_numbers_set(legacy), _numbers_set(structural)),
        "option_count": _metric(_option_counts(legacy), _option_counts(structural)),
        "option_keys": _metric(_option_keys(legacy), _option_keys(structural)),
        "image_count": _metric(_image_counts(legacy), _image_counts(structural)),
        "image_ownership": _metric(
            _image_counts(legacy), _ownership_counts(structural, image_ownership)
        ),
        "subject": _metric(_subjects(legacy), _subjects(structural)),
        "answer_key_coverage": _metric(
            _answer_coverage(legacy, answer), _answer_coverage(structural, answer)
        ),
    }
    return StructuralDiff(
        changed_fields=[name for name, metric in metrics.items() if not metric.equal],
        **metrics,
    )


class StructuralShadowRunner:
    """Run the structural observer while preserving the legacy result."""

    def __init__(
        self,
        *,
        mode: PipelineMode | str | None = None,
        solver: Optional[ConstraintSolver] = None,
        ast_builder: Optional[QuestionASTBuilder] = None,
        arbiter: Optional[ResultArbiter] = None,
        rollout_config: Optional[RolloutConfig] = None,
        candidate_classifier: Any = None,
    ) -> None:
        self.mode = get_pipeline_mode(mode.value if isinstance(mode, PipelineMode) else mode)
        self.solver = solver or ConstraintSolver()
        self.ast_builder = ast_builder or QuestionASTBuilder()
        self.arbiter = arbiter or ResultArbiter()
        self.rollout_config = rollout_config
        self.candidate_classifier = candidate_classifier

    def run(
        self,
        pdf: Any,
        *,
        legacy_result: Optional[Sequence[Mapping[str, Any]]] = None,
        legacy_context: Optional[LegacyParserContext] = None,
        answer_key: Any = None,
        source: Optional[str] = None,
        exam_id: Optional[int | str] = None,
        extract_images: bool = True,
        legacy_parser: Optional[Callable[[Any], Sequence[Mapping[str, Any]]]] = None,
        ml_enabled: Optional[bool] = None,
    ) -> StructuralShadowResult:
        context = legacy_context or LegacyParserContext(
            exam_id=int(exam_id) if str(exam_id).isdigit() else None,
            extract_images=extract_images,
        )
        if legacy_result is None:
            try:
                if legacy_parser is not None:
                    legacy_value = legacy_parser(pdf)
                else:
                    from services.pdf_pipeline import parse_exam_document

                    legacy_value = parse_exam_document(
                        pdf,
                        exam_id=context.exam_id,
                        extract_images=extract_images,
                    )
                legacy_result = list(legacy_value or [])
            except Exception:
                legacy_result = []
        else:
            legacy_result = [dict(item) for item in legacy_result]

        if self.mode is PipelineMode.LEGACY_ONLY:
            return StructuralShadowResult(
                mode=self.mode,
                legacy_result=list(legacy_result),
                metrics={"mode": self.mode.value, "structural_executed": False, "sampled": False},
            )

        rollout = self.rollout_config or RolloutConfig.from_env(mode=self.mode)
        sampled = exam_id is None or should_sample_structural(
            exam_id,
            percent=rollout.rollout_percent,
        )
        if not sampled:
            return StructuralShadowResult(
                mode=self.mode,
                legacy_result=list(legacy_result),
                metrics={
                    "mode": self.mode.value,
                    "structural_executed": False,
                    "sampled": False,
                    "rollout_percent": rollout.rollout_percent,
                },
            )

        resolved_ml_enabled = structural_ml_enabled(ml_enabled)
        try:
            from .pipeline import analyze_structure, extract_physical_document

            document = extract_physical_document(
                pdf,
                source=source,
                exam_id=exam_id,
                extractor=PhysicalExtractor(include_images=extract_images),
            )
            metadata = dict(context.metadata or {})
            if context.declared_banca:
                metadata["declared_banca"] = context.declared_banca
            analysis = analyze_structure(
                document,
                legacy_metadata=metadata,
                candidate_classifier=self.candidate_classifier,
                ml_enabled=resolved_ml_enabled,
            )
            solution = self.solver.solve(
                analysis,
                document=document,
                answer_key=answer_key,
                legacy_questions=legacy_result,
            )
            ast = self.ast_builder.build(
                document,
                analysis,
                solution,
                answer_key=answer_key,
                legacy_questions=legacy_result,
            )
            structural_result = render_legacy_document(ast)
            diff = compare_legacy_structural(
                legacy_result,
                structural_result,
                answer_key=answer_key,
                image_ownership={
                    question.printed_number or "": len(question.figures)
                    for question in ast.questions
                },
            )
            trace = build_structural_trace(analysis, solution)
            arbitration = None
            if self.mode in {PipelineMode.STRUCTURAL_PREFERRED, PipelineMode.STRUCTURAL_ONLY}:
                arbitration = self.arbiter.arbitrate(
                    legacy_result=legacy_result,
                    structural_result=structural_result,
                    structural_confidence=solution.confidence,
                    diff=diff,
                )
            return StructuralShadowResult(
                mode=self.mode,
                legacy_result=list(legacy_result),
                structural_result=structural_result,
                structural_analysis=analysis,
                solution=solution,
                ast=ast,
                diff=diff,
                metrics={
                    "mode": self.mode.value,
                    "structural_executed": True,
                    "sampled": True,
                    "structural_question_count": len(structural_result),
                    "legacy_question_count": len(legacy_result),
                    "confidence": solution.confidence.to_dict(),
                    "diff_fields": list(diff.changed_fields),
                    "recovered_question_count": len(solution.recovered_candidates),
                    "ml_enabled": resolved_ml_enabled,
                },
                arbitration=arbitration,
                trace=trace,
            )
        except Exception as exc:
            arbitration = None
            if self.mode in {PipelineMode.STRUCTURAL_PREFERRED, PipelineMode.STRUCTURAL_ONLY}:
                arbitration = self.arbiter.arbitrate(
                    legacy_result=legacy_result,
                    structural_result=None,
                    structural_confidence=0.0,
                    structural_failed=True,
                )
            return StructuralShadowResult(
                mode=self.mode,
                legacy_result=list(legacy_result),
                metrics={
                    "mode": self.mode.value,
                    "structural_executed": False,
                    "sampled": True,
                    "structural_failure": type(exc).__name__,
                },
                errors=[f"structural_shadow_failure:{type(exc).__name__}"],
                arbitration=arbitration,
            )


def run_structural_shadow(pdf: Any, **kwargs: Any) -> StructuralShadowResult:
    return StructuralShadowRunner(
        mode=kwargs.pop("mode", None),
        arbiter=kwargs.pop("arbiter", None),
        rollout_config=kwargs.pop("rollout_config", None),
        candidate_classifier=kwargs.pop("candidate_classifier", None),
    ).run(pdf, **kwargs)


parse_exam_document_with_mode = run_structural_shadow
run_pipeline_with_mode = run_structural_shadow


def _metric(legacy: Any, structural: Any) -> StructuralMetric:
    delta = structural - legacy if isinstance(legacy, (int, float)) and isinstance(structural, (int, float)) else None
    if isinstance(legacy, list) and isinstance(structural, list):
        delta = len(structural) - len(legacy)
    return StructuralMetric(legacy=legacy, structural=structural, equal=legacy == structural, delta=delta)


def _numbers(questions: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(item.get("numero_questao") or item.get("printed_number") or "") for item in questions]


def _numbers_set(questions: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted(set(_numbers(questions)), key=_number_sort_key)


def _option_counts(questions: Sequence[Mapping[str, Any]]) -> list[int]:
    return [len(item.get("opcoes") or item.get("options") or {}) for item in questions]


def _option_keys(questions: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    return [
        sorted(str(key).upper() for key in (item.get("opcoes") or item.get("options") or {}))
        for item in questions
    ]


def _image_counts(questions: Sequence[Mapping[str, Any]]) -> list[int]:
    return [len(item.get("images") or []) for item in questions]


def _ownership_counts(questions: Sequence[Mapping[str, Any]], ownership: Any) -> list[int]:
    if ownership is None:
        return _image_counts(questions)
    if isinstance(ownership, Mapping):
        return [int(ownership.get(str(item.get("numero_questao") or ""), 0)) for item in questions]
    return _image_counts(questions)


def _subjects(questions: Sequence[Mapping[str, Any]]) -> list[str]:
    return [_normalize_text(item.get("disciplina") or item.get("subject") or "") for item in questions]


def _answer_coverage(questions: Sequence[Mapping[str, Any]], answer: AnswerKeyEvidence) -> Optional[float]:
    if not answer.available:
        return None
    numbers = {
        int(str(item.get("numero_questao") or item.get("printed_number")))
        for item in questions
        if str(item.get("numero_questao") or item.get("printed_number") or "").isdigit()
    }
    return len(numbers & set(answer.answers)) / max(answer.expected_count or len(answer.answers), 1)


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _number_sort_key(value: str) -> tuple[int, str]:
    match = re.match(r"^\s*(\d+)", value)
    return (int(match.group(1)), value) if match else (10**9, value)
