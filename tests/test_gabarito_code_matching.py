import fitz

from services.gabarito import (
    extract_exam_code_ranges_from_pdf,
    parse_gabarito_from_pdf,
)
from services.gabarito.gabarito_service import extract_code_ranges_from_text


WRONG_129_TO_132 = list("BAABDDCCDCABCAADB DCAAABBCBBDBB".replace(" ", ""))
RIGHT_133_TO_139 = list("DCAACBADCACADCADAABABCAD DCDCDA".replace(" ", ""))


def _add_gabarito_page(doc, code_range, answers):
    page = doc.new_page()
    lines = ["PREFEITURA MUNICIPAL DE UBERABA", "QUESTOES", "GABARITO"]
    for number, answer in enumerate(answers, start=1):
        lines.extend([str(number), answer])
    lines.append(f"Fundamental Incompleto ({code_range})")
    page.insert_text((72, 36), "\n".join(lines), fontsize=8)


def test_extracts_exam_code_range_from_header():
    exam_doc = fitz.open()
    page = exam_doc.new_page()
    page.insert_text(
        (72, 72),
        "FUNDAMENTAL INCOMPLETO\nANEXO III - TARDE\nCodigos: 133 a 139",
    )

    assert extract_exam_code_ranges_from_pdf(exam_doc) == [(133, 139)]
    exam_doc.close()


def test_code_parser_tolerates_broken_pdf_accent():
    assert extract_code_ranges_from_text("C\ufffddigos: 133 a 139") == [(133, 139)]


def test_gabarito_code_range_has_priority_over_generic_title_match():
    gab_doc = fitz.open()
    _add_gabarito_page(gab_doc, "129 a 132", WRONG_129_TO_132)
    _add_gabarito_page(gab_doc, "133 a 139", RIGHT_133_TO_139)

    result = parse_gabarito_from_pdf(
        gab_doc,
        cargo_or_title=(
            "AGENTE DE DESENVOLVIMENTO URBANO E RURAL II - COVEIRO - "
            "PREF. UBERABA/MG 2016"
        ),
        exam_code_ranges=[(133, 139)],
    )

    assert result == {
        number: answer
        for number, answer in enumerate(RIGHT_133_TO_139, start=1)
    }
    gab_doc.close()


def test_gabarito_code_mismatch_fails_closed():
    gab_doc = fitz.open()
    _add_gabarito_page(gab_doc, "129 a 132", WRONG_129_TO_132)
    _add_gabarito_page(gab_doc, "133 a 139", RIGHT_133_TO_139)

    result = parse_gabarito_from_pdf(
        gab_doc,
        cargo_or_title="AGENTE DE DESENVOLVIMENTO URBANO E RURAL II - COVEIRO",
        exam_code_ranges=[(140, 145)],
    )

    assert result == {}
    gab_doc.close()


def test_legacy_matching_remains_available_without_indexed_code_pages():
    gab_doc = fitz.open()
    cover = gab_doc.new_page()
    cover.insert_text(
        (72, 72),
        "Codigos: 133 a 139\nUse o final deste caderno apenas para marcar o Gabarito.",
    )
    page = gab_doc.new_page()
    lines = ["GABARITO"]
    for number, answer in enumerate(RIGHT_133_TO_139, start=1):
        lines.extend([str(number), answer])
    page.insert_text((72, 36), "\n".join(lines), fontsize=8)

    result = parse_gabarito_from_pdf(
        gab_doc,
        exam_code_ranges=[(133, 139)],
    )

    assert result == {
        number: answer
        for number, answer in enumerate(RIGHT_133_TO_139, start=1)
    }
    gab_doc.close()
