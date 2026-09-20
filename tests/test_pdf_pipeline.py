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
    _extract_native_text_question_chunks,
    _join_touching_native_word_fragments,
    _looks_like_split_numeric_formula_options,
    _native_question_numbers,
    _native_option_marker_rows,
    _recover_native_geometric_options,
    _ocr_native_option_rows,
    _precision_recovery_targets,
    _reconcile_rust_question_chain,
    _should_run_precision_recovery,
    _repair_image_only_option_question,
    _strip_pdf_page_code_tail,
    _strip_exam_watermark_token,
    _strip_trailing_exam_banner,
    _strip_trailing_pdf_section_header,
    extract_options_from_chunk,
    extract_heuristic_options,
    _normalize_roman_list_option,
    _score_option_map,
    strip_embedded_answer_marker,
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
from services.pdf_pipeline.media.diagram_cropper import (
    _linear_option_row_crop_rects,
    _two_column_option_grid_crop_rects,
)
from services.pdf_pipeline.fallbacks.typography_restorer import restore_ocr_lexical_spacing
from app_core.async_worker import _pdf_contains_idcap

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
        full_page_scan_detected=True,
    )
    assert result["needs_vision_ocr"] is True
    assert "question_coverage:38/40" in result["reasons"]
    assert any(reason.startswith("option_marker_density:") for reason in result["reasons"])


def test_native_text_quality_ignores_inline_images_when_detecting_scans():
    structured = (
        "Este Caderno é composto de 180 questões objetivas.\n"
        + "\n".join(
            f"QUESTÃO {number:03d}\nEnunciado da questão {number}.\n"
            "A\tPrimeira alternativa.\nB\tSegunda alternativa.\n"
            "C\tTerceira alternativa.\nD\tQuarta alternativa.\n"
            "E\tQuinta alternativa."
            for number in range(1, 181)
        )
    )
    result = _assess_native_text_quality(
        structured,
        document_text=structured,
        total_pages=64,
        image_page_count=64,
        total_image_count=2496,
        full_page_scan_detected=False,
    )

    assert result["question_count"] == 180
    assert result["option_marker_count"] == 900
    assert result["average_images_per_page"] == 39.0
    assert result["full_page_scan_detected"] is False
    assert result["needs_vision_ocr"] is False


def test_native_text_quality_uses_complete_document_sequence_when_blocks_lose_headers():
    document_text = (
        "Este caderno é composto de 70 questões objetivas.\n"
        + "\n".join(f"{number}. Enunciado da questão {number}." for number in range(1, 71))
    )
    reordered_blocks = (
        "Este caderno é composto de 70 questões objetivas.\n"
        + "\n".join(f"{number}. Enunciado da questão {number}." for number in range(1, 5))
    )

    result = _assess_native_text_quality(
        reordered_blocks,
        document_text=document_text,
        total_pages=16,
        image_page_count=16,
        total_image_count=160,
        full_page_scan_detected=False,
    )

    assert result["question_count"] == 70
    assert result["needs_vision_ocr"] is False
    assert result["reasons"] == []


def test_native_text_question_chunks_prefer_exam_headers_to_instruction_numbers():
    doc = fitz.open()
    first_page = doc.new_page(width=500, height=700)
    first_page.insert_text((30, 30), "1. Instrucoes gerais")
    first_page.insert_text((30, 50), "2. Confira o caderno")
    first_page.insert_textbox(
        fitz.Rect(30, 90, 470, 300),
        "QUESTAO 01\nPrimeira variante da questao.\n"
        "A. primeira alternativa\nB. segunda alternativa\n"
        "C. terceira alternativa\nD. quarta alternativa\nE. quinta alternativa",
        fontsize=11,
    )
    second_page = doc.new_page(width=500, height=700)
    second_page.insert_textbox(
        fitz.Rect(30, 90, 470, 300),
        "QUESTAO 01\nVariante duplicada que deve ser ignorada.\n"
        "QUESTAO 02\nSegunda questao do caderno.",
        fontsize=11,
    )

    chunks = _extract_native_text_question_chunks(doc)

    assert set(chunks) == {1, 2}
    assert "Primeira variante" in chunks[1]
    assert "Variante duplicada" not in chunks[1]
    assert "Instrucoes gerais" not in chunks[1]
    options, _ = extract_options_from_chunk(chunks[1])
    assert set(options) == set("ABCDE")


def test_native_text_rejoins_only_word_fragments_touching_in_pdf_geometry():
    page_text = "Becomes mine, its distor tions, its queerness; real words stay."
    words = [
        (10.0, 10.0, 34.0, 20.0, "distor", 0, 0, 0),
        (34.2, 10.0, 57.0, 20.0, "tions,", 0, 0, 1),
        (70.0, 10.0, 90.0, 20.0, "real", 0, 1, 0),
        (94.0, 10.0, 120.0, 20.0, "words", 0, 1, 1),
    ]

    normalized = _join_touching_native_word_fragments(page_text, words)

    assert "distortions," in normalized
    assert "real words" in normalized


def test_native_typography_preserves_intact_source_words_and_trims_section_tail():
    chunk = (
        "QUESTAO 4\nEnunciado da questão.\n"
        "A\t primeira alternativa.\nB\t texto representado na figura.\n"
        "C\t chamar a atenção para o significado da educação.\n"
        "D\t quarta alternativa.\nE\t quinta alternativa.\n"
        "LINGUAGENS, CÓDIGOS E SUAS\nTECNOLOGIAS\n"
        "Questões de 01 a 45\nQuestões de 01 a 05 (opção espanhol)"
    )

    options, _statement = extract_options_from_chunk(
        chunk,
        preserve_native_word_boundaries=True,
    )

    assert options["B"] == "texto representado na figura."
    assert options["C"] == "chamar a atenção para o significado da educação."
    assert "TECNOLOGIAS" not in options["E"]
    assert options["E"] == "quinta alternativa."


def test_pdf_page_codes_are_removed_without_truncating_following_text():
    cleaned = _strip_pdf_page_code_tail(
        "trecho *DO0725AZ29* continuação DO0725AZ30 texto final"
    )

    assert "DO0725AZ29" not in cleaned
    assert "DO0725AZ30" not in cleaned
    assert "trecho" in cleaned
    assert "continuação" in cleaned
    assert "texto final" in cleaned


def test_trailing_pdf_section_header_requires_a_recognized_banner_and_range():
    cleaned = _strip_trailing_pdf_section_header(
        "alternativa correta. LINGUAGENS, CÓDIGOS E SUAS TECNOLOGIAS "
        "Questões de 01 a 45 Questões de 01 a 05 (opção espanhol)"
    )

    assert cleaned == "alternativa correta."
    assert _strip_trailing_pdf_section_header(
        "O texto menciona questões de 01 a 45 no edital."
    ) == "O texto menciona questões de 01 a 45 no edital."


def test_native_option_extraction_preserves_numeric_answers_and_strips_page_code():
    chunk = (
        "QUESTAO 180\nA medida calculada e\n"
        "A\t 36 3\nB\t 24 3\nC\t 4 3\nD\t 36\nE\t 72\n"
        "*DO0725AZ31*"
    )

    options, statement = extract_options_from_chunk(chunk)

    assert set(options) == set("ABCDE")
    assert options["D"] == "36"
    assert options["E"] == "72"
    assert all("DO0725AZ31" not in value for value in options.values())
    assert "DO0725AZ31" not in (statement or "")
    assert _looks_like_split_numeric_formula_options(options) is True
    assert _looks_like_split_numeric_formula_options(
        {"A": "12", "B": "16", "C": "20", "D": "24", "E": "32"}
    ) is False


def test_native_option_ocr_keeps_fraction_numerator_above_denominator(monkeypatch):
    from services.pdf_pipeline.layout import layout_detector

    marker_rows = [
        {"label": label, "x0": 10.0, "mid_y": 100.0 + index * 27.0}
        for index, label in enumerate("ABCDE")
    ]
    lines = []
    for index, (numerator, label) in enumerate(zip(("4", "5", "6", "7", "8"), "ABCDE")):
        mid_y = marker_rows[index]["mid_y"]
        lines.extend([
            {"x0": 0.0, "y0": mid_y - 1, "y1": mid_y + 1, "text": label},
            {"x0": 20.0, "y0": mid_y - 7, "y1": mid_y - 3, "text": numerator},
            {"x0": 20.0, "y0": mid_y + 3, "y1": mid_y + 7, "text": "21"},
        ])
    monkeypatch.setattr(
        layout_detector,
        "extract_ocr_lines_from_page",
        lambda *args, **kwargs: lines,
    )

    doc = fitz.open()
    page = doc.new_page()
    options = _ocr_native_option_rows(
        page,
        marker_rows,
        fitz.Rect(0, 0, 100, 300),
    )

    assert options == {
        "A": "4/21",
        "B": "5/21",
        "C": "6/21",
        "D": "7/21",
        "E": "8/21",
    }


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


def test_idcap_is_detected_from_local_pdf_when_source_url_was_normalized():
    assert _pdf_contains_idcap("pdfs/2_prova.pdf") is True


def test_native_question_headers_support_named_and_unpunctuated_forms():
    sample = "\n".join(
        [
            "01. Enunciado numerado.",
            "02",
            "Questão 03",
            "Questão 04 (Correta: A)",
            "QUESTAO 05:",
            "ITEM 06",
        ]
    )

    assert _native_question_numbers(sample) == [1, 2, 3, 4, 5, 6]


def test_global_rust_chain_discards_numeric_noise_before_complete_sequence(monkeypatch):
    strict_headers = [
        {"number": number, "start": number * 100}
        for number in range(1, 71)
    ]
    questions = [
        {"numero_questao": "2", "start_char": 10, "marker": "page-number"},
        {"numero_questao": "12", "start_char": 20, "marker": "footer-number"},
        *[
            {
                "numero_questao": str(number),
                "start_char": number * 100,
                "marker": "real",
            }
            for number in range(1, 71)
        ],
    ]
    monkeypatch.setattr(
        "services.pdf_pipeline.hybrid_extractor.rust_scan_question_headers",
        lambda _text: strict_headers,
    )

    reconciled = _reconcile_rust_question_chain(questions, "full text")

    assert [item["numero_questao"] for item in reconciled] == [
        str(number) for number in range(1, 71)
    ]
    assert all(item["marker"] == "real" for item in reconciled)


def test_declared_question_count_accepts_number_written_in_parentheses():
    from services.pdf_pipeline.hybrid_extractor import _declared_question_count

    assert _declared_question_count(
        "Este caderno contém o enunciado das 70 (setenta) questões objetivas."
    ) == 70


def test_native_tab_delimited_options_split_the_statement_cleanly():
    chunk = (
        "QUESTÃO 117\n"
        "Um pesquisador deseja escolher uma linhagem dentre as cinco mostradas.\n"
        "Qual linhagem deve ser escolhida?\n"
        "A\tI\n"
        "B\tII\n"
        "C\tIII\n"
        "D\tIV\n"
        "E\tV\n"
    )

    options, statement = extract_options_from_chunk(
        chunk,
        preserve_native_word_boundaries=True,
    )

    assert options == {"A": "I", "B": "II", "C": "III", "D": "IV", "E": "V"}
    assert statement is not None
    assert "Qual linhagem deve ser escolhida?" in statement
    assert "A\tI" not in statement


def test_native_geometric_option_recovery_reads_roman_list_rows():
    rows = [
        {
            "label": label,
            "text": f"{label}\t {value}",
            "x0": 10.0,
            "y0": 20.0 + index * 15,
            "y1": 32.0 + index * 15,
            "mid_y": 26.0 + index * 15,
        }
        for index, (label, value) in enumerate(zip("ABCDE", ("I", "II", "III", "IV", "V")))
    ]

    assert _recover_native_geometric_options(rows, [], 500.0) == {
        "A": "I",
        "B": "II",
        "C": "III",
        "D": "IV",
        "E": "V",
    }


def test_native_geometric_option_recovery_rebuilds_stacked_fractions():
    rows = []
    words = []
    for index, label in enumerate("ABCDE"):
        base_y = 100.0 + index * 40.0
        rows.append({
            "label": label,
            "text": label,
            "x0": 0.0,
            "x1": 10.0,
            "y0": base_y - 7.0,
            "y1": base_y + 7.0,
            "mid_y": base_y,
        })
        words.append((0.0, base_y - 5.0, 10.0, base_y + 5.0, label))
        words.extend([
            (20.0, base_y - 10.0, 30.0, base_y - 4.0, "50"),
            (31.0, base_y - 10.0, 35.0, base_y - 4.0, "X"),
            (24.0, base_y + 5.0, 28.0, base_y + 11.0, "4"),
            (40.0, base_y - 5.0, 45.0, base_y + 6.0, "+"),
            (50.0, base_y - 10.0, 60.0, base_y - 4.0, "50"),
            (61.0, base_y - 10.0, 65.0, base_y - 4.0, "Y"),
            (54.0, base_y + 5.0, 58.0, base_y + 11.0, "9"),
        ])

    recovered = _recover_native_geometric_options(rows, words, 200.0)

    assert recovered == {
        label: r"\frac{50X}{4} + \frac{50Y}{9}"
        for label in "ABCDE"
    }


def test_two_column_graph_option_grid_maps_all_five_labels():
    words = []
    for label, x, y in (
        ("A", 50.0, 200.0),
        ("D", 300.0, 200.0),
        ("B", 50.0, 320.0),
        ("E", 300.0, 320.0),
        ("C", 50.0, 440.0),
    ):
        words.append((x, y, x + 9.0, y + 10.0, label))

    crops = _two_column_option_grid_crop_rects(
        words,
        fitz.Rect(0.0, 0.0, 612.0, 792.0),
        question_y=50.0,
        next_question_y=792.0,
    )

    assert crops is not None
    assert set(crops) == set("ABCDE")
    assert crops["A"].x0 == 68.0
    assert crops["D"].x0 == 318.0
    assert crops["A"].y0 == crops["D"].y0
    assert crops["C"].y1 > crops["C"].y0


def test_native_option_markers_ignore_subfigure_labels_between_choices():
    doc = fitz.open()
    try:
        page = doc.new_page(width=612.0, height=792.0)
        page.insert_text((296.0, 50.0), "QUESTÃO 95")
        page.insert_text((315.0, 140.0), "A")
        page.insert_text((373.0, 140.0), "B")
        choice_y = {"A": 180.0, "B": 255.0, "C": 330.0, "D": 405.0, "E": 480.0}
        for label, y in choice_y.items():
            page.insert_text((296.0, y), label)
            if label in {"A", "B"}:
                page.insert_text((315.0, y + 30.0), "A")
                page.insert_text((373.0, y + 30.0), "B")

        target = _native_option_marker_rows(
            doc,
            95,
            {95: (0, 296.0, 50.0)},
        )

        assert target is not None
        _, marker_rows, _ = target
        assert [row["label"] for row in marker_rows] == list("ABCDE")
        assert [row["x0"] for row in marker_rows] == sorted(
            row["x0"] for row in marker_rows
        )
        assert max(row["x0"] for row in marker_rows) - min(
            row["x0"] for row in marker_rows
        ) < 2.0
    finally:
        doc.close()


def test_linear_image_option_rows_ignore_inner_diagram_letters():
    words = []
    for label, y in (("A", 200.0), ("B", 275.0), ("C", 350.0), ("D", 425.0), ("E", 500.0)):
        words.append((296.0, y, 305.0, y + 10.0, label))
        if label in {"A", "B", "C", "D", "E"}:
            words.append((315.0, y + 30.0, 320.0, y + 40.0, "A"))
            words.append((373.0, y + 30.0, 378.0, y + 40.0, "B"))

    crops = _linear_option_row_crop_rects(
        words,
        fitz.Rect(0.0, 0.0, 612.0, 792.0),
        question_x=296.0,
        question_y=50.0,
        next_question_y=792.0,
    )

    assert crops is not None
    assert set(crops) == set("ABCDE")
    assert all(crop.x0 == 314.0 for crop in crops.values())
    assert crops["A"].y0 < crops["B"].y0 < crops["C"].y0 < crops["D"].y0 < crops["E"].y0


def test_idcap_embedded_answer_marker_is_removed_without_losing_answer():
    samples = [
        "(Correta: C)\nNo segundo quadro...",
        "(Correta\n\nC.\nNo segundo quadro...",
        "(CorretaC. No segundo quadro...",
    ]
    for sample in samples:
        cleaned = strip_embedded_answer_marker(sample)
        assert "correta" not in cleaned.casefold()
        assert "No segundo quadro" in cleaned


def test_idcap_image_only_options_return_text_to_statement():
    question = {
        "enunciado": "A manilha é uma conexão resistente. Dentre as imagens apresentadas abaixo, assinale a alternativa.",
        "opcoes": {
            "A": "facilmente desmontáveis,",
            "B": "utilizado na movimentação de cargas,",
            "C": "usualmente empregada para a ligação de dois olhais",
            "D": "ou para a fixação de cabos e aparelhos de laborar,",
            "E": "consistindo em uma conexão muito simples e resistente.",
        },
        "option_images": {letter: f"/static/{letter}.png" for letter in "ABCDE"},
    }

    _repair_image_only_option_question(question)

    assert all(value == "" for value in question["opcoes"].values())
    assert all(letter in question["option_images"] for letter in "ABCDE")
    assert "facilmente desmontáveis" in question["enunciado"]
    assert "conexão muito simples e resistente" in question["enunciado"]


def test_precision_recovery_does_not_target_valid_five_option_questions():
    questions = [
        {
            "numero_questao": str(number),
            "opcoes": {letter: f"Alternativa {letter}" for letter in "ABCDE"},
        }
        for number in range(1, 71)
    ]

    assert _precision_recovery_targets(questions) == set()
    assert _should_run_precision_recovery(
        needs_vision_ocr=False,
        native_layer_usable=False,
    ) is False


def test_precision_recovery_keeps_four_option_scan_repair_signal():
    questions = [
        {
            "numero_questao": "1",
            "opcoes": {letter: f"Alternativa {letter}" for letter in "ABCD"},
        },
        {
            "numero_questao": "2",
            "opcoes": {letter: f"Alternativa {letter}" for letter in "ABC"},
        },
    ]

    assert _precision_recovery_targets(questions) == {2}
    assert _should_run_precision_recovery(
        needs_vision_ocr=True,
        native_layer_usable=False,
    ) is True


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


def test_roman_list_normalizer_does_not_split_accented_words():
    text = "níveis técnicos e favoráveis para a organização"
    assert _normalize_roman_list_option(text) == text


def test_transpetro_banners_are_removed_without_losing_question_text():
    assert _strip_trailing_exam_banner(
        "alternativa correta. RASCUNHO TRANSPETRO LÍNGUA INGLESA"
    ) == "alternativa correta."
    assert _strip_exam_watermark_token(
        "Tabela de apoio\n\nRASCUNHO Para liquidar a dívida"
    ) == "Tabela de apoio\n\nPara liquidar a dívida"


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
