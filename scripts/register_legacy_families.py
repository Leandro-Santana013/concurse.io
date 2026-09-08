"""Export the legacy family catalog: python scripts/register_legacy_families.py."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.pdf_pipeline.legacy.family_catalog import build_legacy_family_catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/legacy_family_catalog.json")
    args = parser.parse_args()
    catalog = build_legacy_family_catalog()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Registered {len(catalog['families'])} families and {len(catalog['legacy_rules'])} legacy rules: {args.output}")


if __name__ == "__main__":
    main()
