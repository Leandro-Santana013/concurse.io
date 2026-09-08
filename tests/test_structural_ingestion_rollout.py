"""Tests for the application seam that connects ingestion to Phase 5."""

import json

from services.pdf_pipeline.structural.arbiter import ArbitrationDecision, ArbitrationStatus
from services.pdf_pipeline.structural.config import PipelineMode
from services.pdf_pipeline.structural.ingestion import (
    merge_structural_questions,
    run_structural_rollout,
)
from services.pdf_pipeline.structural.shadow import StructuralShadowResult


def _result(mode: PipelineMode, decision: ArbitrationDecision | None = None) -> StructuralShadowResult:
    legacy = [
        {
            "numero_questao": "1",
            "enunciado": "legado",
            "opcoes": {"A": "a"},
            "resposta": "B",
            "images": ["legacy-image.png"],
        }
    ]
    structural = [
        {
            "numero_questao": "1",
            "enunciado": "estrutural",
            "opcoes": {"A": "a", "B": "b"},
            "resposta": "B",
            "images": ["source:figure"],
        }
    ]
    return StructuralShadowResult(
        mode=mode,
        legacy_result=legacy,
        structural_result=structural,
        arbitration=decision,
        metrics={"structural_executed": True},
        trace={"pipeline_version": "structural-trace-v1"},
    )


def test_legacy_only_does_not_execute_structural_rollout(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("legacy-only must not invoke structural runner")

    monkeypatch.setattr(
        "services.pdf_pipeline.structural.ingestion.run_structural_shadow",
        fail_if_called,
    )
    outcome = run_structural_rollout(
        "proof.pdf",
        legacy_questions=[],
        answer_key={},
        exam_id=1,
        mode=PipelineMode.LEGACY_ONLY,
    )
    assert outcome.enabled is False
    assert outcome.result is None


def test_shadow_persists_trace_without_promotion(monkeypatch, tmp_path):
    expected = _result(PipelineMode.STRUCTURAL_SHADOW)
    monkeypatch.setattr(
        "services.pdf_pipeline.structural.ingestion.run_structural_shadow",
        lambda *args, **kwargs: expected,
    )
    monkeypatch.setenv("STRUCTURAL_TRACE_DIR", str(tmp_path))

    outcome = run_structural_rollout(
        "proof.pdf",
        legacy_questions=expected.legacy_result,
        answer_key={1: "B"},
        exam_id=42,
        mode=PipelineMode.STRUCTURAL_SHADOW,
    )

    assert outcome.enabled is True
    assert outcome.promoted is False
    trace = json.loads((tmp_path / "exam-42.json").read_text(encoding="utf-8"))
    assert trace["mode"] == "STRUCTURAL_SHADOW"
    assert trace["trace"]["pipeline_version"] == "structural-trace-v1"


def test_preferred_promotion_and_quarantine_are_explicit(monkeypatch):
    promoted = ArbitrationDecision(
        status=ArbitrationStatus.STRUCTURAL,
        result=[{"numero_questao": "1"}],
        source="structural",
        confidence=0.9,
        reason="structural_high",
    )
    quarantined = ArbitrationDecision(
        status=ArbitrationStatus.QUARANTINE,
        result=None,
        source="quarantine",
        confidence=0.6,
        reason="structural_medium_legacy_divergent",
        quarantined=True,
    )
    values = iter([_result(PipelineMode.STRUCTURAL_PREFERRED, promoted), _result(PipelineMode.STRUCTURAL_PREFERRED, quarantined)])
    monkeypatch.setattr(
        "services.pdf_pipeline.structural.ingestion.run_structural_shadow",
        lambda *args, **kwargs: next(values),
    )

    first = run_structural_rollout(
        "proof.pdf", legacy_questions=[], answer_key={}, exam_id=1, mode=PipelineMode.STRUCTURAL_PREFERRED
    )
    second = run_structural_rollout(
        "proof.pdf", legacy_questions=[], answer_key={}, exam_id=2, mode=PipelineMode.STRUCTURAL_PREFERRED
    )
    assert first.promoted is True
    assert second.quarantined is True


def test_merge_keeps_legacy_media_when_renderer_only_has_source_reference():
    legacy = [{
        "numero_questao": "1",
        "enunciado": "legado",
        "opcoes": {"A": "a"},
        "images": ["legacy-image.png"],
        "disciplina": "Direito",
    }]
    structural = [{
        "numero_questao": "1",
        "enunciado": "estrutural",
        "opcoes": {"A": "a", "B": "b"},
        "images": ["source:figure"],
    }]
    merged = merge_structural_questions(legacy, structural)
    assert merged[0]["enunciado"] == "estrutural"
    assert merged[0]["opcoes"] == structural[0]["opcoes"]
    assert merged[0]["images"] == ["legacy-image.png"]
    assert merged[0]["disciplina"] == "Direito"
