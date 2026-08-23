"""
concurse.io — Domínio de Web Scraping e Processamento HTML
"""

from .scraper_service import (
    get_ddgs_class,
    is_administrative_document,
    is_caderno_or_gabarito,
    _search_known_exams,
    _search_qc_provas,
    _scrape_pci_pdfs,
    _scrape_idcap_pdfs,
    _search_pdfs_web,
)
from .html_exam_parser import (
    clean_text_artifacts,
    parse_html_exam,
)

__all__ = [
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
]
