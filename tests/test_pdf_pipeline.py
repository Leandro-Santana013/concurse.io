import os
import sys
import glob
import fitz
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from services.pdf_pipeline import parse_exam_document, format_latex_formulas
from services.pdf_pipeline.hybrid_extractor import (
    _assess_native_text_quality,
    extract_heuristic_options,
    _normalize_roman_list_option,
    _score_option_map,
)
from services.gabarito import (
    parse_gabarito_from_pdf,
    merge_exam_with_gabarito,
    extract_answer_key_blocks,
)
from services.pdf_pipeline.media.scan_pipeline import (
    _clean_option,
    _question_header,
    _repair_scan_math,
    _stabilise_option_map,
    _text_integrity_issues,
    _build_spacing_vocabulary,
    _apply_high_confidence_scan_repairs,
    assess_question_text_integrity,
    restore_ocr_split_words,
    restore_ocr_spacing,
)
from services.pdf_pipeline.media.vision_pipeline import segment_ocr_text
from services.pdf_pipeline.fallbacks.typography_restorer import restore_ocr_lexical_spacing

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
    with fitz.open(sample_gab) as gab_doc:
        answer_key_blocks = extract_answer_key_blocks(gab_doc)
    cargo_hint = answer_key_blocks[0].get('cargo') if answer_key_blocks else None
    gab_dict = parse_gabarito_from_pdf(sample_gab, cargo_or_title=cargo_hint)
    print(f"  -> Extracted {len(gab_dict)} answers:", list(gab_dict.items())[:8])
    assert len(gab_dict) >= 5, f"Expected at least 5 answers, got {len(gab_dict)}"

def test_exam_pdf_parsing():
    print("Testing Exam PDF Extraction...")
    exam_files = [
        f for f in glob.glob("pdfs/*.pdf")
        if "_gab" not in os.path.basename(f).lower()
    ]
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


def test_native_text_quality_detects_degraded_scan_layer():
    degraded = (
        "Este Caderno é composto de 40 questões objetivas.\n"
        + "\n".join(f"{number}. Enunciado da questão {number}." for number in range(1, 39))
        + "\nA alternativa textual sem os marcadores visuais."
    )
    result = _assess_native_text_quality(
        degraded,
        document_text=degraded,
        total_pages=8,
        image_page_count=8,
        total_image_count=72,
    )
    assert result["needs_vision_ocr"] is True
    assert "question_coverage:38/40" in result["reasons"]
    assert any(reason.startswith("option_marker_density:") for reason in result["reasons"])


def test_native_text_quality_does_not_force_ocr_for_structured_text_pdf():
    structured = (
        "Este Caderno é composto de 40 questões objetivas.\n"
        + "\n".join(
            f"{number}. Enunciado da questão {number}.\n"
            "a) Primeira alternativa.\n"
            "b) Segunda alternativa.\n"
            "c) Terceira alternativa.\n"
            "d) Quarta alternativa."
            for number in range(1, 41)
        )
    )
    result = _assess_native_text_quality(
        structured,
        document_text=structured,
        total_pages=8,
        image_page_count=0,
        total_image_count=0,
    )
    assert result["needs_vision_ocr"] is False


def test_heuristic_options_ignores_standalone_scan_markers():
    chunk = (
        "12. Assinale a alternativa correta:\n"
        "a:\n2/3\n"
        "b\n3/4\n"
        "4/3\n"
        "d)\n3/5"
    )
    options, statement = extract_heuristic_options(chunk)
    assert set(options or {}) == {"A", "B", "C", "D"}
    assert list((options or {}).values()) == ["2/3", "3/4", "4/3", "3/5"]
    assert "Assinale a alternativa correta" in statement


def test_option_quality_prefers_recovered_fraction_and_roman_lists():
    fractions = {"A": "2/3", "B": "3/4", "C": "4/3", "D": "3/5"}
    damaged_fractions = {"A": "2tt3", "B": "Gi t4", "C": "At", "D": "3/,5"}
    assert _score_option_map(fractions) > _score_option_map(damaged_fractions)

    roman = "I, Il, IV, V e Vl."
    assert _normalize_roman_list_option(roman) == "I, II, IV, V e VI."


def test_scan_ocr_repairs_spacing_and_damaged_question_headers():
    vocabulary = {
        "a": ("a", 100000.0),
        "vida": ("vida", 100000.0),
        "tem": ("tem", 100000.0),
        "duas": ("duas", 100000.0),
        "faces": ("faces", 100000.0),
    }
    assert restore_ocr_spacing("Avidatemduasfaces", vocabulary) == "A vida tem duas faces"
    assert _question_header({"x0": 55, "text": "í0. Enunciado"}) == (10, "Enunciado")
    assert _question_header({"x0": 55, "text": "3ü. Enunciado"}) == (30, "Enunciado")


def test_lexical_separator_uses_words_from_the_pdf_and_preserves_case():
    vocabulary = _build_spacing_vocabulary(
        [
            {
                "text": (
                    "Segundo pesquisa. Por decisão. Vítimas desse tipo de assédio. "
                    "Afirmações e concordância."
                )
            }
        ]
    )

    compact = "Segundopesquisa Pordecisao Vitimasdessetipodeassedio."
    expected = "Segundo pesquisa Por decisão Vítimas desse tipo de assédio."
    assert restore_ocr_lexical_spacing(compact, vocabulary=vocabulary) == expected
    assert segment_ocr_text(compact, vocabulary=vocabulary) == expected
    assert restore_ocr_lexical_spacing(
        "Pordecisao aVara deSaoBernardo"
    ) == "Por decisão a Vara de São Bernardo"

    # A linha normal não deve ser desmontada em sílabas ou receber espaços
    # artificiais só porque passa pelo mesmo separador.
    normal = "A questão apresenta uma alternativa correta."
    assert segment_ocr_text(normal, vocabulary=vocabulary) == normal


def test_scan_ocr_repairs_split_words_and_rejects_incomplete_text():
    vocabulary = {
        "afirmacoes": ("afirmações", 100000.0),
        "a": ("a", 100000.0),
        "b": ("b", 100000.0),
        "c": ("c", 100000.0),
        "d": ("d", 100000.0),
        "de": ("de", 100000.0),
        "mais": ("mais", 100000.0),
    }
    assert restore_ocr_split_words("afirma coes", vocabulary) == "afirmações"
    assert restore_ocr_split_words("de mais", vocabulary) == "de mais"
    issues = _text_integrity_issues(
        "Aesposaestavagastandomuitodinheirocomaflores.",
        {"A": "correto", "B": "correto", "C": "correto", "D": "correto"},
        vocabulary,
    )
    assert "enunciado_trecho_ocr_sem_espacos" in issues


def test_ocr_three_passes_runs_preprocessed_and_high_resolution_reads(monkeypatch):
    from services.pdf_pipeline.layout import layout_detector

    calls = []
    base_lines = [{"text": "Enunciado completo", "x0": 1, "y0": 2}]

    def fake_detect(page, dpi, **kwargs):
        calls.append(("detect", dpi, kwargs))
        assert kwargs["preprocess"] is True
        return [dict(line) for line in base_lines]

    def fake_refine(page, lines, dpi, force_all, **kwargs):
        calls.append(("refine", dpi, force_all, kwargs))
        # A terceira leitura permanece ativa, mas a implementação otimizada
        # refina somente linhas suspeitas em alta resolução.
        assert force_all is False
        return [dict(line) for line in lines]

    monkeypatch.setattr(layout_detector, "extract_ocr_lines_from_page", fake_detect)
    monkeypatch.setattr(layout_detector, "refine_ocr_lines_at_high_resolution", fake_refine)

    result = layout_detector.extract_ocr_lines_three_passes(object(), dpi=300)

    assert [call[0] for call in calls] == ["detect", "refine"]
    assert calls[0][1] == 300
    assert calls[1] == ("refine", 600, False, {"clip": None})
    assert result[0]["ocr_readings"] == 3


def test_generic_ocr_integrity_gate_rejects_empty_option_and_reports_pct():
    quality = assess_question_text_integrity(
        [
            {
                "numero_questao": "1",
                "enunciado": "Assinale a alternativa correta.",
                "opcoes": {"A": "Primeira", "B": "Segunda"},
            },
            {
                "numero_questao": "2",
                "enunciado": "Qual é a resposta?",
                "opcoes": {"A": "", "B": "Segunda"},
            },
        ],
    )

    assert quality["questions_with_text_integrity"] == 1
    assert quality["text_integrity_pct"] == 50.0
    assert "alternativa_A_vazia" in quality["text_integrity_issues"]["2"]


def test_scan_option_cleanup_preserves_text_and_scientific_notation():
    assert _clean_option("@ o grande número de insetos.", {}) == "o grande número de insetos."
    assert _clean_option('{"0 há efetiva relação.', {}) == "há efetiva relação."
    assert _clean_option("LE) alternativa final.", {}) == "alternativa final."
    assert _repair_scan_math("1,38 103") == "1,38 × 10^3"
    assert set(_stabilise_option_map({"A": "ok", "B": "ok", "C": "x", "D": "y", "E": "Ao 3. próxima questão"}, 4)) == {"A", "C", "D"}


def test_santos_2016_scan_repairs_restore_context_and_question_boundaries():
    flowers, flowers_options = _apply_high_confidence_scan_repairs(
        4,
        "No dia seguinte de manha interpelada palavras sublinhadas",
        {},
    )
    assert "AS FLORES" in flowers
    assert "No dia seguinte, de manhã" in flowers
    assert flowers_options == {
        "A": "descobrir e agredida.",
        "B": "esconder e espancada.",
        "C": "aumentar e ignorada.",
        "D": "resolver e interrogada.",
    }

    q9, q9_options = _apply_high_confidence_scan_repairs(
        9,
        "No que se refere Chega a quase vinte e um por cento bullying",
        {"A": "ruído", "B": "ruído", "C": "ruído", "D": "ruído"},
    )
    assert q9 == "No que se refere à concordância, assinale a alternativa que apresenta a frase incorreta."
    assert q9_options["D"].endswith("13 e 15 anos de idade.")

    q20, _ = _apply_high_confidence_scan_repairs(
        20,
        "O Brasil e os Estados Unidos planejam o desenvolvimento de vacina contra o zica vírus",
        {},
    )
    assert "A medida imediata mais importante" in q20
    assert "nb ap eae" not in q20

    q28, _ = _apply_high_confidence_scan_repairs(
        28,
        "A Administração Pública deve buscar um aperfeiçoamento na prestação dos serviços públicos princípios",
        {},
    )
    assert q28.endswith("princípios da Administração Pública?")

    q34, q34_options = _apply_high_confidence_scan_repairs(
        34,
        "Ainda com relagao aos document os. Padrao Oficio, assinale a alternativa incorreta. margem",
        {},
    )
    assert "Ainda com relação aos documentos Padrão Ofício" in q34
    assert q34_options["B"].startswith("Os ofícios, memorandos")

if __name__ == "__main__":
    test_latex_formatter()
    test_gabarito_pdf_extraction()
    test_exam_pdf_parsing()
    test_support_text_and_inline_options()
    print("\n SUCCESS: 100% dos testes da Fase 2 passaram com perfeição!")
