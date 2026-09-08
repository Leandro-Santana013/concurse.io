"""Phase-4 constraint solver, AST, renderer and shadow tests."""

from dataclasses import replace
import io
import json

import fitz

from services.pdf_pipeline.structural import (
    BBox,
    ConstraintSolver,
    DocumentModel,
    ExamDocumentNode,
    PageModel,
    PhysicalElement,
    PipelineMode,
    StructuralAnalyzer,
    StructuralShadowRunner,
    compare_legacy_structural,
    render_legacy_document,
    render_legacy_question_dict,
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
    return DocumentModel(pages=list(pages), source="phase4-test.pdf")


def _page_with_questions(numbers, *, include_isolated=None):
    elements = []
    step = 220 if include_isolated is not None else 170
    for index, number in enumerate(numbers):
        top = 60 + index * step
        elements.extend(
            [
                _text(0, f"q{number}", 70, top, 210, top + 24, f"Questão {number}", bold=True),
                _text(0, f"body{number}", 70, top + 40, 900, top + 66, f"Enunciado da questão {number}."),
                _text(0, f"a{number}", 90, top + 78, 900, top + 98, "A) primeira alternativa"),
                _text(0, f"b{number}", 90, top + 104, 900, top + 124, "B) segunda alternativa"),
                _text(0, f"c{number}", 90, top + 130, 900, top + 150, "C) terceira alternativa"),
                _text(0, f"d{number}", 90, top + 156, 900, top + 176, "D) quarta alternativa"),
            ]
        )
    if include_isolated is not None:
        elements.append(_text(0, f"isolated{include_isolated}", 70, 250, 130, 270, f"{include_isolated}."))
    return PageModel(page_index=0, width=PAGE_WIDTH, height=PAGE_HEIGHT, elements=elements)


def _analysis(document):
    return StructuralAnalyzer().analyze(document)


def test_solver_prefers_global_sequence_and_uses_answer_key_as_support_only():
    analysis = _analysis(_document(_page_with_questions([1, 99, 2, 3])))
    solution = ConstraintSolver().solve(analysis, answer_key={1: "A", 2: "B", 3: "C"})

    assert solution.printed_numbers[:3] == [1, 2, 3]
    assert 99 not in solution.printed_numbers
    assert solution.confidence.answer_key_coverage == 1.0
    assert solution.metadata["score_formula"]["answer_key_support"]


def test_localized_recovery_finds_q12_between_q11_and_q13_without_global_relaxation():
    document = _document(_page_with_questions([11, 13], include_isolated=12))
    original = _analysis(document)
    kept = [candidate for candidate in original.question_candidates if candidate.metadata.get("question_number") in {11, 13}]
    analysis = replace(original, question_candidates=kept)

    solution = ConstraintSolver().solve(
        analysis,
        document=document,
        answer_key={11: "A", 12: "B", 13: "C"},
    )

    assert solution.printed_numbers == [11, 12, 13]
    assert len(solution.recovered_candidates) == 1
    recovered = solution.recovered_candidates[0]
    assert recovered.metadata["recovery_source"] == "physical_element"
    assert recovered.source_element_ids == ["isolated12"]
    assert solution.metadata["recovery"][0]["number"] == 12


def test_duplicate_and_mismatched_answer_key_are_auditable():
    document = _document(_page_with_questions([1, 2]))
    original = _analysis(document)
    first = next(item for item in original.question_candidates if item.metadata.get("question_number") == 1)
    duplicate = replace(
        first,
        id="question-header:duplicate-q1",
        score=max(0.2, first.score - 0.15),
        metadata={**first.metadata, "line_text": "1."},
    )
    analysis = replace(original, question_candidates=[first, duplicate, *[
        item for item in original.question_candidates if item is not first and item.metadata.get("question_number") != 1
    ]])

    solution = ConstraintSolver().solve(
        analysis,
        document=document,
        answer_key={1: "A", 2: "B", 3: "C"},
    )

    assert solution.printed_numbers == [1, 2]
    assert any(item.rule == "unique_printed_number" for item in solution.violations)
    assert "answer_key_without_candidate" in solution.warnings
    assert solution.confidence.answer_key_coverage < 1.0


def test_overlap_is_impossible_and_ast_keeps_cross_page_source_trace():
    page0 = PageModel(
        page_index=0,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        elements=[
            _text(0, "q1", 70, 60, 180, 84, "Questão 1", bold=True),
            _text(0, "body1", 70, 100, 900, 130, "Enunciado que continua na página seguinte."),
            _text(0, "a1", 90, 160, 900, 182, "A) primeira"),
            _text(0, "b1", 90, 188, 900, 210, "B) segunda"),
            _text(0, "c1", 90, 216, 900, 238, "C) terceira"),
            _text(0, "d1", 90, 244, 900, 266, "D) quarta"),
        ],
    )
    page1 = PageModel(
        page_index=1,
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        elements=[
            _text(1, "continuation", 70, 70, 900, 100, "A continuação do enunciado permanece rastreável."),
            _text(1, "q2", 70, 300, 180, 324, "Questão 2", bold=True),
            _text(1, "body2", 70, 340, 900, 370, "Segundo enunciado."),
        ],
    )
    document = _document(page0, page1)
    analysis = _analysis(document)
    solution = ConstraintSolver().solve(analysis, document=document, answer_key={1: "A", 2: "B"})

    overlapping_regions = [
        analysis.question_regions[0],
        replace(
            analysis.question_regions[1],
            content_element_ids=list(analysis.question_regions[0].content_element_ids),
        ),
    ]
    overlap_solution = ConstraintSolver().solve(
        replace(analysis, question_regions=overlapping_regions),
        document=document,
        answer_key={1: "A", 2: "B"},
    )
    assert any(item.rule == "region_non_overlap" for item in overlap_solution.violations)

    ast = __import__("services.pdf_pipeline.structural", fromlist=["QuestionASTBuilder"]).QuestionASTBuilder().build(
        document, analysis, solution, answer_key={1: "A", 2: "B"}
    )
    q1 = ast.questions[0]
    assert "continuation" in q1.source_element_ids
    assert q1.statement_nodes[0].page_indices == [0, 1]
    assert json.loads(ast.to_json())["questions"][0]["header"]["source_element_ids"]
    assert all(
        not ({left.question_candidate_id, right.question_candidate_id} == {"missing", "missing2"})
        for left in analysis.question_regions
        for right in analysis.question_regions
    )


def test_renderer_is_schema_compatible_and_ast_is_round_trippable():
    question = {
        "node_type": "QuestionNode",
        "source_element_ids": ["q1", "body1"],
        "metadata": {},
        "canonical_index": 1,
        "printed_number": "1",
        "header": {
            "node_type": "QuestionHeaderNode",
            "source_element_ids": ["q1"],
            "metadata": {},
            "printed_number": "1",
            "text": "Questão 1",
            "confidence": 0.9,
            "candidate_id": "question-header:q1",
        },
        "statement_nodes": [{
            "node_type": "StatementNode",
            "source_element_ids": ["body1"],
            "metadata": {},
            "text": "Escolha a alternativa correta.",
            "page_indices": [0],
        }],
        "option_group": {
            "node_type": "OptionGroupNode",
            "source_element_ids": ["a1", "b1"],
            "metadata": {},
            "options": [
                {"node_type": "OptionNode", "source_element_ids": ["a1"], "metadata": {}, "key": "A", "text": "uma"},
                {"node_type": "OptionNode", "source_element_ids": ["b1"], "metadata": {}, "key": "B", "text": "duas"},
            ],
            "confidence": 0.8,
            "marker_types": ["label"],
        },
        "figures": [],
        "tables": [],
        "context_refs": [],
        "subject": "Direito",
        "confidence": 0.9,
        "evidence": {},
        "answer": "B",
        "region_id": None,
    }
    rendered = render_legacy_question_dict(question)
    assert set(rendered) == {
        "numero_questao", "enunciado", "opcoes", "resposta", "disciplina",
        "images", "latex_support", "question_index",
    }
    assert rendered["numero_questao"] == "1"
    assert rendered["opcoes"] == {"A": "uma", "B": "duas"}
    assert rendered["resposta"] == "B"

    document = ExamDocumentNode.from_dict({
        "schema_version": 1,
        "ast_version": "question-ast-v1",
        "node_type": "ExamDocumentNode",
        "source_element_ids": [],
        "metadata": {},
        "contexts": [],
        "questions": [question],
        "source": "fixture.pdf",
        "confidence": None,
        "pipeline_version": "question-ast-v1",
    })
    assert ExamDocumentNode.from_json(document.to_json()).to_dict() == document.to_dict()


def test_shared_context_is_materialized_only_by_compatibility_renderer():
    document = _document(
        PageModel(
            page_index=0,
            width=PAGE_WIDTH,
            height=PAGE_HEIGHT,
            elements=[
                _text(0, "ctx", 70, 50, 900, 75, "Texto para as questões 1 e 2:"),
                _text(0, "ctx-body", 70, 85, 900, 115, "Leia o texto compartilhado."),
                _text(0, "q1", 70, 160, 180, 184, "Questão 1", bold=True),
                _text(0, "body1", 70, 200, 900, 230, "Primeira pergunta."),
                _text(0, "q2", 70, 300, 180, 324, "Questão 2", bold=True),
                _text(0, "body2", 70, 340, 900, 370, "Segunda pergunta."),
            ],
        )
    )
    analysis = _analysis(document)
    solution = ConstraintSolver().solve(analysis, document=document)
    from services.pdf_pipeline.structural import QuestionASTBuilder

    ast = QuestionASTBuilder().build(document, analysis, solution)
    assert len(ast.contexts) == 1
    assert all(ast.contexts[0].context_id in question.context_refs for question in ast.questions)
    rendered = render_legacy_document(ast)
    assert all("Texto de Apoio" in question["enunciado"] for question in rendered)


def test_legacy_only_shadow_and_failed_shadow_never_change_user_result():
    legacy = [{
        "numero_questao": "1",
        "enunciado": "Legado",
        "opcoes": {"A": "uma"},
        "resposta": "A",
        "disciplina": "Geral",
        "images": None,
    }]
    legacy_only = StructuralShadowRunner(mode=PipelineMode.LEGACY_ONLY).run(
        None,
        legacy_result=legacy,
    )
    assert legacy_only.user_result == legacy
    assert legacy_only.structural_result is None

    failed = StructuralShadowRunner(mode=PipelineMode.STRUCTURAL_SHADOW).run(
        b"not a pdf",
        legacy_result=legacy,
    )
    assert failed.user_result == legacy
    assert failed.structural_failed is True
    assert failed.structural_result is None


def test_structural_shadow_generates_semantic_diff_without_replacing_legacy():
    pdf = fitz.open()
    page = pdf.new_page(width=300, height=400)
    page.insert_text((30, 50), "Questão 1", fontname="hebo", fontsize=12)
    page.insert_text((30, 80), "Enunciado de teste.", fontsize=10)
    page.insert_text((30, 120), "A) uma", fontsize=10)
    page.insert_text((30, 145), "B) duas", fontsize=10)
    page.insert_text((30, 170), "C) tres", fontsize=10)
    page.insert_text((30, 195), "D) quatro", fontsize=10)
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    legacy = [{
        "numero_questao": "1",
        "enunciado": "Legado",
        "opcoes": {"A": "uma", "B": "duas"},
        "resposta": "A",
        "disciplina": "Geral",
        "images": None,
    }]

    result = StructuralShadowRunner(mode=PipelineMode.STRUCTURAL_SHADOW).run(
        buffer.getvalue(),
        legacy_result=legacy,
    )

    assert result.user_result == legacy
    assert result.metrics["structural_executed"] is True
    assert result.diff is not None
    assert "option_count" in result.diff.changed_fields


def test_diff_ignores_literal_statement_text():
    legacy = [{"numero_questao": "1", "enunciado": "texto A", "opcoes": {"A": "x"}, "disciplina": "Direito", "images": None}]
    structural = [{"numero_questao": "1", "enunciado": "texto B", "opcoes": {"A": "y"}, "disciplina": "Direito", "images": None}]
    diff = compare_legacy_structural(legacy, structural)
    assert "question_count" not in diff.changed_fields
    assert "question_order" not in diff.changed_fields
    assert "subject" not in diff.changed_fields
