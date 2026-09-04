import fitz

from services.gabarito import (
    build_exam_answer_key_profile,
    extract_answer_key_blocks,
    match_gabarito_from_pdf,
    parse_gabarito_from_pdf,
)


RIGHT_TYPE_1 = {number: "ABCDE"[(number - 1) % 5] for number in range(1, 71)}
RIGHT_TYPE_2 = {number: "EDCBA"[(number - 1) % 5] for number in range(1, 71)}


def _add_block(doc, cargo, tipo, answers):
    page = doc.new_page()
    lines = [f"{cargo} - PROVA TIPO {tipo}"]
    lines.extend(str(number) for number in range(1, 71))
    lines.extend(answers[number] for number in range(1, 71))
    page.insert_text((50, 30), "\n".join(lines), fontsize=4)


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
