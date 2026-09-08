"""Visual alignment and style clustering with explicit DBSCAN noise."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import RobustScaler

from ..model import DocumentModel, PhysicalElement
from .config import DBSCANConfig
from .models import ClusterSummary


ALIGNMENT_FEATURE_NAMES = (
    "x0_norm",
    "center_x_norm",
    "font_size_norm",
    "indent_norm",
)

STYLE_FEATURE_NAMES = (
    "font_size_normalized",
    "bold",
    "italic",
    "uppercase_ratio",
    "digit_ratio",
    "char_count",
    "x0_norm",
    "width_norm",
    "height_norm",
)


def cluster_alignment_elements(
    document: DocumentModel,
    *,
    config: Optional[DBSCANConfig] = None,
) -> tuple[list[ClusterSummary], dict[str, Optional[int]]]:
    """Cluster recurring x/indent/font alignments without semantic labels."""

    cfg = config or DBSCANConfig()
    elements, features = _alignment_features(document)
    return _cluster(
        elements,
        features,
        feature_names=ALIGNMENT_FEATURE_NAMES,
        eps=cfg.alignment_eps,
        min_samples=cfg.alignment_min_samples,
        use_robust_scaler=cfg.use_robust_scaler,
    )


def cluster_style_elements(
    document: DocumentModel,
    *,
    config: Optional[DBSCANConfig] = None,
) -> tuple[list[ClusterSummary], dict[str, Optional[int]]]:
    """Cluster visual text styles; a cluster has no question meaning yet."""

    cfg = config or DBSCANConfig()
    elements, features = _style_features(document)
    return _cluster(
        elements,
        features,
        feature_names=STYLE_FEATURE_NAMES,
        eps=cfg.style_eps,
        min_samples=cfg.style_min_samples,
        use_robust_scaler=cfg.use_robust_scaler,
    )


def _text_elements(document: DocumentModel) -> list[PhysicalElement]:
    return [
        element
        for page in document.pages
        for element in page.elements
        if element.kind == "text"
    ]


def _alignment_features(
    document: DocumentModel,
) -> tuple[list[PhysicalElement], np.ndarray]:
    elements = _text_elements(document)
    rows: list[list[float]] = []
    for element in elements:
        page = document.pages[element.page_index]
        font_size_norm = (
            float(element.font_size) / max(float(page.height), 1e-9)
            if element.font_size is not None
            else 0.0
        )
        x0 = float(element.bbox.nx0)
        x1 = float(element.bbox.nx1)
        rows.append([x0, (x0 + x1) / 2.0, font_size_norm, x0])
    return elements, np.asarray(rows, dtype=float)


def _style_features(
    document: DocumentModel,
) -> tuple[list[PhysicalElement], np.ndarray]:
    elements = _text_elements(document)
    lengths = np.asarray([len(element.text or "") for element in elements], dtype=float)
    median_length = float(np.median(lengths[lengths > 0])) if np.any(lengths > 0) else 1.0
    font_sizes = np.asarray(
        [
            float(element.font_size) / max(float(document.pages[element.page_index].height), 1e-9)
            if element.font_size is not None
            else 0.0
            for element in elements
        ],
        dtype=float,
    )
    positive_font_sizes = font_sizes[font_sizes > 0]
    median_font_size = float(np.median(positive_font_sizes)) if positive_font_sizes.size else 1.0

    rows: list[list[float]] = []
    for index, element in enumerate(elements):
        text = element.text or ""
        alphanumeric = [char for char in text if char.isalnum()]
        uppercase_ratio = (
            sum(char.isupper() for char in alphanumeric) / max(len(alphanumeric), 1)
        )
        digit_ratio = sum(char.isdigit() for char in text) / max(len(text), 1)
        page = document.pages[element.page_index]
        rows.append(
            [
                font_sizes[index] / max(median_font_size, 1e-9),
                float(element.bold),
                float(element.italic),
                float(uppercase_ratio),
                float(digit_ratio),
                float(len(text)) / max(median_length, 1.0),
                float(element.bbox.nx0),
                float(element.bbox.width) / max(float(page.width), 1e-9),
                float(element.bbox.height) / max(float(page.height), 1e-9),
            ]
        )
    return elements, np.asarray(rows, dtype=float)


def _cluster(
    elements: list[PhysicalElement],
    features: np.ndarray,
    *,
    feature_names: Sequence[str],
    eps: float,
    min_samples: int,
    use_robust_scaler: bool,
) -> tuple[list[ClusterSummary], dict[str, Optional[int]]]:
    mapping = {element.id: None for element in elements}
    if not elements:
        return [], mapping
    if len(elements) < max(1, min_samples):
        return [], mapping

    finite_features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
    scaled = (
        RobustScaler().fit_transform(finite_features)
        if use_robust_scaler
        else finite_features
    )
    labels = DBSCAN(
        eps=float(eps),
        min_samples=max(1, int(min_samples)),
    ).fit_predict(scaled)

    grouped: dict[int, list[int]] = defaultdict(list)
    for index, label in enumerate(labels):
        if int(label) >= 0:
            grouped[int(label)].append(index)
    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: (
            float(np.mean(features[item[1], 0])),
            float(np.mean(features[item[1], 1])) if features.shape[1] > 1 else 0.0,
            item[0],
        ),
    )

    summaries: list[ClusterSummary] = []
    raw_to_stable: dict[int, int] = {}
    for stable_id, (raw_id, indices) in enumerate(ordered_groups):
        raw_to_stable[raw_id] = stable_id
        centroid = {
            name: float(np.mean(features[indices, column]))
            for column, name in enumerate(feature_names)
        }
        summaries.append(
            ClusterSummary(
                cluster_id=stable_id,
                element_ids=[elements[index].id for index in indices],
                centroid=centroid,
                is_noise=False,
            )
        )
    for index, label in enumerate(labels):
        if int(label) in raw_to_stable:
            mapping[elements[index].id] = raw_to_stable[int(label)]
    return summaries, mapping

