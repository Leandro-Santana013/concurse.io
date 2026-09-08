"""Physical extraction adapters used by the Phase 1 POM."""

from .extractor import PhysicalExtractor
from .ocr_bridge import extract_ocr_elements, read_ocr_lines

__all__ = ["PhysicalExtractor", "extract_ocr_elements", "read_ocr_lines"]
