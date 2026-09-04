"""Resolução e nomenclatura dos PDFs associados a uma prova."""

from pathlib import Path
from typing import Optional, Tuple


def canonical_exam_pdf_path(exam_id: int, pdf_dir: str = "pdfs") -> str:
    return str(Path(pdf_dir) / f"{int(exam_id)}_prova.pdf")


def canonical_answer_key_pdf_path(exam_id: int, pdf_dir: str = "pdfs") -> str:
    return str(Path(pdf_dir) / f"{int(exam_id)}_gab.pdf")


def is_pdf_file(path: Path, *, minimum_bytes: int = 4) -> bool:
    """Aceita somente arquivos locais que parecem PDFs completos."""
    try:
        if not (
            path.is_file()
            and path.suffix.lower() == ".pdf"
            and path.stat().st_size >= minimum_bytes
        ):
            return False
        with path.open("rb") as stream:
            return stream.read(4) == b"%PDF"
    except OSError:
        return False


def _artifact_sort_key(path: Path, canonical_name: str):
    # O nome canônico é a fonte preferida; entre artefatos legados, o mais
    # recente normalmente é a versão baixada na última ingestão.
    is_canonical = path.name.lower() == canonical_name.lower()
    try:
        modified_ns = path.stat().st_mtime_ns
    except OSError:
        modified_ns = 0
    return (0 if is_canonical else 1, -modified_ns, path.name.lower())


def find_local_exam_pdf(exam_id: int, pdf_dir: str = "pdfs") -> Optional[str]:
    """Encontra o caderno do exame sem confundir um gabarito de outro tipo."""
    root = Path(pdf_dir)
    if not root.is_dir():
        return None

    prefix = f"{int(exam_id)}_"
    canonical_name = f"{int(exam_id)}_prova.pdf"
    candidates = []
    for path in root.glob(f"{int(exam_id)}_*.pdf"):
        lower_name = path.name.lower()
        if not lower_name.startswith(prefix):
            continue
        if lower_name.startswith(f"{int(exam_id)}_gab") or lower_name.startswith(
            f"{int(exam_id)}_gabarito"
        ):
            continue
        if is_pdf_file(path, minimum_bytes=5_000):
            candidates.append(path)

    candidates.sort(key=lambda item: _artifact_sort_key(item, canonical_name))
    return str(candidates[0]) if candidates else None


def find_local_answer_key_pdf(exam_id: int, pdf_dir: str = "pdfs") -> Optional[str]:
    """Encontra somente o gabarito cujo prefixo de arquivo é o ID do exame."""
    root = Path(pdf_dir)
    if not root.is_dir():
        return None

    exam_id_text = str(int(exam_id))
    canonical_name = f"{exam_id_text}_gab.pdf"
    candidates = []
    for path in root.glob(f"{exam_id_text}_*.pdf"):
        lower_name = path.name.lower()
        if lower_name in {canonical_name, f"{exam_id_text}_gabarito.pdf"}:
            matches_answer_key = True
        else:
            matches_answer_key = lower_name.startswith(
                (f"{exam_id_text}_gab_", f"{exam_id_text}_gabarito_")
            )
        if matches_answer_key and is_pdf_file(path):
            candidates.append(path)

    candidates.sort(key=lambda item: _artifact_sort_key(item, canonical_name))
    return str(candidates[0]) if candidates else None


def find_local_exam_artifacts(
    exam_id: int, pdf_dir: str = "pdfs"
) -> Tuple[Optional[str], Optional[str]]:
    """Retorna (prova, gabarito), ambos limitados ao mesmo ID."""
    return (
        find_local_exam_pdf(exam_id, pdf_dir),
        find_local_answer_key_pdf(exam_id, pdf_dir),
    )
