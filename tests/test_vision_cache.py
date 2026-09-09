from services.pdf_pipeline.vision_cache import (
    VISION_CACHE_VERSION,
    load_page_ocr_cache,
    save_page_ocr_cache,
)


def test_page_ocr_cache_round_trip_and_dpi_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_PARSE_CACHE_ENABLED", "1")
    monkeypatch.setenv("PDF_PARSE_CACHE_DIR", str(tmp_path))

    lines = [{
        "page": 0,
        "x0": 10.0,
        "y0": 20.0,
        "x1": 100.0,
        "y1": 30.0,
        "text": "Questão 1",
    }]
    document_sha256 = "a" * 64

    assert load_page_ocr_cache(document_sha256, dpi=200, page_index=0) is None
    save_page_ocr_cache(
        document_sha256,
        dpi=200,
        page_index=0,
        lines=lines,
    )

    assert load_page_ocr_cache(document_sha256, dpi=200, page_index=0) == lines
    assert load_page_ocr_cache(document_sha256, dpi=300, page_index=0) is None
    assert VISION_CACHE_VERSION == "vision-ocr-cache-v1"
