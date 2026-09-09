"""Compatibility rendering from the Question AST to the legacy schema."""

from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from typing import Any, Callable, Mapping, Optional, Sequence

from .question_ast import ContextNode, ExamDocumentNode, QuestionNode
from .solver import AnswerKeyEvidence


def render_legacy_question_dict(
    ast_question: QuestionNode | Mapping[str, Any],
    *,
    contexts: Optional[Mapping[str, ContextNode | Mapping[str, Any]]] = None,
    answer_key: Any = None,
    question_index: Optional[int] = None,
    late_formatting: bool = False,
    formatter: Optional[Callable[[str, bool], str]] = None,
) -> dict[str, Any]:
    """Render one AST question using the existing application dictionary.

    The renderer deliberately does not expose AST classes to API/frontend/DB
    callers.  Shared contexts can be materialized here for compatibility with
    the old repeated-text payload; the AST itself keeps a single ContextNode.
    """

    question = (
        QuestionNode.from_dict(ast_question)
        if isinstance(ast_question, ABCMapping)
        else ast_question
    )
    answer = AnswerKeyEvidence.from_value(answer_key)
    statement = "\n\n".join(
        item.text.strip()
        for item in question.statement_nodes
        if str(item.text or "").strip()
    ).strip()
    context_text = _context_text(question, contexts)
    if context_text and context_text not in statement:
        statement = f"{context_text}\n\n---\n\n{statement}".strip()
    if not statement:
        statement = ""
    statement = _format_text(statement, is_option=False, late_formatting=late_formatting, formatter=formatter)

    options: dict[str, str] = {}
    if question.option_group is not None:
        for option in question.option_group.options:
            key = str(option.key or "").strip().upper()
            if not key:
                key = chr(ord("A") + len(options))
            options[key] = _format_text(
                str(option.text or "").strip(),
                is_option=True,
                late_formatting=late_formatting,
                formatter=formatter,
            )

    number = question.printed_number
    answer_value = question.answer
    if number is not None:
        try:
            answer_value = answer.answers.get(int(number), answer_value)
        except (TypeError, ValueError):
            pass
    image_values = _render_images(question)
    return {
        "numero_questao": str(number) if number is not None else "",
        "enunciado": statement,
        "opcoes": options,
        "resposta": str(answer_value or "").strip().upper(),
        "disciplina": question.subject or "Geral",
        "images": image_values or None,
        "latex_support": int(_has_latex(statement)),
        "question_index": (
            int(question_index)
            if question_index is not None
            else max(0, int(question.canonical_index) - 1)
        ),
    }


def render_legacy_document(
    ast_document: ExamDocumentNode | Mapping[str, Any],
    *,
    answer_key: Any = None,
    materialize_context: bool = True,
    late_formatting: bool = False,
    formatter: Optional[Callable[[str, bool], str]] = None,
) -> list[dict[str, Any]]:
    """Render all AST questions without changing the AST or the legacy parser."""

    document = (
        ExamDocumentNode.from_dict(ast_document)
        if isinstance(ast_document, ABCMapping)
        else ast_document
    )
    contexts = {context.context_id: context for context in document.contexts} if materialize_context else None
    return [
        render_legacy_question_dict(
            question,
            contexts=contexts,
            answer_key=answer_key,
            question_index=index,
            late_formatting=late_formatting,
            formatter=formatter,
        )
        for index, question in enumerate(document.questions)
    ]


def _context_text(
    question: QuestionNode,
    contexts: Optional[Mapping[str, ContextNode | Mapping[str, Any]]],
) -> str:
    if not contexts:
        return ""
    parts: list[str] = []
    for context_id in question.context_refs:
        context = contexts.get(context_id)
        if context is None:
            continue
        if isinstance(context, ABCMapping):
            text = str(context.get("text") or "").strip()
            numbers = context.get("applies_to_question_numbers") or []
        else:
            text = str(context.text or "").strip()
            numbers = context.applies_to_question_numbers
        if not text:
            continue
        number_label = ", ".join(str(item) for item in numbers)
        prefix = f"📖 **Texto de Apoio (Questões {number_label}):**\n\n" if number_label else "📖 **Texto de Apoio:**\n\n"
        parts.append(prefix + text)
    return "\n\n".join(parts)


def _render_images(question: QuestionNode) -> list[Any]:
    values: list[Any] = []
    for figure in question.figures:
        metadata = figure.metadata or {}
        value = (
            metadata.get("path")
            or metadata.get("image_path")
            or metadata.get("url")
            or metadata.get("legacy_path")
        )
        if value:
            values.append(value)
        elif figure.source_element_ids:
            values.append(f"source:{figure.source_element_ids[0]}")
    return values


def _format_text(
    text: str,
    *,
    is_option: bool,
    late_formatting: bool,
    formatter: Optional[Callable[[str, bool], str]],
) -> str:
    if not late_formatting:
        return text
    if formatter is not None:
        return str(formatter(text, is_option))
    try:
        from ..fallbacks.typography_restorer import restore_exam_typography
        from ..formatters.formula_formatter import format_latex_formulas

        restored = restore_exam_typography(text, is_option=is_option)
        formatted, _ = format_latex_formulas(restored)
        if not is_option:
            from ..layout.layout_detector import format_markdown_tables_in_text

            formatted = format_markdown_tables_in_text(formatted)
        return formatted
    except Exception:
        # Formatting is deliberately late and optional; AST content remains
        # available if a legacy formatter is unavailable in a minimal runtime.
        return text


def _has_latex(text: str) -> bool:
    return any(token in text for token in ("$", "\\(", "\\[", "\\begin{"))
