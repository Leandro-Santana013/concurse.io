import json

from services.pdf_pipeline.structural import (
    BBox,
    DocumentModel,
    EdgeType,
    PageModel,
    PhysicalElement,
    StructuralAnalyzer,
)
from services.pdf_pipeline.structural.candidates.features import (
    QUESTION_HEADER_FEATURES,
    FeatureSchemaV1,
)


PAGE_WIDTH = 1000.0
PAGE_HEIGHT = 1000.0


def _text(page, element_id, x0, y0, x1, y1, text, *, font_size=10.0, bold=False):
    return PhysicalElement(
        id=element_id,
        page_index=page,
        kind="text",
        bbox=BBox.from_absolute(x0, y0, x1, y1, PAGE_WIDTH, PAGE_HEIGHT),
        text=text,
        font_family="Helvetica",
        font_size=font_size,
        bold=bold,
    )


def _image(page, element_id, x0, y0, x1, y1):
    return PhysicalElement(
        id=element_id,
        page_index=page,
        kind="image",
        bbox=BBox.from_absolute(x0, y0, x1, y1, PAGE_WIDTH, PAGE_HEIGHT),
        source="raster",
    )


def _document(*pages):
    return DocumentModel(pages=list(pages), metadata={"declared_banca": "IBAM"})


def test_question_headers_have_schema_v1_and_decomposable_scores():
    page = PageModel(
        page_index=0,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        elements=[
            _text(0, "q12", 80, 80, 180, 105, "Questão 12", font_size=12, bold=True),
            _text(0, "body12", 80, 125, 850, 150, "Assinale a alternativa correta."),
            _text(0, "q13", 80, 260, 145, 285, "13."),
            _text(0, "body13", 80, 305, 850, 330, "Outro enunciado."),
            _text(0, "q14", 80, 440, 110, 465, "14"),
            _text(0, "body14", 80, 485, 850, 510, "Mais um enunciado."),
            _text(0, "false-number", 80, 560, 850, 585, "O artigo 15 da lei não é um cabeçalho."),
        ],
    )

    result = StructuralAnalyzer().analyze(_document(page))
    numbers = [item.metadata["question_number"] for item in result.question_candidates]

    assert {12, 13, 14}.issubset(numbers)
    assert 15 not in numbers
    candidate = next(item for item in result.question_candidates if item.metadata["question_number"] == 12)
    assert candidate.features.schema_version == 1
    assert set(QUESTION_HEADER_FEATURES).issubset(candidate.features.values)
    assert set(candidate.score_breakdown) >= {
        "numeric",
        "sequential",
        "same_alignment",
        "same_style_cluster",
        "options_below",
        "regex",
        "vertical_structure",
    }
    assert candidate.evidence["legacy_bank_header_match"] >= 0.0
    assert FeatureSchemaV1.to_dict()["feature_schema_version"] == 1


def test_option_alternatives_context_and_cross_page_image_region():
    page0 = PageModel(
        page_index=0,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        elements=[
            _text(0, "q21", 80, 70, 180, 95, "Questão 21", bold=True),
            _text(0, "ctx", 80, 120, 850, 145, "Texto para as questões 21 a 22:"),
            _text(0, "ctx-body", 80, 155, 850, 205, "Leia o texto compartilhado para responder às duas questões."),
            _text(0, "statement21", 80, 230, 850, 260, "Conforme a figura abaixo, escolha a resposta."),
            _image(0, "figure21", 250, 285, 750, 470),
            _text(0, "opt-a", 100, 500, 850, 525, "A) primeira alternativa"),
            _text(0, "opt-b", 100, 535, 850, 560, "B) segunda alternativa"),
            _text(0, "opt-c", 100, 570, 850, 595, "C) terceira alternativa"),
            _text(0, "opt-d", 100, 605, 850, 630, "D) quarta alternativa"),
        ],
    )
    page1 = PageModel(
        page_index=1,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        elements=[
            _text(1, "continued", 80, 70, 850, 120, "Continuação do contexto e do enunciado."),
            _text(1, "q22", 80, 250, 180, 275, "22.", bold=True),
            _text(1, "statement22", 80, 300, 850, 330, "Segundo o texto, assinale a opção correta."),
            _text(1, "bullet-a", 100, 365, 850, 390, "• uma alternativa"),
            _text(1, "bullet-b", 100, 400, 850, 425, "• outra alternativa"),
            _text(1, "bullet-c", 100, 435, 850, 460, "• mais uma alternativa"),
            _text(1, "bullet-d", 100, 470, 850, 495, "• última alternativa"),
            _text(1, "check-a", 100, 550, 850, 575, "☐ primeira escolha"),
            _text(1, "check-b", 100, 585, 850, 610, "☐ segunda escolha"),
            _text(1, "check-c", 100, 620, 850, 645, "☐ terceira escolha"),
            _text(1, "check-d", 100, 655, 850, 680, "☐ quarta escolha"),
        ],
    )

    result = StructuralAnalyzer().analyze(_document(page0, page1))
    labels = [item.metadata.get("labels") for item in result.option_candidates]
    marker_types = [item.metadata.get("marker_types") for item in result.option_candidates]

    assert any(labels_item and labels_item[:4] == ["A", "B", "C", "D"] for labels_item in labels)
    assert any("bullet" in (types or []) for types in marker_types)
    assert any("checkbox" in (types or []) for types in marker_types)
    assert len(result.question_regions) == 2
    first_region = result.question_regions[0]
    assert first_region.metadata["cross_page"] is True
    assert "figure21" in first_region.image_element_ids
    assert result.image_ownership
    assert result.image_ownership[0].evidence["inside_question_region"] == 1.0
    assert result.context_blocks
    assert set(result.context_blocks[0].question_numbers) == {21, 22}
    assert set(result.context_blocks[0].applies_to_candidate_ids) == {
        result.question_regions[0].question_candidate_id,
        result.question_regions[1].question_candidate_id,
    }
    assert any(
        edge.relation == EdgeType.APPLIES_TO.value
        for edge in result.graph.edges()
    )


def test_graph_is_sparse_and_trace_is_serializable():
    elements = [
        _text(0, f"line-{index}", 80, 50 + index * 12, 900, 60 + index * 12, f"linha {index}")
        for index in range(420)
    ]
    result = StructuralAnalyzer().analyze(
        _document(
            PageModel(
                page_index=0,
                width=PAGE_WIDTH,
                height=PAGE_HEIGHT,
                elements=elements,
            )
        )
    )
    stats = result.graph.stats()
    assert stats["edge_count"] < stats["node_count"] * 30
    trace = result.trace()
    assert trace["pipeline_version"] == "structural-v1"
    assert "document_profile" in trace
    assert "question_candidates" in trace
    assert "graph_stats" in trace
    json.loads(result.to_json())
