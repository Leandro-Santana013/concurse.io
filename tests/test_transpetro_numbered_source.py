import re
from pathlib import Path

import pytest

from services.pdf_pipeline.hybrid_extractor import parse_exam_document


PDF_PATH = Path(__file__).resolve().parents[1] / "pdfs" / "8_prova.pdf"


@pytest.mark.skipif(not PDF_PATH.is_file(), reason="PDF real da Transpetro não está disponível")
def test_transpetro_keeps_numbered_support_text_out_of_question_chain(monkeypatch):
    monkeypatch.setenv("PDF_PARSE_CACHE_ENABLED", "0")
    questions = parse_exam_document(
        str(PDF_PATH),
        exam_id=8008,
        extract_images=False,
        allow_ocr=False,
    )

    assert len(questions) == 70
    statement = questions[0]["enunciado"]
    assert "### À moda brasileira" in statement
    assert re.findall(r"(?m)^(\d{1,2}) ", statement) == [str(number) for number in range(1, 10)]
    assert "Estou me vendo debaixo de uma árvore, lendo a pequena história da literatura brasileira." in statement
    assert "8 Fechei o livro e recuei. Sempre que meu pai queria mudar de assunto" in statement
    assert "que- ria" not in statement
    assert "brasil e irá" not in statement
    assert not re.search(r"(?m)^>", statement)
    assert "---\n\nO fragmento de abertura" in statement
    assert set(questions[0]["opcoes"]) == set("ABCDE")
