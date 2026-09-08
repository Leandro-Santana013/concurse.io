"""Text-layer and selective raster projection for gutter detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np

from ..model import PageModel, PhysicalElement
from .config import GutterConfig
from .models import GutterCandidate, GutterEvidence


Rasterizer = Callable[[PageModel, int], Any]


@dataclass
class _Projection:
    values: np.ndarray
    band_values: np.ndarray
    occupied_intervals: list[list[float]]
    diagnostics: dict[str, Any]


class GutterDetector:
    """Find persistent empty x-regions without assuming a 50/50 split.

    The text layer is always the first source. Raster projection is evaluated
    only for pages whose physical model indicates a degraded or OCR-heavy text
    layer. This keeps OpenCV out of the normal native-text path.
    """

    def __init__(
        self,
        config: Optional[GutterConfig] = None,
        *,
        rasterizer: Optional[Rasterizer] = None,
    ) -> None:
        self.config = config or GutterConfig()
        self.rasterizer = rasterizer

    def detect(self, page: PageModel) -> GutterEvidence:
        text_projection = self._text_projection(page)
        selected = text_projection
        source = "text_layer"
        used_raster = False
        raster_projection: list[float] = []
        raster_dpi: Optional[int] = None

        if self._needs_raster_projection(page) and self.config.rasterize_scans:
            raster = self._raster_projection(page)
            if raster is not None:
                raster_projection = [float(value) for value in raster.values]
                selected = self._combine_projections(text_projection, raster)
                source = "text_layer+raster" if text_projection.values.any() else "raster_projection"
                used_raster = True
                raster_dpi = self.config.raster_dpi

        candidates = self._find_candidates(selected, source=source)
        return GutterEvidence(
            page_index=page.page_index,
            candidates=candidates,
            projection=[float(value) for value in selected.values],
            raster_projection=raster_projection,
            occupied_intervals=text_projection.occupied_intervals,
            source=source,
            used_raster=used_raster,
            raster_dpi=raster_dpi,
            diagnostics={
                **text_projection.diagnostics,
                "raster_diagnostics": (
                    selected.diagnostics if used_raster else {}
                ),
            },
        )

    def _needs_raster_projection(self, page: PageModel) -> bool:
        native = page.raster_features.get("native_text") or {}
        native_chars = int(native.get("character_count", 0) or 0)
        text_count = sum(1 for item in page.elements if item.kind == "text")
        ocr_count = int(page.raster_features.get("ocr_count", 0) or 0)
        ocr_used = bool(page.raster_features.get("ocr_used"))
        ocr_ratio = ocr_count / max(text_count, 1)
        return (
            native_chars < self.config.scan_native_char_threshold
            or (ocr_used and ocr_ratio >= self.config.scan_ocr_ratio_threshold)
        )

    def _text_projection(self, page: PageModel) -> _Projection:
        text_elements = [item for item in page.elements if item.kind == "text"]
        intervals: list[tuple[float, float, float, float]] = []
        for element in text_elements:
            x0 = max(0.0, min(1.0, float(element.bbox.nx0)))
            x1 = max(0.0, min(1.0, float(element.bbox.nx1)))
            y0 = max(0.0, min(1.0, float(element.bbox.ny0)))
            y1 = max(0.0, min(1.0, float(element.bbox.ny1)))
            if x1 > x0 and y1 >= y0:
                intervals.append((x0, x1, y0, y1))

        values, bands = self._interval_projection(intervals)
        return _Projection(
            values=values,
            band_values=bands,
            occupied_intervals=[[x0, x1] for x0, x1, _, _ in intervals],
            diagnostics={
                "text_element_count": len(text_elements),
                "active_bands": int(np.count_nonzero(bands.sum(axis=1))),
            },
        )

    def _interval_projection(
        self,
        intervals: list[tuple[float, float, float, float]],
    ) -> tuple[np.ndarray, np.ndarray]:
        bins = max(8, int(self.config.bins))
        bands = max(1, int(self.config.persistence_bands))
        projection = np.zeros(bins, dtype=float)
        band_projection = np.zeros((bands, bins), dtype=float)

        for x0, x1, y0, y1 in intervals:
            start = max(0, min(bins - 1, int(np.floor(x0 * bins))))
            end = max(start + 1, min(bins, int(np.ceil(x1 * bins))))
            projection[start:end] += 1.0
            band_start = max(0, min(bands - 1, int(np.floor(y0 * bands))))
            band_end = max(
                band_start + 1,
                min(bands, int(np.ceil(max(y1, y0 + 1e-6) * bands))),
            )
            band_projection[band_start:band_end, start:end] += 1.0

        if projection.max() > 0:
            projection /= projection.max()
        for row_index in range(bands):
            row_max = band_projection[row_index].max()
            if row_max > 0:
                band_projection[row_index] /= row_max
        return projection, band_projection

    def _raster_projection(self, page: PageModel) -> Optional[_Projection]:
        if self.rasterizer is None:
            return None
        try:
            raster = self.rasterizer(page, self.config.raster_dpi)
            array = np.asarray(raster)
        except Exception:
            return None
        if array.size == 0 or array.ndim < 2:
            return None

        diagnostics: dict[str, Any] = {
            "raster_shape": list(array.shape),
            "morphology": False,
            "connected_components": 0,
        }
        try:
            import cv2

            if array.ndim == 3:
                channels = array.shape[2]
                if channels == 4:
                    gray = cv2.cvtColor(array, cv2.COLOR_RGBA2GRAY)
                else:
                    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
            else:
                gray = array.astype(np.uint8)
            _, binary = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
            )
            kernel_size = max(1, int(self.config.morphology_kernel))
            if kernel_size > 1:
                kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
                binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
                diagnostics["morphology"] = True
            component_count, _, _, _ = cv2.connectedComponentsWithStats(binary)
            diagnostics["connected_components"] = max(0, int(component_count) - 1)
            ink = (binary > 0).astype(float)
        except Exception:
            if array.ndim == 3:
                gray = array[..., :3].mean(axis=2)
            else:
                gray = array.astype(float)
            threshold = float(np.quantile(gray, 0.35))
            ink = (gray <= threshold).astype(float)

        projection = ink.mean(axis=0)
        if projection.size == 0:
            return None
        resized = np.interp(
            np.linspace(0, projection.size - 1, max(8, self.config.bins)),
            np.arange(projection.size),
            projection,
        )
        # A raster gap is a low ink projection; the shared candidate finder
        # interprets its values as occupancy after normalizing to the maximum.
        max_value = float(resized.max())
        if max_value > 0:
            resized = resized / max_value
        return _Projection(
            values=resized,
            band_values=np.empty((0, resized.size)),
            occupied_intervals=[],
            diagnostics=diagnostics,
        )

    @staticmethod
    def _combine_projections(text: _Projection, raster: _Projection) -> _Projection:
        if not text.values.any():
            return raster
        if not raster.values.any():
            return text
        values = np.minimum(text.values, raster.values)
        return _Projection(
            values=values,
            band_values=text.band_values,
            occupied_intervals=text.occupied_intervals,
            diagnostics={**text.diagnostics, **raster.diagnostics},
        )

    def _find_candidates(
        self,
        projection: _Projection,
        *,
        source: str,
    ) -> list[GutterCandidate]:
        values = np.asarray(projection.values, dtype=float)
        if values.size == 0 or not values.any():
            return []

        quantile = float(
            np.quantile(values, self.config.low_occupancy_quantile)
        )
        low_threshold = max(0.01, quantile * 0.40)
        low = values <= low_threshold
        candidates: list[GutterCandidate] = []
        start: Optional[int] = None
        for index, is_low in enumerate(np.r_[low, False]):
            if is_low and start is None:
                start = index
            if not is_low and start is not None:
                interval_start = start
                interval_end = index
                x0 = interval_start / values.size
                x1 = interval_end / values.size
                start = None
                if not self._is_candidate_width(x0, x1):
                    continue

                persistence = self._persistence(
                    projection.band_values,
                    start_index=interval_start,
                    end_index=interval_end,
                    low_threshold=low_threshold,
                )
                if projection.band_values.size and persistence < self.config.persistence_threshold:
                    continue
                valley = 1.0 - float(values[interval_start:interval_end].mean())
                score = max(0.0, min(1.0, 0.55 * valley + 0.45 * persistence))
                candidates.append(
                    GutterCandidate(
                        x0_norm=float(x0),
                        x1_norm=float(x1),
                        score=float(score),
                        persistence=float(persistence),
                        source=source,
                    )
                )
        return sorted(candidates, key=lambda item: (-item.score, item.x0_norm))

    def _is_candidate_width(self, x0: float, x1: float) -> bool:
        if x1 - x0 < self.config.min_gutter_width:
            return False
        if x1 - x0 > self.config.max_gutter_width:
            return False
        # Page margins are not column gutters. Keep a central region so a
        # sparse single-column page does not produce its outer whitespace.
        if x1 <= self.config.page_margin or x0 >= 1.0 - self.config.page_margin:
            return False
        return True

    @staticmethod
    def _persistence(
        band_values: np.ndarray,
        *,
        start_index: int,
        end_index: int,
        low_threshold: float,
    ) -> float:
        if band_values.size == 0:
            return 1.0
        start_index = max(0, min(band_values.shape[1], start_index))
        end_index = max(start_index + 1, min(band_values.shape[1], end_index))
        gap_values = band_values[:, start_index:end_index]
        active = band_values.sum(axis=1) > 0
        if not active.any():
            return 1.0
        low_by_band = (gap_values <= low_threshold).all(axis=1)
        return float(low_by_band[active].mean())
