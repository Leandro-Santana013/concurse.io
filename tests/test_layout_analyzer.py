import numpy as np

from services.pdf_pipeline.structural import (
    BBox,
    DocumentModel,
    DocumentProfile,
    LayoutAnalyzer,
    LayoutAnalyzerConfig,
    PageModel,
    PhysicalElement,
)


PAGE_WIDTH = 1000.0
PAGE_HEIGHT = 1000.0


def _text(
    page_index,
    element_id,
    x0,
    y0,
    x1,
    y1,
    text="linha de texto",
    *,
    font_size=10.0,
    bold=False,
    italic=False,
    source="pdf_text",
    confidence=1.0,
):
    return PhysicalElement(
        id=element_id,
        page_index=page_index,
        kind="text",
        bbox=BBox.from_absolute(
            x0,
            y0,
            x1,
            y1,
            PAGE_WIDTH,
            PAGE_HEIGHT,
        ),
        text=text,
        font_family="Helvetica",
        font_size=font_size,
        bold=bold,
        italic=italic,
        source=source,
        source_confidence=confidence,
    )


def _column_page(page_index, ranges, *, spanning=False, topology="N_ORDER"):
    elements = []
    if spanning:
        elements.append(
            _text(page_index, f"p{page_index}-title", 50, 70, 950, 100, "titulo")
        )
    for column_index, (x0, x1) in enumerate(ranges):
        for row in range(10):
            elements.append(
                _text(
                    page_index,
                    f"p{page_index}-c{column_index}-r{row}",
                    x0,
                    140 + row * 70,
                    x1,
                    160 + row * 70,
                    f"coluna {column_index} linha {row}",
                )
            )
    return PageModel(
        page_index=page_index,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        elements=elements,
        raster_features={
            "native_text": {
                "element_count": len(elements),
                "character_count": sum(len(element.text or "") for element in elements),
            }
        },
    )


def _document(*pages, topology=None):
    metadata = {}
    if topology:
        metadata["legacy_topology"] = topology
    return DocumentModel(pages=list(pages), metadata=metadata)


def test_gmm_detects_one_two_three_and_asymmetric_columns():
    analyzer = LayoutAnalyzer()

    one = analyzer.analyze(_document(_column_page(0, [(80, 900)])))
    two = analyzer.analyze(_document(_column_page(0, [(70, 420), (580, 930)])))
    three = analyzer.analyze(
        _document(_column_page(0, [(50, 280), (370, 630), (720, 950)]))
    )
    asymmetric = analyzer.analyze(
        _document(_column_page(0, [(55, 390), (575, 950)]))
    )

    assert len(one.pages[0].columns) == 1
    assert len(two.pages[0].columns) == 2
    assert len(three.pages[0].columns) == 3
    assert len(asymmetric.pages[0].columns) == 2
    assert asymmetric.pages[0].columns[0].center_x_norm < 0.35
    assert asymmetric.pages[0].columns[1].center_x_norm > 0.60
    assert any(candidate.score > 0 for candidate in two.pages[0].gutter.candidates)
    assert {"1", "2"}.issubset(two.pages[0].column_diagnostics["bics"])


def test_spanning_elements_are_kept_outside_column_assignments():
    result = LayoutAnalyzer().analyze(
        _document(
            _column_page(
                0,
                [(70, 420), (580, 930)],
                spanning=True,
            )
        )
    )

    title = next(item for item in result.pages[0].elements if item.element_id.endswith("title"))
    assert len(result.pages[0].columns) == 2
    assert title.is_spanning is True
    assert title.column_id is None
    assert result.pages[0].reading_order.sequence[0].endswith("title")


def test_repeated_header_footer_are_marked_without_deleting_elements():
    pages = []
    for page_index in range(3):
        elements = [
            _text(page_index, f"p{page_index}-header", 100, 30, 900, 55, "Caderno oficial"),
            _text(page_index, f"p{page_index}-footer", 420, 940, 580, 965, f"Pagina {page_index + 1}"),
            *_column_page(page_index, [(80, 900)]).elements,
        ]
        pages.append(
            PageModel(
                page_index=page_index,
                width=PAGE_WIDTH,
                height=PAGE_HEIGHT,
                elements=elements,
                raster_features={
                    "native_text": {
                        "character_count": sum(len(element.text or "") for element in elements)
                    }
                },
            )
        )

    result = LayoutAnalyzer().analyze(_document(*pages))
    assert result.zones.header_zone is not None
    assert result.zones.footer_zone is not None
    assert len(result.zones.element_roles) >= 6
    assert all(
        "HEADER_NOISE" in result.zones.element_roles[f"p{index}-header"]
        for index in range(3)
    )
    assert all(
        "FOOTER_NOISE" in result.zones.element_roles[f"p{index}-footer"]
        for index in range(3)
    )
    assert all(
        any(item.element_id == f"p{index}-header" for item in page.elements)
        for index, page in enumerate(result.pages)
    )


def test_reading_order_uses_n_order_and_explicit_next_links():
    page = _column_page(0, [(70, 420), (580, 930)], topology="N_ORDER")
    result = LayoutAnalyzer().analyze(_document(page, topology="N_ORDER"))
    reading = result.pages[0].reading_order

    assert reading.mode == "N_ORDER"
    left = [item.element_id for item in result.pages[0].elements if item.column_id == 0]
    right = [item.element_id for item in result.pages[0].elements if item.column_id == 1]
    assert reading.sequence.index(left[-1]) < reading.sequence.index(right[0])
    assert reading.next_reading_block[reading.sequence[0]] == reading.sequence[1]
    assert reading.next_reading_block[reading.sequence[-1]] is None


def test_scan_gutter_uses_raster_projection_only_when_native_text_is_degraded():
    page = PageModel(
        page_index=0,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        elements=[],
        raster_features={
            "native_text": {"element_count": 0, "character_count": 0},
            "ocr_used": True,
            "ocr_count": 0,
        },
    )

    def rasterizer(page_model, dpi):
        assert dpi == 120
        image = np.full((200, 200, 3), 255, dtype=np.uint8)
        image[:, 20:80] = 0
        image[:, 120:180] = 0
        return image

    result = LayoutAnalyzer(rasterizer=rasterizer).analyze(_document(page))
    gutter = result.pages[0].gutter
    assert gutter.used_raster is True
    assert gutter.source == "raster_projection"
    assert gutter.raster_projection
    assert any(0.35 < candidate.x0_norm < 0.55 for candidate in gutter.candidates)


def test_dbscan_visual_clusters_keep_outliers_and_profile_is_round_trippable():
    page = _column_page(0, [(80, 420), (580, 920)])
    page.elements.append(
        _text(0, "p0-outlier", 930, 900, 990, 925, "OUTLIER", font_size=22, bold=True)
    )
    document = _document(page, topology="N_ORDER")
    first = LayoutAnalyzer().analyze(document)
    second = LayoutAnalyzer().analyze(document)
    profile = first.profile
    restored = DocumentProfile.from_json(profile.to_json())

    assert len(first.profile.style_clusters) >= 1
    outlier = next(item for item in first.pages[0].elements if item.element_id == "p0-outlier")
    assert outlier.style_cluster_id is None
    assert restored.to_dict() == profile.to_dict()
    assert first.profile.fingerprint == second.profile.fingerprint
    assert len(first.profile.fingerprint) == len(first.profile.fingerprint_features)
    assert first.profile.fingerprint_version == "layout-profile-v1"
