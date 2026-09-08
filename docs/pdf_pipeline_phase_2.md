# PDF pipeline migration - Phase 2

## Scope and production seam

Phase 2 consumes the Phase 1 `DocumentModel` and returns a serializable
`LayoutAnalysis` containing a `DocumentProfile`. It is opt-in:

```python
from services.pdf_pipeline import extract_and_analyze_layout

analysis = extract_and_analyze_layout("pdfs/56_1788095849.pdf")
profile = analysis.profile
```

The application continues to use the legacy parser. No API route, database
schema, question dictionary contract, or legacy adapter is changed by this
module.

## Layout evidence

`GutterDetector` first projects native text-span intervals in normalized X
coordinates and checks valleys across vertical persistence bands. Raster
projection is conditional: it runs only when native text is absent/degraded or
OCR dominates the page. The raster path uses moderate DPI, grayscale/Otsu
binarization, light morphology, and connected-component diagnostics.

`ColumnModeler` fits `GaussianMixture` models for `k=1..3` using:

```text
center_x_norm, x0_norm, x1_norm, width_norm
```

The selected model is not the raw minimum BIC by itself. A multi-column model
must also have non-trivial component sizes, separated centers, and either a
geometric gap or gutter support. Per-page diagnostics expose the BIC values and
selection reason.

`DBSCAN` with `RobustScaler` is used for alignment and visual style clusters.
Outliers remain unassigned; clusters do not receive semantic labels.

## Structural output

- `PageLayout.columns` describes observed column models, including asymmetric
  columns and their gutter scores.
- `ElementLayout` records column assignment, spanning status, visual cluster
  IDs, non-destructive `HEADER_NOISE`/`FOOTER_NOISE` roles, and order index.
- `ReadingOrder.sequence` contains physical element IDs and
  `next_reading_block` links. `N_ORDER`/`Z_ORDER` is selected from the existing
  topology evidence or an explicit configuration, never from a banca name.
- `DocumentProfile` contains page statistics, dominant fonts, style clusters,
  optional future semantic signatures set to `null`, OCR/scan signals, and a
  fixed `layout-profile-v1` fingerprint.

## Public configuration

`LayoutAnalyzerConfig` exposes `GutterConfig`, `ColumnConfig`, `DBSCANConfig`
and `ZoneConfig`. Important defaults include:

```text
GMM: k=1..3, min_bic_gain=6.0, min_center_separation=0.08,
     min_component_fraction=0.06, spanning_width=0.72
DBSCAN alignment: eps=0.85, min_samples=2
DBSCAN style:     eps=1.25, min_samples=2
```

All thresholds are layout evidence parameters. There is no `if bank == ...`
branch in this package.

## Phase stop point

This phase does not implement question headers, `QuestionRegion`, image
ownership, sequence constraint solving, `QuestionAST`, supervised learning, or
historical layout families.

