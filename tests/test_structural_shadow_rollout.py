import io
import json

import fitz

from services.pdf_pipeline.structural import (
    ArbiterConfig,
    PipelineMode,
    ResultArbiter,
    RolloutConfig,
    StructuralShadowRunner,
    should_sample_structural,
)


LEGACY = [
    {
        "numero_questao": "1",
        "enunciado": "Conteúdo legado privado",
        "opcoes": {"A": "uma"},
        "resposta": "A",
        "disciplina": "Geral",
        "images": None,
    }
]


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((30, 50), "Questão 1", fontname="hebo", fontsize=12)
    page.insert_text((30, 80), "Enunciado privado para o teste.", fontsize=10)
    page.insert_text((30, 120), "A) uma", fontsize=10)
    page.insert_text((30, 145), "B) duas", fontsize=10)
    page.insert_text((30, 170), "C) tres", fontsize=10)
    page.insert_text((30, 195), "D) quatro", fontsize=10)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def test_sampling_is_stable_and_has_immediate_off_switch():
    assert should_sample_structural("72", percent=0.0) is False
    assert should_sample_structural("72", percent=100.0) is True
    assert should_sample_structural("72", percent=37.5) == should_sample_structural("72", percent=37.5)


def test_legacy_only_never_executes_structural_pipeline():
    result = StructuralShadowRunner(mode=PipelineMode.LEGACY_ONLY).run(
        b"not a pdf",
        legacy_result=LEGACY,
    )

    assert result.user_result == LEGACY
    assert result.metrics["structural_executed"] is False
    assert result.metrics["sampled"] is False


def test_shadow_failure_keeps_legacy_and_never_raises():
    result = StructuralShadowRunner(
        mode=PipelineMode.STRUCTURAL_SHADOW,
        rollout_config=RolloutConfig(
            mode=PipelineMode.STRUCTURAL_SHADOW,
            rollout_percent=100.0,
        ),
    ).run(b"not a pdf", legacy_result=LEGACY, exam_id=72)

    assert result.user_result == LEGACY
    assert result.structural_failed is True
    assert result.metrics["structural_failure"]


def test_shadow_valid_run_keeps_legacy_and_redacts_trace_content():
    result = StructuralShadowRunner(
        mode=PipelineMode.STRUCTURAL_SHADOW,
        rollout_config=RolloutConfig(
            mode=PipelineMode.STRUCTURAL_SHADOW,
            rollout_percent=100.0,
        ),
    ).run(_pdf_bytes(), legacy_result=LEGACY, exam_id=72)

    assert result.user_result == LEGACY
    assert result.metrics["structural_executed"] is True
    trace_text = json.dumps(result.trace, ensure_ascii=False)
    assert "Enunciado privado" not in trace_text
    assert "uma" not in trace_text
    assert result.trace["pipeline_version"].endswith("redacted")


def test_preferred_divergence_quarantines_without_dropping_legacy():
    structural = [{**LEGACY[0], "opcoes": {"A": "uma", "B": "duas"}}]
    decision = ResultArbiter(ArbiterConfig()).arbitrate(
        legacy_result=LEGACY,
        structural_result=structural,
        structural_confidence=0.60,
    )

    assert decision.status is not None
    assert decision.status.value == "QUARANTINE"
    assert decision.quarantined is True
    assert decision.selected_result == LEGACY
