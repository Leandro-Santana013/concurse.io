"""PyMuPDF Physical Extractor and Page Object Model builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import fitz

from ..model import BBox, DocumentModel, PageModel, PhysicalElement
from .drawing_extractor import extract_drawing_elements
from .image_extractor import extract_image_elements
from .ocr_bridge import OCRReader, extract_ocr_elements
from .text_extractor import extract_text_elements, native_text_statistics


class PhysicalExtractor:
    """Extract physical PDF evidence without semantic question parsing."""

    def __init__(
        self,
        *,
        include_images: bool = True,
        include_drawings: bool = True,
        include_tables: bool = True,
        use_ocr: bool = True,
        ocr_dpi: int = 150,
        min_native_text_chars: int = 20,
        ocr_reader: Optional[OCRReader] = None,
    ) -> None:
        self.include_images = include_images
        self.include_drawings = include_drawings
        self.include_tables = include_tables
        self.use_ocr = use_ocr
        self.ocr_dpi = ocr_dpi
        self.min_native_text_chars = min_native_text_chars
        self.ocr_reader = ocr_reader

    def extract(
        self,
        pdf_bytes_or_path: Any,
        *,
        source: Optional[str] = None,
    ) -> DocumentModel:
        """Build a document model and close only documents opened here."""

        document, owns_document = self._open_document(pdf_bytes_or_path)
        pages: list[PageModel] = []
        legacy_topology: Optional[str] = None
        try:
            repeated_rects = self._detect_repeated_rects(document)
            try:
                # Existing N_ORDER/Z_ORDER inference is retained as an
                # evidence signal for Phase 2, never as a bank selector.
                from services.pdf_pipeline.layout.layout_detector import infer_document_topology

                legacy_topology = infer_document_topology(document, repeated_rects)
            except Exception:
                legacy_topology = None
            for page_index, page in enumerate(document):
                pages.append(
                    self._extract_page(
                        page,
                        page_index,
                        watermark_rects=repeated_rects,
                    )
                )
        finally:
            if owns_document:
                document.close()

        resolved_source = source
        if resolved_source is None and isinstance(pdf_bytes_or_path, (str, Path)):
            resolved_source = str(pdf_bytes_or_path)
        return DocumentModel(
            pages=pages,
            source=resolved_source,
            metadata={
                "extractor": "PhysicalExtractor",
                "semantic_question_detection": False,
                "legacy_topology": legacy_topology,
            },
        )

    @staticmethod
    def _open_document(pdf_bytes_or_path: Any) -> tuple[fitz.Document, bool]:
        if isinstance(pdf_bytes_or_path, fitz.Document):
            return pdf_bytes_or_path, False
        if isinstance(pdf_bytes_or_path, (bytes, bytearray)):
            return fitz.open(stream=pdf_bytes_or_path, filetype="pdf"), True
        return fitz.open(pdf_bytes_or_path), True

    @staticmethod
    def _detect_repeated_rects(
        document: fitz.Document,
    ) -> set[tuple[int, int, int, int]]:
        """Reuse the legacy media helper without cropping or assigning ownership."""

        try:
            from services.pdf_pipeline.media.diagram_cropper import ExamImageExtractor

            helper = ExamImageExtractor(
                output_dir="static/images/questions",
                dpi=160,
                watermark_page_threshold=3,
            )
            return helper.detect_watermarks_and_headers(document)
        except Exception:
            return set()

    def _extract_page(
        self,
        page: fitz.Page,
        page_index: int,
        *,
        watermark_rects: set[tuple[int, int, int, int]],
    ) -> PageModel:
        text_elements = extract_text_elements(page, page_index)
        image_elements = (
            extract_image_elements(
                page,
                page_index,
                watermark_rects=watermark_rects,
            )
            if self.include_images
            else []
        )
        drawing_elements = (
            extract_drawing_elements(
                page,
                page_index,
                watermark_rects=watermark_rects,
            )
            if self.include_drawings
            else []
        )
        table_elements = (
            self._extract_table_elements(page, page_index)
            if self.include_tables
            else []
        )

        elements: list[PhysicalElement] = [
            *text_elements,
            *image_elements,
            *drawing_elements,
            *table_elements,
        ]
        native_stats = native_text_statistics(text_elements)
        ocr_reason: Optional[str] = None
        ocr_elements: list[PhysicalElement] = []

        has_degraded_text = native_stats["character_count"] < self.min_native_text_chars
        if self.use_ocr and has_degraded_text:
            ocr_reason = "no_native_text" if not text_elements else "low_native_text"
            ocr_elements = extract_ocr_elements(
                page,
                page_index,
                dpi=self.ocr_dpi,
                reader=self.ocr_reader,
                reason=ocr_reason,
            )
            elements.extend(ocr_elements)

        return PageModel(
            page_index=page_index,
            width=float(page.rect.width),
            height=float(page.rect.height),
            elements=elements,
            raster_features={
                "native_text": native_stats,
                "image_count": len(image_elements),
                "drawing_count": len(drawing_elements),
                "table_count": len(table_elements),
                "ocr_count": len(ocr_elements),
                "ocr_used": bool(ocr_elements),
                "ocr_reason": ocr_reason,
                "repeated_rect_count": len(watermark_rects),
            },
        )

    @staticmethod
    def _extract_table_elements(
        page: fitz.Page,
        page_index: int,
    ) -> list[PhysicalElement]:
        """Reuse the existing table detector as a physical table source."""

        try:
            from services.pdf_pipeline.layout.layout_detector import extract_tables_from_page

            tables = extract_tables_from_page(page)
        except Exception:
            tables = []

        page_width = float(page.rect.width)
        page_height = float(page.rect.height)
        elements: list[PhysicalElement] = []
        for table_index, table in enumerate(tables):
            bbox = table.get("bbox")
            if bbox is None:
                continue
            elements.append(
                PhysicalElement(
                    id=f"p{page_index}-table{table_index}",
                    page_index=page_index,
                    kind="table",
                    bbox=BBox.from_absolute(
                        *bbox,
                        page_width=page_width,
                        page_height=page_height,
                    ),
                    text=table.get("markdown"),
                    source="vector",
                    source_confidence=1.0,
                    metadata={
                        "table_index": table_index,
                        "source_representation": "layout.extract_tables_from_page",
                    },
                )
            )
        return elements
