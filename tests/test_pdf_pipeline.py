import os
import sys
import glob
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from services.pdf_pipeline import parse_exam_document, format_latex_formulas
from services.gabarito import parse_gabarito_from_pdf, merge_exam_with_gabarito

def test_latex_formatter():
    print("Testing LaTeX Formatter...")
    raw = "Calcule o valor de x^2 + √16 quando y ≤ 10 e a área é 25 cm²"
    formatted, has_latex = format_latex_formulas(raw)
    assert has_latex is True
    assert "$" in formatted
    print("  -> OK: Formatted LaTeX ->", formatted)

def test_gabarito_pdf_extraction():
    print("Testing Gabarito Extraction from PDF...")
    gab_files = glob.glob("pdfs/*gab*.pdf")
    if not gab_files:
        print("  -> No gabarito files in pdfs/, skipping test.")
        return

    sample_gab = gab_files[0]
    print(f"  -> Testing on {sample_gab}...")
    gab_dict = parse_gabarito_from_pdf(sample_gab)
    print(f"  -> Extracted {len(gab_dict)} answers:", list(gab_dict.items())[:8])
    assert len(gab_dict) >= 5, f"Expected at least 5 answers, got {len(gab_dict)}"

def test_exam_pdf_parsing():
    print("Testing Exam PDF Extraction...")
    exam_files = [f for f in glob.glob("pdfs/*.pdf") if "_gab_" not in f]
    if not exam_files:
        print("  -> No exam files in pdfs/, skipping test.")
        return

    sample_exam = exam_files[0]
    print(f"  -> Testing on {sample_exam}...")
    questions = parse_exam_document(sample_exam, extract_images=True)
    print(f"  -> Extracted {len(questions)} questions.")
    assert len(questions) >= 5, f"Expected at least 5 questions, got {len(questions)}"
    
    first_q = questions[0]
    print("  -> Question 1 preview:")
    print("     Statement:", first_q["enunciado"][:120], "...")
    print("     Options:", list(first_q["opcoes"].keys()))
    print("     Subject:", first_q["disciplina"])
    assert len(first_q["opcoes"]) >= 2, "Options should be parsed"

def test_support_text_and_inline_options():
    print("Testing Support Text Regex & Inline Options Parsing...")
    from services.pdf_pipeline.layout.layout_detector import CONTEXT_TEXT_HEADER_REGEX, extract_context_blocks
    from services.pdf_pipeline.hybrid_extractor import extract_options_from_chunk

    sample_text = (
        "Leia o texto abaixo para responder as questões de nº 01 a 02\n\n"
        "Texto motivador de teste com dados e informações.\n\n"
        "QUESTÃO 01\n"
        "De acordo com o texto acima, podemos afirmar que:\n"
        "a)A maioria dos jogadores não quiseram responder a pergunta.\n"
        "b) Mais da metade dos entrevistados bebem todos os dias.\n"
        "c) A maioria dos jogadores bebem pelo menos uma vez por semana.\n"
        "d) Todos os entrevistados fazem uso de bebidas alcoólicas.\n\n"
        "QUESTÃO 02\n"
        "Na frase: 'Dos entrevistados, 24% não quiseram responder a pergunta.', a palavra destacada\n"
        "a) pode ser classificada como:\n"
        "b) Advérbio de negação.\n"
        "c) Advérbio de tempo.\n"
        "d) Advérbio de intensidade.\n"
    )

    m = CONTEXT_TEXT_HEADER_REGEX.search(sample_text)
    assert m is not None, "CONTEXT_TEXT_HEADER_REGEX deve capturar 'de nº 01 a 02'"
    ctx_blocks = extract_context_blocks(sample_text)
    assert len(ctx_blocks) >= 1, "extract_context_blocks deve extrair o texto de apoio para Q1 a Q2"
    q_min, q_max, body, _ = ctx_blocks[0]
    assert q_min == 1 and q_max == 2
    assert "Texto motivador de teste" in body

    q1_chunk = (
        "QUESTÃO 01\nDe acordo com o texto acima, podemos afirmar que:\n"
        "a)A maioria dos jogadores não quiseram responder a pergunta.\n"
        "b) Mais da metade dos entrevistados bebem todos os dias.\n"
        "c) A maioria dos jogadores bebem pelo menos uma vez por semana.\n"
        "d) Todos os entrevistados fazem uso de bebidas alcoólicas."
    )
    opts, stmt = extract_options_from_chunk(q1_chunk)
    assert set(opts.keys()) == {'A', 'B', 'C', 'D'}
    assert "A maioria dos jogadores não quiseram responder a pergunta." in opts['A']
    assert "responder a pergunta" not in stmt, "O artigo 'a' em 'responder a pergunta' não deve ser interpretado como letra da opção A"
    print("  -> OK: Support Text & Inline Options test passed!")

if __name__ == "__main__":
    test_latex_formatter()
    test_gabarito_pdf_extraction()
    test_exam_pdf_parsing()
    test_support_text_and_inline_options()
    print("\n SUCCESS: 100% dos testes da Fase 2 passaram com perfeição!")
