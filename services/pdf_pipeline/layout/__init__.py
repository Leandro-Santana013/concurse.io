"""
concurse.io — Detecção de Layout Geométrico, Colunas e Ordem de Leitura
"""

from .layout_detector import (
    detect_layout_and_ordered_blocks,
    detect_watermarks,
    extract_context_blocks,
    LayoutConfig,
)

__all__ = [
    "detect_layout_and_ordered_blocks",
    "detect_watermarks",
    "extract_context_blocks",
    "LayoutConfig",
]
