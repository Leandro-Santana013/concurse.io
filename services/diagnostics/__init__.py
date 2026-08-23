"""
concurse.io — Domínio de Diagnósticos e Inspeção de Documentos
"""

from .pdf_inspector import (
    inspect_pdf_document,
    is_administrative_document,
)

__all__ = [
    "inspect_pdf_document",
    "is_administrative_document",
]
