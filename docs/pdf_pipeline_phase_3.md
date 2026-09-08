# PDF pipeline migration - Phase 3

## Scope and production seam

Phase 3 is an opt-in structural analysis layer over the Phase-1
`DocumentModel` and the Phase-2 `LayoutAnalysis`/`DocumentProfile`:

```text
Document Profile
      |
      v
Candidate Detector -> DocumentGraph -> QuestionRegion
```

The public seam is:

```python
from services.pdf_pipeline import extract_and_analyze_structure

analysis = extract_and_analyze_structure("pdfs/56_1788095849.pdf")
trace = analysis.trace()
```

The application still calls the legacy parser. No API route, database schema,
question dictionary, Dataprev/IBAM/IDCAP adapter or answer-key behavior was
changed.

## Feature Schema v1

`FeatureSchemaV1` and `FeatureVector` live in
`services.pdf_pipeline.structural.candidates.features`. The schema is fixed at
`feature_schema_version = 1` and contains the requested `content`, `geometry`,
`style`, `sequence`, `context`, `profile` and `legacy` fields.

`Candidate.features` serializes both the version and the flat feature names.
`Candidate.evidence` contains the normalized signals and
`Candidate.score_breakdown` contains each weighted contribution.

## Candidate detector

`CandidateDetector` recognizes explicit `Questão 12`, numeric `12` and
punctuated `12.`/`12)` forms. A numeric occurrence inside ordinary prose is
not accepted as a question header. The detector also emits option-group,
subject and shared-context candidates.

Question-header weights are centralized in `CandidateScoreWeights`:

```text
numeric             0.15
sequential          0.20
same_alignment      0.15
same_style_cluster  0.10
options_below       0.20
regex               0.10
vertical_structure  0.10
legacy_bonus        0.05 (capped)
```

The legacy bonus is intentionally smaller than the physical/layout evidence.
`bank_name` is not a dominant feature.

## Legacy evidence providers

`LegacyEvidenceProvider` reuses the current rule seam as evidence only:

- `extract_options_from_chunk` contributes `legacy_option_pattern`;
- `SUBJECT_REGEX` and `format_subject_title` contribute subject signals;
- the registered Dataprev, IBAM, IDCAP and other rule families contribute a
  bounded `legacy_bank_header_match` signal;
- the existing context-block detector contributes context evidence;
- existing image trigger regexes are used only as optional proximity evidence.

No provider invokes the production parser to make the structural result win,
and none changes the legacy output.

## Option groups and context

Option groups support A-E labels, bullets, checkboxes/circles, recurring
alignment and spacing, repeated visual style and the group position below a
statement. Existing A-E regex extraction is a label signal, not the only
detector.

Subject candidates remain deterministic and reuse the current classifier.
`ContextBlock` keeps one physical source and lists the question candidates it
applies to; semantic text is not duplicated in each question node.

## DocumentGraph

`DocumentGraph` uses:

```python
nodes: dict[str, GraphNode]
edges_by_source: dict[str, list[GraphEdge]]
```

It serializes nodes, edges, evidence and statistics. The builder uses reading
order links, column/line/style adjacency, x-alignment buckets and bounded
spatial buckets. It does not run an all-pairs comparison. It emits:

```text
ABOVE, BELOW, LEFT_OF, RIGHT_OF, SAME_COLUMN, SAME_LINE,
ALIGNED_LEFT, ALIGNED_CENTER, NEAR, CONTAINS, OVERLAPS,
SAME_STYLE_CLUSTER, NEXT_READING_BLOCK, APPLIES_TO, OWNS_IMAGE
```

## Question regions and image ownership

`QuestionRegionBuilder` takes consecutive preliminary headers and creates
`PageSegment` records. A region can therefore span pages without flattening
the physical model. Image ownership scores geometry first:

```text
inside_question_region
same_column
nearest_statement
trigger_word_nearby
crossing_next_question_penalty
header/footer_penalty
```

The trigger word remains optional. Ownership is kept as an
`ImageOwnership` record and as an `OWNS_IMAGE` graph edge.

## Diagnostics

`StructuralAnalysis.trace()` returns an inspectable object with:

```json
{
  "pipeline_version": "structural-v1",
  "feature_schema_version": 1,
  "document_profile": {},
  "question_candidates": [],
  "option_candidates": [],
  "context_blocks": [],
  "graph_stats": {},
  "question_regions": [],
  "warnings": []
}
```

## Phase stop point

This phase does not implement global sequence solving, complete recovery,
answer-key constraints, the final Question AST, supervised ML or historical
layout-family clustering.

