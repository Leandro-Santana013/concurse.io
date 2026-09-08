import io
import json

import fitz
from PIL import Image

from services.pdf_pipeline import (
    BBox,
    DocumentModel,
    PhysicalExtractor,
    PipelineMode,
    get_pipeline_mode,
)
from services.pdf_pipeline.legacy import (
    LegacyParserContext,
    build_default_legacy_registry,
    build_legacy_snapshot,
    write_legacy_snapshot,
)


def _new_pdf_with_text() -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((20, 40), "Questão 1: texto preservado", fontname="helv", fontsize=12)
    page.insert_text((20, 80), "Título em negrito", fontname="hebo", fontsize=14)
    page.insert_text((20, 110), "Texto em itálico", fontname="heit", fontsize=11)
    return doc


def test_bbox_normalizes_absolute_coordinates():
    bbox = BBox.from_absolute(10, 20, 110, 220, 200, 400)

    assert bbox.to_dict() == {
        "x0": 10.0,
        "y0": 20.0,
        "x1": 110.0,
        "y1": 220.0,
        "nx0": 0.05,
        "ny0": 0.05,
        "nx1": 0.55,
        "ny1": 0.55,
    }


def test_physical_extractor_preserves_text_style_and_avoids_question_parsing():
    doc = _new_pdf_with_text()
    try:
        model = PhysicalExtractor(
            use_ocr=False,
            include_tables=False,
        ).extract(doc)
    finally:
        doc.close()

    elements = model.pages[0].elements
    text_elements = [element for element in elements if element.kind == "text"]
    text = "".join(element.text or "" for element in text_elements)

    assert "Questão 1: texto preservado" in text
    assert any(element.source == "pdf_text" for element in text_elements)
    assert any(element.bold for element in text_elements)
    assert any(element.italic for element in text_elements)
    page = model.pages[0]
    assert all(
        abs(element.bbox.nx0 - element.bbox.x0 / page.width) < 1e-9
        and abs(element.bbox.nx1 - element.bbox.x1 / page.width) < 1e-9
        for element in elements
    )
    assert all(
        abs(element.bbox.ny0 - element.bbox.y0 / page.height) < 1e-9
        and abs(element.bbox.ny1 - element.bbox.y1 / page.height) < 1e-9
        for element in elements
    )
    assert "questions" not in model.to_dict()


def test_physical_extractor_represents_images_drawings_and_serializes():
    doc = fitz.open()
    page = doc.new_page(width=240, height=320)
    image = Image.new("RGB", (20, 20), (220, 40, 40))
    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    page.insert_image(fitz.Rect(40, 100, 120, 180), stream=image_buffer.getvalue())
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(140, 100, 210, 170))
    shape.finish(color=(0, 0, 1), width=2)
    shape.commit()

    try:
        model = PhysicalExtractor(
            use_ocr=False,
            include_tables=False,
        ).extract(doc)
    finally:
        doc.close()

    kinds = {element.kind for element in model.pages[0].elements}
    assert "image" in kinds
    assert "drawing" in kinds

    round_trip = DocumentModel.from_json(model.to_json())
    assert round_trip.page_count == 1
    assert len(round_trip.pages[0].elements) == len(model.pages[0].elements)
    assert json.loads(model.to_json())["schema_version"] == 1


def test_ocr_elements_keep_origin_and_confidence():
    doc = fitz.open()
    doc.new_page(width=200, height=300)

    def fake_reader(page, dpi):
        assert dpi == 144
        return [
            {
                "bbox": (20, 30, 100, 45),
                "text": "texto vindo do OCR",
                "confidence": 0.87,
            }
        ]

    try:
        model = PhysicalExtractor(
            use_ocr=True,
            ocr_dpi=144,
            include_tables=False,
            ocr_reader=fake_reader,
        ).extract(doc)
    finally:
        doc.close()

    ocr_elements = [
        element for element in model.pages[0].elements if element.source == "ocr"
    ]
    assert len(ocr_elements) == 1
    assert ocr_elements[0].text == "texto vindo do OCR"
    assert ocr_elements[0].source_confidence == 0.87
    assert ocr_elements[0].metadata["fallback_reason"] == "no_native_text"
    assert model.pages[0].raster_features["ocr_used"] is True


def test_debug_export_uses_exam_scoped_path(tmp_path):
    doc = _new_pdf_with_text()
    try:
        model = PhysicalExtractor(use_ocr=False, include_tables=False).extract(doc)
    finally:
        doc.close()

    from services.pdf_pipeline.structural import export_page_model_debug

    path = export_page_model_debug(model, artifacts_dir=tmp_path, exam_id="exam/42")
    assert path == tmp_path / "exam_42" / "page_model.json"
    assert json.loads(path.read_text(encoding="utf-8"))["page_count"] == 1


def test_legacy_registry_exposes_known_rules_and_snapshot_shape(tmp_path, monkeypatch):
    monkeypatch.delenv("PDF_PIPELINE_MODE", raising=False)
    monkeypatch.delenv("STRUCTURAL_PIPELINE_MODE", raising=False)
    assert get_pipeline_mode() is PipelineMode.LEGACY_ONLY

    registry = build_default_legacy_registry()
    for name in ("dataprev", "ibam", "idcap"):
        adapter = registry.get(name)
        context = LegacyParserContext(declared_banca=name)
        assert adapter.supports(context) > 0.0
        assert registry.resolve(context).name == name

    questions = [
        {
            "numero_questao": "1",
            "question_index": 0,
            "enunciado": "Enunciado",
            "opcoes": {"A": "Uma opção"},
            "images": None,
            "disciplina": "Geral",
            "resposta": "A",
        }
    ]
    snapshot = build_legacy_snapshot(questions, source="fixture.pdf", adapter_name="idcap")
    assert snapshot["questions"][0]["statement"] == "Enunciado"
    assert snapshot["questions"][0]["options"] == {"A": "Uma opção"}
    assert snapshot["questions"][0]["correct_answer"] == "A"

    output = write_legacy_snapshot(
        tmp_path / "legacy.json",
        questions,
        source="fixture.pdf",
        adapter_name="idcap",
    )
    assert json.loads(output.read_text(encoding="utf-8"))["adapter"] == "idcap"
