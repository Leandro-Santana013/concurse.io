"""Deep layout-analysis interface built on the physical document model."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import fitz
import numpy as np

from ..model import DocumentModel
from .clustering import cluster_alignment_elements, cluster_style_elements
from .columns import ColumnModeler
from .config import LayoutAnalyzerConfig
from .gutter import GutterDetector, Rasterizer
from .models import ElementLayout, LayoutAnalysis, PageLayout
from .profile import build_document_profile
from .reading_order import build_reading_order
from .zones import detect_repeated_zones


class LayoutAnalyzer:
    """Auto-calibrate layout evidence without selecting a bank parser.

    Interface:
        ``analyze(document_model) -> LayoutAnalysis``

    The implementation combines selective projections, guarded GMM column
    evidence, robust DBSCAN clusters and structural reading-order links. It
    does not assign question, option or subject semantics.
    """

    def __init__(
        self,
        config: Optional[LayoutAnalyzerConfig] = None,
        *,
        rasterizer: Optional[Rasterizer] = None,
    ) -> None:
        self.config = config or LayoutAnalyzerConfig()
        self._rasterizer = rasterizer

    def analyze(self, document: DocumentModel) -> LayoutAnalysis:
        zones = detect_repeated_zones(document, config=self.config.zones)
        rasterizer = self._rasterizer or self._default_rasterizer(document)
        gutter_detector = GutterDetector(
            self.config.gutter,
            rasterizer=rasterizer,
        )
        column_modeler = ColumnModeler(self.config.columns)
        topology_hint = document.metadata.get("legacy_topology")

        page_detections = []
        for page in document.pages:
            gutter = gutter_detector.detect(page)
            columns = column_modeler.detect(page, gutter)
            page_detections.append((page, gutter, columns))

        alignment_clusters, alignment_mapping = cluster_alignment_elements(
            document,
            config=self.config.clustering,
        )
        style_clusters, style_mapping = cluster_style_elements(
            document,
            config=self.config.clustering,
        )

        page_layouts: list[PageLayout] = []
        for page, gutter, columns in page_detections:
            elements = [
                ElementLayout(
                    element_id=element.id,
                    page_index=page.page_index,
                    column_id=columns.assignments.get(element.id),
                    is_spanning=element.id in columns.spanning_ids,
                    roles=list(zones.element_roles.get(element.id, [])),
                    alignment_cluster_id=alignment_mapping.get(element.id),
                    style_cluster_id=style_mapping.get(element.id),
                )
                for element in page.elements
            ]
            reading_order = build_reading_order(
                page,
                elements,
                columns.columns,
                topology_hint=topology_hint,
                requested_mode=self.config.reading_order_mode,
                line_bucket_factor=self.config.line_bucket_factor,
            )
            page_layouts.append(
                PageLayout(
                    page_index=page.page_index,
                    columns=columns.columns,
                    gutter=gutter,
                    elements=elements,
                    reading_order=reading_order,
                    column_diagnostics={
                        "selected_k": columns.selected_k,
                        "bics": {str(key): value for key, value in columns.bics.items()},
                        "gmm_features": list(ColumnModeler.FEATURE_NAMES),
                        "gmm_selection": "bic_plus_gutter_and_geometry",
                    },
                )
            )

        profile = build_document_profile(
            document,
            page_layouts,
            zones,
            style_clusters=style_clusters,
            alignment_clusters=alignment_clusters,
            fingerprint_version=self.config.fingerprint_version,
        )
        return LayoutAnalysis(
            pages=page_layouts,
            document_profile=profile,
            zones=zones,
        )

    @staticmethod
    def _default_rasterizer(document: DocumentModel) -> Optional[Rasterizer]:
        source = document.source
        if not source:
            return None
        try:
            source_path = Path(str(source))
        except (TypeError, ValueError):
            return None
        if not source_path.is_file():
            return None

        def rasterize(page_model, dpi: int):
            with fitz.open(source_path) as pdf:
                page = pdf[page_model.page_index]
                matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                array = np.frombuffer(pixmap.samples, dtype=np.uint8)
                channels = max(1, int(pixmap.n))
                return array.reshape(pixmap.height, pixmap.width, channels)

        return rasterize
