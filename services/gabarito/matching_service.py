"""Selecao auditavel de gabaritos por identidade e estrutura da prova.

O parser legado continua responsavel por ler respostas. Este modulo decide se o
bloco lido realmente pertence ao caderno, combinando identificadores fortes e
validacoes estruturais. Na duvida, a decisao e fechada: nenhum gabarito e
atribuido automaticamente.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import fitz

from .gabarito_service import (
    GABARITO_HEADER_REGEX,
    _code_range_matches,
    extract_all_matrix_gabaritos,
    extract_code_ranges_from_text,
    extract_exam_code_ranges_from_pdf,
    parse_fgv_vertical_gabarito,
    parse_gabarito_from_pdf,
    parse_gabarito_from_text,
)


ANSWER_KEY_CONTEXT_REGEX = re.compile(
    r"\b(?:gabarito|folha\s+de\s+respostas?|respostas?\s+das?\s+quest(?:ao|oes)|"
    r"errata|retifica(?:cao|do)|resultado\s+definitivo)\b",
    re.IGNORECASE,
)

_COLORS = {
    "azul",
    "amarela",
    "amarelo",
    "branca",
    "branco",
    "cinza",
    "laranja",
    "rosa",
    "roxa",
    "roxo",
    "verde",
    "vermelha",
    "vermelho",
}

_TOKEN_STOP_WORDS = {
    "agente",
    "analista",
    "assistente",
    "auxiliar",
    "banca",
    "cargo",
    "com",
    "concurso",
    "edital",
    "fundamental",
    "geral",
    "ibam",
    "medio",
    "municipal",
    "municipio",
    "para",
    "pela",
    "pelo",
    "pref",
    "prefeitura",
    "prova",
    "sobre",
    "superior",
    "tecnico",
    "tipo",
}


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = (
        text.lower()
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("_", " ")
    )
    return re.sub(r"\s+", " ", text).strip()


def _unique(values: Iterable[Any]) -> List[Any]:
    result: List[Any] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _normalized_tokens(value: str, *, remove_generic: bool = True) -> List[str]:
    tokens = re.findall(r"[a-z0-9]{3,}", _normalize_text(value))
    if remove_generic:
        tokens = [token for token in tokens if token not in _TOKEN_STOP_WORDS]
    return _unique(tokens)


def _normalize_variant(value: str) -> str:
    normalized = _normalize_text(value)
    if normalized.isdigit():
        return str(int(normalized))
    return normalized


@dataclass
class IdentityMetadata:
    code_ranges: List[Tuple[int, int]] = field(default_factory=list)
    exam_types: List[str] = field(default_factory=list)
    variants: List[str] = field(default_factory=list)
    colors: List[str] = field(default_factory=list)
    cargo_codes: List[str] = field(default_factory=list)
    edital_ids: List[str] = field(default_factory=list)
    labeled_dates: List[str] = field(default_factory=list)
    shifts: List[str] = field(default_factory=list)
    education_levels: List[str] = field(default_factory=list)
    option_labels: List[str] = field(default_factory=list)
    years: List[str] = field(default_factory=list)
    subject_counts: Dict[str, int] = field(default_factory=dict)
    publication_status: str = "unknown"


@dataclass
class ExamAnswerKeyProfile:
    title: str
    metadata: IdentityMetadata
    question_numbers: List[int] = field(default_factory=list)
    question_count: int = 0
    reliable_numbering: bool = False
    option_labels: List[str] = field(default_factory=list)
    subject_counts: Dict[str, int] = field(default_factory=dict)
    cargo_tokens: List[str] = field(default_factory=list)
    locality_tokens: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnswerKeyCandidate:
    answers: Dict[int, str]
    page: Optional[int]
    method: str
    metadata: IdentityMetadata
    has_header: bool
    cargo_text: str = ""
    raw_text: str = field(default="", repr=False)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "method": self.method,
            "answer_count": len(self.answers),
            "question_numbers": sorted(self.answers),
            "has_header": self.has_header,
            "cargo_text": self.cargo_text[:300],
            "metadata": asdict(self.metadata),
        }


@dataclass
class AnswerKeyMatchResult:
    answers: Dict[int, str] = field(default_factory=dict)
    accepted: bool = False
    status: str = "not_found"
    confidence: float = 0.0
    method: str = "none"
    candidate_page: Optional[int] = None
    source_relation: str = "unknown"
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    profile: Optional[ExamAnswerKeyProfile] = None
    candidate: Optional[Dict[str, Any]] = None
    errata_pages: List[int] = field(default_factory=list)

    def to_audit_dict(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "accepted": self.accepted,
            "status": self.status,
            "confidence": self.confidence,
            "method": self.method,
            "candidate_page": self.candidate_page,
            "source_relation": self.source_relation,
            "answer_count": len(self.answers),
            "reasons": self.reasons,
            "warnings": self.warnings,
            "conflicts": self.conflicts,
            "profile": self.profile.to_dict() if self.profile else None,
            "candidate": self.candidate,
            "errata_pages": self.errata_pages,
        }

    def to_audit_json(self) -> str:
        return json.dumps(self.to_audit_dict(), ensure_ascii=False, sort_keys=True)


def _extract_identity_metadata(text: str) -> IdentityMetadata:
    normalized = _normalize_text(text)
    metadata = IdentityMetadata()
    metadata.code_ranges = extract_code_ranges_from_text(
        text,
        allow_parenthesized=True,
    )

    type_values: List[str] = []
    for pattern in (
        r"\b(?:prova\s+)?tipo\s*(?:n\s*[o0]?\s*)?[:#-]?\s*([0-9]{1,2}|[a-e])\b",
        r"\bcaderno\s*(?:n\s*[o0]?\s*)?[:#-]?\s*(?:tipo\s*)?([0-9]{1,2}|[a-e])\b",
    ):
        type_values.extend(match.group(1) for match in re.finditer(pattern, normalized))
    metadata.exam_types = _unique(_normalize_variant(value) for value in type_values)

    variant_values: List[str] = []
    for match in re.finditer(
        r"\b(?:versao|modelo)\s*(?:n\s*[o0]?\s*)?[:#-]?\s*([a-z0-9]{1,15})\b",
        normalized,
    ):
        variant_values.append(match.group(1))
    metadata.variants = _unique(_normalize_variant(value) for value in variant_values)
    metadata.colors = sorted(color for color in _COLORS if re.search(rf"\b{color}\b", normalized))

    cargo_codes: List[str] = []
    for match in re.finditer(
        r"\b(?:codigo\s+(?:do\s+)?cargo|cargo\s+n\s*[o0]?|cargo\s+codigo)\s*[:#-]?\s*([a-z0-9./-]{1,20})\b",
        normalized,
    ):
        cargo_codes.append(match.group(1).strip(".-/"))
    metadata.cargo_codes = _unique(code for code in cargo_codes if code)

    edital_ids: List[str] = []
    for match in re.finditer(
        r"\bedital\s*(?:n\s*[o0]?\s*)?[:#-]?\s*([0-9]{1,4}(?:[./-][0-9]{1,4})?)\b",
        normalized,
    ):
        edital_ids.append(match.group(1))
    metadata.edital_ids = _unique(edital_ids)

    labeled_dates: List[str] = []
    for line in normalized.splitlines() if "\n" in normalized else [_normalize_text(line) for line in str(text or "").splitlines()]:
        if not any(marker in line for marker in ("data da prova", "data de prova", "aplicacao", "realizacao")):
            continue
        labeled_dates.extend(
            match.group(0)
            for match in re.finditer(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", line)
        )
    metadata.labeled_dates = _unique(labeled_dates)

    shifts: List[str] = []
    for shift in ("manha", "tarde", "noite"):
        if re.search(rf"\b{shift}\b", normalized):
            shifts.append(shift)
    metadata.shifts = shifts

    education: List[str] = []
    for level in (
        "fundamental incompleto",
        "fundamental completo",
        "medio tecnico",
        "ensino medio",
        "nivel medio",
        "ensino superior",
        "nivel superior",
    ):
        if level in normalized:
            education.append(level)
    if not education and re.search(r"\bfundamental\b", normalized):
        education.append("fundamental")
    metadata.education_levels = _unique(education)

    declared_labels: List[str] = []
    for match in re.finditer(
        r"\b(?:alternativas?|opcoes?)\s*(?:de\s*)?([a-e])\s*(?:a|ate|-)\s*([a-e])\b",
        normalized,
    ):
        start, end = ord(match.group(1).upper()), ord(match.group(2).upper())
        if ord("A") <= start <= end <= ord("E"):
            declared_labels.extend(chr(code) for code in range(start, end + 1))
    for match in re.finditer(r"\b([2-5])\s+alternativas?\b", normalized):
        declared_labels.extend(chr(ord("A") + index) for index in range(int(match.group(1))))
    if re.search(r"\b(?:certo\s*(?:e|/)\s*errado|certo\s+ou\s+errado)\b", normalized):
        declared_labels.extend(["C", "E"])
    metadata.option_labels = sorted(set(declared_labels))
    metadata.years = _unique(re.findall(r"\b(?:19|20)\d{2}\b", normalized))

    for match in re.finditer(
        r"([a-z][a-z\s]{3,60})\s*[:=-]\s*(\d{1,3})\s*(?:questoes|itens)\b",
        normalized,
    ):
        subject = _normalize_text(match.group(1)).strip(" -:.;")
        if subject:
            metadata.subject_counts[subject] = int(match.group(2))

    if re.search(r"\b(?:errata|retificacao|retificado)\b", normalized):
        metadata.publication_status = "errata"
    elif re.search(r"\b(?:definitivo|pos[- ]?recursos?|apos\s+recursos?)\b", normalized):
        metadata.publication_status = "definitive"
    elif re.search(r"\b(?:preliminar|provisorio)\b", normalized):
        metadata.publication_status = "preliminary"

    return metadata


def _title_identity(title: str) -> Tuple[List[str], List[str]]:
    normalized = _normalize_text(title)
    pref_match = re.search(
        r"\b(?:pref(?:eitura)?|municipio)\.?\s+(?:municipal\s+de\s+)?"
        r"([a-z][a-z\s'-]{2,}?)(?:/[a-z]{2}|\s+(?:19|20)\d{2}|$)",
        normalized,
    )
    locality = pref_match.group(1) if pref_match else ""
    cargo_part = normalized[: pref_match.start()] if pref_match else normalized
    cargo_part = re.sub(r"\b(?:19|20)\d{2}\b", " ", cargo_part)
    cargo_tokens = _normalized_tokens(cargo_part)
    locality_tokens = _normalized_tokens(locality, remove_generic=False)
    return cargo_tokens, locality_tokens


def _question_number(question: Any) -> Optional[int]:
    if isinstance(question, dict):
        raw = question.get("numero_questao")
    else:
        raw = getattr(question, "numero_questao", None)
    match = re.match(r"^\s*(\d+)", str(raw or ""))
    return int(match.group(1)) if match else None


def _question_options(question: Any) -> Iterable[str]:
    raw = question.get("opcoes") if isinstance(question, dict) else getattr(question, "options", None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = {}
    if isinstance(raw, dict):
        return [str(key).upper() for key in raw if re.fullmatch(r"[A-Ea-e]", str(key))]
    if isinstance(raw, list):
        labels: List[str] = []
        for item in raw:
            if isinstance(item, dict):
                key = item.get("letter") or item.get("key") or item.get("letra")
                if key and re.fullmatch(r"[A-Ea-e]", str(key)):
                    labels.append(str(key).upper())
            elif isinstance(item, str):
                match = re.match(r"^\s*\(?([A-Ea-e])\)?", item)
                if match:
                    labels.append(match.group(1).upper())
        return labels
    return []


def _question_subject(question: Any) -> str:
    if isinstance(question, dict):
        value = question.get("disciplina") or question.get("subject")
    else:
        value = getattr(question, "subject", None)
    return _normalize_text(value or "geral")


def build_exam_answer_key_profile(
    pdf_input: Any,
    questions: Sequence[Any],
    *,
    title: str = "",
    tipo: Optional[str] = None,
    code_ranges: Optional[List[Tuple[int, int]]] = None,
    max_pages: int = 3,
) -> ExamAnswerKeyProfile:
    """Constroi a identidade esperada do gabarito a partir do caderno extraido."""
    header_text = ""
    doc = None
    should_close = False
    try:
        if isinstance(pdf_input, fitz.Document):
            doc = pdf_input
        elif isinstance(pdf_input, (bytes, bytearray)):
            doc = fitz.open(stream=pdf_input, filetype="pdf")
            should_close = True
        elif isinstance(pdf_input, str) and pdf_input:
            doc = fitz.open(pdf_input)
            should_close = True
        if doc is not None:
            header_text = "\n".join(
                doc[index].get_text() for index in range(min(len(doc), max_pages))
            )
    finally:
        if should_close and doc is not None:
            doc.close()

    metadata = _extract_identity_metadata(f"{title}\n{header_text}")
    if code_ranges is None and pdf_input:
        try:
            code_ranges = extract_exam_code_ranges_from_pdf(pdf_input, max_pages=max_pages)
        except Exception:
            code_ranges = []
    metadata.code_ranges = _unique(code_ranges or metadata.code_ranges)
    if tipo:
        normalized_tipo = _normalize_variant(tipo)
        metadata.exam_types = _unique([normalized_tipo, *metadata.exam_types])

    numbers = _unique(
        number for number in (_question_number(question) for question in questions) if number is not None
    )
    sorted_numbers = sorted(numbers)
    reliable_numbering = bool(
        len(sorted_numbers) >= 5
        and sorted_numbers[0] == 1
        and sorted_numbers == list(range(1, sorted_numbers[-1] + 1))
        and len(sorted_numbers) == len(questions)
    )
    option_labels = sorted(
        set(label for question in questions for label in _question_options(question))
    )
    subject_counts = dict(Counter(_question_subject(question) for question in questions))
    cargo_tokens, locality_tokens = _title_identity(title)
    return ExamAnswerKeyProfile(
        title=title,
        metadata=metadata,
        question_numbers=sorted_numbers,
        question_count=len(questions),
        reliable_numbering=reliable_numbering,
        option_labels=option_labels,
        subject_counts=subject_counts,
        cargo_tokens=cargo_tokens,
        locality_tokens=locality_tokens,
    )


def _answer_text_without_identity_lines(text: str) -> str:
    kept_lines: List[str] = []
    for line in str(text or "").splitlines():
        if extract_code_ranges_from_text(line, allow_parenthesized=True):
            continue
        kept_lines.append(line)
    return "\n".join(kept_lines)


def _answers_from_page_text(text: str) -> Dict[int, str]:
    answer_text = _answer_text_without_identity_lines(text)
    answers = parse_fgv_vertical_gabarito(answer_text)
    if not answers:
        answers = parse_gabarito_from_text(answer_text)
    return {int(number): str(answer).upper() for number, answer in answers.items()}


def _extract_candidates(
    doc: fitz.Document,
    *,
    document_hint: str = "",
) -> List[AnswerKeyCandidate]:
    candidates: List[AnswerKeyCandidate] = []
    page_texts = [page.get_text() for page in doc]
    matrix_pages = set()

    for matrix in extract_all_matrix_gabaritos(doc):
        page_number = int(matrix.get("page") or 0) or None
        if page_number is not None:
            matrix_pages.add(page_number)
        page_text = page_texts[page_number - 1] if page_number else ""
        metadata = _extract_identity_metadata(
            f"{document_hint}\n{page_text}\n{matrix.get('cargo', '')}\nTIPO {matrix.get('tipo', '')}"
        )
        candidate = AnswerKeyCandidate(
            answers={int(number): str(answer).upper() for number, answer in matrix["gabarito"].items()},
            page=page_number,
            method="matrix_row",
            metadata=metadata,
            has_header=True,
            cargo_text=str(matrix.get("cargo") or ""),
            raw_text=page_text,
        )
        candidates.append(candidate)

    for page_index, page_text in enumerate(page_texts, start=1):
        if page_index in matrix_pages:
            continue
        metadata = _extract_identity_metadata(f"{document_hint}\n{page_text}")
        has_header = bool(
            GABARITO_HEADER_REGEX.search(page_text)
            or ANSWER_KEY_CONTEXT_REGEX.search(_normalize_text(page_text))
        )
        if not has_header:
            continue
        answers = _answers_from_page_text(page_text)
        minimum = 1 if metadata.publication_status == "errata" else 5
        if len(answers) < minimum:
            continue
        candidates.append(
            AnswerKeyCandidate(
                answers=answers,
                page=page_index,
                method="page_text",
                metadata=metadata,
                has_header=True,
                raw_text=page_text,
            )
        )

    deduplicated: List[AnswerKeyCandidate] = []
    seen = set()
    for candidate in candidates:
        key = (candidate.page, tuple(sorted(candidate.answers.items())))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(candidate)
    return deduplicated


def _sets_conflict(expected: Sequence[str], actual: Sequence[str]) -> bool:
    return bool(expected and actual and set(expected).isdisjoint(actual))


def _range_sets_match(
    expected: Sequence[Tuple[int, int]],
    actual: Sequence[Tuple[int, int]],
) -> bool:
    return any(
        _code_range_matches(expected_range, actual_range)
        for expected_range in expected
        for actual_range in actual
    )


def _token_coverage(expected: Sequence[str], candidate_text: str) -> float:
    if not expected:
        return 0.0
    candidate_tokens = set(_normalized_tokens(candidate_text, remove_generic=False))
    return len(set(expected).intersection(candidate_tokens)) / len(set(expected))


def _candidate_subject_counts(
    candidate: AnswerKeyCandidate,
    expected_subjects: Dict[str, int],
) -> Dict[str, int]:
    counts = dict(candidate.metadata.subject_counts)
    normalized_text = _normalize_text(candidate.raw_text)
    for subject in expected_subjects:
        if subject in {"", "geral", "conhecimentos gerais"} or subject in counts:
            continue
        subject_pattern = re.escape(subject)
        explicit = re.search(
            rf"\b{subject_pattern}\b.{{0,50}}?(\d{{1,3}})\s*(?:questoes|itens)\b",
            normalized_text,
        )
        if explicit:
            counts[subject] = int(explicit.group(1))
            continue
        interval = re.search(
            rf"\b{subject_pattern}\b.{{0,50}}?(\d{{1,3}})\s*(?:a|ate|-)\s*(\d{{1,3}})\b",
            normalized_text,
        )
        if interval:
            start, end = int(interval.group(1)), int(interval.group(2))
            if end >= start:
                counts[subject] = end - start + 1
    return counts


def _score_candidate(
    profile: ExamAnswerKeyProfile,
    candidate: AnswerKeyCandidate,
    source_relation: str,
) -> Tuple[float, List[str], List[str], List[str]]:
    score = 0.0
    reasons: List[str] = []
    warnings: List[str] = []
    conflicts: List[str] = []
    expected = profile.metadata
    actual = candidate.metadata

    if source_relation in {"paired", "embedded", "same_document", "manual"}:
        score += 20
        reasons.append(f"source_relation:{source_relation}")
    if candidate.has_header:
        score += 10
        reasons.append("answer_key_header_or_layout")

    if expected.code_ranges and actual.code_ranges:
        if _range_sets_match(expected.code_ranges, actual.code_ranges):
            score += 120
            reasons.append("code_range_exact")
        else:
            conflicts.append("code_range_mismatch")
    elif expected.code_ranges:
        warnings.append("candidate_has_no_code_range")

    if expected.cargo_codes and actual.cargo_codes:
        if not _sets_conflict(expected.cargo_codes, actual.cargo_codes):
            score += 100
            reasons.append("cargo_code_exact")
        else:
            conflicts.append("cargo_code_mismatch")

    expected_types = [_normalize_variant(value) for value in expected.exam_types]
    actual_types = [_normalize_variant(value) for value in actual.exam_types]
    if expected_types and actual_types:
        if not _sets_conflict(expected_types, actual_types):
            score += 45
            reasons.append("exam_type_exact")
        else:
            conflicts.append("exam_type_mismatch")

    expected_variants = [_normalize_variant(value) for value in expected.variants]
    actual_variants = [_normalize_variant(value) for value in actual.variants]
    if expected_variants and actual_variants:
        if not _sets_conflict(expected_variants, actual_variants):
            score += 45
            reasons.append("version_exact")
        else:
            conflicts.append("version_mismatch")

    if expected.colors and actual.colors:
        if not _sets_conflict(expected.colors, actual.colors):
            score += 45
            reasons.append("booklet_color_exact")
        else:
            conflicts.append("booklet_color_mismatch")

    if expected.edital_ids and actual.edital_ids:
        if not _sets_conflict(expected.edital_ids, actual.edital_ids):
            score += 40
            reasons.append("edital_exact")
        else:
            conflicts.append("edital_mismatch")

    if expected.labeled_dates and actual.labeled_dates:
        if not _sets_conflict(expected.labeled_dates, actual.labeled_dates):
            score += 25
            reasons.append("exam_date_exact")
        else:
            conflicts.append("exam_date_mismatch")

    if expected.shifts and actual.shifts:
        if not _sets_conflict(expected.shifts, actual.shifts):
            score += 25
            reasons.append("shift_exact")
        else:
            conflicts.append("shift_mismatch")

    candidate_numbers = sorted(candidate.answers)
    if profile.question_count >= 5:
        if len(candidate.answers) == profile.question_count:
            score += 35
            reasons.append("question_count_exact")
        elif actual.publication_status != "errata":
            conflicts.append("question_count_mismatch")

    if profile.reliable_numbering:
        if candidate_numbers == profile.question_numbers:
            score += 40
            reasons.append("question_sequence_exact")
        elif actual.publication_status != "errata":
            conflicts.append("question_sequence_mismatch")

    observed_answers = {answer for answer in candidate.answers.values() if answer != "X"}
    if profile.option_labels:
        declared_or_observed = set(actual.option_labels) or observed_answers
        unexpected = declared_or_observed.difference(profile.option_labels)
        if unexpected:
            conflicts.append("option_alphabet_mismatch")
        elif actual.option_labels and declared_or_observed == set(profile.option_labels):
            score += 25
            reasons.append("option_format_exact")
        else:
            score += 20
            reasons.append("option_alphabet_compatible")

    cargo_source = candidate.cargo_text or candidate.raw_text
    cargo_coverage = _token_coverage(profile.cargo_tokens, cargo_source)
    if profile.cargo_tokens:
        if cargo_coverage == 1.0:
            score += 60
            reasons.append("full_cargo_match")
        elif cargo_coverage >= 0.65:
            score += 30
            reasons.append("partial_cargo_match")
        elif cargo_coverage > 0:
            score += 10 * cargo_coverage
            warnings.append("weak_cargo_match")
        elif candidate.cargo_text:
            conflicts.append("cargo_mismatch")

    locality_coverage = _token_coverage(profile.locality_tokens, candidate.raw_text)
    if profile.locality_tokens:
        if locality_coverage == 1.0:
            score += 25
            reasons.append("locality_exact")
        elif locality_coverage > 0:
            score += 5
            warnings.append("partial_locality_match")

    if expected.education_levels and actual.education_levels:
        if not _sets_conflict(expected.education_levels, actual.education_levels):
            score += 10
            reasons.append("education_level_match")
        else:
            warnings.append("education_level_mismatch")

    if expected.years and actual.years:
        if not _sets_conflict(expected.years, actual.years):
            score += 10
            reasons.append("year_match")
        else:
            warnings.append("year_mismatch")

    candidate_subjects = _candidate_subject_counts(candidate, profile.subject_counts)
    comparable_subjects = set(profile.subject_counts).intersection(candidate_subjects)
    if comparable_subjects:
        if all(
            profile.subject_counts[subject] == candidate_subjects[subject]
            for subject in comparable_subjects
        ):
            score += 15
            reasons.append("subject_distribution_match")
        else:
            conflicts.append("subject_distribution_mismatch")

    if actual.publication_status == "definitive":
        score += 25
        reasons.append("definitive_answer_key")
    elif actual.publication_status == "preliminary":
        reasons.append("preliminary_answer_key")
    elif actual.publication_status == "errata":
        score += 30
        reasons.append("errata")

    return score, reasons, warnings, _unique(conflicts)


def _confidence(score: float, reasons: Sequence[str]) -> float:
    if "code_range_exact" in reasons and "question_count_exact" in reasons:
        return 99.0
    if "cargo_code_exact" in reasons and "question_count_exact" in reasons:
        return 98.0
    if "code_range_exact" in reasons:
        return 94.0
    if score >= 180:
        return 96.0
    if score >= 140:
        return 91.0
    if score >= 105:
        return 86.0
    if score >= 85:
        return 79.0
    return 70.0


def _strong_identity_compatible(
    profile: ExamAnswerKeyProfile,
    candidate: AnswerKeyCandidate,
) -> bool:
    expected = profile.metadata
    actual = candidate.metadata
    if expected.code_ranges and actual.code_ranges and not _range_sets_match(expected.code_ranges, actual.code_ranges):
        return False
    for expected_values, actual_values in (
        (expected.cargo_codes, actual.cargo_codes),
        (expected.exam_types, actual.exam_types),
        (expected.variants, actual.variants),
        (expected.colors, actual.colors),
        (expected.edital_ids, actual.edital_ids),
        (expected.labeled_dates, actual.labeled_dates),
        (expected.shifts, actual.shifts),
    ):
        if _sets_conflict(expected_values, actual_values):
            return False
    return True


def match_gabarito_from_pdf(
    pdf_input: Any,
    profile: ExamAnswerKeyProfile,
    *,
    source_relation: str = "unknown",
    document_hint: str = "",
) -> AnswerKeyMatchResult:
    """Seleciona um gabarito somente quando as evidencias nao se contradizem."""
    doc = None
    should_close = False
    try:
        if isinstance(pdf_input, fitz.Document):
            doc = pdf_input
        elif isinstance(pdf_input, (bytes, bytearray)):
            doc = fitz.open(stream=pdf_input, filetype="pdf")
            should_close = True
        elif isinstance(pdf_input, str):
            doc = fitz.open(pdf_input)
            should_close = True
        else:
            return AnswerKeyMatchResult(
                status="invalid_input",
                conflicts=["unsupported_pdf_input"],
                profile=profile,
                source_relation=source_relation,
            )

        candidates = _extract_candidates(doc, document_hint=document_hint)
        if not candidates:
            legacy_answers = parse_gabarito_from_pdf(
                doc,
                cargo_or_title=profile.title,
                tipo=profile.metadata.exam_types[0] if profile.metadata.exam_types else None,
                exam_code_ranges=profile.metadata.code_ranges,
            )
            if legacy_answers:
                candidates = [
                    AnswerKeyCandidate(
                        answers=legacy_answers,
                        page=None,
                        method="legacy_validated",
                        metadata=_extract_identity_metadata(document_hint),
                        has_header=False,
                    )
                ]

        scored: List[Tuple[float, AnswerKeyCandidate, List[str], List[str], List[str]]] = []
        errata_candidates: List[AnswerKeyCandidate] = []
        for candidate in candidates:
            score, reasons, warnings, conflicts = _score_candidate(
                profile,
                candidate,
                source_relation,
            )
            if candidate.metadata.publication_status == "errata" and len(candidate.answers) < profile.question_count:
                errata_candidates.append(candidate)
                continue
            scored.append((score, candidate, reasons, warnings, conflicts))

        eligible = [item for item in scored if not item[4] and item[0] >= 70]
        eligible.sort(key=lambda item: (item[0], len(item[1].answers)), reverse=True)
        if not eligible:
            best = max(scored, key=lambda item: item[0], default=None)
            return AnswerKeyMatchResult(
                accepted=False,
                status="rejected" if best else "not_found",
                confidence=0.0,
                method=best[1].method if best else "none",
                candidate_page=best[1].page if best else None,
                source_relation=source_relation,
                reasons=best[2] if best else [],
                warnings=best[3] if best else [],
                conflicts=best[4] if best else ["no_answer_key_candidate"],
                profile=profile,
                candidate=best[1].snapshot() if best else None,
            )

        best = eligible[0]
        if len(eligible) > 1:
            runner_up = eligible[1]
            if best[1].answers != runner_up[1].answers and best[0] - runner_up[0] < 15:
                return AnswerKeyMatchResult(
                    accepted=False,
                    status="ambiguous",
                    confidence=0.0,
                    method=best[1].method,
                    candidate_page=best[1].page,
                    source_relation=source_relation,
                    reasons=best[2],
                    warnings=_unique([*best[3], "multiple_candidates_with_similar_score"]),
                    conflicts=["ambiguous_answer_key"],
                    profile=profile,
                    candidate=best[1].snapshot(),
                )

        score, candidate, reasons, warnings, conflicts = best
        answers = dict(candidate.answers)
        errata_pages: List[int] = []
        for errata in errata_candidates:
            if not _strong_identity_compatible(profile, errata):
                continue
            if profile.question_numbers and not set(errata.answers).issubset(profile.question_numbers):
                continue
            answers.update(errata.answers)
            if errata.page is not None:
                errata_pages.append(errata.page)
        if errata_pages:
            reasons = _unique([*reasons, "compatible_errata_applied"])

        return AnswerKeyMatchResult(
            answers=answers,
            accepted=True,
            status="confirmed",
            confidence=_confidence(score, reasons),
            method=candidate.method,
            candidate_page=candidate.page,
            source_relation=source_relation,
            reasons=reasons,
            warnings=warnings,
            conflicts=conflicts,
            profile=profile,
            candidate=candidate.snapshot(),
            errata_pages=errata_pages,
        )
    finally:
        if should_close and doc is not None:
            doc.close()


def explicit_answer_key_result(
    answers: Dict[int, str],
    profile: ExamAnswerKeyProfile,
    *,
    method: str,
    source_relation: str,
) -> AnswerKeyMatchResult:
    """Registra fontes explicitamente escolhidas sem fingir selecao automatica."""
    normalized_answers = {
        int(number): str(answer).upper() for number, answer in (answers or {}).items()
    }
    return AnswerKeyMatchResult(
        answers=normalized_answers,
        accepted=bool(normalized_answers),
        status="explicit" if normalized_answers else "not_found",
        confidence=100.0 if normalized_answers else 0.0,
        method=method,
        source_relation=source_relation,
        reasons=["explicit_user_or_source_answer_key"] if normalized_answers else [],
        conflicts=[] if normalized_answers else ["no_answers"],
        profile=profile,
    )
