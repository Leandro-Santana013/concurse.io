"""Train the optional Phase-5 candidate model from a trusted PDF manifest.

Usage:
    python scripts/train_pdf_pipeline_phase5.py --manifest golden/phase5_corpus.json

The command is intentionally explicit about answer-key files and split names.
It writes model artifacts only to the requested output directory; it never
changes the legacy parser or application database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from dataclasses import replace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.gabarito import (  # noqa: E402
    build_exam_answer_key_profile,
    match_gabarito_from_pdf,
)
from services.pdf_pipeline import (  # noqa: E402
    CandidateClassifierTrainer,
    ExamLabelInput,
    GroupKFoldSplitter,
    ModelRegistry,
    ReliableDatasetBuilder,
    build_layout_families,
    extract_physical_document,
    analyze_structure,
)
from services.pdf_pipeline.hybrid_extractor import parse_exam_document  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "golden" / "phase5_corpus.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "phase5")
    parser.add_argument("--estimator", choices=("logistic", "hist_gradient_boosting"), default="logistic")
    args = parser.parse_args()

    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    entries = _entries(manifest_path)
    if not entries:
        raise SystemExit("manifest has no entries")

    profiles = []
    profile_ids = []
    raw_inputs: list[ExamLabelInput] = []
    answer_key_audits: list[dict] = []
    for entry in entries:
        exam_id = str(entry["id"])
        pdf_path = _root_path(entry["pdf"])
        answer_path = _root_path(entry["answer_key"])
        if not pdf_path.exists() or not answer_path.exists():
            raise FileNotFoundError(f"missing PDF pair for {exam_id}: {pdf_path} / {answer_path}")
        legacy = parse_exam_document(str(pdf_path), extract_images=False)
        answer_key, answer_key_audit = _resolve_answer_key(
            pdf_path,
            answer_path,
            legacy,
            entry,
        )
        answer_key_audits.append({"exam_id": exam_id, **answer_key_audit})
        document = extract_physical_document(str(pdf_path), source=entry["pdf"])
        analysis = analyze_structure(document, legacy_metadata={"banca": entry.get("banca")})
        profiles.append(analysis.document_profile)
        profile_ids.append(exam_id)
        raw_inputs.append(
            ExamLabelInput(
                exam_id=exam_id,
                # The legacy parser uses fallback answers (often ``A``) when
                # no embedded key is present.  Candidate labels rely only on
                # validated question numbering; official answers are used as
                # the independent consistency source above.
                legacy_questions=_questions_for_labels(legacy),
                candidates=analysis.question_candidates,
                answer_key=answer_key,
                source=entry["pdf"],
                expected_count=entry.get("expected_question_count"),
                curated=False,
            )
        )
        print(f"analyzed {exam_id}: legacy={len(legacy)} candidates={len(analysis.question_candidates)}")

    holdout_ids = {
        str(entry["id"])
        for entry in entries
        if str(entry.get("split", "")).upper() == "HOLDOUT"
    }
    family_fit_indices = [
        index
        for index, entry in enumerate(entries)
        if str(entry.get("split", "")).upper() != "HOLDOUT"
    ]
    family_model = build_layout_families(
        [profiles[index] for index in family_fit_indices],
        document_ids=[profile_ids[index] for index in family_fit_indices],
    )
    enriched_inputs = []
    for item, profile in zip(raw_inputs, profiles):
        assignment = family_model.predict(profile, document_id=item.exam_id)
        enriched_inputs.append(replace(item, layout_family=assignment.layout_family or "noise"))

    dataset = ReliableDatasetBuilder().build(enriched_inputs)
    if not dataset.records:
        raise SystemExit(f"no reliable weak labels; rejected={list(dataset.rejected_exams)}")
    validation_ids = {
        str(entry["id"])
        for entry in entries
        if str(entry.get("split", "")).upper() == "VALIDATION"
    }
    splits = GroupKFoldSplitter(n_splits=3).split(
        dataset,
        holdout_groups=holdout_ids,
        validation_groups=validation_ids or None,
    )
    trainer = CandidateClassifierTrainer(random_state=0)
    model = trainer.train(dataset, splits=splits, estimator=args.estimator)
    comparison = trainer.compare(dataset, splits=splits)

    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = model.save(output_dir / "candidate_classifier.joblib")
    family_path = family_model.save(output_dir / "layout_families.json")
    dataset_path = output_dir / "weak_labels.json"
    dataset_path.write_text(json.dumps(dataset.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    registry = ModelRegistry(output_dir / "model_registry.json")
    registry.register(
        "candidate_classifier",
        path=model_path.name,
        version="1",
        feature_schema=model.metadata.feature_schema_version,
        model_version=model.metadata.model_version,
        training_dataset_version=dataset.version,
    )
    registry.register(
        "layout_clusterer",
        path=family_path.name,
        version="1",
        feature_schema=1,
    )
    registry.save()
    report = {
        "dataset": dataset.to_dict(),
        "splits": splits.to_dict(),
        "model": model.metadata.to_dict(),
        "comparison": comparison,
        "answer_key_audits": answer_key_audits,
        "layout_families": family_model.to_dict(),
        "artifacts": {
            "model_registry": str(output_dir / "model_registry.json"),
            "candidate_classifier": str(model_path),
            "layout_families": str(family_path),
            "weak_labels": str(dataset_path),
        },
    }
    (output_dir / "training_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "metrics": model.metadata.metrics, "splits": splits.to_dict()}, ensure_ascii=False, indent=2))
    return 0


def _entries(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", payload) if isinstance(payload, dict) else payload
    return [dict(item) for item in entries]


def _root_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _resolve_answer_key(
    pdf_path: Path,
    answer_path: Path,
    legacy_questions: list[dict],
    entry: dict,
) -> tuple[dict[int, str], dict]:
    """Use the same identity-aware matcher as application ingestion."""

    profile = build_exam_answer_key_profile(
        str(pdf_path),
        legacy_questions,
        # Do not turn a technical manifest id into an exam identity.  For
        # example, ``phase5-56-a`` would create a fake cargo token and reject
        # an otherwise compatible paired answer key.  The PDF header and an
        # explicit manifest title are the only trusted identity sources.
        title=str(entry.get("title") or ""),
        tipo=entry.get("tipo"),
    )
    match = match_gabarito_from_pdf(
        str(answer_path),
        profile,
        source_relation="paired",
        document_hint=str(answer_path),
    )
    audit = match.to_audit_dict()
    audit["path"] = str(answer_path)
    return (dict(match.answers) if match.accepted else {}), audit


def _questions_for_labels(questions: list[dict]) -> list[dict]:
    """Remove parser fallback answers from the numbering-label input."""

    sanitized: list[dict] = []
    for question in questions:
        item = dict(question)
        item.pop("resposta", None)
        item.pop("correct_answer", None)
        sanitized.append(item)
    return sanitized


if __name__ == "__main__":
    raise SystemExit(main())
