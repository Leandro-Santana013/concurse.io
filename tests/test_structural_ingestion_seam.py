import io
import json

import fitz

from services.pdf_pipeline.structural import (
    ArbitrationStatus,
    ArbiterConfig,
    PipelineMode,
    ResultArbiter,
    StructuralRolloutOutcome,
    StructuralShadowResult,
    merge_structural_questions,
    run_structural_rollout,
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


def test_legacy_only_seam_is_reversible_and_does_not_write_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("STRUCTURAL_TRACE_DIR", str(tmp_path))

    outcome = run_structural_rollout(
        b"not a pdf",
        legacy_questions=LEGACY,
        answer_key={1: "A"},
        exam_id=72,
        mode=PipelineMode.LEGACY_ONLY,
    )

    assert outcome.mode is PipelineMode.LEGACY_ONLY
    assert outcome.promoted is False
    assert outcome.trace_path is None
    assert list(tmp_path.iterdir()) == []


def test_shadow_trace_is_atomic_redacted_and_never_contains_user_content(tmp_path, monkeypatch):
    monkeypatch.setenv("STRUCTURAL_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("STRUCTURAL_ROLLOUT_PERCENT", "100")

    outcome = run_structural_rollout(
        _pdf_bytes(),
        legacy_questions=LEGACY,
        answer_key={1: "A"},
        exam_id=72,
        mode=PipelineMode.STRUCTURAL_SHADOW,
    )

    assert outcome.result is not None
    assert outcome.promoted is False
    assert outcome.trace_path is not None
    trace_path = tmp_path / "exam-72.json"
    assert trace_path.is_file()
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "Conteúdo legado privado" not in serialized
    assert "Enunciado privado" not in serialized
    assert "uma" not in serialized
    assert payload["schema_version"] == 1


def test_quarantine_preserves_legacy_and_cannot_be_promoted():
    structural = [{**LEGACY[0], "opcoes": {"A": "uma", "B": "duas"}}]
    decision = ResultArbiter(ArbiterConfig()).arbitrate(
        legacy_result=LEGACY,
        structural_result=structural,
        structural_confidence=0.95,
        diff={"has_differences": True, "changed_fields": ["option_count"]},
    )
    result = StructuralShadowResult(
        mode=PipelineMode.STRUCTURAL_PREFERRED,
        legacy_result=LEGACY,
        structural_result=structural,
        arbitration=decision,
    )
    outcome = StructuralRolloutOutcome(
        mode=PipelineMode.STRUCTURAL_PREFERRED,
        result=result,
    )

    assert decision.status is ArbitrationStatus.QUARANTINE
    assert outcome.quarantined is True
    assert outcome.promoted is False
    assert outcome.selected_result == LEGACY
    assert result.user_result == LEGACY


def test_merge_never_turns_missing_answer_into_a_default():
    structural = [{
        "numero_questao": "1",
        "enunciado": "novo enunciado",
        "opcoes": {"A": "uma", "B": "duas"},
        "resposta": "",
    }]

    merged = merge_structural_questions(LEGACY, structural)

    assert merged[0]["resposta"] == "A"
    assert merged[0]["enunciado"] == "novo enunciado"
