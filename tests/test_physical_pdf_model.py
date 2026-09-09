import io
import json

import fitz
from PIL import Image

from services.pdf_pipeline.structural import BBox, DocumentModel, PhysicalExtractor


def _text_pdf() -> fitz.Document:
    document = fitz.open()
    page = document.new_page(width=200, height=300)
    page.insert_text((20, 40), "Questão 1: texto preservado", fontname="helv", fontsize=12)
    page.insert_text((20, 80), "Título em negrito", fontname="hebo", fontsize=14)
    page.insert_text((20, 110), "Texto em itálico", fontname="heit", fontsize=11)
    return document


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


def test_physical_extractor_preserves_text_style_without_question_parsing():
    document = _text_pdf()
    try:
        model = PhysicalExtractor(use_ocr=False, include_tables=False).extract(document)
    finally:
        document.close()

    page = model.pages[0]
    text_elements = [element for element in page.elements if element.kind == "text"]
    text = "".join(element.text or "" for element in text_elements)

    assert "Questão 1: texto preservado" in text
    assert any(element.bold for element in text_elements)
    assert any(element.italic for element in text_elements)
    assert all(
        abs(element.bbox.nx0 - element.bbox.x0 / page.width) < 1e-9
        and abs(element.bbox.nx1 - element.bbox.x1 / page.width) < 1e-9
        for element in page.elements
    )
    assert "questions" not in model.to_dict()


def test_physical_extractor_represents_images_drawings_and_round_trips_json():
    document = fitz.open()
    page = document.new_page(width=240, height=320)
    image = Image.new("RGB", (20, 20), (220, 40, 40))
    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    page.insert_image(fitz.Rect(40, 100, 120, 180), stream=image_buffer.getvalue())
    shape = page.new_shape()
    shape.draw_rect(fitz.Rect(140, 100, 210, 170))
    shape.finish(color=(0, 0, 1), width=2)
    shape.commit()

    try:
        model = PhysicalExtractor(use_ocr=False, include_tables=False).extract(document)
    finally:
        document.close()

    kinds = {element.kind for element in model.pages[0].elements}
    assert "image" in kinds
    assert "drawing" in kinds

    round_trip = DocumentModel.from_json(model.to_json())
    assert round_trip.page_count == 1
    assert len(round_trip.pages[0].elements) == len(model.pages[0].elements)
    assert json.loads(model.to_json())["schema_version"] == 1


def test_physical_extractor_keeps_injected_ocr_origin_and_confidence():
    document = fitz.open()
    document.new_page(width=200, height=300)

    def fake_reader(page, dpi):
        assert dpi == 144
        return [{"bbox": (20, 30, 100, 45), "text": "texto OCR", "confidence": 0.87}]

    try:
        model = PhysicalExtractor(
            use_ocr=True,
            ocr_dpi=144,
            include_tables=False,
            ocr_reader=fake_reader,
        ).extract(document)
    finally:
        document.close()

    ocr_elements = [
        element for element in model.pages[0].elements if element.source == "ocr"
    ]
    assert len(ocr_elements) == 1
    assert ocr_elements[0].text == "texto OCR"
    assert ocr_elements[0].source_confidence == 0.87
    assert ocr_elements[0].metadata["fallback_reason"] == "no_native_text"
    assert model.pages[0].raster_features["ocr_used"] is True
