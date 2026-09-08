from pathlib import Path

from services.pdf_pipeline import parse_exam_document
from services.pdf_pipeline.hybrid_extractor import extract_options_from_chunk


REPO_ROOT = Path(__file__).resolve().parents[1]
PROOF_56 = REPO_ROOT / "pdfs" / "56_1788095849.pdf"
PROOF_79 = REPO_ROOT / "pdfs" / "79_prova.pdf"


def test_inline_checkbox_options_do_not_promote_wrapped_statement_lines():
    chunk = (
        "Uma agente comunitária de saúde realiza visita a\n"
        "uma criança com 25 dias de vida. Nessa visita, a\n"
        "vacina contra a seguinte doença deve estar\n"
        "anotada no cartão de vacinação da criança:\n"
        "A ( ) poliomielite B ( ) hepatite B C ( ) catapora D ( ) sarampo"
    )

    options, statement = extract_options_from_chunk(chunk)

    assert statement.endswith("anotada no cartão de vacinação da criança:")
    assert options == {
        "A": "poliomielite",
        "B": "hepatite B",
        "C": "catapora",
        "D": "sarampo",
    }


def test_numeric_inline_options_are_not_removed_as_page_numbers():
    options, statement = extract_options_from_chunk(
        "Os direitos adquiridos pelo Estatuto do Idoso são garantidos a todas "
        "as pessoas com idade, em anos, igual ou superior a:\n"
        "A ( ) 55 B ( ) 60 C ( ) 65 D ( ) 70"
    )

    assert statement.endswith("igual ou superior a:")
    assert options == {"A": "55", "B": "60", "C": "65", "D": "70"}


def test_styled_option_marker_does_not_leave_html_tags_in_adjacent_options():
    options, statement = extract_options_from_chunk(
        "Enunciado da questao:\n"
        "(A) 1,5 m/s2.\n"
        "(B) 2,5 m/s2.\n"
        "(C) 5 m/s2.\n"
        "(D) 7,5 m/s2.\n"
        "(<u>E) 8 m/s2</u>."
    )

    assert statement == "Enunciado da questao:"
    assert options == {
        "A": "1,5 m/s2.",
        "B": "2,5 m/s2.",
        "C": "5 m/s2.",
        "D": "7,5 m/s2.",
        "E": "8 m/s2.",
    }


def test_real_two_column_proof_preserves_question_bodies_and_options():
    questions = parse_exam_document(PROOF_56, extract_images=False)
    by_number = {int(question["numero_questao"]): question for question in questions}

    assert len(questions) == 30
    assert set(by_number) == set(range(1, 31))

    assert by_number[1]["enunciado"].endswith(
        "anotada no cartão de vacinação da criança:"
    )
    assert by_number[1]["opcoes"] == {
        "A": "poliomielite",
        "B": "hepatite B",
        "C": "catapora",
        "D": "sarampo",
    }
    assert by_number[3]["opcoes"] == {
        "A": "55",
        "B": "60",
        "C": "65",
        "D": "70",
    }
    assert by_number[5]["opcoes"] == {
        "A": "18",
        "B": "21",
        "C": "24",
        "D": "35",
    }

    for question in questions:
        options = question["opcoes"]
        assert len(options) == 4
        assert all(str(value).strip() for value in options.values())
        assert not any("( )" in str(value) for value in options.values())


def test_numeric_question_headers_and_five_options_are_preserved():
    questions = parse_exam_document(PROOF_79, extract_images=False)
    by_number = {int(question["numero_questao"]): question for question in questions}

    assert len(questions) == 70
    assert all(len(question["opcoes"]) == 5 for question in questions)
    assert all(
        all(str(value).strip() for value in question["opcoes"].values())
        for question in questions
    )
    assert by_number[48]["opcoes"] == {
        "A": "1,5 m/s2.",
        "B": "2,5 m/s2.",
        "C": "5 m/s2.",
        "D": "7,5 m/s2.",
        "E": "8 m/s2.",
    }
    assert by_number[12]["opcoes"]["E"].endswith(
        "desigualdade social."
    )
    assert by_number[18]["opcoes"]["E"] == "Teijo Kelander"
    assert by_number[20]["opcoes"]["E"] == "The printer sale."
    assert by_number[35]["opcoes"]["E"] == "V – V – F."
