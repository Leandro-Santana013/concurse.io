from services.pdf_pipeline.parse_cache import (
    PARSE_CACHE_VERSION,
    _image_payload_is_available,
    load_parse_cache,
    prepare_parse_source,
    save_parse_cache,
)


def test_parse_cache_round_trip_is_content_addressed(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_PARSE_CACHE_ENABLED", "1")
    monkeypatch.setenv("PDF_PARSE_CACHE_DIR", str(tmp_path))

    source = b"stable-pdf-content"
    prepared, cache_key = prepare_parse_source(
        source,
        exam_id=72,
        extract_images=False,
        gabarito_override=None,
        force_ocr=False,
        layout_config=None,
    )

    assert prepared == source
    assert cache_key
    assert load_parse_cache(cache_key) is None

    questions = [{
        "numero_questao": "1",
        "enunciado": "Enunciado preservado",
        "opcoes": {"A": "Alternativa"},
        "resposta": "",
        "images": None,
    }]
    save_parse_cache(cache_key, questions, pages=3)

    loaded = load_parse_cache(cache_key)
    assert loaded == (questions, 3)


def test_cache_key_changes_with_parser_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_PARSE_CACHE_ENABLED", "1")
    monkeypatch.setenv("PDF_PARSE_CACHE_DIR", str(tmp_path))

    kwargs = {
        "exam_id": 72,
        "extract_images": False,
        "gabarito_override": None,
        "force_ocr": False,
        "layout_config": None,
    }
    _, first = prepare_parse_source(b"same-pdf", **kwargs)
    _, second = prepare_parse_source(b"same-pdf-changed", **kwargs)
    _, third = prepare_parse_source(b"same-pdf", **{**kwargs, "force_ocr": True})

    assert PARSE_CACHE_VERSION == "legacy-parse-cache-v2"
    assert first != second
    assert first != third


def test_cache_validates_option_image_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    image_path = tmp_path / "static" / "images" / "questions"
    image_path.mkdir(parents=True)
    image_file = image_path / "option.png"
    image_file.write_bytes(b"png")
    question = [{"images": None, "option_images": {"A": "/static/images/questions/option.png"}}]

    assert _image_payload_is_available(question) is True
    image_file.unlink()
    assert _image_payload_is_available(question) is False
