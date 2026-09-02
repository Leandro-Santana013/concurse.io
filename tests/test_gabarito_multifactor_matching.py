import json

import fitz

from services.gabarito import (
    build_exam_answer_key_profile,
    match_gabarito_from_pdf,
    merge_exam_with_gabarito,
)


ANSWERS_A = {number: "ABCD"[(number - 1) % 4] for number in range(1, 31)}
ANSWERS_B = {number: "DCBA"[(number - 1) % 4] for number in range(1, 31)}


def _questions(count=30, labels="ABCD", subjects=None):
    subjects = subjects or ["Conhecimentos Especificos"] * count
    return [
        {
            "numero_questao": str(number),
            "enunciado": f"Questao {number}",
            "opcoes": {label: f"Opcao {label}" for label in labels},
            "disciplina": subjects[number - 1],
        }
        for number in range(1, count + 1)
    ]


def _add_answer_page(doc, metadata_lines, answers):
    page = doc.new_page()
    lines = ["GABARITO", *metadata_lines]
    for number, answer in sorted(answers.items()):
        lines.extend([str(number), answer])
    page.insert_text((50, 30), "\n".join(lines), fontsize=7)


def _exam_doc(*lines):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "\n".join(lines), fontsize=9)
    return doc


def test_code_range_beats_same_schooling_and_generic_title():
    profile = build_exam_answer_key_profile(
        None,
        _questions(),
        title="AGENTE DE DESENVOLVIMENTO URBANO E RURAL II - COVEIRO - PREF. UBERABA/MG 2016",
        code_ranges=[(133, 139)],
    )
    answer_doc = fitz.open()
    _add_answer_page(
        answer_doc,
        ["FUNDAMENTAL INCOMPLETO (129 a 132)", "AGENTE SOCIAL"],
        ANSWERS_B,
    )
    _add_answer_page(
        answer_doc,
        ["FUNDAMENTAL INCOMPLETO (133 a 139)", "COVEIRO"],
        ANSWERS_A,
    )

    result = match_gabarito_from_pdf(answer_doc, profile, source_relation="paired")

    assert result.accepted is True
    assert result.answers == ANSWERS_A
    assert result.candidate_page == 2
    assert "code_range_exact" in result.reasons
    answer_doc.close()


def test_exact_question_count_and_option_alphabet_are_hard_constraints():
    profile = build_exam_answer_key_profile(None, _questions(), title="COVEIRO - PREF. UBERABA/MG 2016")

    count_doc = fitz.open()
    forty_answers = {number: "A" for number in range(1, 41)}
    _add_answer_page(count_doc, ["COVEIRO", "PREFEITURA DE UBERABA"], forty_answers)
    count_result = match_gabarito_from_pdf(count_doc, profile, source_relation="paired")
    assert count_result.accepted is False
    assert "question_count_mismatch" in count_result.conflicts
    count_doc.close()

    alphabet_doc = fitz.open()
    invalid_alphabet = dict(ANSWERS_A)
    _add_answer_page(
        alphabet_doc,
        ["COVEIRO", "PREFEITURA DE UBERABA", "5 alternativas"],
        invalid_alphabet,
    )
    alphabet_result = match_gabarito_from_pdf(alphabet_doc, profile, source_relation="paired")
    assert alphabet_result.accepted is False
    assert "option_alphabet_mismatch" in alphabet_result.conflicts
    alphabet_doc.close()


def test_type_version_color_cargo_edital_date_and_shift_select_exact_candidate():
    exam_doc = _exam_doc(
        "TIPO 2",
        "VERSAO B",
        "CADERNO AZUL",
        "CODIGO DO CARGO: COV-02",
        "EDITAL 01/2016",
        "DATA DA PROVA: 20/03/2016",
        "TARDE",
    )
    profile = build_exam_answer_key_profile(
        exam_doc,
        _questions(),
        title="COVEIRO - PREF. UBERABA/MG 2016",
    )
    answer_doc = fitz.open()
    shared = [
        "COVEIRO",
        "PREFEITURA DE UBERABA",
        "VERSAO B",
        "CADERNO AZUL",
        "EDITAL 01/2016",
        "DATA DA PROVA: 20/03/2016",
        "TARDE",
    ]
    _add_answer_page(answer_doc, ["TIPO 1", "CODIGO DO CARGO: COV-01", *shared], ANSWERS_B)
    _add_answer_page(answer_doc, ["TIPO 2", "CODIGO DO CARGO: COV-02", *shared], ANSWERS_A)

    result = match_gabarito_from_pdf(answer_doc, profile, source_relation="paired")

    assert result.accepted is True
    assert result.answers == ANSWERS_A
    assert result.candidate_page == 2
    for reason in (
        "exam_type_exact",
        "version_exact",
        "booklet_color_exact",
        "cargo_code_exact",
        "edital_exact",
        "exam_date_exact",
        "shift_exact",
    ):
        assert reason in result.reasons
    exam_doc.close()
    answer_doc.close()


def test_full_cargo_and_locality_prevent_match_on_generic_agente_word():
    profile = build_exam_answer_key_profile(
        None,
        _questions(),
        title="AGENTE DE DESENVOLVIMENTO URBANO E RURAL II - COVEIRO - PREF. UBERABA/MG 2016",
    )
    answer_doc = fitz.open()
    _add_answer_page(
        answer_doc,
        ["AGENTE SOCIAL", "PREFEITURA DE UBERLANDIA"],
        ANSWERS_B,
    )
    _add_answer_page(
        answer_doc,
        [
            "AGENTE DE DESENVOLVIMENTO URBANO E RURAL II - COVEIRO",
            "PREFEITURA DE UBERABA",
        ],
        ANSWERS_A,
    )

    result = match_gabarito_from_pdf(answer_doc, profile, source_relation="paired")

    assert result.accepted is True
    assert result.answers == ANSWERS_A
    assert "full_cargo_match" in result.reasons
    assert "locality_exact" in result.reasons
    answer_doc.close()


def test_subject_distribution_conflict_rejects_candidate():
    subjects = ["Lingua Portuguesa"] * 10 + ["Conhecimentos Especificos"] * 20
    profile = build_exam_answer_key_profile(None, _questions(subjects=subjects), title="COVEIRO")
    answer_doc = fitz.open()
    _add_answer_page(
        answer_doc,
        [
            "COVEIRO",
            "Lingua Portuguesa: 12 questoes",
            "Conhecimentos Especificos: 18 questoes",
        ],
        ANSWERS_A,
    )

    result = match_gabarito_from_pdf(answer_doc, profile, source_relation="paired")

    assert result.accepted is False
    assert "subject_distribution_mismatch" in result.conflicts
    answer_doc.close()


def test_definitive_key_is_preferred_and_compatible_errata_is_applied():
    profile = build_exam_answer_key_profile(
        None,
        _questions(),
        title="COVEIRO - PREF. UBERABA/MG 2016",
        code_ranges=[(133, 139)],
    )
    answer_doc = fitz.open()
    _add_answer_page(
        answer_doc,
        ["GABARITO PRELIMINAR", "CODIGOS: 133 a 139", "COVEIRO"],
        ANSWERS_B,
    )
    _add_answer_page(
        answer_doc,
        ["GABARITO DEFINITIVO", "CODIGOS: 133 a 139", "COVEIRO"],
        ANSWERS_A,
    )
    errata_page = answer_doc.new_page()
    errata_page.insert_text(
        (50, 50),
        "ERRATA DO GABARITO\nCODIGOS: 133 a 139\nQuestao 5: B",
        fontsize=9,
    )

    result = match_gabarito_from_pdf(answer_doc, profile, source_relation="paired")

    assert result.accepted is True
    assert result.candidate_page == 2
    assert result.answers[5] == "B"
    assert result.errata_pages == [3]
    assert "definitive_answer_key" in result.reasons
    assert "compatible_errata_applied" in result.reasons
    answer_doc.close()


def test_strict_merge_never_applies_partial_or_shifted_key():
    questions = _questions()
    shifted_answers = {number: "A" for number in range(2, 32)}

    updated, stats = merge_exam_with_gabarito(questions, shifted_answers, strict=True)

    assert stats["has_official_answers"] is False
    assert stats["coverage_pct"] == 0.0
    assert "question_sequence_mismatch" in stats["integrity_conflicts"]
    assert all(question["has_official_answer"] is False for question in updated)


def test_match_decision_serializes_all_audit_factors():
    profile = build_exam_answer_key_profile(None, _questions(), title="COVEIRO")
    answer_doc = fitz.open()
    _add_answer_page(answer_doc, ["COVEIRO"], ANSWERS_A)

    result = match_gabarito_from_pdf(answer_doc, profile, source_relation="paired")
    audit = json.loads(result.to_audit_json())

    assert audit["accepted"] is True
    assert audit["answer_count"] == 30
    assert audit["profile"]["question_count"] == 30
    assert "question_count_exact" in audit["reasons"]
    assert "question_sequence_exact" in audit["reasons"]
    answer_doc.close()
