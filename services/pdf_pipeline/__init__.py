"""
concurse.io — Motor Central de Extração de PDFs e Questões
"""

from .layout import (
    detect_layout_and_ordered_blocks,
    detect_watermarks,
    extract_context_blocks,
    LayoutConfig,
)
from .media import (
    ExamImageExtractor,
    extract_images_from_pdf,
    find_diagram_clusters,
    extract_and_crop_diagrams,
    get_rapidocr_engine,
    ocr_page_fallback,
    IMAGE_TRIGGER_REGEX,
    CAPTION_REGEX,
    extract_exam_via_vision_ocr,
)
from .formatters import (
    format_latex_formulas,
    detect_banca_family,
    get_specialized_patterns,
    BancaFamily,
)
from .native import (
    is_rust_available,
    rust_process_exam_text,
    rust_restore_typography,
    rust_restore_ocr_lexical_spacing,
    rust_classify_subject,
    rust_scan_subject_sections,
    rust_match_image_triggers,
)
from .hybrid_extractor import parse_exam_document

__all__ = [
    "detect_layout_and_ordered_blocks",
    "detect_watermarks",
    "extract_context_blocks",
    "LayoutConfig",
    "ExamImageExtractor",
    "extract_images_from_pdf",
    "find_diagram_clusters",
    "extract_and_crop_diagrams",
    "get_rapidocr_engine",
    "ocr_page_fallback",
    "IMAGE_TRIGGER_REGEX",
    "CAPTION_REGEX",
    "extract_exam_via_vision_ocr",
    "format_latex_formulas",
    "detect_banca_family",
    "get_specialized_patterns",
    "BancaFamily",
    "is_rust_available",
    "rust_process_exam_text",
    "rust_restore_typography",
    "rust_restore_ocr_lexical_spacing",
    "rust_classify_subject",
    "rust_scan_subject_sections",
    "rust_match_image_triggers",
    "parse_exam_document",
]
