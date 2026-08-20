import os
import sys
import glob
import fitz

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from services.pdf_pipeline.diagram_cropper import (
    ExamImageExtractor,
    extract_images_from_pdf,
    find_diagram_clusters,
    IMAGE_TRIGGER_REGEX,
    CAPTION_REGEX,
)
from services.pdf_pipeline.hybrid_extractor import parse_exam_document

def test_image_trigger_regex():
    print("Testing IMAGE_TRIGGER_REGEX...")
    test_cases = [
        ("Considere a figura abaixo para responder", True),
        ("Analise o gráfico a seguir", True),
        ("Observe o diagrama elétrico apresentado", True),
        ("De acordo com a charge acima", True),
        ("Texto puramente conceitual sobre direito administrativo", False),
    ]
    for text, expected in test_cases:
        matched = bool(IMAGE_TRIGGER_REGEX.search(text))
        assert matched == expected, f"Failed for '{text}': got {matched}, expected {expected}"
    print("  -> OK: IMAGE_TRIGGER_REGEX validado!")

def test_caption_regex():
    print("Testing CAPTION_REGEX...")
    test_cases = [
        ("Figura 1 - Esquema representativo", True),
        ("Gráfico 2: Evolução temporal", True),
        ("Tabela III - Distribuição amostral", True),
        ("Charge - Crítica social", True),
        ("Esta questão trata de biologia celular", False),
    ]
    for text, expected in test_cases:
        matched = bool(CAPTION_REGEX.search(text))
        assert matched == expected, f"Failed for '{text}': got {matched}, expected {expected}"
    print("  -> OK: CAPTION_REGEX validado!")

def test_synthetic_pdf_extraction_and_2phase_linking():
    print("Testing ExamImageExtractor on synthetic PDF...")
    doc = fitz.open()

    # Create 3 pages with repeated header (watermark)
    for p_no in range(3):
        page = doc.new_page(width=595, height=842)
        # Header drawing at (50, 10, 545, 20) repeated on all 3 pages
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(50, 10, 545, 20))
        shape.finish(color=(0.5, 0.5, 0.5), fill=(0.8, 0.8, 0.8))
        shape.commit()

        if p_no == 0:
            # Add a vector diagram at (100, 150, 300, 280)
            diag_shape = page.new_shape()
            diag_shape.draw_rect(fitz.Rect(100, 150, 300, 280))
            diag_shape.draw_line(fitz.Point(100, 150), fitz.Point(300, 280))
            diag_shape.finish(color=(0, 0, 1), width=2)
            diag_shape.commit()

            # Add caption below diagram
            page.insert_text(fitz.Point(100, 295), "Figura 1 - Circuito elétrico sob teste")

            # Add an orphan diagram at (100, 450, 300, 560)
            orphan_shape = page.new_shape()
            orphan_shape.draw_rect(fitz.Rect(100, 450, 300, 560))
            orphan_shape.finish(color=(1, 0, 0), width=2)
            orphan_shape.commit()

    extractor = ExamImageExtractor(output_dir="static/images/questions_test", dpi=100)

    # 1. Test watermark detection
    watermarks = extractor.detect_watermarks_and_headers(doc)
    assert len(watermarks) >= 1, "Should detect repeated header as watermark"
    print(f"  -> Detected {len(watermarks)} watermark/header rects.")

    # 2. Test cluster finding with caption on page 0
    p0 = doc[0]
    p0_blocks = p0.get_text('blocks')
    clusters = extractor.find_diagram_clusters(p0, watermarks, text_blocks=p0_blocks)
    assert len(clusters) >= 2, f"Expected 2 clusters on page 0, got {len(clusters)}"
    print(f"  -> Found {len(clusters)} clusters on page 0.")

    # Check that caption was included in cluster
    diag_cluster = clusters[0]
    assert diag_cluster.y1 >= 290, "Caption should be included in the cluster"

    # 3. Test 2-Phase linking
    page_diagrams = {0: clusters}
    mock_questions = [
        {
            'numero_questao': '1',
            'enunciado': 'QUESTÃO 1. Com base na Figura 1, calcule a impedância equivalente.',
            'opcoes': {'A': '10 ohms', 'B': '20 ohms'},
            'resposta': 'A',
            'disciplina': 'Física',
            'images': None,
            '_page': 0,
            '_x': 100,
            '_y': 100
        },
        {
            'numero_questao': '2',
            'enunciado': 'QUESTÃO 2. Calcule o fluxo térmico do condutor.',
            'opcoes': {'A': '50 W', 'B': '100 W'},
            'resposta': 'B',
            'disciplina': 'Física',
            'images': None,
            '_page': 0,
            '_x': 100,
            '_y': 400
        }
    ]

    linked_qs = extractor.attach_images_to_questions(
        doc=doc,
        questions=mock_questions,
        page_diagrams=page_diagrams,
        exam_id=999
    )

    # Question 1 should get image via Phase 1 (Trigger Word)
    assert linked_qs[0]['images'] is not None and len(linked_qs[0]['images']) >= 1
    assert "qimg_exam999_q1_1.png" in linked_qs[0]['images'][0]
    print(f"  -> Q1 linked image (Phase 1 Trigger): {linked_qs[0]['images']}")

    # Question 2 should get orphan image via Phase 2 (Gap Visual Scan)
    assert linked_qs[1]['images'] is not None and len(linked_qs[1]['images']) >= 1
    print(f"  -> Q2 linked image (Phase 2 Gap Scan): {linked_qs[1]['images']}")

    # Test MD5 deduplication
    prev_hash_count = len(extractor.saved_image_hashes)
    dup_url = extractor.render_and_save_crop(p0, clusters[0], exam_id=999, q_num='dup', img_index=1)
    assert len(extractor.saved_image_hashes) == prev_hash_count, "MD5 deduplication should not create a duplicate entry"

    doc.close()
    print("  -> OK: Synthetic PDF extraction and 2-phase linking passed!")

def test_real_pdf_pipeline_with_images():
    print("Testing real PDF pipeline with image extraction...")
    pdf_files = [f for f in glob.glob("pdfs/*.pdf") if "_gab_" not in f]
    if not pdf_files:
        print("  -> No PDF files found in pdfs/, skipping.")
        return

    sample_pdf = pdf_files[0]
    print(f"  -> Parsing {sample_pdf}...")
    questions = parse_exam_document(sample_pdf, exam_id=123, extract_images=True)
    assert len(questions) > 0, "Should extract questions"
    
    total_imgs = sum(len(q['images']) for q in questions if q.get('images'))
    print(f"  -> Extracted {len(questions)} questions with {total_imgs} total linked images.")
    print("  -> OK: Real PDF processing succeeded!")

if __name__ == '__main__':
    test_image_trigger_regex()
    test_caption_regex()
    test_synthetic_pdf_extraction_and_2phase_linking()
    test_real_pdf_pipeline_with_images()
    print("\n🎉 SUCCESS: Todos os testes do ExamImageExtractor passaram com 100% de sucesso!")
