import fitz

from services.gabarito import extract_gabarito_from_doc
from services.pdf_pipeline.hybrid_extractor import extract_options_from_chunk


def test_matrix_answers_are_not_overwritten_by_letter_lists_in_the_last_page():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Questão 01\n(Correta: D)\nQual é a alternativa?\n(A) Primeira\n(B) Segunda\n(C) Terceira\n(D) Quarta")
    page = doc.new_page()
    page.insert_text((50, 50), "Questão 02\n(Correta: B)\nAssocie as colunas.\n(A) C, B, A.\n(B) A, B, C.\n(C) B, A, C.\n(D) A, C, B.")

    assert extract_gabarito_from_doc(doc) == {1: "D", 2: "B"}
    doc.close()


def test_embedded_answer_can_continue_on_the_next_page_after_an_exam_footer():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Questão 48\nFiscal de Obras, Posturas e Meio Ambiente - 1\n11")
    page = doc.new_page()
    page.insert_text((50, 50), "(Correta: C)\nQual é a alternativa?\n(A) Vermelho\n(B) Azul\n(C) Verde\n(D) Preto")

    assert extract_gabarito_from_doc(doc) == {48: "C"}
    doc.close()


def test_association_columns_stay_in_statement_and_letter_permutations_stay_in_options():
    chunk = (
        "Questão 49\n(Correta: B)\nAssocie as ferramentas com suas etapas:\n"
        "Coluna 1:\nA.Torquês.\nB.Mangote.\nC.Martelo.\n"
        "Coluna 2:\n(__)Armação.\n(__)Concretagem.\n(__)Formas.\n"
        "Assinale a sequência correta:\n"
        "(A) C,\n B,\n A.\n(B) A,\n B,\n C.\n(C) B,\n A,\n C.\n(D) A,\n C,\n B.\n"
    )
    options, statement = extract_options_from_chunk(chunk)

    assert options == {"A": "C, B, A.", "B": "A, B, C.", "C": "B, A, C.", "D": "A, C, B."}
    assert "A.Torquês." in statement
    assert "B.Mangote." in statement
    assert "C.Martelo." in statement
