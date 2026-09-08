# PDF pipeline migration - Phase 1

## Scope and stop point

Phase 1 adds the physical document foundation while the application remains
on the current legacy parser. The new entry point is
services.pdf_pipeline.structural.extract_physical_document, which returns a
serializable DocumentModel containing PageModel and PhysicalElement records.

No question header detection, ownership assignment, layout profile, graph,
constraint solver, Question AST, ML model or structural rollout is included.

## Existing legacy rules

The repository has one question parser implementation:

- services/pdf_pipeline/hybrid_extractor.py owns the current question
  extraction and compatibility dictionary output.
- services/pdf_pipeline/layout/layout_detector.py owns layout ordering,
  column handling, table detection, watermark filtering and an OCR line
  fallback.
- services/pdf_pipeline/media/diagram_cropper.py owns image/diagram
  extraction, crops, watermark filtering and the existing RapidOCR engine.
- services/pdf_pipeline/formatters/banca_clusterizer.py contains known banca
  families and their legacy patterns.
- services/gabarito/gabarito_service.py contains answer-key and table
  extraction rules used by the ingestion flow.
- services/pdf_pipeline/native/rust_bridge.py provides the optional Rust
  acceleration and Python fallback.

There are no independent Dataprev, IBAM or IDCAP question parser functions to
move in this phase. The legacy registry therefore exposes named adapters for
those rule families, but each named adapter delegates to the unchanged
hybrid parser. This makes the seam explicit without inventing a second parser
or changing production behavior.

## New physical interface

PhysicalExtractor reads PyMuPDF dict text at span granularity and keeps block,
line and span identity in element IDs and metadata. Every BBox includes
absolute and page-normalized coordinates. Image blocks, direct image
placements, vector drawings and existing table detections are represented
without question ownership. The existing ExamImageExtractor watermark scan is
reused only to tag repeated layout artifacts; crop and ownership remain in the
legacy media path.

Normalized coordinates are the direct absolute-coordinate/page-dimension
quotient. A source PDF element that crosses the page trim can therefore have a
normalized coordinate below zero or above one; the absolute bbox is retained
and no clipping is performed in the POM.

If a page has no native text, or has little native text alongside raster
content, the existing RapidOCR integration adds separate text elements with
source=ocr and source_confidence. Native elements are not replaced.

Optional debug output:

    python -c "from services.pdf_pipeline import extract_physical_document; extract_physical_document('pdfs/56_1788095849.pdf', exam_id=56, debug_export=True)"

This writes artifacts/debug/56/page_model.json and does not persist anything
to the database.

## Legacy snapshots

Build snapshots for the manifest or for an individual fixture:

    python scripts/build_legacy_snapshots.py --manifest golden/corpus.json
    python scripts/build_legacy_snapshots.py pdfs/56_1788095849.pdf

Snapshots contain the compatibility fields numero_questao,
question_index, statement, options, images, subject and correct_answer.

## Pipeline mode

get_pipeline_mode() defaults to LEGACY_ONLY. The other enum values are
declared for later phases but no code in Phase 1 selects or rolls out a
structural result.
