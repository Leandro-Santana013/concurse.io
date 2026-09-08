"""Configuration for the phase-2, bank-agnostic layout analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GutterConfig:
    """Controls text and scan projection used to find persistent valleys."""

    bins: int = 64
    persistence_bands: int = 8
    min_gutter_width: float = 0.025
    max_gutter_width: float = 0.30
    page_margin: float = 0.08
    persistence_threshold: float = 0.55
    low_occupancy_quantile: float = 0.25
    rasterize_scans: bool = True
    raster_dpi: int = 120
    scan_native_char_threshold: int = 24
    scan_ocr_ratio_threshold: float = 0.50
    morphology_kernel: int = 3


@dataclass(frozen=True)
class ColumnConfig:
    """Parameters for the guarded Gaussian-mixture column model."""

    max_columns: int = 3
    max_training_width: float = 0.78
    spanning_width: float = 0.72
    min_component_fraction: float = 0.06
    min_center_separation: float = 0.08
    min_bic_gain: float = 6.0
    min_geometric_gap: float = 0.02
    min_gutter_score: float = 0.25
    covariance_type: str = "full"
    reg_covar: float = 1e-5
    random_state: int = 0


@dataclass(frozen=True)
class DBSCANConfig:
    """Robust-scaled DBSCAN parameters for visual group discovery."""

    use_robust_scaler: bool = True
    alignment_eps: float = 0.85
    alignment_min_samples: int = 2
    style_eps: float = 1.25
    style_min_samples: int = 2


@dataclass(frozen=True)
class ZoneConfig:
    """Repetition thresholds for non-destructive header/footer marking."""

    header_max_y: float = 0.24
    footer_min_y: float = 0.76
    position_tolerance: float = 0.035
    x_tolerance: float = 0.12
    text_similarity_threshold: float = 0.72
    min_repeat_pages: int = 2
    min_repeat_fraction: float = 0.40


@dataclass(frozen=True)
class LayoutAnalyzerConfig:
    """Public configuration surface for :class:`LayoutAnalyzer`."""

    gutter: GutterConfig = field(default_factory=GutterConfig)
    columns: ColumnConfig = field(default_factory=ColumnConfig)
    clustering: DBSCANConfig = field(default_factory=DBSCANConfig)
    zones: ZoneConfig = field(default_factory=ZoneConfig)
    reading_order_mode: str = "AUTO"
    line_bucket_factor: float = 1.25
    fingerprint_version: str = "layout-profile-v1"

