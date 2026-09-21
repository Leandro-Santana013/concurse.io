import fitz

from services.gabarito import (
    build_exam_answer_key_profile,
    extract_answer_key_blocks,
    match_gabarito_from_pdf,
    parse_gabarito_from_pdf,
)
from services.gabarito.gabarito_service import extract_all_matrix_gabaritos


RIGHT_TYPE_1 = {number: "ABCDE"[(number - 1) % 5] for number in range(1, 71)}
RIGHT_TYPE_2 = {number: "EDCBA"[(number - 1) % 5] for number in range(1, 71)}


def _add_block(doc, cargo, tipo, answers):
    page = doc.new_page()
    lines = [f"{cargo} - PROVA TIPO {tipo}"]
    lines.extend(str(number) for number in range(1, 71))
    lines.extend(answers[number] for number in range(1, 71))
    page.insert_text((50, 30), "\n".join(lines), fontsize=4)


def _add_plain_block(doc, cargo, answers):
    page = doc.new_page()
    lines = [cargo]
    lines.extend(f"{number} {answers[number]}" for number in range(1, 71))
    page.insert_text((50, 30), "\n".join(lines), fontsize=4)


def _add_transpetro_matrix_fixture(doc, answers):
    common_page = doc.new_page()
    common_lines = ["TRANSPETRO", "GABARITO"]
    common_lines.extend(
        f"{number} - {answers[number]}" for number in range(1, 21)
    )
    common_page.insert_text((40, 30), "\n".join(common_lines), fontsize=8)

    matrix_page = doc.new_page()
    matrix_page.insert_text((470, 30), "TRANSPETRO GABARITO", fontsize=8)
    matrix_page.insert_text((50, 160), "PROVA 1 ADMINISTRACAO NIVEL SUPERIOR", fontsize=8)
    for index, number in enumerate(range(21, 46)):
        matrix_page.insert_text(
            (50, 220 + index * 15),
            f"{number} - {answers[number]}",
            fontsize=8,
        )
    for index, number in enumerate(range(46, 71)):
        matrix_page.insert_text(
            (125, 220 + index * 15),
            f"{number} - {answers[number]}",
            fontsize=8,
        )


def _profile(title="Analista de Tecnologia da Informacao - Comunicacao Social", tipo="1"):
    questions = [
        {
            "numero_questao": str(number),
            "enunciado": f"Questao {number}",
            "opcoes": {label: f"Opcao {label}" for label in "ABCDE"},
            "disciplina": "Geral",
        }
        for number in range(1, 71)
    ]
    exam_doc = fitz.open()
    page = exam_doc.new_page()
    page.insert_text((50, 50), f"ATI - COMUNICACAO SOCIAL\nNIVEL SUPERIOR TIPO {tipo}")
    profile = build_exam_answer_key_profile(exam_doc, questions, title=title)
    exam_doc.close()
    return profile


def test_aggregate_pdf_is_split_into_complete_identity_blocks():
    doc = fitz.open()
    _add_block(doc, "AUXILIAR OU TECNICO DE ENFERMAGEM DO TRABALHO", 1, RIGHT_TYPE_2)
    _add_block(doc, "ATI - COMUNICACAO SOCIAL", 1, RIGHT_TYPE_1)
    _add_block(doc, "ATI - COMUNICACAO SOCIAL", 2, RIGHT_TYPE_2)

    blocks = extract_answer_key_blocks(doc)

    assert len(blocks) == 3
    assert all(block["total_q"] == 70 for block in blocks)
    assert [(block["cargo"], block["tipo"]) for block in blocks] == [
        ("AUXILIAR OU TECNICO DE ENFERMAGEM DO TRABALHO", "1"),
        ("ATI - COMUNICACAO SOCIAL", "1"),
        ("ATI - COMUNICACAO SOCIAL", "2"),
    ]
    doc.close()


def test_aggregate_pdf_selects_cargo_alias_and_type_in_legacy_api():
    doc = fitz.open()
    _add_block(doc, "AUXILIAR OU TECNICO DE ENFERMAGEM DO TRABALHO", 1, RIGHT_TYPE_2)
    _add_block(doc, "ATI - COMUNICACAO SOCIAL", 1, RIGHT_TYPE_1)
    _add_block(doc, "ATI - COMUNICACAO SOCIAL", 2, RIGHT_TYPE_2)

    result = parse_gabarito_from_pdf(
        doc,
        cargo_or_title="Analista de Tecnologia da Informacao - Comunicacao Social",
        tipo="1",
    )

    assert result == RIGHT_TYPE_1
    doc.close()


def test_matcher_does_not_create_partial_matrix_candidates_for_aggregate_pdf():
    doc = fitz.open()
    _add_block(doc, "AUXILIAR OU TECNICO DE ENFERMAGEM DO TRABALHO", 1, RIGHT_TYPE_2)
    _add_block(doc, "ATI - COMUNICACAO SOCIAL", 1, RIGHT_TYPE_1)
    _add_block(doc, "ATI - COMUNICACAO SOCIAL", 2, RIGHT_TYPE_2)

    result = match_gabarito_from_pdf(doc, _profile(), source_relation="paired")

    assert result.accepted is True
    assert result.method == "structured_block"
    assert result.candidate_page == 2
    assert result.candidate["block_index"] == 1
    assert len(result.answers) == 70
    assert result.answers == RIGHT_TYPE_1
    doc.close()


def test_unknown_cargo_fails_closed_when_aggregate_has_many_blocks():
    doc = fitz.open()
    _add_block(doc, "CARGO DIFERENTE", 1, RIGHT_TYPE_1)
    _add_block(doc, "OUTRO CARGO", 1, RIGHT_TYPE_2)

    result = match_gabarito_from_pdf(doc, _profile("Cargo inexistente"), source_relation="paired")

    assert result.accepted is False
    assert result.answers == {}
    assert result.status in {"rejected", "not_found"}
    doc.close()


def test_plain_cargo_blocks_select_the_matching_cargo_without_tipo_header():
    doc = fitz.open()
    _add_plain_block(doc, "AGENTE CULTURAL", RIGHT_TYPE_1)
    _add_plain_block(doc, "ATI - COMUNICACAO SOCIAL", RIGHT_TYPE_2)

    result = match_gabarito_from_pdf(
        doc,
        _profile(),
        source_relation="paired",
    )

    assert result.accepted is True
    assert result.method == "plain_cargo_block"
    assert result.candidate["cargo_text"] == "ATI - COMUNICACAO SOCIAL"
    assert result.answers == RIGHT_TYPE_2
    doc.close()


def test_transpetro_matrix_keeps_common_and_two_column_question_ranges():
    answers = RIGHT_TYPE_1
    doc = fitz.open()
    try:
        _add_transpetro_matrix_fixture(doc, answers)

        matrices = extract_all_matrix_gabaritos(doc)

        assert len(matrices) == 1
        assert matrices[0]["tipo"] == "1"
        assert matrices[0]["total_q"] == 70
        assert matrices[0]["gabarito"] == answers
    finally:
        doc.close()
