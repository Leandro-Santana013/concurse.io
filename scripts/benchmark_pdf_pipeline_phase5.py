"""Run the Phase-5 benchmark over the repository's PDF corpus.

Usage:
    python scripts/benchmark_pdf_pipeline_phase5.py --manifest golden/phase5_corpus.json
    python scripts/benchmark_pdf_pipeline_phase5.py --manifest golden/corpus.json --limit 1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.gabarito import (  # noqa: E402
    build_exam_answer_key_profile,
    match_gabarito_from_pdf,
)
from services.pdf_pipeline import (  # noqa: E402
    BenchmarkCase,
    LayoutFamilyModel,
    PipelineMode,
    build_layout_families,
    evaluate_exam,
    parse_exam_document,
    run_structural_shadow,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "golden" / "phase5_corpus.json")
    parser.add_argument("--mode", choices=[mode.value for mode in PipelineMode], default=PipelineMode.STRUCTURAL_SHADOW.value)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    entries = _entries(path)
    if args.limit:
        entries = entries[: args.limit]
    analyses = []
    profiles = []
    rows = []
    for entry in entries:
        exam_id = str(entry.get("id") or Path(entry["pdf"]).stem)
        pdf_path = _root_path(entry["pdf"])
        if not pdf_path.exists():
            print(f"SKIP {exam_id}: missing {pdf_path}")
            continue
        legacy = parse_exam_document(str(pdf_path), extract_images=False)
        answer_key = None
        answer_path = entry.get("answer_key")
        if answer_path and _root_path(answer_path).exists():
            answer_key = _resolve_answer_key(
                pdf_path,
                _root_path(answer_path),
                legacy,
                entry,
            )
        result = run_structural_shadow(
            pdf_path,
            mode=args.mode,
            legacy_result=legacy,
            answer_key=answer_key,
            source=str(entry["pdf"]),
            extract_images=False,
        )
        analyses.append((entry, result, legacy))
        if result.structural_analysis is not None:
            profiles.append(result.structural_analysis.document_profile)
        print(
            f"{exam_id}: legacy={len(legacy)} structural={len(result.structural_result or [])} "
            f"errors={len(result.errors)}"
        )

    family_model = LayoutFamilyModel()
    if profiles:
        family_model.fit(profiles, document_ids=[str(item[0].get("id")) for item in analyses if item[1].structural_analysis is not None])
    for entry, result, legacy in analyses:
        expected_count = entry.get("expected_question_count")
        if expected_count is None:
            expected = [int(item.get("numero_questao")) for item in legacy if str(item.get("numero_questao", "")).isdigit()]
        else:
            expected = list(range(1, int(expected_count) + 1))
        options = None
        if entry.get("expected_option_count"):
            labels = [chr(ord("A") + index) for index in range(int(entry["expected_option_count"]))]
            options = {number: labels for number in expected}
        assignment = None
        if result.structural_analysis is not None and family_model.families:
            assignment = family_model.predict(result.structural_analysis.document_profile, document_id=str(entry.get("id")))
        metrics = evaluate_exam(
            BenchmarkCase(
                exam_id=str(entry.get("id")),
                expected_numbers=expected,
                structural_result=result.structural_result or [],
                legacy_result=legacy,
                expected_options=options,
                banca=entry.get("banca"),
                layout_family=assignment.layout_family if assignment else None,
                split=str(entry.get("split", entry.get("category", "holdout"))).upper(),
            )
        )
        rows.append(metrics)

    from services.pdf_pipeline.structural.benchmark import BenchmarkReport

    report = BenchmarkReport(cases=rows).to_dict()
    output = args.output
    if output is not None:
        output = output if output.is_absolute() else ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
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
) -> dict[int, str] | None:
    profile = build_exam_answer_key_profile(
        str(pdf_path),
        legacy_questions,
        # Keep technical manifest ids out of the answer-key identity profile.
        title=str(entry.get("title") or ""),
        tipo=entry.get("tipo"),
    )
    result = match_gabarito_from_pdf(
        str(answer_path),
        profile,
        source_relation="paired",
        document_hint=str(answer_path),
    )
    return dict(result.answers) if result.accepted else None


if __name__ == "__main__":
    raise SystemExit(main())
