"""
concurse.io — Camada de Fallback Puro em Python
===============================================
Fornece implementações puras em Python para processamento tipográfico,
desaglutinação de OCR e classificação taxonômica de matérias,
garantindo execução resiliente caso o motor nativo em Rust (concurse_core)
esteja indisponível ou encontre falhas.
"""

from .typography_restorer import (
    restore_exam_typography,
    restore_ocr_lexical_spacing,
)
from .subject_classifier import (
    SUBJECT_PATTERNS,
    SUBJECT_REGEX,
    format_subject_title,
    _format_subject_title,
    rust_classify_subject,
)

__all__ = [
    "restore_exam_typography",
    "restore_ocr_lexical_spacing",
    "SUBJECT_PATTERNS",
    "SUBJECT_REGEX",
    "format_subject_title",
    "_format_subject_title",
    "rust_classify_subject",
]
