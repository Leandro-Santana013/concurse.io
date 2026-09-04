import fitz

from services.gabarito import (
    AnswerKeyMatchResult,
    build_exam_answer_key_profile,
    has_complete_official_answer_key,
    match_gabarito_from_pdf,
)


def _pdf_with_text(text: str) -> fitz.Document:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_textbox((30, 30, 565, 810), text, fontsize=8)
    return document


def _answer_key_block(cargo: str, answers: list[str]) -> str:
    numbers = "\n".join(str(number) for number in range(1, len(answers) + 1))
    values = "\n".join(answers)
    return f"{cargo} - PROVA TIPO 1\n{numbers}\n{values}\n"


def test_rejected_or_partial_match_cannot_be_saved_as_official():
    profile_pdf = _pdf_with_text("")
    profile = build_exam_answer_key_profile(
        profile_pdf,
        [{"numero_questao": str(number)} for number in range(1, 71)],
        title="prova dataprev",
    )
    profile_pdf.close()
    rejected = AnswerKeyMatchResult(
        profile=profile,
        accepted=False,
        status="rejected",
    )

    assert not has_complete_official_answer_key(
        rejected,
        {"has_official_answers": True, "coverage_pct": 100.0},
        "attached_pdf",
    )
    assert not has_complete_official_answer_key(
        rejected,
        {"has_official_answers": False, "coverage_pct": 0.0},
        "none",
    )


def test_dataprev_cargo_is_inferred_from_exam_header_when_title_is_generic():
    proof = _pdf_with_text(
        "ATI - CONTABILIDADE\nNÍVEL SUPERIOR TIPO 1 - BRANCA\n"
    )
    answer_key = _pdf_with_text(
        _answer_key_block("ATI - ANÁLISE DE NEGÓCIO DE TI", ["A"] * 10)
        + _answer_key_block("ATI - CONTABILIDADE", ["E", "D", "C", "C", "A", "D", "C", "D", "A", "D"])
    )
    questions = [
        {
            "numero_questao": str(number),
            "opcoes": {"A": "", "B": "", "C": "", "D": "", "E": ""},
            "disciplina": "Geral",
        }
        for number in range(1, 11)
    ]

    profile = build_exam_answer_key_profile(
        proof,
        questions,
        title="Nova Prova de Concurso",
    )
    result = match_gabarito_from_pdf(answer_key, profile, source_relation="paired")

    assert result.accepted is True
    assert result.candidate["cargo_text"] == "ATI - CONTABILIDADE"
    assert result.answers[1] == "E"
    assert result.answers[10] == "D"
