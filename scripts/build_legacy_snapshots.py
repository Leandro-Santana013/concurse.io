"""Build deterministic regression snapshots from the legacy PDF parser.

Examples:
    python scripts/build_legacy_snapshots.py --manifest golden/corpus.json
    python scripts/build_legacy_snapshots.py pdfs/56_1788095849.pdf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.pdf_pipeline.legacy import (  # noqa: E402
    LegacyParserContext,
    build_default_legacy_registry,
    write_legacy_snapshot,
)


def _safe_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or "snapshot"


def _manifest_entries(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", payload) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("Corpus manifest must contain an entries list")
    return [dict(entry) for entry in entries]


def _input_entries(args: argparse.Namespace) -> Iterable[dict[str, Any]]:
    if args.manifest:
        yield from _manifest_entries(args.manifest)
        return
    for pdf_path in args.pdf_paths:
        yield {"id": Path(pdf_path).stem, "pdf": pdf_path}


def build_snapshots(args: argparse.Namespace) -> int:
    registry = build_default_legacy_registry()
    output_dir = args.output_dir

    for entry in _input_entries(args):
        raw_pdf = Path(str(entry["pdf"]))
        pdf_path = raw_pdf if raw_pdf.is_absolute() else ROOT / raw_pdf
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF fixture not found: {pdf_path}")

        exam_id = entry.get("exam_id", args.exam_id)
        context = LegacyParserContext(
            declared_banca=entry.get("banca"),
            exam_id=exam_id,
            extract_images=args.extract_images,
        )
        adapter = registry.resolve(context)
        questions = adapter.parse(pdf_path, context)

        snapshot_name = _safe_name(entry.get("id") or pdf_path.stem) + ".json"
        output_path = output_dir / snapshot_name
        write_legacy_snapshot(
            output_path,
            questions,
            source=raw_pdf.as_posix(),
            adapter_name=adapter.name,
        )
        print(f"{adapter.name}: {raw_pdf.as_posix()} -> {output_path.as_posix()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pdf_paths",
        nargs="*",
        help="PDF paths, relative to the repository root unless absolute",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Corpus manifest with entries containing id and pdf",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "golden" / "snapshots" / "legacy",
    )
    parser.add_argument("--exam-id", type=int)
    parser.add_argument(
        "--extract-images",
        action="store_true",
        help="Keep the legacy image extraction side effect in the snapshot run",
    )
    args = parser.parse_args()
    if not args.manifest and not args.pdf_paths:
        parser.error("provide at least one PDF path or --manifest")
    return build_snapshots(args)


if __name__ == "__main__":
    raise SystemExit(main())
