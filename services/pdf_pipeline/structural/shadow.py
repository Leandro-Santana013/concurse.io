"""STRUCTURAL_SHADOW orchestration and semantic diff metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Any, Callable, Mapping, Optional, Sequence

from ..legacy.adapter import HybridLegacyParserAdapter, LegacyParserAdapter, LegacyParserContext
from .adapters import LegacyAdapterRoles, build_legacy_adapter_roles
from .arbiter import ArbitrationDecision, ResultArbiter
from .config import PipelineMode, get_pipeline_mode
from .layout_families import LayoutFamilyAssignment, LayoutFamilyModel
from .ml import ModelRegistry
from .model import DocumentModel
from .question_ast import ExamDocumentNode, QuestionASTBuilder
from .renderer import render_legacy_document
from .rollout import RolloutConfig, structural_ml_enabled
from .solver import AnswerKeyEvidence, ConstraintSolver, SequenceSolution, SolverConfig
from .trace import build_structural_trace


@dataclass
class StructuralMetric:
    """One semantic legacy-vs-structural comparison."""

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
    """Diff fields required by the Phase-4 shadow gate.

    Values intentionally compare structure (numbers, option keys, counts and
    normalized subjects), never full statement strings.
    """

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
            "question_count": self.question_count.to_dict(),
            "question_order": self.question_order.to_dict(),
            "printed_numbers": self.printed_numbers.to_dict(),
            "option_count": self.option_count.to_dict(),
            "option_keys": self.option_keys.to_dict(),
            "image_count": self.image_count.to_dict(),
            "image_ownership": self.image_ownership.to_dict(),
            "subject": self.subject.to_dict(),
            "answer_key_coverage": self.answer_key_coverage.to_dict(),
            "changed_fields": list(self.changed_fields),
            "has_differences": self.has_differences,
            "difference_count": self.difference_count,
        }


@dataclass
class StructuralShadowResult:
    """Result of shadow execution; ``user_result`` always remains legacy."""

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
    layout_family: Optional[LayoutFamilyAssignment] = None
    legacy_adapter_used: Optional[str] = None
    ml_models_used: list[str] = field(default_factory=list)

    @property
    def user_result(self) -> list[dict[str, Any]]:
        """The only result visible to the current application contract."""

        if (
            self.mode in {PipelineMode.STRUCTURAL_PREFERRED, PipelineMode.STRUCTURAL_ONLY}
            and self.arbitration is not None
            and self.arbitration.status.value == "STRUCTURAL"
            and self.arbitration.result is not None
        ):
            return list(self.arbitration.result)
        return self.legacy_result

    @property
    def structural_failed(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "legacy_result": self.legacy_result,
            "structural_result": self.structural_result,
            "structural_analysis": self.structural_analysis.trace() if self.structural_analysis else None,
            "solution": self.solution.to_dict() if self.solution else None,
            "ast": self.ast.to_dict() if self.ast else None,
            "diff": self.diff.to_dict() if self.diff else None,
            "metrics": self.metrics,
            "errors": list(self.errors),
            "arbitration": self.arbitration.to_dict() if self.arbitration else None,
            "trace": dict(self.trace),
            "layout_family": self.layout_family.to_dict() if self.layout_family else None,
            "legacy_adapter_used": self.legacy_adapter_used,
            "ml_models_used": list(self.ml_models_used),
        }


def compare_legacy_structural(
    legacy_questions: Sequence[Mapping[str, Any]],
    structural_questions: Sequence[Mapping[str, Any]],
    *,
    answer_key: Any = None,
    image_ownership: Optional[Mapping[str, Any] | Sequence[Any]] = None,
) -> StructuralDiff:
    """Compare only semantic fields that affect the current application."""

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
            _image_counts(legacy),
            _ownership_counts(structural, image_ownership),
        ),
        "subject": _metric(_subjects(legacy), _subjects(structural)),
        "answer_key_coverage": _metric(
            _answer_coverage(legacy, answer),
            _answer_coverage(structural, answer),
        ),
    }
    changed = [name for name, metric in metrics.items() if not metric.equal]
    return StructuralDiff(changed_fields=changed, **metrics)


class StructuralShadowRunner:
    """Run structural work as a non-blocking observer of the legacy parser."""

    def __init__(
        self,
        *,
        mode: PipelineMode | str | None = None,
        solver: Optional[ConstraintSolver] = None,
        ast_builder: Optional[QuestionASTBuilder] = None,
        legacy_adapter: Optional[LegacyParserAdapter] = None,
        arbiter: Optional[ResultArbiter] = None,
        rollout_config: Optional[RolloutConfig] = None,
        candidate_classifier: Any = None,
        layout_family_model: Optional[LayoutFamilyModel] = None,
    ) -> None:
        self.mode = get_pipeline_mode(mode.value if isinstance(mode, PipelineMode) else mode)
        self.solver = solver or ConstraintSolver()
        self.ast_builder = ast_builder or QuestionASTBuilder()
        self.legacy_adapter = legacy_adapter or HybridLegacyParserAdapter()
        self.arbiter = arbiter or ResultArbiter()
        self.rollout_config = rollout_config
        self.candidate_classifier = candidate_classifier
        self.layout_family_model = layout_family_model

    def run(
        self,
        pdf: Any,
        *,
        legacy_result: Optional[Sequence[Mapping[str, Any]]] = None,
        legacy_context: Optional[LegacyParserContext] = None,
        answer_key: Any = None,
        answer_key_pdf: Any = None,
        source: Optional[str] = None,
        exam_id: Optional[int | str] = None,
        extract_images: bool = True,
        legacy_parser: Optional[Callable[[Any], Sequence[Mapping[str, Any]]]] = None,
        ml_enabled: Optional[bool] = None,
        layout_family_model: Optional[LayoutFamilyModel] = None,
    ) -> StructuralShadowResult:
        context = legacy_context or LegacyParserContext(
            exam_id=int(exam_id) if str(exam_id).isdigit() else None,
            extract_images=extract_images,
        )
        if legacy_result is None:
            if legacy_parser is not None:
                legacy_value = legacy_parser(pdf)
            else:
                legacy_value = self.legacy_adapter.parse(pdf, context)
            legacy_result = list(legacy_value or [])
        else:
            legacy_result = [dict(item) for item in legacy_result]

        if self.mode is PipelineMode.LEGACY_ONLY:
            return StructuralShadowResult(
                mode=self.mode,
                legacy_result=list(legacy_result),
                metrics={"mode": self.mode.value, "structural_executed": False},
                legacy_adapter_used=getattr(self.legacy_adapter, "name", None),
            )

        resolved_rollout = self.rollout_config or RolloutConfig.from_env(mode=self.mode)
        resolved_ml_enabled = structural_ml_enabled(ml_enabled) if ml_enabled is not None else resolved_rollout.ml.enabled
        resolved_layout_model = layout_family_model or self.layout_family_model
        classifier = self.candidate_classifier
        ml_models_used: list[str] = []
        preflight_warnings: list[str] = []
        if resolved_ml_enabled and classifier is None and resolved_rollout.ml.registry_path:
            try:
                classifier = ModelRegistry.load(
                    resolved_rollout.ml.registry_path,
                    runtime_feature_schema=resolved_rollout.ml.feature_schema_version,
                ).load_candidate_classifier(name=resolved_rollout.ml.model_name)
                ml_models_used.append(getattr(classifier, "model_version", resolved_rollout.ml.model_name))
            except Exception as exc:
                preflight_warnings.append(f"ml_model_load_failed:{type(exc).__name__}")
        elif resolved_ml_enabled and classifier is not None:
            ml_models_used.append(getattr(classifier, "model_version", "candidate-classifier"))
        try:
            resolved_answer_key = _resolve_answer_key(answer_key, answer_key_pdf)
            from .pipeline import analyze_structure, extract_physical_document

            document = extract_physical_document(pdf, source=source)
            roles = build_legacy_adapter_roles(
                self.legacy_adapter,
                document=document,
                context=context,
            )
            analysis = analyze_structure(
                document,
                legacy_metadata={
                    **dict(context.metadata),
                    "declared_banca": context.declared_banca,
                    "legacy_adapter": getattr(self.legacy_adapter, "name", None),
                },
                candidate_classifier=classifier,
                ml_enabled=resolved_ml_enabled,
                legacy_evidence_provider=roles.evidence,
            )
            solution = self.solver.solve(
                analysis,
                document=document,
                answer_key=resolved_answer_key,
                legacy_questions=legacy_result,
                legacy_recovery_provider=roles.recovery,
            )
            ast = self.ast_builder.build(
                document,
                analysis,
                solution,
                answer_key=resolved_answer_key,
                legacy_questions=legacy_result,
            )
            structural_result = render_legacy_document(ast)
            assignment = None
            if resolved_layout_model is not None:
                assignment = resolved_layout_model.predict(
                    analysis.document_profile,
                    document_id=str(exam_id) if exam_id is not None else source,
                )
            trace = build_structural_trace(
                analysis,
                solution,
                layout_family=assignment,
                legacy_adapter_used=getattr(self.legacy_adapter, "name", None),
                ml_models_used=ml_models_used,
                warnings=preflight_warnings,
            )
            diff = compare_legacy_structural(
                legacy_result,
                structural_result,
                answer_key=resolved_answer_key,
                image_ownership={
                    question.printed_number or "": len(question.figures)
                    for question in ast.questions
                },
            )
            metrics = {
                "mode": self.mode.value,
                "structural_executed": True,
                "structural_question_count": len(structural_result),
                "legacy_question_count": len(legacy_result),
                "confidence": solution.confidence.to_dict(),
                "diff_fields": list(diff.changed_fields),
                "recovered_question_count": len(solution.recovered_candidates),
                "layout_family": assignment.to_dict() if assignment else None,
                "ml_enabled": resolved_ml_enabled,
                "ml_models_used": list(ml_models_used),
                "warnings": list(preflight_warnings),
            }
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
                metrics=metrics,
                arbitration=arbitration,
                trace=trace,
                layout_family=assignment,
                legacy_adapter_used=getattr(self.legacy_adapter, "name", None),
                ml_models_used=ml_models_used,
            )
        except Exception as exc:
            # Shadow failures are diagnostics only.  The legacy result is
            # returned untouched, including when physical extraction fails.
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
                    "structural_failure": type(exc).__name__,
                },
                errors=[f"structural_shadow_failure:{type(exc).__name__}:{exc}"],
                arbitration=arbitration,
                legacy_adapter_used=getattr(self.legacy_adapter, "name", None),
            )


def run_structural_shadow(
    pdf: Any,
    *,
    mode: PipelineMode | str | None = None,
    legacy_result: Optional[Sequence[Mapping[str, Any]]] = None,
    legacy_context: Optional[LegacyParserContext] = None,
    answer_key: Any = None,
    answer_key_pdf: Any = None,
    source: Optional[str] = None,
    exam_id: Optional[int | str] = None,
    extract_images: bool = True,
    legacy_parser: Optional[Callable[[Any], Sequence[Mapping[str, Any]]]] = None,
    arbiter: Optional[ResultArbiter] = None,
    rollout_config: Optional[RolloutConfig] = None,
    candidate_classifier: Any = None,
    layout_family_model: Optional[LayoutFamilyModel] = None,
    ml_enabled: Optional[bool] = None,
) -> StructuralShadowResult:
    return StructuralShadowRunner(
        mode=mode,
        arbiter=arbiter,
        rollout_config=rollout_config,
        candidate_classifier=candidate_classifier,
        layout_family_model=layout_family_model,
    ).run(
        pdf,
        legacy_result=legacy_result,
        legacy_context=legacy_context,
        answer_key=answer_key,
        answer_key_pdf=answer_key_pdf,
        source=source,
        exam_id=exam_id,
        extract_images=extract_images,
        legacy_parser=legacy_parser,
        ml_enabled=ml_enabled,
        layout_family_model=layout_family_model,
    )


def parse_exam_document_with_mode(
    pdf: Any,
    *,
    mode: PipelineMode | str | None = None,
    legacy_context: Optional[LegacyParserContext] = None,
    answer_key: Any = None,
    answer_key_pdf: Any = None,
    source: Optional[str] = None,
    exam_id: Optional[int | str] = None,
    extract_images: bool = True,
    arbiter: Optional[ResultArbiter] = None,
    rollout_config: Optional[RolloutConfig] = None,
    candidate_classifier: Any = None,
    layout_family_model: Optional[LayoutFamilyModel] = None,
    ml_enabled: Optional[bool] = None,
) -> StructuralShadowResult:
    """Compatibility entry point for legacy, shadow and preferred rollout.

    Existing callers that still need the list can read ``result.user_result``;
    ``LEGACY_ONLY`` remains the default and preferred modes are gated by the
    ``ResultArbiter`` with legacy fallback.
    """

    return run_structural_shadow(
        pdf,
        mode=mode,
        legacy_context=legacy_context,
        answer_key=answer_key,
        answer_key_pdf=answer_key_pdf,
        source=source,
        exam_id=exam_id,
        extract_images=extract_images,
        arbiter=arbiter,
        rollout_config=rollout_config,
        candidate_classifier=candidate_classifier,
        layout_family_model=layout_family_model,
        ml_enabled=ml_enabled,
    )


run_pipeline_with_mode = parse_exam_document_with_mode


def _metric(legacy: Any, structural: Any) -> StructuralMetric:
    equal = legacy == structural
    delta: Any = None
    if isinstance(legacy, (int, float)) and isinstance(structural, (int, float)):
        delta = structural - legacy
    elif isinstance(legacy, list) and isinstance(structural, list):
        delta = len(structural) - len(legacy)
    return StructuralMetric(legacy=legacy, structural=structural, equal=equal, delta=delta)


def _numbers(questions: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(item.get("numero_questao") or item.get("printed_number") or "") for item in questions]


def _numbers_set(questions: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted(set(_numbers(questions)), key=_number_sort_key)


def _option_counts(questions: Sequence[Mapping[str, Any]]) -> list[int]:
    return [len(item.get("opcoes") or item.get("options") or {}) for item in questions]


def _option_keys(questions: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    return [sorted(str(key).upper() for key in (item.get("opcoes") or item.get("options") or {})) for item in questions]


def _image_counts(questions: Sequence[Mapping[str, Any]]) -> list[int]:
    return [len(item.get("images") or []) for item in questions]


def _ownership_counts(
    questions: Sequence[Mapping[str, Any]],
    ownership: Optional[Mapping[str, Any] | Sequence[Any]],
) -> list[int]:
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


def _resolve_answer_key(answer_key: Any, answer_key_pdf: Any) -> Any:
    if answer_key is not None:
        return answer_key
    if answer_key_pdf is None:
        return None
    try:
        from services.gabarito import parse_gabarito_from_pdf

        return parse_gabarito_from_pdf(answer_key_pdf)
    except Exception:
        return None


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _number_sort_key(value: str) -> tuple[int, str]:
    match = re.match(r"^\s*(\d+)", value)
    return (int(match.group(1)), value) if match else (10**9, value)
