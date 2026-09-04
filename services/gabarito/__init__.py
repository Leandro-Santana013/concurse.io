"""
concurse.io — Domínio de Gabaritos (Extração, Parsing e Fusão)
"""

from .gabarito_service import (
    parse_gabarito_from_pdf,
    parse_gabarito_from_text,
    merge_exam_with_gabarito,
    format_gabarito_summary,
    extract_gabarito_from_doc,
    extract_exam_code_ranges_from_pdf,
    extract_answer_key_blocks,
    _extract_gabarito_from_doc,
)
from .matching_service import (
    AnswerKeyMatchResult,
    ExamAnswerKeyProfile,
    build_exam_answer_key_profile,
    explicit_answer_key_result,
    has_complete_official_answer_key,
    match_gabarito_from_pdf,
)

__all__ = [
    "parse_gabarito_from_pdf",
    "parse_gabarito_from_text",
    "merge_exam_with_gabarito",
    "format_gabarito_summary",
    "extract_gabarito_from_doc",
    "extract_exam_code_ranges_from_pdf",
    "extract_answer_key_blocks",
    "_extract_gabarito_from_doc",
    "AnswerKeyMatchResult",
    "ExamAnswerKeyProfile",
    "build_exam_answer_key_profile",
    "explicit_answer_key_result",
    "has_complete_official_answer_key",
    "match_gabarito_from_pdf",
]
