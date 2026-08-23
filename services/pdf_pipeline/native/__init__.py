"""
concurse.io — Camada de Aceleração Nativa em Rust (concurse_core)
"""

from .rust_bridge import (
    is_rust_available,
    rust_process_exam_text,
    rust_restore_typography,
    rust_restore_ocr_lexical_spacing,
    rust_classify_subject,
    rust_scan_subject_sections,
    rust_match_image_triggers,
    concurse_core,
)

__all__ = [
    "is_rust_available",
    "rust_process_exam_text",
    "rust_restore_typography",
    "rust_restore_ocr_lexical_spacing",
    "rust_classify_subject",
    "rust_scan_subject_sections",
    "rust_match_image_triggers",
    "concurse_core",
]
