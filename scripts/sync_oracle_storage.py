"""Upload existing canonical PDFs and extracted question images to OCI.

The command is dry-run by default.  Use ``--apply`` only after configuring the
server-only OCI variables.  It is intentionally separate from the API so a
one-time migration does not need a public upload endpoint.
"""

from __future__ import annotations

import argparse
import mimetypes
import re
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.exam_files import is_pdf_file
from services.object_storage import (
    ObjectStorageSettings,
    exam_pdf_object_key,
    put_file,
    question_object_key,
)


PDF_PATTERN = re.compile(r"^(?P<exam_id>\d+)_(?P<kind>prova|gab|gabarito)\.pdf$", re.IGNORECASE)


def iter_artifacts(root: Path):
    image_root = (root / "static" / "images" / "questions").resolve()
    if image_root.is_dir():
        for path in sorted(image_root.iterdir()):
            if path.is_file():
                yield question_object_key(path.name), path, mimetypes.guess_type(path.name)[0]

    pdf_root = (root / "pdfs").resolve()
    if pdf_root.is_dir():
        for path in sorted(pdf_root.iterdir()):
            match = PDF_PATTERN.match(path.name)
            if not match or not is_pdf_file(path):
                continue
            kind = "prova" if match.group("kind").lower() == "prova" else "gabarito"
            yield exam_pdf_object_key(int(match.group("exam_id")), kind), path, "application/pdf"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--apply", action="store_true", help="realiza os uploads")
    args = parser.parse_args()

    settings = ObjectStorageSettings.from_environment()
    if args.apply and not settings.configured:
        parser.error("configure as variáveis OCI_OBJECT_STORAGE_* antes de usar --apply")

    artifacts = list(iter_artifacts(args.root.resolve()))
    for object_key, path, content_type in artifacts:
        action = "upload" if args.apply else "planejado"
        print(f"{action}: {path} -> {object_key}")
        if args.apply:
            put_file(object_key, path, content_type=content_type or "application/octet-stream")
    print(f"{len(artifacts)} artefato(s) encontrados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
