"""
concurse.io — Visão Computacional, Recorte de Imagens, Diagramas e OCR
"""

from .diagram_cropper import (
    ExamImageExtractor,
    extract_images_from_pdf,
    find_diagram_clusters,
    extract_and_crop_diagrams,
    get_rapidocr_engine,
    ocr_page_fallback,
    IMAGE_TRIGGER_REGEX,
    CAPTION_REGEX,
    _get_rapidocr_engine,
)
from .vision_pipeline import (
    extract_exam_via_vision_ocr,
)

__all__ = [
    "ExamImageExtractor",
    "extract_images_from_pdf",
    "find_diagram_clusters",
    "extract_and_crop_diagrams",
    "get_rapidocr_engine",
    "ocr_page_fallback",
    "IMAGE_TRIGGER_REGEX",
    "CAPTION_REGEX",
    "_get_rapidocr_engine",
    "extract_exam_via_vision_ocr",
]
