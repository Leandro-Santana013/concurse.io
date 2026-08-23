"""
concurse.io — Pacote Principal de Serviços
"""

from .search import (
    BANCAS_MAP,
    ORGAOS_MAP,
    CARGOS_MAP,
    ESTADOS_UFS,
    CIDADES_MAP,
    interpret_search_query_deterministic,
    calculate_card_match_score,
    standardize_card_title,
    filter_and_rank_exam_cards,
)
from .crawlers import (
    get_ddgs_class,
    is_administrative_document,
    is_caderno_or_gabarito,
    _search_known_exams,
    _search_qc_provas,
    _scrape_pci_pdfs,
    _scrape_idcap_pdfs,
    _search_pdfs_web,
    clean_text_artifacts,
    parse_html_exam,
)
from .gabarito import (
    parse_gabarito_from_pdf,
    parse_gabarito_from_text,
    merge_exam_with_gabarito,
    format_gabarito_summary,
    extract_gabarito_from_doc,
)
from .diagnostics import (
    inspect_pdf_document,
)
from .pdf_pipeline import (
    parse_exam_document,
    detect_layout_and_ordered_blocks,
    format_latex_formulas,
)

__all__ = [
    "BANCAS_MAP",
    "ORGAOS_MAP",
    "CARGOS_MAP",
    "ESTADOS_UFS",
    "CIDADES_MAP",
    "interpret_search_query_deterministic",
    "calculate_card_match_score",
    "standardize_card_title",
    "filter_and_rank_exam_cards",
    "get_ddgs_class",
    "is_administrative_document",
    "is_caderno_or_gabarito",
    "_search_known_exams",
    "_search_qc_provas",
    "_scrape_pci_pdfs",
    "_scrape_idcap_pdfs",
    "_search_pdfs_web",
    "clean_text_artifacts",
    "parse_html_exam",
    "parse_gabarito_from_pdf",
    "parse_gabarito_from_text",
    "merge_exam_with_gabarito",
    "format_gabarito_summary",
    "extract_gabarito_from_doc",
    "inspect_pdf_document",
    "parse_exam_document",
    "detect_layout_and_ordered_blocks",
    "format_latex_formulas",
]
