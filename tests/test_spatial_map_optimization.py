import fitz

from services.pdf_pipeline.hybrid_extractor import (
    _build_question_spatial_map,
    _build_question_spatial_map_fast,
    _build_question_spatial_map_legacy,
)


def _synthetic_question_document():
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 80), "QUESTÃO 01\nEnunciado da primeira questão")
    page.insert_text((60, 180), "2. Enunciado da segunda questão")
    page.insert_text((60, 280), "ITEM 03\nEnunciado da terceira questão")
    return doc


def test_fast_spatial_map_preserves_legacy_coordinates_for_common_headers():
    doc = _synthetic_question_document()
    try:
        legacy, _ = _build_question_spatial_map_legacy(doc, 0, len(doc))
        fast, _ = _build_question_spatial_map_fast(doc, 0, len(doc))

        assert {1, 2, 3}.issubset(fast)
        assert fast[1] == legacy[1]
        assert fast[3] == legacy[3]
        # Para cabeçalhos numéricos o mapa rápido usa o início do bloco, sem
        # permitir que uma busca textual coincidente em outro enunciado seja
        # confundida com a posição real da questão.
        assert fast[2][0] == 0
        assert 160 < fast[2][2] < 185
    finally:
        doc.close()


def test_spatial_map_has_configuration_rollback(monkeypatch):
    doc = _synthetic_question_document()
    try:
        expected, _ = _build_question_spatial_map_legacy(doc, 0, len(doc))
        monkeypatch.setenv("PDF_PIPELINE_FAST_SPATIAL_MAP", "0")
        actual, _ = _build_question_spatial_map(doc, 0, len(doc))
        assert actual == expected
    finally:
        doc.close()
