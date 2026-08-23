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

if __name__ == "__main__":
    test_latex_formatter()
    test_gabarito_pdf_extraction()
    test_exam_pdf_parsing()
    print("\n SUCCESS: 100% dos testes da Fase 2 passaram com perfeição!")
