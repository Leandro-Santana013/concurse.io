"""Guarded Gaussian-mixture modeling of page columns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from sklearn.mixture import GaussianMixture

from ..model import PageModel, PhysicalElement
from .config import ColumnConfig
from .models import ColumnModel, GutterEvidence


@dataclass
class ColumnDetection:
    columns: list[ColumnModel]
    assignments: dict[str, Optional[int]] = field(default_factory=dict)
    spanning_ids: set[str] = field(default_factory=set)
    bics: dict[int, float] = field(default_factory=dict)
    selected_k: int = 1


class ColumnModeler:
    """Fit 1..3 GMMs, then require geometric evidence before accepting k>1."""

    FEATURE_NAMES = ("center_x_norm", "x0_norm", "x1_norm", "width_norm")

    def __init__(self, config: Optional[ColumnConfig] = None) -> None:
        self.config = config or ColumnConfig()

    def detect(
        self,
        page: PageModel,
        gutter: GutterEvidence,
    ) -> ColumnDetection:
        text_elements = [element for element in page.elements if element.kind == "text"]
        training_elements = [
            element
            for element in text_elements
            if element.bbox.width / max(page.width, 1e-9) <= self.config.max_training_width
        ]
        features = self._features(training_elements, page)

        models: dict[int, tuple[GaussianMixture, np.ndarray]] = {}
        bics: dict[int, float] = {}
        if len(training_elements) >= 2:
            for k in range(1, min(self.config.max_columns, len(training_elements)) + 1):
                if len(training_elements) < max(2 * k, 4):
                    continue
                if np.unique(features, axis=0).shape[0] < k:
                    continue
                try:
                    model = GaussianMixture(
                        n_components=k,
                        covariance_type=self.config.covariance_type,
                        reg_covar=self.config.reg_covar,
                        random_state=self.config.random_state,
                        n_init=2,
                    )
                    model.fit(features)
                    bics[k] = float(model.bic(features))
                    models[k] = (model, model.predict(features))
                except (ValueError, FloatingPointError):
                    continue

        if 1 not in models:
            return self._fallback(page, text_elements, bics=bics)

        base_bic = bics[1]
        selected_k = 1
        selected_model, selected_labels = models[1]
        selected_quality = -float("inf")
        for k in range(2, min(self.config.max_columns, len(training_elements)) + 1):
            if k not in models:
                continue
            model, labels = models[k]
            candidate = self._evaluate_candidate(
                k,
                model,
                labels,
                training_elements,
                page,
                gutter,
                base_bic,
            )
            if candidate is None:
                continue
            quality = (base_bic - bics[k]) + candidate["gutter_score"]
            if quality > selected_quality:
                selected_quality = quality
                selected_k = k
                selected_model, selected_labels = model, labels

        columns = self._build_columns(
            selected_k,
            selected_model,
            selected_labels,
            training_elements,
            page,
            gutter,
            base_bic,
            bics.get(selected_k),
        )
        assignments, spanning = self._assign_all(page.elements, columns)
        return ColumnDetection(
            columns=columns,
            assignments=assignments,
            spanning_ids=spanning,
            bics=bics,
            selected_k=selected_k,
        )

    def _features(
        self,
        elements: list[PhysicalElement],
        page: PageModel,
    ) -> np.ndarray:
        page_width = max(float(page.width), 1e-9)
        rows = []
        for element in elements:
            x0 = float(element.bbox.x0) / page_width
            x1 = float(element.bbox.x1) / page_width
            rows.append(((x0 + x1) / 2.0, x0, x1, max(0.0, x1 - x0)))
        return np.asarray(rows, dtype=float)

    def _evaluate_candidate(
        self,
        k: int,
        model: GaussianMixture,
        labels: np.ndarray,
        elements: list[PhysicalElement],
        page: PageModel,
        gutter: GutterEvidence,
        base_bic: float,
    ) -> Optional[dict[str, float]]:
        counts = np.bincount(labels, minlength=k)
        minimum_count = max(
            2,
            int(np.ceil(len(elements) * self.config.min_component_fraction)),
        )
        if any(int(count) < minimum_count for count in counts):
            return None

        centers = np.asarray(model.means_[:, 0], dtype=float)
        order = np.argsort(centers)
        sorted_centers = centers[order]
        if np.any(np.diff(sorted_centers) < self.config.min_center_separation):
            return None

        gutter_scores: list[float] = []
        geometric_gaps: list[float] = []
        features = self._features(elements, page)
        for left_component, right_component in zip(order[:-1], order[1:]):
            left_x1 = float(features[labels == left_component, 2].max())
            right_x0 = float(features[labels == right_component, 1].min())
            gap = max(0.0, right_x0 - left_x1)
            geometric_gaps.append(gap)
            midpoint = (float(sorted_centers[len(gutter_scores)]) + float(
                sorted_centers[len(gutter_scores) + 1]
            )) / 2.0
            gutter_scores.append(self._gutter_score_at(gutter, midpoint))

        gutter_score = float(np.mean(gutter_scores)) if gutter_scores else 0.0
        geometry_ok = all(gap >= self.config.min_geometric_gap for gap in geometric_gaps)
        gutter_ok = all(score >= self.config.min_gutter_score for score in gutter_scores)
        bic_gain = base_bic - float(model.bic(features))
        if bic_gain < self.config.min_bic_gain:
            return None
        if not geometry_ok and not gutter_ok:
            return None
        return {
            "bic_gain": float(bic_gain),
            "gutter_score": gutter_score,
        }

    def _build_columns(
        self,
        k: int,
        model: GaussianMixture,
        labels: np.ndarray,
        elements: list[PhysicalElement],
        page: PageModel,
        gutter: GutterEvidence,
        base_bic: float,
        selected_bic: Optional[float],
    ) -> list[ColumnModel]:
        features = self._features(elements, page)
        order = np.argsort(model.means_[:, 0])
        columns: list[ColumnModel] = []
        for index, component in enumerate(order):
            component_mask = labels == component
            component_features = features[component_mask]
            center = float(model.means_[component, 0])
            x0 = float(component_features[:, 1].min())
            x1 = float(component_features[:, 2].max())
            # The model feature width describes individual text spans. The
            # public column width should describe the observed column extent.
            width = max(0.0, x1 - x0)
            if x1 < x0:
                x0, x1 = center - width / 2.0, center + width / 2.0
            adjacent_score = self._adjacent_gutter_score(
                index,
                order,
                model,
                gutter,
            )
            columns.append(
                ColumnModel(
                    index=index,
                    center_x_norm=center,
                    x0_norm=x0,
                    x1_norm=x1,
                    width_norm=max(0.0, width),
                    weight=float(model.weights_[component]),
                    sample_count=int(component_mask.sum()),
                    bic=selected_bic,
                    bic_gain=(base_bic - selected_bic) if selected_bic is not None else 0.0,
                    gutter_score=adjacent_score,
                    gutter_validated=adjacent_score >= self.config.min_gutter_score,
                )
            )
        return columns

    def _fallback(
        self,
        page: PageModel,
        elements: list[PhysicalElement],
        *,
        bics: dict[int, float],
    ) -> ColumnDetection:
        page_width = max(float(page.width), 1e-9)
        if elements:
            x0 = min(float(item.bbox.x0) for item in elements) / page_width
            x1 = max(float(item.bbox.x1) for item in elements) / page_width
            center = (x0 + x1) / 2.0
            width = max(0.0, x1 - x0)
        else:
            x0, center, x1, width = 0.0, 0.5, 1.0, 1.0
        column = ColumnModel(
            index=0,
            center_x_norm=center,
            x0_norm=x0,
            x1_norm=x1,
            width_norm=width,
            weight=1.0,
            sample_count=len(elements),
            bic=bics.get(1),
        )
        assignments, spanning = self._assign_all(page.elements, [column])
        return ColumnDetection(
            columns=[column],
            assignments=assignments,
            spanning_ids=spanning,
            bics=bics,
            selected_k=1,
        )

    def _assign_all(
        self,
        elements: list[PhysicalElement],
        columns: list[ColumnModel],
    ) -> tuple[dict[str, Optional[int]], set[str]]:
        assignments: dict[str, Optional[int]] = {}
        spanning: set[str] = set()
        multiple = len(columns) > 1
        gap_midpoints = [
            (left.x1_norm + right.x0_norm) / 2.0
            for left, right in zip(columns[:-1], columns[1:])
        ]
        for element in elements:
            x0 = float(element.bbox.nx0)
            x1 = float(element.bbox.nx1)
            width = max(0.0, x1 - x0)
            is_spanning = multiple and (
                width >= self.config.spanning_width
                or any(x0 < midpoint < x1 for midpoint in gap_midpoints)
            )
            if is_spanning:
                assignments[element.id] = None
                spanning.add(element.id)
                continue
            center = (x0 + x1) / 2.0
            assignments[element.id] = min(
                range(len(columns)),
                key=lambda index: abs(columns[index].center_x_norm - center),
            )
        return assignments, spanning

    def _gutter_score_at(self, gutter: GutterEvidence, midpoint: float) -> float:
        scores = [
            candidate.score
            for candidate in gutter.candidates
            if candidate.x0_norm <= midpoint <= candidate.x1_norm
        ]
        return max(scores, default=0.0)

    def _adjacent_gutter_score(
        self,
        index: int,
        order: np.ndarray,
        model: GaussianMixture,
        gutter: GutterEvidence,
    ) -> float:
        if index >= len(order) - 1:
            return 0.0
        left = float(model.means_[order[index], 0])
        right = float(model.means_[order[index + 1], 0])
        return self._gutter_score_at(gutter, (left + right) / 2.0)
