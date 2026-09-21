"""Benchmark reproducível do OCR atual contra o RapidOCR PP-OCRv6 Tiny.

O benchmark é deliberadamente opt-in: não altera o motor da aplicação, não
grava cache de produção e executa cada combinação de motor/prova em um worker
persistente, uma página por vez. O processo filho emite um JSON por página;
assim uma página que travar ou exceder o limite vira ``timeout`` explícito e
não um resultado vazio.

Exemplo (a partir da raiz do repositório)::

    venv\\Scripts\\python.exe scripts/benchmarks/benchmark_ocr_comparison.py \
        --dpi 300 --threads 1 --page-timeout 180

O candidato moderno é executado com o Python passado em ``--candidate-python``
e precisa encontrar um diretório de modelos PP-OCRv6 em ``--model-root``. O
script não instala pacotes automaticamente.
"""

from __future__ import annotations

import argparse
import ctypes
import difflib
import hashlib
import json
import os
import queue
import re
import statistics
import subprocess
import sys
import threading
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE_ENV = ROOT / "tmp" / "ocr_benchmark_env_20260910"
DEFAULT_MODEL_ROOT = DEFAULT_CANDIDATE_ENV / "models"


@dataclass(frozen=True)
class Fixture:
    path: Path
    expected_questions: Optional[int]
    expected_options: Optional[int]


DEFAULT_FIXTURES = (
    Fixture(ROOT / "pdfs" / "6_prova.pdf", expected_questions=50, expected_options=4),
    Fixture(ROOT / "pdfs" / "5_prova.pdf", expected_questions=40, expected_options=4),
)

QUESTION_RE = re.compile(
    r"^\s*(?:quest(?:ão|ao)\s*)?0*(\d{1,3})\s*[\.\)\-–—,:]\s*",
    re.IGNORECASE,
)
OPTION_RE = re.compile(r"^\s*[\(\[\{]?\s*([A-Ea-e])\s*[\)\]\}\.\-–—,:]\s+")
OPTION_ONLY_RE = re.compile(r"^\s*[\(\[\{]?\s*([A-Ea-e])\s*[\)\]\}\.\-–—,:]\s*$")
WATERMARK_RE = re.compile(
    r"pcimarkpci|www\.pciconcursos\.com\.br|qconcursos\.com", re.IGNORECASE
)
PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,3}\s*/\s*\d{1,3}\s*$")


def _memory_info() -> Dict[str, float]:
    """Retorna RSS atual e pico no Windows sem depender de psutil."""

    if os.name != "nt":
        return {}

    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    fn = ctypes.windll.psapi.GetProcessMemoryInfo
    fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
    fn.restype = wintypes.BOOL
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if not fn(handle, ctypes.byref(counters), counters.cb):
        return {}
    return {
        "rss_mib": round(counters.WorkingSetSize / 2**20, 2),
        "peak_rss_mib": round(counters.PeakWorkingSetSize / 2**20, 2),
    }


def _sha256(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalise_text(value: str, *, accents: bool = True) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    if not accents:
        text = "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))
    return re.sub(r"[^0-9a-zA-ZÀ-ÿ]+", " ", text).strip()


def _clean_reference_lines(value: str) -> List[str]:
    lines: List[str] = []
    for raw in str(value or "").splitlines():
        line = raw.strip()
        if not line or WATERMARK_RE.search(line) or PAGE_NUMBER_RE.match(line):
            continue
        lines.append(line)
    return lines


def _token_metrics(reference: str, observed: str) -> Dict[str, float]:
    ref_tokens = Counter(_normalise_text(reference, accents=True).split())
    obs_tokens = Counter(_normalise_text(observed, accents=True).split())
    overlap = sum((ref_tokens & obs_tokens).values())
    precision = overlap / max(sum(obs_tokens.values()), 1)
    recall = overlap / max(sum(ref_tokens.values()), 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-12)
    return {
        "token_precision_pct": round(precision * 100.0, 2),
        "token_recall_pct": round(recall * 100.0, 2),
        "token_f1_pct": round(f1 * 100.0, 2),
    }


def _reference_metrics(reference: str, observed: str) -> Dict[str, Any]:
    ref = " ".join(_clean_reference_lines(reference))
    obs = " ".join(_clean_reference_lines(observed))
    strict_ref = _normalise_text(ref, accents=True)
    strict_obs = _normalise_text(obs, accents=True)
    loose_ref = _normalise_text(ref, accents=False)
    loose_obs = _normalise_text(obs, accents=False)
    strict_ratio = difflib.SequenceMatcher(None, strict_ref, strict_obs, autojunk=False).ratio()
    loose_ratio = difflib.SequenceMatcher(None, loose_ref, loose_obs, autojunk=False).ratio()
    result: Dict[str, Any] = {
        "reference_chars": len(strict_ref),
        "observed_chars": len(strict_obs),
        "char_similarity_pct": round(strict_ratio * 100.0, 2),
        "accent_insensitive_similarity_pct": round(loose_ratio * 100.0, 2),
    }
    result.update(_token_metrics(ref, obs))
    return result


def _line_text(lines: Sequence[Dict[str, Any]]) -> str:
    ordered = sorted(lines or [], key=lambda item: (float(item.get("y0", 0)), float(item.get("x0", 0))))
    return "\n".join(str(item.get("text") or "").strip() for item in ordered if str(item.get("text") or "").strip())


def _structural_metrics(lines: Sequence[Dict[str, Any]], expected_options: Optional[int]) -> Dict[str, Any]:
    question_numbers: List[int] = []
    groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    option_lines = 0
    char_count = 0
    scores: List[float] = []
    for line in sorted(lines or [], key=lambda item: (float(item.get("y0", 0)), float(item.get("x0", 0)))):
        text = str(line.get("text") or "").strip()
        if not text:
            continue
        char_count += len(text)
        if line.get("score") is not None:
            try:
                scores.append(float(line["score"]))
            except (TypeError, ValueError):
                pass
        question_match = QUESTION_RE.match(text)
        if question_match:
            if current is not None:
                groups.append(current)
            number = int(question_match.group(1))
            question_numbers.append(number)
            current = {"number": number, "options": set()}
            continue
        option_match = OPTION_RE.match(text)
        if option_match:
            option_lines += 1
            if current is not None:
                current["options"].add(option_match.group(1).upper())
            continue
        option_only_match = OPTION_ONLY_RE.match(text)
        if option_only_match:
            option_lines += 1
            if current is not None:
                current["options"].add(option_only_match.group(1).upper())
    if current is not None:
        groups.append(current)
    unique_numbers = sorted(set(question_numbers))
    option_counts = [len(group["options"]) for group in groups]
    with_expected_options = None
    if expected_options:
        with_expected_options = sum(count == expected_options for count in option_counts)
    return {
        "line_count": len([line for line in lines or [] if str(line.get("text") or "").strip()]),
        "char_count": char_count,
        "question_headers": len(question_numbers),
        "question_numbers": unique_numbers,
        "duplicate_question_headers": len(question_numbers) - len(unique_numbers),
        "option_marker_lines": option_lines,
        "question_groups": len(groups),
        "option_counts": option_counts,
        "questions_with_expected_options": with_expected_options,
        "mean_confidence": round(statistics.fmean(scores), 4) if scores else None,
        "low_confidence_ratio": round(sum(score < 0.70 for score in scores) / max(len(scores), 1), 4) if scores else None,
    }


def _candidate_params(model_root: Path, threads: int) -> Dict[str, Any]:
    from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion

    return {
        "Global.model_root_dir": str(model_root),
        "Global.log_level": "warning",
        "EngineConfig.onnxruntime.intra_op_num_threads": int(threads),
        "EngineConfig.onnxruntime.inter_op_num_threads": int(threads),
        "Det.engine_type": EngineType.ONNXRUNTIME,
        "Det.lang_type": LangDet.CH,
        "Det.model_type": ModelType.TINY,
        "Det.ocr_version": OCRVersion.PPOCRV6,
        "Rec.engine_type": EngineType.ONNXRUNTIME,
        "Rec.lang_type": LangRec.CH,
        "Rec.model_type": ModelType.TINY,
        "Rec.ocr_version": OCRVersion.PPOCRV6,
        "Cls.engine_type": EngineType.ONNXRUNTIME,
        "Cls.lang_type": LangDet.CH,
        "Cls.model_type": ModelType.MOBILE,
        "Cls.ocr_version": OCRVersion.PPOCRV4,
    }


def _pixmap_array(pix: Any) -> Any:
    import numpy as np

    array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n > 3:
        array = array[:, :, :3]
    return array.copy()


def _decode_candidate_output(output: Any, page: Any, dpi: int, clip: Any, source: str) -> List[Dict[str, Any]]:
    boxes = getattr(output, "boxes", None)
    texts = getattr(output, "txts", None)
    scores = getattr(output, "scores", None)
    if boxes is None:
        boxes = []
    if texts is None:
        texts = []
    if scores is None:
        scores = []
    scale = 72.0 / float(dpi)
    decoded: List[Dict[str, Any]] = []
    for index, box in enumerate(boxes):
        if index >= len(texts):
            break
        text = str(texts[index] or "").strip()
        score = float(scores[index]) if index < len(scores) else 0.0
        if not text:
            continue
        try:
            x0 = float(clip.x0) + float(box[0][0]) * scale
            y0 = float(clip.y0) + float(box[0][1]) * scale
            x1 = float(clip.x0) + float(box[2][0]) * scale
            y1 = float(clip.y0) + float(box[2][1]) * scale
        except (IndexError, TypeError, ValueError):
            continue
        decoded.append(
            {
                "page": page.number,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "mid_x": (x0 + x1) / 2.0,
                "width": x1 - x0,
                "text": text,
                "score": score,
                "source": source,
            }
        )
    return decoded


def _merge_candidate_lines(candidates: Iterable[Sequence[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for batch in candidates:
        for candidate in batch:
            text = str(candidate.get("text") or "")
            compact = _normalise_text(text, accents=False).replace(" ", "")
            best_index: Optional[int] = None
            best_distance = float("inf")
            for index, existing in enumerate(merged):
                if abs(float(existing.get("y0", 0)) - float(candidate.get("y0", 0))) > 6.0:
                    continue
                distance = abs(float(existing.get("y0", 0)) - float(candidate.get("y0", 0))) + abs(
                    float(existing.get("x0", 0)) - float(candidate.get("x0", 0))
                ) / 30.0
                if distance < best_distance:
                    best_distance = distance
                    best_index = index
            if best_index is None:
                merged.append(dict(candidate))
                continue
            existing = merged[best_index]
            existing_text = str(existing.get("text") or "")
            existing_marker = bool(
                QUESTION_RE.match(existing_text)
                or OPTION_RE.match(existing_text)
                or OPTION_ONLY_RE.match(existing_text)
            )
            candidate_marker = bool(
                QUESTION_RE.match(text)
                or OPTION_RE.match(text)
                or OPTION_ONLY_RE.match(text)
            )
            # Detecção pode devolver o número/letra em uma caixa e o texto em
            # outra caixa quase na mesma ordenada. Nunca deixe uma linha maior
            # apagar esse marcador: ele é essencial para a integridade
            # estrutural, mesmo quando o texto das passadas diverge.
            if existing_marker != candidate_marker:
                if existing_marker:
                    continue
                merged[best_index] = dict(candidate)
                continue
            existing_compact = _normalise_text(existing_text, accents=False).replace(" ", "")
            candidate_spaces = len(re.findall(r"\s+", text))
            existing_spaces = len(re.findall(r"\s+", str(existing.get("text") or "")))
            if len(compact) > max(3, int(len(existing_compact) * 1.08)) or (
                len(compact) >= max(3, int(len(existing_compact) * 0.75)) and candidate_spaces > existing_spaces
            ):
                merged[best_index] = dict(candidate)
    return sorted(merged, key=lambda item: (float(item.get("y0", 0)), float(item.get("x0", 0))))


def _candidate_refine(
    engine: Any,
    page: Any,
    lines: List[Dict[str, Any]],
    dpi: int,
    *,
    force_render: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Reconhece só linhas suspeitas, mas registra sempre a rasterização 600 DPI."""

    import numpy as np
    from rapidocr.ch_ppocr_rec.typings import TextRecInput

    target_dpi = max(500, min(700, int(dpi) + 300))
    started = time.perf_counter()
    pix = page.get_pixmap(dpi=target_dpi, alpha=False)
    page_image = _pixmap_array(pix)
    render_seconds = time.perf_counter() - started
    page_scale = target_dpi / 72.0
    candidates: List[Tuple[int, Dict[str, Any], Any]] = []
    for index, line in enumerate(lines):
        text = str(line.get("text") or "").strip()
        compact = _normalise_text(text, accents=False).replace(" ", "")
        suspicious = (
            float(line.get("score", 1.0)) < 0.70
            or "\ufffd" in text
            or bool(re.search(r"[A-Za-zÀ-ÿ]{10,}", text))
        )
        if not suspicious or len(compact) < 3:
            continue
        px0 = max(0, int(round(float(line.get("x0", 0)) * page_scale)) - int(3 * page_scale))
        py0 = max(0, int(round(float(line.get("y0", 0)) * page_scale)) - int(2.5 * page_scale))
        px1 = min(page_image.shape[1], int(round(float(line.get("x1", 0)) * page_scale)) + int(3 * page_scale))
        py1 = min(page_image.shape[0], int(round(float(line.get("y1", 0)) * page_scale)) + int(2.5 * page_scale))
        if px1 - px0 >= 8 and py1 - py0 >= 3:
            candidates.append((index, line, page_image[py0:py1, px0:px1]))
    result = [dict(line) for line in lines]
    rec_calls = 0
    rec_crops = 0
    rec_seconds = 0.0
    if candidates:
        for start in range(0, len(candidates), 24):
            batch = candidates[start : start + 24]
            rec_started = time.perf_counter()
            recognized = engine.text_rec(TextRecInput(img=[item[2] for item in batch], return_word_box=False))
            rec_seconds += time.perf_counter() - rec_started
            rec_calls += 1
            rec_crops += len(batch)
            texts = getattr(recognized, "txts", None)
            scores = getattr(recognized, "scores", None)
            if texts is None:
                texts = []
            if scores is None:
                scores = []
            for offset, (line_index, original, _crop) in enumerate(batch):
                if offset >= len(texts):
                    continue
                refined_text = str(texts[offset] or "").strip()
                refined_score = float(scores[offset]) if offset < len(scores) else 0.0
                original_text = str(original.get("text") or "").strip()
                if refined_score < 0.42 or not refined_text:
                    continue
                old_compact = _normalise_text(original_text, accents=False).replace(" ", "")
                new_compact = _normalise_text(refined_text, accents=False).replace(" ", "")
                if len(new_compact) < max(8, int(len(old_compact) * 0.68)):
                    continue
                if difflib.SequenceMatcher(None, old_compact, new_compact, autojunk=False).ratio() < 0.78:
                    continue
                if len(re.findall(r"\s+", refined_text)) <= len(re.findall(r"\s+", original_text)) and "\ufffd" not in original_text:
                    continue
                result[line_index]["text"] = refined_text
                result[line_index]["score"] = refined_score
                result[line_index]["source"] = "ocr_refined"
                result[line_index]["ocr_original_text"] = original_text
    return result, {
        "refine_target_dpi": target_dpi,
        "refine_render_seconds": round(render_seconds, 4) if force_render else 0.0,
        "refine_rec_calls": rec_calls,
        "refine_rec_crops": rec_crops,
        "refine_rec_seconds": round(rec_seconds, 4),
    }


def _candidate_page(engine: Any, page: Any, dpi: int, strategy: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    import cv2

    clip = page.rect
    started = time.perf_counter()
    pix = page.get_pixmap(dpi=int(dpi), clip=clip, alpha=False)
    image = _pixmap_array(pix)
    render_seconds = time.perf_counter() - started
    call_count = 0
    model_seconds = 0.0

    def call(input_image: Any, source: str) -> List[Dict[str, Any]]:
        nonlocal call_count, model_seconds
        call_count += 1
        call_started = time.perf_counter()
        output = engine(input_image)
        model_seconds += time.perf_counter() - call_started
        return _decode_candidate_output(output, page, dpi, clip, source)

    original = call(image, "ocr")
    details: Dict[str, Any] = {
        "render_seconds": round(render_seconds, 4),
        "model_seconds": round(model_seconds, 4),
        "engine_calls": call_count,
        "recovery_triggered": False,
        "fallback_triggered": False,
    }
    if strategy == "candidate_adaptive":
        quick = _structural_metrics(original, expected_options=None)
        bad_page = not original or (quick["line_count"] < 4 and quick["char_count"] < 120)
        missing_structure = bool(
            quick["question_groups"]
            and any(count < 3 for count in (quick.get("option_counts") or []))
        )
        scores = [float(item.get("score", 0.0)) for item in original]
        low_ratio = sum(score < 0.70 for score in scores) / max(len(scores), 1)
        min_score = min(scores, default=1.0)
        needs_recovery = (
            bad_page
            or missing_structure
            or low_ratio >= 0.25
            or min_score < 0.58
            or any("\ufffd" in str(item.get("text") or "") for item in original)
        )
        lines = original
        if needs_recovery and original:
            details["recovery_triggered"] = True
            lines, refine_details = _candidate_refine(engine, page, original, dpi)
            details.update(refine_details)
        post_refine = _structural_metrics(lines, expected_options=None)
        still_missing_structure = bool(
            post_refine["question_groups"]
            and any(count < 3 for count in (post_refine.get("option_counts") or []))
        )
        if bad_page or still_missing_structure:
            details["fallback_triggered"] = True
            enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY))
            adaptive = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
            otsu = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            lines = _merge_candidate_lines([lines, call(adaptive, "ocr_preprocessed"), call(otsu, "ocr_otsu")])
        details["model_seconds"] = round(model_seconds, 4)
        details["engine_calls"] = call_count
        return lines, details

    enhanced_gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(cv2.cvtColor(image, cv2.COLOR_RGB2GRAY))
    adaptive = cv2.adaptiveThreshold(enhanced_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
    otsu = cv2.threshold(enhanced_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    lines = _merge_candidate_lines([original, call(adaptive, "ocr_preprocessed"), call(otsu, "ocr_otsu")])
    lines, refine_details = _candidate_refine(engine, page, lines, dpi)
    details.update(refine_details)
    details["model_seconds"] = round(model_seconds, 4)
    details["engine_calls"] = call_count
    return lines, details


class _CurrentProbe:
    def __init__(self, target: Any):
        self.target = target
        self.engine_calls = 0
        self.refine_rec_calls = 0
        self.refine_rec_crops = 0
        self.model_seconds = 0.0
        self.refine_rec_seconds = 0.0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.engine_calls += 1
        started = time.perf_counter()
        output = self.target(*args, **kwargs)
        self.model_seconds += time.perf_counter() - started
        return output

    def text_rec(self, crops: Any, *args: Any, **kwargs: Any) -> Any:
        self.refine_rec_calls += 1
        self.refine_rec_crops += len(crops)
        started = time.perf_counter()
        output = self.target.text_rec(crops, *args, **kwargs)
        self.refine_rec_seconds += time.perf_counter() - started
        return output


def _worker_ready(profile: str, threads: int, model_root: Path) -> Dict[str, Any]:
    os.environ["OMP_NUM_THREADS"] = str(threads)
    os.environ["MKL_NUM_THREADS"] = str(threads)
    os.environ["OPENBLAS_NUM_THREADS"] = str(threads)
    os.environ["NUMEXPR_NUM_THREADS"] = str(threads)
    started = time.perf_counter()
    if profile == "current_three_passes":
        from rapidocr_onnxruntime import RapidOCR

        from services.pdf_pipeline.layout import layout_detector

        engine = RapidOCR(intra_op_num_threads=threads, inter_op_num_threads=threads)
        layout_detector._OCR_ENGINE = engine
        package_root = Path(__import__("rapidocr_onnxruntime").__file__).resolve().parent
        model_files = [
            package_root / "models" / "ch_PP-OCRv4_det_infer.onnx",
            package_root / "models" / "ch_PP-OCRv4_rec_infer.onnx",
            package_root / "models" / "ch_ppocr_mobile_v2.0_cls_infer.onnx",
        ]
        return {
            "engine": engine,
            "layout_detector": layout_detector,
            "load_seconds": round(time.perf_counter() - started, 4),
            "package": "rapidocr-onnxruntime",
            "package_version": _package_version("rapidocr-onnxruntime"),
            "model_files": [str(path).replace("\\", "/") for path in model_files],
        }
    if profile not in {"candidate_three_passes", "candidate_adaptive"}:
        raise ValueError(f"Unknown profile: {profile}")
    from rapidocr import RapidOCR

    engine = RapidOCR(params=_candidate_params(model_root, threads))
    model_files = [str(path).replace("\\", "/") for path in sorted(model_root.glob("*.onnx"))]
    return {
        "engine": engine,
        "load_seconds": round(time.perf_counter() - started, 4),
        "package": "rapidocr",
        "package_version": _package_version("rapidocr"),
        "model_files": model_files,
    }


def _package_version(name: str) -> Optional[str]:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def _run_worker(args: argparse.Namespace) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import fitz

    doc = fitz.open(args.pdf)
    ready = _worker_ready(args.profile, args.threads, Path(args.model_root))
    engine = ready.pop("engine")
    print(
        json.dumps(
            {
                "kind": "ready",
                "profile": args.profile,
                "pdf": args.pdf,
                "threads": args.threads,
                "load_seconds": ready["load_seconds"],
                "package": ready["package"],
                "package_version": ready["package_version"],
                "model_files": ready["model_files"],
                "model_sha256": {path: _sha256(Path(path)) for path in ready["model_files"]},
                **_memory_info(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    page_indexes = [int(value) for value in args.pages.split(",") if value.strip()]
    for page_index in page_indexes:
        started = time.perf_counter()
        try:
            page = doc[page_index]
            if args.profile == "current_three_passes":
                from services.pdf_pipeline.layout import layout_detector

                probe = _CurrentProbe(engine)
                layout_detector._OCR_ENGINE = probe
                lines = layout_detector.extract_ocr_lines_three_passes(page, dpi=args.dpi, min_score=0.25)
                strategy = {
                    "engine_calls": probe.engine_calls,
                    "model_seconds": round(probe.model_seconds, 4),
                    "refine_rec_calls": probe.refine_rec_calls,
                    "refine_rec_crops": probe.refine_rec_crops,
                    "refine_rec_seconds": round(probe.refine_rec_seconds, 4),
                }
            else:
                lines, strategy = _candidate_page(engine, page, args.dpi, args.profile)
            text = _line_text(lines)
            structural = _structural_metrics(lines, expected_options=args.expected_options)
            page_result = {
                "kind": "page",
                "status": "ok",
                "page_index": page_index,
                "page_1based": page_index + 1,
                "native_text": page.get_text("text"),
                "lines": lines,
                "ocr_text": text,
                "structural": structural,
                "strategy": strategy,
                "wall_seconds": round(time.perf_counter() - started, 4),
                **_memory_info(),
            }
        except Exception as exc:
            page_result = {
                "kind": "page",
                "status": "error",
                "page_index": page_index,
                "page_1based": page_index + 1,
                "error": f"{type(exc).__name__}: {exc}",
                "wall_seconds": round(time.perf_counter() - started, 4),
                **_memory_info(),
            }
        print(json.dumps(page_result, ensure_ascii=False), flush=True)
    return 0


def _parse_fixture_spec(spec: str) -> Fixture:
    path = (ROOT / spec).resolve() if not Path(spec).is_absolute() else Path(spec)
    name = path.name.lower()
    if name == "6_prova.pdf":
        return Fixture(path, 50, 4)
    if name == "5_prova.pdf":
        return Fixture(path, 40, 4)
    return Fixture(path, None, None)


def _read_stream(stream: Any, events: queue.Queue[Tuple[str, str]], label: str) -> None:
    try:
        for line in iter(stream.readline, ""):
            events.put((label, line))
    finally:
        events.put((label, ""))


def _run_profile_fixture(
    python: Path,
    profile: str,
    fixture: Fixture,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    import fitz

    with fitz.open(fixture.path) as fixture_doc:
        page_count = len(fixture_doc)
    if args.max_pages > 0:
        page_count = min(page_count, args.max_pages)
    if args.page_indices:
        requested = []
        for value in args.page_indices.split(","):
            if not value.strip():
                continue
            index = int(value)
            if index < 0 or index >= page_count:
                raise ValueError(f"Índice de página fora do fixture: {index}")
            requested.append(index)
        pages = sorted(set(requested))
    else:
        pages = list(range(page_count))
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["OMP_NUM_THREADS"] = str(args.threads)
    env["MKL_NUM_THREADS"] = str(args.threads)
    env["OPENBLAS_NUM_THREADS"] = str(args.threads)
    env["NUMEXPR_NUM_THREADS"] = str(args.threads)
    if profile != "current_three_passes":
        candidate_site = ROOT / "venv" / "Lib" / "site-packages"
        env["PYTHONPATH"] = str(candidate_site) + os.pathsep + env.get("PYTHONPATH", "")
    command = [
        str(python),
        str(Path(__file__).resolve()),
        "--worker",
        "--profile",
        profile,
        "--pdf",
        str(fixture.path),
        "--pages",
        ",".join(str(page) for page in pages),
        "--dpi",
        str(args.dpi),
        "--threads",
        str(args.threads),
        "--model-root",
        str(args.model_root),
        "--expected-options",
        str(fixture.expected_options or 0),
    ]
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    events: queue.Queue[Tuple[str, str]] = queue.Queue()
    stdout_thread = threading.Thread(target=_read_stream, args=(process.stdout, events, "stdout"), daemon=True)
    stderr_thread = threading.Thread(target=_read_stream, args=(process.stderr, events, "stderr"), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    ready: Dict[str, Any] = {}
    page_results: List[Dict[str, Any]] = []
    stderr_lines: List[str] = []
    remaining = set(pages)
    deadline = time.monotonic() + args.page_timeout
    terminated_reason: Optional[str] = None
    while remaining:
        try:
            label, line = events.get(timeout=max(0.1, deadline - time.monotonic()))
        except queue.Empty:
            terminated_reason = "startup_timeout" if not ready else "page_timeout"
            process.kill()
            break
        if not line:
            if label == "stdout" and process.poll() is not None:
                terminated_reason = "worker_exit"
                break
            continue
        if label == "stderr":
            stderr_lines.append(line.rstrip())
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("kind") == "ready":
            ready = event
            deadline = time.monotonic() + args.page_timeout
            continue
        if event.get("kind") == "page":
            page_results.append(event)
            remaining.discard(int(event.get("page_index", -1)))
            status = event.get("status", "unknown")
            print(
                f"[{profile}] {fixture.path.name} pág. {event.get('page_1based')} "
                f"{status} ({event.get('wall_seconds', '?')} s)",
                flush=True,
            )
            deadline = time.monotonic() + args.page_timeout
    if remaining and terminated_reason:
        process.kill()
        for page in sorted(remaining):
            page_results.append(
                {
                    "kind": "page",
                    "status": terminated_reason,
                    "page_index": page,
                    "page_1based": page + 1,
                }
            )
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    return {
        "profile": profile,
        "fixture": str(fixture.path),
        "expected_questions": fixture.expected_questions,
        "expected_options": fixture.expected_options,
        "pages_requested": pages,
        "pages": sorted(page_results, key=lambda item: int(item.get("page_index", 0))),
        "ready": ready,
        "worker_exit_code": process.returncode,
        "worker_termination": terminated_reason,
        "worker_wall_seconds": round(time.perf_counter() - started, 4),
        "stderr_tail": stderr_lines[-20:],
    }


def _aggregate_run(run: Dict[str, Any]) -> Dict[str, Any]:
    pages = run.get("pages") or []
    ok_pages = [page for page in pages if page.get("status") == "ok"]
    native_text = "\n".join(str(page.get("native_text") or "") for page in ok_pages)
    ocr_text = "\n".join(str(page.get("ocr_text") or "") for page in ok_pages)
    all_lines = [line for page in ok_pages for line in (page.get("lines") or [])]
    structural = _structural_metrics(all_lines, run.get("expected_options"))
    expected = run.get("expected_questions")
    found = set(structural.get("question_numbers") or [])
    if expected:
        expected_set = set(range(1, int(expected) + 1))
        covered = sorted(found & expected_set)
        structural.update(
            {
                "expected_question_count": int(expected),
                "question_coverage_count": len(covered),
                "question_coverage_pct": round(len(covered) / expected * 100.0, 2),
                "missing_question_numbers": sorted(expected_set - found),
            }
        )
    native_clean_chars = len(_normalise_text(" ".join(_clean_reference_lines(native_text)), accents=True))
    result: Dict[str, Any] = {
        "ok_page_count": len(ok_pages),
        "timeout_or_error_page_count": len(pages) - len(ok_pages),
        "wall_seconds": run.get("worker_wall_seconds"),
        "warm_page_seconds": [page.get("wall_seconds") for page in ok_pages],
        "warm_page_seconds_median": round(statistics.median([page.get("wall_seconds", 0) for page in ok_pages]), 4) if ok_pages else None,
        "warm_page_seconds_p90": round(statistics.quantiles([page.get("wall_seconds", 0) for page in ok_pages], n=10)[8], 4) if len(ok_pages) >= 2 else (ok_pages[0].get("wall_seconds") if ok_pages else None),
        "peak_rss_mib_max": max((float(page.get("peak_rss_mib", 0)) for page in ok_pages), default=0.0),
        "ocr_char_count": len(ocr_text),
        "structural": structural,
        "strategy": {
            "engine_calls": sum(int((page.get("strategy") or {}).get("engine_calls", 0)) for page in ok_pages),
            "recovery_pages": sum(bool((page.get("strategy") or {}).get("recovery_triggered")) for page in ok_pages),
            "fallback_pages": sum(bool((page.get("strategy") or {}).get("fallback_triggered")) for page in ok_pages),
            "refine_rec_crops": sum(int((page.get("strategy") or {}).get("refine_rec_crops", 0)) for page in ok_pages),
        },
    }
    if native_clean_chars >= 300:
        result["reference_kind"] = "native_proxy"
        result["text_reference"] = _reference_metrics(native_text, ocr_text)
    else:
        result["reference_kind"] = "structural_only"
        result["text_reference"] = {
            "note": "A camada nativa não tem texto suficiente; não há CER/semelhança textual confiável para este scan."
        }
    return result


def _main(args: argparse.Namespace) -> int:
    fixtures = [_parse_fixture_spec(spec) for spec in args.fixtures.split(",") if spec.strip()]
    profiles = [profile.strip() for profile in args.profiles.split(",") if profile.strip()]
    for fixture in fixtures:
        if not fixture.path.is_file():
            raise FileNotFoundError(f"Fixture não encontrada: {fixture.path}")
    output_path = Path(args.out) if args.out else ROOT / "tmp" / f"ocr_benchmark_{time.strftime('%Y%m%d_%H%M%S')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    runs: List[Dict[str, Any]] = []
    for profile in profiles:
        python = Path(args.current_python) if profile == "current_three_passes" else Path(args.candidate_python)
        if not python.is_file():
            raise FileNotFoundError(f"Python do perfil {profile} não encontrado: {python}")
        for fixture in fixtures:
            run = _run_profile_fixture(python, profile, fixture, args)
            run["aggregate"] = _aggregate_run(run)
            runs.append(run)
    by_key = {(run["profile"], Path(run["fixture"]).name): run["aggregate"] for run in runs}
    comparisons: List[Dict[str, Any]] = []
    for fixture in fixtures:
        name = fixture.path.name
        current = by_key.get(("current_three_passes", name), {})
        for profile in profiles:
            if profile == "current_three_passes":
                continue
            candidate = by_key.get((profile, name), {})
            current_median = current.get("warm_page_seconds_median")
            candidate_median = candidate.get("warm_page_seconds_median")
            current_f1 = (current.get("text_reference") or {}).get("token_f1_pct")
            candidate_f1 = (candidate.get("text_reference") or {}).get("token_f1_pct")
            comparisons.append(
                {
                    "fixture": name,
                    "candidate_profile": profile,
                    "median_speedup_vs_current": round(current_median / candidate_median, 3) if current_median and candidate_median else None,
                    "text_token_f1_delta_pct_points": round(candidate_f1 - current_f1, 2) if current_f1 is not None and candidate_f1 is not None else None,
                    "question_coverage_delta_pct_points": round(
                        float((candidate.get("structural") or {}).get("question_coverage_pct", 0))
                        - float((current.get("structural") or {}).get("question_coverage_pct", 0)),
                        2,
                    )
                    if (candidate.get("structural") or {}).get("question_coverage_pct") is not None
                    and (current.get("structural") or {}).get("question_coverage_pct") is not None
                    else None,
                }
            )
    report = {
        "benchmark": "ocr-current-vs-rapidocr-ppocrv6-tiny",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo": str(ROOT),
        "git_head": _git_head(),
        "hardware": {"platform": sys.platform, "python": sys.version, "cpu_count": os.cpu_count(), "threads": args.threads},
        "settings": {"dpi": args.dpi, "page_timeout_seconds": args.page_timeout, "profiles": profiles, "fixtures": [str(f.path) for f in fixtures]},
        "runs": runs,
        "comparisons": comparisons,
        "interpretation": {
            "native_proxy_warning": "5_prova.pdf usa a camada nativa como referência proxy; ela própria contém OCR/acentos imperfeitos.",
            "scan_warning": "6_prova.pdf é scan sem camada textual útil; a integridade é estrutural (questões/alternativas), não uma prova de CER.",
            "warm_time_definition": "warm_page_seconds mede o tempo de leitura da página dentro de um worker persistente e separa o carregamento do modelo.",
        },
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"result": str(output_path), "comparisons": comparisons}, ensure_ascii=False, indent=2))
    return 0


def _git_head() -> Optional[str]:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return None


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--profile", default="current_three_passes")
    parser.add_argument("--pdf", default="")
    parser.add_argument("--pages", default="0")
    parser.add_argument("--expected-options", type=int, default=0)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--model-root", type=Path, default=DEFAULT_MODEL_ROOT)
    parser.add_argument("--current-python", type=Path, default=ROOT / "venv" / "Scripts" / "python.exe")
    parser.add_argument("--candidate-python", type=Path, default=DEFAULT_CANDIDATE_ENV / "Scripts" / "python.exe")
    parser.add_argument("--fixtures", default="pdfs/6_prova.pdf,pdfs/5_prova.pdf")
    parser.add_argument("--profiles", default="current_three_passes,candidate_three_passes,candidate_adaptive")
    parser.add_argument("--max-pages", type=int, default=0, help="Limita páginas por fixture; 0 = todas")
    parser.add_argument("--page-indices", default="", help="Lista opcional de índices 0-based (ex.: 1,2,3)")
    parser.add_argument("--page-timeout", type=float, default=180.0)
    parser.add_argument("--out", default="")
    return parser.parse_args(argv)


if __name__ == "__main__":
    parsed = _parse_args()
    if parsed.worker:
        raise SystemExit(_run_worker(parsed))
    raise SystemExit(_main(parsed))
