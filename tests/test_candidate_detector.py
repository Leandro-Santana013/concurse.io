from services.pdf_pipeline.structural import (
    BBox,
    CandidateDetector,
    DocumentModel,
    LayoutAnalyzer,
    PageModel,
    PhysicalElement,
)
from services.pdf_pipeline.structural.candidates.features import (
    QUESTION_HEADER_FEATURES,
    FeatureSchemaV1,
)


def _text(element_id, y0, text, *, x0=80, x1=850, font_size=10.0, bold=False):
    return PhysicalElement(
        id=element_id,
        page_index=0,
        kind="text",
        bbox=BBox.from_absolute(x0, y0, x1, y0 + 25, 1000, 1000),
        text=text,
        font_family="Helvetica",
        font_size=font_size,
        bold=bold,
    )


def test_question_headers_and_labeled_options_have_auditable_features():
    page = PageModel(
        page_index=0,
        width=1000,
        height=1000,
        elements=[
            _text("q12", 80, "Questão 12", font_size=12, bold=True),
            _text("body12", 125, "Assinale a alternativa correta."),
            _text("opt-a", 165, "A) primeira alternativa"),
            _text("opt-b", 205, "B) segunda alternativa"),
            _text("opt-c", 245, "C) terceira alternativa"),
            _text("opt-d", 285, "D) quarta alternativa"),
            _text("q13", 380, "13."),
            _text("body13", 425, "Outro enunciado."),
            _text("q14", 540, "14"),
            _text("body14", 585, "Mais um enunciado."),
            _text("false-number", 680, "O artigo 15 da lei não é um cabeçalho."),
        ],
    )
    document = DocumentModel(pages=[page], metadata={"declared_banca": "IBAM"})
    layout = LayoutAnalyzer().analyze(document)
    detection = CandidateDetector().detect(document, layout)

    numbers = [item.metadata["question_number"] for item in detection.question_headers]
    assert {12, 13, 14}.issubset(numbers)
    assert 15 not in numbers
    candidate = next(item for item in detection.question_headers if item.metadata["question_number"] == 12)
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
    assert detection.option_groups
