"""
concurse.io — Domínio de Gabaritos (Extração, Parsing e Fusão)
"""

from .gabarito_service import (
    parse_gabarito_from_pdf,
    parse_gabarito_from_text,
    merge_exam_with_gabarito,
    format_gabarito_summary,
    extract_gabarito_from_doc,
    _extract_gabarito_from_doc,
)

__all__ = [
    "parse_gabarito_from_pdf",
    "parse_gabarito_from_text",
    "merge_exam_with_gabarito",
    "format_gabarito_summary",
    "extract_gabarito_from_doc",
    "_extract_gabarito_from_doc",
]
