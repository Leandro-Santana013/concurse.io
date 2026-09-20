import os
import re
import io
import math
import hashlib
import json
import time
import fitz
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple, Set

from .layout.layout_detector import (
    detect_watermarks,
    detect_layout_and_ordered_blocks,
    extract_context_blocks,
    is_instruction_or_cover_page,
    infer_document_topology,
    LayoutConfig,
)
from .media.diagram_cropper import (
    ExamImageExtractor,
)
from .formatters.formula_formatter import format_latex_formulas
from .fallbacks.subject_classifier import SUBJECT_REGEX, format_subject_title, _format_subject_title, rust_classify_subject
from services.gabarito.gabarito_service import (
    extract_gabarito_from_doc,
    _extract_gabarito_from_doc,
    normalize_answer_or_empty,
)
from services.crawlers.html_exam_parser import clean_text_artifacts
from .native.rust_bridge import rust_scan_question_headers, rust_process_exam_text, is_rust_available
from .fallbacks.typography_restorer import restore_exam_typography, format_markdown_tables_in_text
from .parse_cache import load_parse_cache, prepare_parse_source, save_parse_cache


def _env_flag(name: str, default: bool = False) -> bool:
    """Lê flags operacionais sem registrar conteúdo do documento."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "off", "no"}


class _PipelineTiming:
    """Mede etapas sem incluir enunciados, respostas ou dados do usuário."""

    def __init__(self) -> None:
        self.enabled = _env_flag("PDF_PIPELINE_TIMING", default=False)
        self.started_at = time.perf_counter()
        self.last_mark = self.started_at
        self.stages: Dict[str, float] = {}

    def mark(self, name: str) -> None:
        now = time.perf_counter()
        self.stages[name] = round(now - self.last_mark, 4)
        self.last_mark = now

    def finish(self, *, pages: int, questions: Optional[int] = None) -> None:
        if not self.enabled:
            return
        payload = {
            "event": "pdf_pipeline_timing",
            "pages": int(pages),
            "questions": questions,
            "stages_seconds": self.stages,
            "total_seconds": round(time.perf_counter() - self.started_at, 4),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


# A camada textual de PDFs reais usa três famílias de cabeçalho:
# ``05.``, ``05`` (isolado) e ``Questão 05``/``ITEM 05``.  O padrão numérico
# continua exigindo pontuação ou uma linha/rotulo isolado para não transformar
# anos, páginas e números no corpo do enunciado em questões.
_NATIVE_QUESTION_HEADER_RE = re.compile(
    r"(?im)^[ \t]*0*(\d{1,3})"
    # Scans antigos às vezes convertem o ponto de ``19.`` em aspas.
    r"(?:[ \t]*[\.\)\-–—,:\"'](?=[ \t]|$)|(?=[ \t]*(?:\(|$)))"
)
_NATIVE_NAMED_QUESTION_HEADER_RE = re.compile(
    r"(?im)^[ \t]*(?:quest(?:[ãa]o|ao)|item)[ \t]+0*(\d{1,3})"
    r"(?=$|[ \t\.\)\-–—,:\"'])"
)
_NATIVE_OPTION_MARKER_RE = re.compile(
    r"(?im)^[ \t]*(?:\(?[A-Ea-e]\s*\)[ \t]*|"
    r"[A-Ea-e]\s*[\.\-:][ \t]+|[A-Ea-e]\t[ \t]*\S)"
)
_DECLARED_QUESTION_COUNT_PATTERNS = (
    re.compile(
        r"(?i)\b(?:composto|cont[eé]m|contendo|total(?:iza|de)?)"
        r"\D{0,30}(\d{1,3})\s*"
        r"(?:\([^\)\n]{1,30}\)\s*)?\s+quest(?:[õo]es|oes)\b"
    ),
    re.compile(r"(?i)\b(\d{1,3})\s+quest(?:[õo]es|oes)\b"),
)


def _native_question_numbers(text: str) -> List[int]:
    """Retorna os rótulos numéricos que parecem cabeçalhos de questões."""
    source = str(text or "")
    numbers = {
        int(match.group(1))
        for header_re in (
            _NATIVE_NAMED_QUESTION_HEADER_RE,
            _NATIVE_QUESTION_HEADER_RE,
        )
        for match in header_re.finditer(source)
        if 1 <= int(match.group(1)) <= 250
    }
    return sorted(numbers)


def _native_question_header_match(text: str):
    """Encontra um cabeçalho nativo nomeado ou numérico em uma linha."""
    return (
        _NATIVE_NAMED_QUESTION_HEADER_RE.match(text)
        or _NATIVE_QUESTION_HEADER_RE.match(text)
    )


_SOURCE_PARAGRAPH_LINE_RE = re.compile(
    r"(?m)^[ \t]*@@P(?P<number>\d{1,3})(?=\s|$)"
)


def _source_title_from_prefix(prefix: str) -> str:
    """Extrai o título editorial que antecede o primeiro parágrafo numerado."""
    lines = [line.strip() for line in str(prefix or "").splitlines() if line.strip()]
    if not lines:
        return ""

    subject_line = re.compile(
        r"(?i)^(?:CONHECIMENTOS\b|L[ÍI]NGUA\b|PORTUGU[ÊE]S\b|"
        r"MATEM[ÁA]TICA\b|DIREITO\b|NO[ÇC]ÕES\b)"
    )
    subject_index = None
    for index, line in enumerate(lines):
        if subject_line.match(line):
            subject_index = index

    candidates = lines[subject_index:] if subject_index is not None else lines[-2:]
    if not candidates:
        return ""

    first = re.sub(
        r"(?i)^(?:CONHECIMENTOS(?:\s+(?:B[ÁA]SICOS|GERAIS|ESPEC[ÍI]FICOS|REGIONAIS))?\s*)?"
        r"(?:L[ÍI]NGUA\s+(?:PORTUGUESA|INGLESA)|PORTUGU[ÊE]S|MATEM[ÁA]TICA|"
        r"DIREITO(?:\s+[^:–—-]+)?)\s*[:–—-]?\s*",
        "",
        candidates[0],
    ).strip()
    title_lines = ([first] if first else []) + [line for line in candidates[1:] if line]
    title = " ".join(title_lines).strip()
    if title.upper() in {"TRANSPETRO", "CONHECIMENTOS BÁSICOS", "CONHECIMENTOS GERAIS"}:
        return ""
    return re.sub(r"\s+", " ", title)


def _extract_numbered_source_context_blocks(
    full_text: str,
    found_positions: List[Tuple[int, int, int]],
) -> List[Tuple[int, int, str, int]]:
    """Recupera textos de apoio cujo PDF só imprime números na margem.

    Esses documentos não têm o banner textual ``Texto para as questões...``.
    Os marcadores ``@@P`` foram inseridos pelo detector geométrico a partir da
    fonte/gutter original. Assim, o scanner global só enxerga os cabeçalhos
    reais e podemos associar o apoio até o próximo grupo numerado.
    """
    marker_matches = list(_SOURCE_PARAGRAPH_LINE_RE.finditer(full_text or ""))
    if len(marker_matches) < 2:
        return []

    groups: List[List[re.Match[str]]] = []
    current: List[re.Match[str]] = []
    previous_number: Optional[int] = None
    previous_start: Optional[int] = None
    for match in marker_matches:
        number = int(match.group("number"))
        starts_new_group = bool(
            current
            and (
                previous_number is None
                or number != previous_number + 1
                or (
                    previous_start is not None
                    and match.start() - previous_start > 16000
                )
            )
        )
        if starts_new_group:
            groups.append(current)
            current = []
        current.append(match)
        previous_number = number
        previous_start = match.start()
    if current:
        groups.append(current)

    question_positions = sorted(
        (
            int(number),
            int(start),
            int(end),
        )
        for number, start, end in found_positions
        if 1 <= int(number) <= 250
    )
    contexts: List[Tuple[int, int, str, int]] = []
    for group_index, group in enumerate(groups):
        if len(group) < 2:
            continue
        first_marker = group[0]
        last_marker = group[-1]
        next_group_start = (
            groups[group_index + 1][0].start()
            if group_index + 1 < len(groups)
            else len(full_text)
        )
        group_questions = [
            item
            for item in question_positions
            if last_marker.end() <= item[1] < next_group_start
        ]
        if not group_questions:
            continue

        first_question_start = min(item[1] for item in group_questions)
        prefix_start = full_text.rfind("\n\n", 0, first_marker.start()) + 2
        title = _source_title_from_prefix(
            full_text[prefix_start:first_marker.start()]
        )
        body = full_text[first_marker.start():first_question_start].strip()
        if not body:
            continue
        context_text = f"### {title}\n\n{body}" if title else body
        q_min = min(item[0] for item in group_questions)
        q_max = max(item[0] for item in group_questions)
        contexts.append((q_min, q_max, context_text, prefix_start))
    return contexts


def _prepare_numbered_source_context(
    text: str,
    *,
    preserve_native_word_boundaries: bool = False,
) -> str:
    """Formata o bloco numerado sem acionar a heurística de poema."""
    if "@@P" not in str(text or ""):
        return restore_exam_typography(
            text,
            preserve_native_word_boundaries=preserve_native_word_boundaries,
        )

    first_marker = _SOURCE_PARAGRAPH_LINE_RE.search(text)
    if not first_marker:
        return restore_exam_typography(
            text,
            preserve_native_word_boundaries=preserve_native_word_boundaries,
        )

    title = text[:first_marker.start()].strip()
    body = text[first_marker.start():]
    markers = list(_SOURCE_PARAGRAPH_LINE_RE.finditer(body))
    paragraphs: List[str] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(body)
        paragraph = body[marker.start():end].strip()
        paragraph = re.sub(
            r"(?<=[A-Za-zÀ-ÿ])-[ \t\r\n]+(?=[a-zà-ÿ])",
            "",
            paragraph,
        )
        paragraph = re.sub(r"\s*\n\s*", " ", paragraph).strip()
        paragraphs.append(paragraph)

    prepared = "\n\n".join(part for part in ([title] if title else []) + paragraphs if part)
    return prepared


def _unprotect_source_paragraph_markers(text: str) -> str:
    """Converte marcadores internos em números visíveis após toda a tipografia."""
    return re.sub(r"@@P(\d{1,3})(?=\s|$)", r"\1", str(text or ""))


def _declared_question_count(text: str) -> Optional[int]:
    """Encontra uma quantidade de questões declarada no caderno/capa."""
    candidates = []
    source = str(text or "")
    for pattern in _DECLARED_QUESTION_COUNT_PATTERNS:
        candidates.extend(int(match.group(1)) for match in pattern.finditer(source))
    plausible = [value for value in candidates if 5 <= value <= 250]
    return max(plausible) if plausible else None


def _reconcile_rust_question_chain(
    questions: List[Dict[str, Any]],
    full_text: str,
) -> List[Dict[str, Any]]:
    """Remove reinícios espúrios quando o scanner estrito fecha uma cadeia.

    O processador Rust considera banners de disciplina para permitir provas que
    reiniciam a numeração. Em PDFs com rodapés numéricos, porém, esse caminho
    pode escolher ``2, 12, 1..N`` em vez da cadeia física ``1..N``. O scanner
    estrito já calcula a cadeia contínua sem reinícios; quando ela é completa e
    o resultado processado só tem candidatos extras/duplicados, usamos suas
    posições como âncora para escolher o corpo correto de cada número. Nenhuma
    questão é criada aqui e uma cadeia incompleta continua no caminho original.
    """

    if len(questions) < 5:
        return questions

    strict_headers = rust_scan_question_headers(full_text)
    if not strict_headers or len(strict_headers) < 5:
        return questions

    strict_numbers: List[int] = []
    strict_positions: Dict[int, int] = {}
    for header in strict_headers:
        try:
            number = int(header.get("number"))
            position = int(header.get("start"))
        except (AttributeError, TypeError, ValueError):
            continue
        if number in strict_positions:
            continue
        strict_numbers.append(number)
        strict_positions[number] = position

    if (
        not strict_numbers
        or strict_numbers[0] != 1
        or strict_numbers != list(range(1, strict_numbers[-1] + 1))
        or len(questions) <= len(strict_numbers)
    ):
        return questions

    candidates_by_number: Dict[int, List[Dict[str, Any]]] = {}
    for question in questions:
        try:
            number = int(question.get("numero_questao"))
        except (AttributeError, TypeError, ValueError):
            continue
        if number in strict_positions:
            candidates_by_number.setdefault(number, []).append(question)

    if any(number not in candidates_by_number for number in strict_numbers):
        return questions

    selected: List[Dict[str, Any]] = []
    for number in strict_numbers:
        candidates = candidates_by_number[number]
        target = strict_positions[number]

        def distance(candidate: Dict[str, Any]) -> Tuple[int, int]:
            try:
                start = int(candidate.get("start_char"))
            except (AttributeError, TypeError, ValueError):
                return (10**12, 0)
            return (abs(start - target), start)

        selected.append(min(candidates, key=distance))

    return selected


def _assess_native_text_quality(
    full_text: str,
    *,
    document_text: str = "",
    total_pages: int = 1,
    image_page_count: int = 0,
    total_image_count: int = 0,
    full_page_scan_detected: bool = False,
) -> Dict[str, Any]:
    """Avalia se a camada nativa parece confiável para estruturar a prova.

    PDFs escaneados frequentemente carregam uma camada OCR ruim: ela pode ter
    milhares de caracteres, mas perder cabeçalhos, letras das alternativas e
    pedaços de palavras. Contar caracteres, sozinho, classifica esses arquivos
    incorretamente como documentos textuais.
    """
    text = str(full_text or "")
    document_source = str(document_text or text)
    question_numbers = _native_question_numbers(text)
    declared_count = _declared_question_count(document_source)
    document_question_numbers = _native_question_numbers(document_source)
    if (
        not full_page_scan_detected
        and declared_count
        and document_question_numbers == list(range(1, declared_count + 1))
    ):
        # O detector de blocos pode perder cabeçalhos quando a página tem
        # muitas imagens inline, embora a camada textual nativa contenha a
        # sequência completa. Nesse caso, não acione OCR por uma deficiência
        # do diagnóstico intermediário.
        question_numbers = document_question_numbers
    option_marker_count = len(_NATIVE_OPTION_MARKER_RE.findall(text))
    replacement_count = text.count("\ufffd")
    mojibake_count = len(
        re.findall(r"(?:Ã[\x80-\xbf]|Â[\x80-\xbf]|â(?:[\x80-\xbf]|[€™œ]))", text)
    )
    page_count = max(1, int(total_pages or 1))
    image_ratio = float(image_page_count or 0) / page_count
    average_images = float(total_image_count or 0) / page_count
    # Embedded diagrams and illustrations are common in text-based exams.
    # Use the geometric full-page scan profile computed by the caller instead
    # of treating image-object density as evidence that the text is OCR output.
    scan_like = bool(full_page_scan_detected)

    reasons: List[str] = []
    if replacement_count >= 3:
        reasons.append(f"replacement_chars:{replacement_count}")
    if mojibake_count >= 3:
        reasons.append(f"mojibake_sequences:{mojibake_count}")
    if declared_count and len(question_numbers) < declared_count:
        reasons.append(
            f"question_coverage:{len(question_numbers)}/{declared_count}"
        )

    # Em um scan com várias imagens, a ausência das marcações A..E é um sinal
    # forte de que a camada nativa perdeu a estrutura visual das alternativas.
    if scan_like and question_numbers and option_marker_count < max(
        4, math.ceil(len(question_numbers) * 0.5)
    ):
        reasons.append(
            f"option_marker_density:{option_marker_count}/{len(question_numbers)}"
        )

    return {
        "needs_vision_ocr": bool(reasons),
        "reasons": reasons,
        "declared_question_count": declared_count,
        "question_numbers": question_numbers,
        "question_count": len(question_numbers),
        "option_marker_count": option_marker_count,
        "replacement_count": replacement_count,
        "mojibake_count": mojibake_count,
        "image_page_ratio": image_ratio,
        "average_images_per_page": average_images,
        "full_page_scan_detected": scan_like,
    }


def _extract_native_question_chunks(doc: fitz.Document) -> Dict[int, str]:
    """Extrai blocos espaciais da camada nativa para recuperação do scan."""
    damaged_header_re = re.compile(
        r'^\s*(?:\ufffd|í|I|!|\|)\s*(\d)\s*[\.,\-–—\)\"\']\s*(.*)$',
        re.IGNORECASE,
    )
    damaged_thirty_re = re.compile(
        r'^\s*3\s*[üuU]\s*[\.,\-–—\)\"\']\s*(.*)$',
        re.IGNORECASE,
    )
    chunks: Dict[int, str] = {}
    current_number: Optional[int] = None
    current_lines: List[str] = []

    def flush_current() -> None:
        nonlocal current_number, current_lines
        if current_number is not None and current_lines:
            chunks.setdefault(current_number, '\n'.join(current_lines).strip())
        current_number = None
        current_lines = []

    for page in doc:
        try:
            native_dict = page.get_text('dict')
        except Exception:
            continue
        page_lines = []
        for block in native_dict.get('blocks', []):
            if block.get('type') != 0:
                continue
            for native_line in block.get('lines', []):
                text = ' '.join(
                    str(span.get('text') or '').strip()
                    for span in native_line.get('spans', [])
                    if str(span.get('text') or '').strip()
                ).strip()
                if not text:
                    continue
                x0 = float(native_line.get('bbox', (999, 0, 0, 0))[0])
                y0 = float(native_line.get('bbox', (0, 999999, 0, 0))[1])
                page_lines.append((y0, x0, text))

        # A camada OCR embutida do PDF nem sempre está ordenada pelos blocos
        # visuais. Em scans isso colocava o texto da questão 39 dentro da 38
        # e o da 16 dentro da 15, apesar de os cabeçalhos terem coordenadas
        # corretas.
        for _y0, x0, text in sorted(
            page_lines,
            key=lambda item: (round(item[0] / 3.0) * 3.0, item[1]),
        ):
                match = _native_question_header_match(text)
                damaged_match = damaged_header_re.match(text) if not match else None
                thirty_match = damaged_thirty_re.match(text) if not match and not damaged_match else None
                if (match or damaged_match or thirty_match) and x0 < 75:
                    if damaged_match:
                        suffix = int(damaged_match.group(1))
                        question_number = 10 + suffix
                        normalized = f'{question_number}. {damaged_match.group(2).strip()}'.strip()
                    elif thirty_match:
                        question_number = 30
                        normalized = f'30. {thirty_match.group(1).strip()}'.strip()
                    else:
                        question_number = int(match.group(1))
                        normalized = text
                    if not 1 <= question_number <= 250:
                        continue
                    flush_current()
                    current_number = question_number
                    current_lines = [normalized]
                elif current_number is not None:
                    current_lines.append(text)
        # A question may continue on the next page, so the active block is
        # intentionally carried across page boundaries.

    flush_current()
    return chunks


_PDF_PAGE_CODE_RE = re.compile(
    r"(?i)(?<![A-Z0-9])\*?[A-Z]{2}\d{4}[A-Z]{2}\d{1,3}\*?(?![A-Z0-9])"
)
_NATIVE_ENCODING_DAMAGE_RE = re.compile(
    r"(?:\ufffd|Ã[\x80-\xbf]|Â[\x80-\xbf]|â(?:[\x80-\xbf]|[€™œ]))"
)

_PDF_SECTION_HEADER_TAIL_RE = re.compile(
    r"\s+(?:"
    r"LINGUAGENS\s*,?\s*C[ÓO]DIGOS\s+E\s+SUAS\s+TECNOLOGIAS|"
    r"CI[ÊE]NCIAS\s+(?:HUMANAS|DA\s+NATUREZA)\s+E\s+SUAS\s+TECNOLOGIAS|"
    r"MATEM[ÁA]TICA\s+E\s+SUAS\s+TECNOLOGIAS"
    r")\s+QUEST[ÕO]ES\s+DE\s+\d{1,3}\s+A\s+\d{1,3}"
    r"(?:\s+QUEST[ÕO]ES\s+DE\s+\d{1,3}\s+A\s+\d{1,3}(?:\s*\([^)]*\))?)?\s*$",
    re.IGNORECASE,
)


def _strip_pdf_page_code_tail(text: Any) -> str:
    """Remove identificadores PCI de paginação onde quer que vazem no texto."""

    value = str(text or "")
    return _PDF_PAGE_CODE_RE.sub("", value)


def _strip_trailing_pdf_section_header(text: Any) -> str:
    """Remove um banner de seção/range repetido que tenha sido colado ao fim."""

    value = str(text or "")
    return _PDF_SECTION_HEADER_TAIL_RE.sub("", value).rstrip()


def _strip_trailing_exam_banner(text: Any) -> str:
    """Remove banners de caderno que vazam para a última alternativa.

    A diagramação da Transpetro repete ``RASCUNHO`` e ``TRANSPETRO`` entre
    blocos. A camada textual pode colar esse rodapé ao fim da alternativa E;
    o conteúdo anterior ao primeiro banner continua sendo o texto impresso da
    alternativa.
    """

    value = str(text or "")
    value = re.split(r"\s+RASCUNHO\b", value, maxsplit=1)[0]
    # O cabeçalho institucional é impresso em caixa alta. Restringir a
    # remoção a esse formato evita apagar uma menção legítima a Transpetro
    # dentro do texto de uma alternativa.
    value = re.sub(r"\s+TRANSPETRO\b.*$", "", value)
    return value.rstrip()


def _strip_exam_watermark_token(text: Any) -> str:
    """Remove a leaked standalone ``RASCUNHO`` watermark token."""

    value = re.sub(r"(?i)(?<![A-ZÀ-Ý0-9])RASCUNHO(?![A-ZÀ-Ý0-9])", "", str(text or ""))
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    return value.strip()


def _strict_native_question_integrity(
    questions: List[Dict[str, Any]],
    *,
    expected_count: int,
    expected_option_labels: str = "ABCDE",
) -> Dict[str, List[str]]:
    """Gate fail-closed para texto nativo que não pode perder caracteres.

    A validação de OCR existente também procura palavras aglutinadas, mas é
    deliberadamente probabilística e pode sinalizar palavras legítimas. Para
    um caderno textual como o da Transpetro, este gate usa apenas invariantes
    determinísticos: sequência, rótulos, conteúdo não vazio, codificação e
    ausência de banners.
    """

    expected_labels = set(expected_option_labels)
    issues: Dict[str, List[str]] = {}
    if len(questions) != int(expected_count):
        issues["document"] = [
            f"question_count:{len(questions)}/{int(expected_count)}"
        ]

    for index, question in enumerate(questions or [], start=1):
        number = str(question.get("numero_questao") or "").strip()
        question_issues: List[str] = []
        if number != str(index):
            question_issues.append(f"numero_questao:{number or 'vazio'}")
        statement = str(question.get("enunciado") or "")
        options = question.get("opcoes") or {}
        labels = {str(label).strip().upper() for label in options}
        if not statement.strip():
            question_issues.append("enunciado_vazio")
        if labels != expected_labels:
            question_issues.append("rotulos_alternativas_incompletos")
        if any(not str(options.get(label) or "").strip() for label in expected_labels):
            question_issues.append("alternativa_vazia")
        fields = [statement, *[str(options.get(label) or "") for label in expected_labels]]
        if any(_NATIVE_ENCODING_DAMAGE_RE.search(value) for value in fields):
            question_issues.append("codificacao_danificada")
        if any(
            re.search(r"(?i)\b(?:RASCUNHO|TRANSPETRO|pcimarkpci|www\.pciconcursos)\b", value)
            for value in fields[1:]
        ):
            question_issues.append("banner_ou_marca_dagua")
        if question_issues:
            issues[number or f"index_{index}"] = sorted(set(question_issues))

    return issues


def _join_touching_native_word_fragments(text: str, words: Any) -> str:
    """Recompõe tokens que o PDF separou apesar de não haver espaço visual."""

    line_words: Dict[Tuple[int, int], List[Tuple[float, float, str, int]]] = {}
    for word in words or []:
        try:
            x0, _y0, x1, _y1, token, block_no, line_no, word_no = word[:8]
            line_words.setdefault((int(block_no), int(line_no)), []).append(
                (float(x0), float(x1), str(token), int(word_no))
            )
        except (TypeError, ValueError):
            continue

    value = str(text or "")
    for line in line_words.values():
        line.sort(key=lambda item: item[3])
        for left, right in zip(line, line[1:]):
            left_token, right_token = left[2], right[2]
            gap = right[0] - left[1]
            if gap < -0.5 or gap > 0.75:
                continue
            if not re.fullmatch(r"[A-Za-zÀ-ÿ]{3,}", left_token):
                continue
            if not re.fullmatch(r"[A-Za-zÀ-ÿ]{2,}[.,;:!?)]*", right_token):
                continue
            split_pair = re.compile(
                rf"(?<![A-Za-zÀ-ÿ]){re.escape(left_token)}\s+{re.escape(right_token)}"
                rf"(?![A-Za-zÀ-ÿ])"
            )
            value = split_pair.sub(lambda _match: left_token + right_token, value, count=1)
    return value


def _extract_native_text_question_chunks(doc: fitz.Document) -> Dict[int, str]:
    """Extrai questões explicitamente numeradas na ordem textual do PDF.

    Usa o fluxo de texto do PDF, que preserva a ordem das colunas em cadernos
    como o ENEM. A extração espacial legada continua disponível para scans;
    este mapa é apenas uma fonte de recuperação para PDFs com texto nativo.
    Numerações simples de páginas de instruções não são tratadas como questões.
    """

    chunks: Dict[int, str] = {}
    for page in doc:
        current_number: Optional[int] = None
        current_lines: List[str] = []

        def flush_current() -> None:
            nonlocal current_number, current_lines
            if current_number is not None and current_lines:
                chunks.setdefault(
                    current_number,
                    _strip_pdf_page_code_tail("\n".join(current_lines).strip()),
                )
            current_number = None
            current_lines = []

        page_text = _join_touching_native_word_fragments(
            page.get_text(),
            page.get_text("words"),
        )
        for line in page_text.splitlines():
            match = _NATIVE_NAMED_QUESTION_HEADER_RE.match(line)
            if match:
                flush_current()
                question_number = int(match.group(1))
                if 1 <= question_number <= 250:
                    current_number = question_number
                    current_lines = [line]
            elif current_number is not None:
                current_lines.append(line)

        # A continuação de uma questão em outra página não vira candidato de
        # recuperação: só aceitamos um bloco que contenha a sequência completa.
        flush_current()
    return chunks

def extract_options_from_chunk(
    chunk: str,
    *,
    preserve_native_word_boundaries: bool = False,
) -> Tuple[Dict[str, str], Optional[str]]:
    """
    Extrai alternativas formatadas (A..E) diretamente do chunk de texto de uma questão.
    Retorna (opcoes_dict, novo_enunciado_limpo).
    """
    pattern_primary = re.compile(
        r'(?:^|\n|\s+)'
        r'(?:'
        r'([A-Ea-e])\s*\(\s*\)|'
        r'\(?\s*([A-Ea-e])\s*\)?\s*[\.\-\–\—\:\)]|'
        r'\(([A-Ea-e])\)|'
        r'\[([A-Ea-e])\]|'
        r'(?<=[\n\r])[ \t]*(?:\d+[\s\(\)\/]+)?\*?([A-Ea-e])\*?(?:\s*[\)\.\-\–\—\:]|[ \t]+)(?=[\w\u00C0-\u00FF\u201C\u201D\u2018\u2019\u00AB\u00BB\"\'\(\[\$\*\<])'
        r')'
    )
    pattern_native_tab = re.compile(
        r"(?m)^[ \t]*([A-Ea-e])[ \t]*\t+[ \t]*"
    )
    matches = []
    for m in pattern_primary.finditer(chunk):
        letter = None
        for g in m.groups():
            if g:
                letter = g.upper()
                break
        if letter:
            matches.append((letter, m.start(), m.end()))
    for match in pattern_native_tab.finditer(chunk):
        matches.append((match.group(1).upper(), match.start(), match.end()))
    matches.sort(key=lambda match: (match[1], match[0]))

    if not matches or len(matches) < 2:
        return {}, None

    def find_valid_sequence(match_list, chunk_length):
        if not match_list or len(match_list) < 2:
            return None
        valid_sequences = []
        start_indices = [idx for idx, m in enumerate(match_list) if m[0] == 'A']
        for s_idx in start_indices:
            seq = [match_list[s_idx]]
            expected_ord = ord('B')
            for next_m in match_list[s_idx + 1:]:
                letter = next_m[0]
                if ord(letter) == expected_ord:
                    seq.append(next_m)
                    expected_ord += 1
                    if expected_ord > ord('E'):
                        break
                elif ord(letter) < expected_ord:
                    continue
            if len(seq) >= 2:
                score = len(seq) * 1000 + (seq[0][1] / max(1, chunk_length)) * 100
                valid_sequences.append((score, seq))
        if not valid_sequences:
            return None
        valid_sequences.sort(key=lambda x: x[0], reverse=True)
        return valid_sequences[0][1]

    seq = find_valid_sequence(matches, len(chunk))
    if not seq:
        return {}, None

    new_enunciado = chunk[:seq[0][1]].strip()

    options = {}
    for o_idx, om in enumerate(seq):
        letter = om[0]
        s_val = om[2]
        e_val = seq[o_idx + 1][1] if o_idx + 1 < len(seq) else len(chunk)
        opt_content = chunk[s_val:e_val].strip()
        opt_content = re.sub(r'^[A-Ea-e]\s*[\(\[]\s*[\)\]]\s*', '', opt_content)
        opt_content = re.sub(r'^\(?[A-Ea-e]\s*[\)\.\-–—:]\s*', '', opt_content)
        opt_content = re.sub(r'^\(\s*\)\s*', '', opt_content)
        opt_content = _strip_pdf_page_code_tail(opt_content)
        opt_content = _strip_trailing_pdf_section_header(opt_content)
        numeric_only_option = opt_content.strip()
        opt_content = clean_text_artifacts(opt_content)
        # O limpador remove números isolados de rodapés. Eles também são
        # alternativas válidas (por exemplo, 36 e 72 em uma questão de cálculo).
        if not opt_content and re.fullmatch(r'[+\-−]?\d{1,3}(?:[.,]\d+)?%?', numeric_only_option):
            opt_content = numeric_only_option
        if o_idx == len(seq) - 1:
            opt_lines = opt_content.splitlines()
            while opt_lines and SUBJECT_REGEX.match(opt_lines[-1].strip()):
                opt_lines.pop()
            opt_content = '\n'.join(opt_lines).strip()
            opt_content = re.sub(r'\s*(?:<[^\s>]+>|\*{1,3}|_{1,3})+\s*(?:Conhecimentos\s+Espec[íi\ufffd\?]?ficos|Conhecimentos\s+Gerais|Conhecimentos\s+B[áa\ufffd\?]?sicos|L[íi\ufffd\?]?ngua\s+Portuguesa|Portugu[êe]s|Matem[áa]tica|No[çc\ufffd\?][õo\ufffd\?]?es\s+de\s+[^\n<]+|Racioc[íi\ufffd\?]?nio\s+L[óo\ufffd\?]?gico[^\n<]*|Legisla[çc\ufffd\?][ãa\ufffd\?]?o\s+Espec[íi\ufffd\?]?fica|Inform[áa\ufffd\?]?tica|Direito\s+[^\n<]+|TEXTO:\s*[^\n<]+)(?:<[^\s>]+>|\*{1,3}|_{1,3})+\s*$', '', opt_content, flags=re.IGNORECASE)
        opt_content = restore_exam_typography(
            opt_content,
            is_option=True,
            preserve_native_word_boundaries=preserve_native_word_boundaries,
        )
        formatted_opt, _ = format_latex_formulas(opt_content)
        options[letter] = formatted_opt

    short_non_numeric = sum(
        1
        for value in options.values()
        if len(re.sub(r'\s+', '', str(value or ''))) <= 3
        and not re.search(r'\d', str(value or ''))
    )
    roman_only_options = bool(options) and all(
        re.fullmatch(
            r"(?:I|II|III|IV|V|VI|VII|VIII|IX|X)",
            str(value or "").strip(),
            re.IGNORECASE,
        )
        for value in options.values()
    )
    if short_non_numeric >= 2 and not roman_only_options:
        # Sequências A..D capturadas em rótulos de diagramas costumam gerar
        # valores como "D A", "E" e "C B". Elas não são alternativas válidas.
        return {}, None

    return options, new_enunciado

def extract_heuristic_options(chunk: str) -> Tuple[Optional[Dict[str, str]], str]:
    """
    Quando as alternativas não possuem letras (A), (B), (C), (D) explícitas
    porque o scanner da banca transformou as letras em símbolos (@, §, (â, 6) ou removeu,
    detecta as 4 ou 5 opções verticais finais e atribui A, B, C, D, E.
    """
    if not chunk or len(chunk.strip()) < 20:
        return None, chunk

    def is_noise_line(line: str) -> bool:
        normalized = re.sub(r'[^a-zA-Z0-9]', '', line or '').lower()
        if normalized in {
            'oficialdeadministracao',
            'pcimarkpci',
            'wwwpciconcursoscombr',
            '1n',
            '2n',
            '3n',
            '4n',
            '5n',
            '6n',
            '7n',
        }:
            return True
        if (
            normalized.startswith('pcimarkpci')
            or normalized.startswith('wwwpciconcursoscombr')
            or normalized.startswith(('oicialdeadministra', 'oflcialdeadministra'))
        ):
            return True
        if re.fullmatch(r'(?i)f{2,}i?\s*[itluü]*', line or ''):
            return True
        if re.fullmatch(r'\s*[Àà]\s*', line or ''):
            return True
        return bool(re.search(
            r'(?i)(?:of[ií]cial|o[ií]icial|oflcial)\s+de\s+administra',
            line or '',
        ))

    def is_standalone_marker(line: str) -> bool:
        if re.fullmatch(
            r'\s*[\(\[\{]?\s*[A-Ea-e]\s*[\)\]\}\.\-]?\s*',
            line or '',
        ):
            return True
        if re.fullmatch(r'\s*[\(\[\{]\s*[A-Za-z]\s*[\)\]\}]?\s*', line or ''):
            # Ex.: ``(p`` é a leitura degradada de um marcador circular da
            # figura, não uma quinta alternativa.
            return True
        # Símbolos de círculos e letras corrompidas que o OCR separa do texto.
        return bool(re.fullmatch(
            r'\s*[\(\[\{]?(?:[@§©®•*#�]+|[!|/\\]{1,3}[A-Za-z]?|[lI][O0]?|'
            r'[GgÜüYyOoVv]|[âãäöüç§©®]+|\d{1,2})\s*[\)\]\}\.,:\-]?\s*',
            line or '',
        ))

    def clean_marker_prefix(line: str) -> str:
        text = (line or '').strip()
        text = re.sub(
            r'^\s*\(?[A-Ea-e]\s*[\)\.\-–—:]\s+(?=\S)',
            '',
            text,
        )
        text = re.sub(
            r'^\s*[\{\[\(@§©®•*#�/\\|]+'
            r'(?:\s*["\']?\d+)?\s*',
            '',
            text,
        )
        text = re.sub(
            r'^\s*[-/]{1,3}[A-Za-z]{0,2}\s+',
            '',
            text,
        )
        text = re.sub(
            r'^\s*[!|/\\]{1,3}[A-Za-z]?\s+',
            '',
            text,
        )
        text = re.sub(
            r'^\s*[A-Za-z]{1,3}\s*[\)\.\-]\s+(?=\S)',
            '',
            text,
        )
        text = re.sub(
            r'^\s*[lI][O0]\s+',
            '',
            text,
        )
        # Uma alternativa da questão 40 pode começar por ``I,``/``II,``.
        # Não tratar esse prefixo romano como uma letra de marcador perdida;
        # somente remove sequências alfabéticas fora da lista romana.
        roman_list_prefix_re = re.compile(
            r'^\s*(?:I|II|III|IV|V|VI|VII|VIII|IX|Il|Ill|lV|Vl|VIl|Vll|Vlll|lX)\s*[,;:]\s+',
            re.IGNORECASE,
        )
        if not roman_list_prefix_re.match(text):
            text = re.sub(
                r'^\s*[A-ZÀ-Ý]{1,3}\s*[,;:]\s+(?=[A-Za-zÀ-ÿ0-9])',
                '',
                text,
            )
        text = re.sub(
            r'^\s*[íÍàÀäöüç]{1,3}\s+(?=[A-Za-zÀ-ÿ])',
            '',
            text,
        )
        return text.strip()

    raw_lines = []
    for raw_line in chunk.split('\n'):
        line = raw_line.strip()
        if not line or is_noise_line(line):
            continue
        raw_lines.append(line)

    if len(raw_lines) < 4:
        return None, chunk

    def cleaned_lines_from(source: List[str]) -> List[str]:
        cleaned = []
        for line in source:
            if is_standalone_marker(line):
                continue
            text = clean_marker_prefix(line)
            if text:
                cleaned.append(text)
        return cleaned

    lines = cleaned_lines_from(raw_lines)
    if len(lines) < 4:
        return None, chunk

    def format_option_candidate(candidate_opts: List[str], candidate_enunciado: str):
        if len(candidate_opts) not in (4, 5) or len(candidate_enunciado) < 15:
            return None
        letters = ['A', 'B', 'C', 'D', 'E'][:len(candidate_opts)]
        options_dict = {}
        for idx, opt_txt in enumerate(candidate_opts):
            opt_clean = restore_exam_typography(opt_txt, is_option=True)
            formatted_opt, _ = format_latex_formulas(opt_clean)
            options_dict[letters[idx]] = formatted_opt
        return options_dict, candidate_enunciado

    def marked_option_groups(source: List[str]) -> List[str]:
        """Reconstrói opções quando o círculo/rotulagem ficou separado."""
        groups: List[str] = []
        current: List[str] = []
        pending_marker = False

        for raw_line in source:
            if is_noise_line(raw_line):
                continue
            if is_standalone_marker(raw_line):
                pending_marker = True
                continue

            cleaned = clean_marker_prefix(raw_line)
            if not cleaned:
                continue
            attached_marker = cleaned != raw_line.strip()
            starts_option = pending_marker or attached_marker

            if starts_option and current:
                groups.append(' '.join(current).strip())
                current = []
            if starts_option or current:
                current.append(cleaned)
            else:
                current = [cleaned]
            pending_marker = False

        if current:
            groups.append(' '.join(current).strip())
        return groups

    punctuation_commands = [
        idx for idx, line in enumerate(lines)
        if re.search(r'[\?\:]\s*$', line)
    ]
    keyword_commands = [
        idx for idx, line in enumerate(lines)
        if re.search(
            r'(?:assinale|marque|indique|identifique|correto|incorreto|'
            r'podemos\s+afirmar|qual\s+alternativa|dizer)',
            line,
            re.IGNORECASE,
        )
    ]
    if punctuation_commands:
        command_index = punctuation_commands[-1]
    elif keyword_commands:
        command_index = keyword_commands[0]
    else:
        command_index = -1

    # Usa os marcadores danificados como fronteiras. Isso evita juntar as
    # duas linhas de uma alternativa ao início da alternativa seguinte.
    if command_index >= 0:
        raw_command = lines[command_index]
        raw_command_position = raw_lines.index(raw_command) if raw_command in raw_lines else command_index
        raw_tail = raw_lines[raw_command_position + 1:]
        marker_start = next(
            (
                marker_idx
                for marker_idx, marker_line in enumerate(raw_tail)
                if is_standalone_marker(marker_line)
                or clean_marker_prefix(marker_line) != marker_line.strip()
            ),
            0,
        )
        marked_groups = marked_option_groups(raw_tail[marker_start:])
        if len(marked_groups) in (4, 5):
            statement_lines = cleaned_lines_from(
                raw_lines[:raw_command_position + 1 + marker_start],
            )
            candidate = format_option_candidate(
                marked_groups,
                '\n'.join(statement_lines).strip(),
            )
            if candidate:
                return candidate
        direct_tail = lines[command_index + 1:]
        if len(direct_tail) in (4, 5):
            candidate = format_option_candidate(
                direct_tail,
                '\n'.join(lines[:command_index + 1]).strip(),
            )
            if candidate:
                return candidate

    # Quando o comando da questão termina em ':' ou '?', a sequência seguinte
    # costuma ser exatamente a lista de alternativas. Usar essa fronteira é
    # mais seguro que pegar cegamente as últimas quatro linhas: em scans o OCR
    # pode inserir letras soltas de diagramas entre elas.
    for cmd_idx in range(len(lines) - 4, -1, -1):
        command_line = lines[cmd_idx]
        if not (
            re.search(r'[\?\:]\s*$', command_line)
            or re.search(
                r'(?:assinale|marque|indique|identifique|correto|incorreto|'
                r'podemos\s+afirmar|qual\s+alternativa|dizer)',
                command_line,
                re.IGNORECASE,
            )
        ):
            continue
        tail = lines[cmd_idx + 1:]
        if len(tail) in (4, 5):
            candidate = format_option_candidate(
                tail,
                '\n'.join(lines[:cmd_idx + 1]).strip(),
            )
            if candidate:
                return candidate

    for num_opts in [5, 4]:
        if len(lines) >= num_opts + 1:
            candidate_opts = lines[-num_opts:]
            candidate_enunciado = '\n'.join(lines[:-num_opts]).strip()

            if all(len(opt) >= 1 for opt in candidate_opts):
                candidate = format_option_candidate(candidate_opts, candidate_enunciado)
                if candidate:
                    return candidate

    return None, chunk


def _score_option_map(options: Optional[Dict[str, str]]) -> float:
    """Pontua a qualidade estrutural de um conjunto de alternativas."""
    if not options or len(options) < 4:
        return float('-inf')

    roman_tokens = {
        'i': 'I', 'ii': 'II', 'iii': 'III', 'iv': 'IV', 'v': 'V',
        'vi': 'VI', 'vii': 'VII', 'viii': 'VIII', 'ix': 'IX',
        # Confusões recorrentes do OCR visual/nativo desta família de provas.
        'i1': 'II', 'il': 'II', 'll': 'II', 'ill': 'III', 'lll': 'III', 'lv': 'IV', 'vl': 'VI',
        'vil': 'VII', 'vll': 'VII', 'vill': 'VIII', 'vlll': 'VIII', 'lx': 'IX', '1': 'I',
    }

    def roman_list_profile(value: str) -> Tuple[int, int]:
        tokens = re.findall(r'[A-Za-z0-9]+', value or '')
        if len(tokens) < 3 or not (',' in value or re.search(r'\be\b', value, re.I)):
            return 0, 0
        content_tokens = [token for token in tokens if token.lower() != 'e']
        if len(content_tokens) < 3:
            return 0, 0
        # Texto comum de alternativas como ``nos itens I e III, apenas``
        # também contém algarismos romanos, mas não é uma lista romana pura.
        # Palavras maiores que quatro caracteres distinguem esse caso dos
        # conjuntos curtos usados nas questões de protocolo.
        if any(len(token) > 4 for token in content_tokens):
            return 0, 0
        valid = sum(1 for token in content_tokens if token.lower() in roman_tokens)
        invalid = len(content_tokens) - valid
        return valid, invalid

    score = 40.0 if len(options) == 4 else 15.0
    for value in options.values():
        text = str(value or '').strip()
        compact = re.sub(r'\s+', '', text)
        words = re.findall(r'[A-Za-zÀ-ÿ]{2,}', text)
        score += min(len(text), 220) / 6.0
        score += min(len(words), 24) * 2.0
        score += min(text.count(' '), 20) * 0.5

        if len(compact) <= 3:
            score -= 28.0
            if not re.search(r'\d', text):
                score -= 42.0
        elif len(compact) <= 6 and not re.search(r'\d', text):
            score -= 12.0
        if re.search(r'pcimarkpci|www\.pciconcursos|oficial\s+de\s+administra', text, re.I):
            score -= 100.0
        if '\ufffd' in text or re.search(r'(?:Ã[\x80-\xbf]|Â[\x80-\xbf])', text):
            score -= 12.0
        if re.match(r'^\s*[^A-Za-zÀ-ÿ0-9"\']{1,3}\s*$', text):
            score -= 24.0

        # Alternativas matemáticas curtas continuam sendo válidas quando
        # apresentam uma expressão numérica reconhecível.
        if len(compact) <= 10 and re.search(r'\d', text):
            score += 16.0

        # Frações/razões são alternativas completas mesmo quando têm somente
        # três ou quatro caracteres; sem este bônus elas perdem para ruídos
        # como ``2tt3`` por causa da penalização de texto curto.
        if re.fullmatch(r'\d+\s*/\s*\d+\.?', text):
            score += 72.0
        elif len(compact) <= 12 and re.search(r'\d', text) and not re.fullmatch(
            r'[\d\s.,%()+\-×*/^]+', text
        ):
            # Não deixar uma expressão numérica corrompida (``2tt3`` ou
            # ``Gi t4``) vencer uma fração recuperada do OCR visual.
            score -= 55.0

        valid_roman, invalid_roman = roman_list_profile(text)
        if valid_roman:
            score += valid_roman * 16.0
            score -= invalid_roman * 34.0

    return score


def _normalize_roman_list_option(text: str) -> str:
    """Normaliza tokens romanos somente em alternativas que são listas."""
    value = str(text or '')
    # O OCR ocasionalmente cola o conector em ``V e VI`` como ``Ve Vl``.
    value = re.sub(
        r'(?i)(?<![A-Za-zÀ-ÿ0-9])([ivx]+)e(?=\s*[ivx])',
        r'\1 e',
        value,
    )
    roman_tokens = {
        'i': 'I', 'ii': 'II', 'iii': 'III', 'iv': 'IV', 'v': 'V',
        'vi': 'VI', 'vii': 'VII', 'viii': 'VIII', 'ix': 'IX',
        'i1': 'II', 'il': 'II', 'll': 'II', 'ill': 'III', 'lll': 'III', 'lv': 'IV', 'vl': 'VI',
        'vil': 'VII', 'vll': 'VII', 'vill': 'VIII', 'vlll': 'VIII', 'lx': 'IX', '1': 'I',
    }
    tokens = re.findall(r'[A-Za-z0-9]+', value)
    content_tokens = [token for token in tokens if token.lower() != 'e']
    if len(content_tokens) < 3 or not (',' in value or re.search(r'\be\b', value, re.I)):
        return value
    if not all(token.lower() in roman_tokens for token in content_tokens):
        return value

    return re.sub(
        r'(?<![A-Za-z0-9])[A-Za-z0-9]+(?![A-Za-z0-9])',
        lambda match: roman_tokens.get(match.group(0).lower(), match.group(0)),
        value,
    )


_ROMAN_CONFUSION_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:i1|il|ill|ivl?|vll|vlll|lx)(?![A-Za-z0-9])"
)

# IDCAP imprime o gabarito no próprio caderno. Dependendo da camada de texto,
# ``(Correta: C)`` chega inteiro ou quebrado em linhas como
# ``(Correta\n\nC.``. O gabarito já é guardado separadamente em ``resposta``;
# esse marcador nunca deve aparecer no enunciado entregue ao aluno.
_EMBEDDED_ANSWER_MARKER_RE = re.compile(
    r"(?im)(^|\n)[ \t]*\(?\s*correta\s*(?::\s*|\n+\s*)?"
    r"([A-E])\s*[\)\.]?[ \t]*(?=\n|$|[A-ZÁ-Úa-zá-ú])"
)


def strip_embedded_answer_marker(text: Any) -> str:
    """Remove somente o marcador visual de resposta embutida do enunciado."""

    value = str(text or "")
    cleaned = _EMBEDDED_ANSWER_MARKER_RE.sub(
        lambda match: match.group(1),
        value,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _repair_image_only_option_question(question: Dict[str, Any]) -> None:
    """Reconstrói uma questão cujo texto foi confundido com opções visuais.

    Em provas como a IDCAP 3/2024, o PDF contém os rótulos A--E e somente
    desenhos abaixo deles. O parser textual pode então tratar o restante do
    enunciado como cinco alternativas. Quando o vínculo espacial encontrou
    pelo menos quatro imagens rotuladas, os fragmentos textuais são devolvidos
    ao enunciado e as opções ficam vazias, preservando as chaves e o gabarito.
    """

    raw_option_images = question.get("option_images") or {}
    if not isinstance(raw_option_images, dict) or len(raw_option_images) < 4:
        return

    statement = strip_embedded_answer_marker(question.get("enunciado", ""))
    raw_options = question.get("opcoes") or {}
    if not isinstance(raw_options, dict):
        return
    labels = sorted(
        {str(label).strip().upper() for label in raw_option_images if str(label).strip()},
        key=lambda label: (label not in "ABCDE", label),
    )
    values = [str(raw_options.get(label, "") or "").strip() for label in labels]
    nonempty_values = [value for value in values if value]
    if len(nonempty_values) < 4:
        return

    option_context = f"{statement} {' '.join(nonempty_values)}"
    if not re.search(
        r"(?i)\b(?:imagens?|figuras?|desenhos?)\b.*\b(?:alternativa|abaixo|a\s+seguir|apresentad)",
        option_context,
    ):
        return

    # Fragmentos deslocados do enunciado normalmente começam em minúscula ou
    # são conectores curtos (``de``, ``e``, ``consistindo``). Exigir maioria
    # evita apagar alternativas textuais legítimas acompanhadas de uma figura.
    continuation_like = sum(
        bool(re.match(r"(?i)^(?:[a-zá-úà-ÿ]|e\b|de\b|do\b|da\b|em\b|para\b|com\b)", value))
        for value in nonempty_values
    )
    if continuation_like < max(3, len(nonempty_values) - 1):
        return

    tail = " ".join(nonempty_values).strip()
    if tail and tail.casefold() not in statement.casefold():
        statement = f"{statement.rstrip()} {tail}".strip()
    question["enunciado"] = statement
    question["opcoes"] = {label: "" for label in labels}
    question["option_images"] = {
        label: str(raw_option_images[label])
        for label in labels
        if raw_option_images.get(label)
    }


def _dominant_option_count(questions: List[Dict[str, Any]]) -> Optional[int]:
    """Detecta o tamanho dominante do mapa de alternativas da prova.

    A recuperação de precisão nasceu para cadernos com quatro alternativas.
    Provas A-E são válidas e não podem ser tratadas como incompletas apenas
    porque possuem cinco opções.
    """
    counts: Counter[int] = Counter()
    for question in questions:
        options = question.get("opcoes") or {}
        option_count = len(options) if isinstance(options, (dict, list)) else 0
        if 2 <= option_count <= 5:
            counts[option_count] += 1

    if not counts:
        return None
    most_common = counts.most_common()
    if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
        return None
    return most_common[0][0]


def _precision_recovery_targets(questions: List[Dict[str, Any]]) -> Set[int]:
    """Retorna somente questões que justificam uma leitura OCR de precisão."""
    expected_option_count = _dominant_option_count(questions)
    targets: Set[int] = set()

    for question in questions:
        raw_number = question.get("numero_questao")
        if not str(raw_number or "").isdigit():
            continue

        options = question.get("opcoes") or {}
        option_count = len(options) if isinstance(options, (dict, list)) else 0
        needs_precision = option_count < 4 or (
            expected_option_count == 4 and option_count != 4
        )
        option_values = (
            options.values()
            if isinstance(options, dict)
            else options
            if isinstance(options, list)
            else []
        )
        for value in option_values:
            text = str(value or "").strip()
            compact = re.sub(r"\s+", "", text)
            if _ROMAN_CONFUSION_RE.search(text) or (
                len(compact) <= 12
                and re.search(r"\d", text)
                and not re.fullmatch(r"[\d\s.,%()+\-×*/^]+", text)
            ):
                needs_precision = True
                break

        if needs_precision:
            targets.add(int(raw_number))

    return targets


def _should_run_precision_recovery(
    *,
    needs_vision_ocr: bool,
    native_layer_usable: bool,
) -> bool:
    """Impede uma segunda passada OCR em PDFs textuais já confiáveis."""
    return bool(needs_vision_ocr and not native_layer_usable)


def _recover_scan_options_at_high_resolution(
    doc: fitz.Document,
    questions: List[Dict[str, Any]],
    q_spatial_map: Dict[int, Tuple[int, float, float]],
    dpi: int = 400,
) -> None:
    """Recupera alternativas curtas que o OCR padrão confundiu no scan.

    A passada normal é suficiente para a maior parte do caderno. Se uma
    questão ainda tiver uma expressão numérica corrompida, uma lista romana
    ambígua ou alternativas insuficientes, repete somente a página
    correspondente em alta resolução e substitui o mapa apenas quando a nova
    estrutura for claramente melhor.
    """
    from .media.vision_pipeline import _supplement_native_question_headers
    from services.pdf_pipeline.layout.layout_detector import (
        _get_ocr_engine,
        extract_ocr_lines_three_passes,
    )

    targets = _precision_recovery_targets(questions)
    if not targets:
        return

    page_targets: Dict[int, Set[int]] = {}
    for q_num in targets:
        spatial = q_spatial_map.get(q_num)
        if spatial:
            page_targets.setdefault(int(spatial[0]), set()).add(q_num)
    if not page_targets:
        return

    question_by_number = {
        int(question['numero_questao']): question
        for question in questions
        if str(question.get('numero_questao', '')).isdigit()
    }
    header_re = re.compile(r'^\s*0*(\d{1,3})\s*[\.\)\-–—,:]\s*')

    def crop_option_lines(
        page: fitz.Page,
        block_lines: List[Dict[str, Any]],
    ) -> List[str]:
        """Executa OCR em uma faixa estreita, onde as opções realmente estão."""
        option_lines = []
        page_width = float(page.rect.width)
        for line in block_lines:
            text = str(line.get('text') or '').strip()
            x0 = float(line.get('x0', 0.0))
            y0 = float(line.get('y0', 0.0))
            if not text or not (page_width * 0.16 <= x0 <= page_width * 0.50):
                continue
            if y0 >= float(page.rect.height) * 0.95:
                continue
            if re.fullmatch(r'\s*[A-Ea-e]\s*', text):
                continue
            if re.fullmatch(r'\s*\d{2,4}\s*', text):
                continue
            option_lines.append(line)
        if len(option_lines) < 4:
            return []

        # Uma faixa um pouco mais larga preserva o contexto dos círculos e da
        # linha inteira. O recorte estreito fazia o RapidOCR trocar ``VI``
        # por ``V`` e fundir o conector ``e``.
        x0 = max(0.0, float(page.rect.width) * 0.097)
        x1 = min(float(page.rect.width), float(page.rect.width) * 0.529)
        y0 = max(0.0, min(float(line.get('y0', 0.0)) for line in option_lines) - 21.0)
        y1 = min(float(page.rect.height), max(float(line.get('y1', 0.0)) for line in option_lines) + 10.0)
        if x1 <= x0 or y1 <= y0:
            return []

        engine = _get_ocr_engine()
        if not engine:
            return []
        try:
            crop_rect = fitz.Rect(x0, y0, x1, y1)
            precision_dpi = 400
            pix = page.get_pixmap(clip=crop_rect, dpi=precision_dpi)
            results, _ = engine(pix.tobytes('png'))
        except Exception:
            return []
        if not results:
            return []

        scale = 72.0 / precision_dpi
        recognized = []
        for box, text, score in results:
            clean_text = str(text or '').strip()
            if not clean_text or float(score or 0.0) < 0.4:
                continue
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            recognized.append((
                y0 + min(ys) * scale,
                x0 + min(xs) * scale,
                clean_text,
            ))
        recognized.sort(key=lambda item: (item[0], item[1]))

        texts = []
        for _line_y, line_x, text in recognized:
            if line_x < page_width * 0.14:
                continue
            if re.fullmatch(r'\s*[A-Ea-e]\s*', text):
                continue
            if re.fullmatch(r'\s*[\(\[\{]?[A-Za-z]\s*[\)\]\}]?\s*', text):
                continue
            if re.fullmatch(r'\s*\d{2,4}\s*', text):
                continue
            texts.append(text)
        return texts if len(texts) == 4 else texts[-4:]

    for page_index, page_question_numbers in page_targets.items():
        if page_index < 0 or page_index >= len(doc):
            continue
        page = doc[page_index]
        try:
            lines = extract_ocr_lines_three_passes(
                page,
                dpi=max(300, int(dpi)),
                min_score=0.25,
            )
            lines = _supplement_native_question_headers(page, lines)
        except Exception as exc:
            print(f"[Precision OCR] Falha na página {page_index + 1}: {exc}", flush=True)
            continue
        if not lines:
            continue

        blocks: Dict[int, List[Dict[str, Any]]] = {}
        current_number: Optional[int] = None
        for line in sorted(
            lines,
            key=lambda item: (
                round(float(item.get('y0', 0.0)) / 4.0) * 4.0,
                float(item.get('x0', 0.0)),
            ),
        ):
            text = str(line.get('text') or '').strip()
            if not text:
                continue
            match = header_re.match(text)
            if match and float(line.get('x0', 0.0)) < 72.0:
                current_number = int(match.group(1))
                blocks.setdefault(current_number, []).append(line)
            elif current_number is not None:
                blocks.setdefault(current_number, []).append(line)

        for q_num in page_question_numbers:
            block_lines = blocks.get(q_num) or []
            if not block_lines:
                continue
            chunk = '\n'.join(str(line.get('text') or '').strip() for line in block_lines)
            explicit_options, _ = extract_options_from_chunk(chunk)
            heuristic_options, _ = extract_heuristic_options(chunk)
            candidates = [
                candidate
                for candidate in (explicit_options, heuristic_options or {})
                if candidate and len(candidate) == 4
            ]
            crop_texts = crop_option_lines(page, block_lines)
            if len(crop_texts) == 4:
                candidates.append({
                    letter: text
                    for letter, text in zip(('A', 'B', 'C', 'D'), crop_texts)
                })
            if not candidates:
                continue
            recovered_options = max(candidates, key=_score_option_map)
            question = question_by_number.get(q_num)
            if not question:
                continue
            current_options = question.get('opcoes') or {}
            if len(current_options) == 4 and _score_option_map(recovered_options) <= _score_option_map(current_options):
                continue

            formatted_options = {}
            for letter, value in recovered_options.items():
                clean_value = _normalize_roman_list_option(str(value or '').strip())
                clean_value = restore_exam_typography(clean_value, is_option=True)
                clean_value, _ = format_latex_formulas(clean_value)
                formatted_options[letter] = clean_value
            question['opcoes'] = formatted_options
            print(
                f"[Precision OCR] Alternativas recuperadas na questão {q_num} "
                f"(página {page_index + 1})",
                flush=True,
            )


def _native_option_marker_rows(
    doc: fitz.Document,
    question_number: int,
    q_spatial_map: Dict[int, Tuple[int, float, float]],
) -> Optional[Tuple[fitz.Page, List[Dict[str, Any]], fitz.Rect]]:
    """Localiza cinco linhas A..E na coluna da questão para OCR regional."""

    spatial = q_spatial_map.get(question_number)
    if not spatial:
        return None
    page_index, question_x, question_y = spatial
    if page_index < 0 or page_index >= len(doc):
        return None
    page = doc[page_index]

    next_question_y = float(page.rect.height)
    for other_number, (other_page, other_x, other_y) in q_spatial_map.items():
        if (
            other_number != question_number
            and other_page == page_index
            and other_y > question_y
            and abs(other_x - question_x) <= 40.0
        ):
            next_question_y = min(next_question_y, float(other_y))

    other_column_x = [
        float(other_x)
        for other_page, other_x, _other_y in q_spatial_map.values()
        if other_page == page_index and other_x > question_x + 80.0
    ]
    right_edge = (
        min(other_column_x) - 10.0
        if other_column_x and question_x < float(page.rect.width) * 0.5
        else float(page.rect.width) - 5.0
    )

    rows: List[Dict[str, Any]] = []
    try:
        native_dict = page.get_text("dict")
    except Exception:
        return None
    for block in native_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            bbox = line.get("bbox") or (0.0, 0.0, 0.0, 0.0)
            x0, y0, x1, y1 = (float(value) for value in bbox)
            if (
                x0 < question_x - 8.0
                or x0 > question_x + 80.0
                or y0 <= question_y + 8.0
                or y0 >= next_question_y
            ):
                continue
            spans = [
                str(span.get("text") or "")
                for span in line.get("spans", [])
                if str(span.get("text") or "").strip()
            ]
            text = " ".join(spans).strip()
            marker = re.match(r"^\s*([A-E])(?=\s|[.)\-:])", text, re.IGNORECASE)
            if not marker and text.upper() in set("ABCDE"):
                marker = re.match(r"^([A-E])$", text, re.IGNORECASE)
            if not marker:
                continue
            rows.append({
                "label": marker.group(1).upper(),
                "x0": x0,
                "x1": x1,
                "y0": y0,
                "y1": y1,
                "mid_y": (y0 + y1) / 2.0,
                "text": text,
            })

    rows.sort(key=lambda row: (row["mid_y"], row["x0"]))
    sequences: List[List[Dict[str, Any]]] = []
    for start_index, row in enumerate(rows):
        if row["label"] != "A":
            continue
        sequence = [row]
        expected = "B"
        for next_row in rows[start_index + 1:]:
            label = next_row["label"]
            if label == expected and abs(next_row["x0"] - row["x0"]) <= 14.0:
                sequence.append(next_row)
                expected = chr(ord(expected) + 1)
                if expected > "E":
                    break
            elif label <= expected:
                continue
            else:
                break
        if len(sequence) == 5:
            horizontal_spread = max(row["x0"] for row in sequence) - min(
                row["x0"] for row in sequence
            )
            vertical_gaps = [
                sequence[index + 1]["mid_y"] - sequence[index]["mid_y"]
                for index in range(len(sequence) - 1)
            ]
            if (
                horizontal_spread <= 14.0
                and all(8.0 <= gap <= 180.0 for gap in vertical_gaps)
            ):
                sequences.append(sequence)
    if not sequences:
        return None

    # Quando o enunciado começa com "A ...", a última sequência A..E é a
    # lista de alternativas; usar a posição final evita tratar o artigo como rótulo.
    marker_rows = max(sequences, key=lambda sequence: sequence[0]["mid_y"])
    clip = fitz.Rect(
        max(0.0, question_x - 3.0),
        max(0.0, marker_rows[0]["y0"] - 3.0),
        max(question_x + 40.0, right_edge),
        min(float(page.rect.height), marker_rows[-1]["y1"] + 4.0),
    )
    if clip.width <= 0 or clip.height <= 0:
        return None
    return page, marker_rows, clip


def _has_dense_vector_option_rows(
    page: fitz.Page,
    marker_rows: List[Dict[str, Any]],
    clip: fitz.Rect,
) -> bool:
    """Detecta alternativas visuais em linhas para não exigir OCR de seus rótulos."""

    if len(marker_rows) != 5:
        return False
    vertical_gaps = [
        float(marker_rows[index + 1]["mid_y"])
        - float(marker_rows[index]["mid_y"])
        for index in range(len(marker_rows) - 1)
    ]
    if not vertical_gaps or any(gap <= 8.0 or gap > 180.0 for gap in vertical_gaps):
        return False
    half_height = min(55.0, max(10.0, min(vertical_gaps) / 2.0 - 2.0))
    drawings = page.get_drawings()
    for marker in marker_rows:
        center_y = float(marker["mid_y"])
        row_rect = fitz.Rect(
            clip.x0,
            max(0.0, center_y - half_height),
            clip.x1,
            min(float(page.rect.height), center_y + half_height),
        )
        local_drawings = 0
        for drawing in drawings:
            rect = fitz.Rect(drawing.get("rect") or (0.0, 0.0, 0.0, 0.0))
            page_scale = (
                rect.width >= float(page.rect.width) * 0.8
                and rect.height >= float(page.rect.height) * 0.8
            )
            if not page_scale and rect.intersects(row_rect):
                local_drawings += 1
        if local_drawings < 5:
            return False
    return True


def _recover_native_geometric_options(
    marker_rows: List[Dict[str, Any]],
    native_words: List[Tuple[Any, ...]],
    clip_right: float,
) -> Optional[Dict[str, str]]:
    """Recupera listas curtas e frações empilhadas pela geometria do texto nativo."""

    if len(marker_rows) != 5 or [row.get("label") for row in marker_rows] != list("ABCDE"):
        return None

    roman_options: Dict[str, str] = {}
    for row in marker_rows:
        match = re.match(
            r"^\s*[A-E]\s*(?:[.)\-:]\s*)?(.*?)\s*$",
            str(row.get("text") or ""),
            re.IGNORECASE,
        )
        suffix = str((match.group(1) if match else "") or "").strip()
        if not re.fullmatch(r"[IVXLCDM]+", suffix, re.IGNORECASE):
            roman_options = {}
            break
        roman_options[row["label"]] = suffix.upper()
    if set(roman_options) == set("ABCDE"):
        return roman_options

    words: List[Tuple[float, float, float, float, str]] = []
    for word in native_words:
        if len(word) < 5:
            continue
        try:
            x0, y0, x1, y1 = (float(value) for value in word[:4])
        except (TypeError, ValueError):
            continue
        value = str(word[4] or "").strip()
        if value:
            words.append((x0, y0, x1, y1, value))

    recovered: Dict[str, str] = {}
    for row in marker_rows:
        label = str(row["label"]).upper()
        label_words = [
            word
            for word in words
            if word[4].upper() == label
            and abs(word[0] - float(row.get("x0", 0.0))) <= 16.0
            and word[1] <= float(row.get("y1", 0.0)) + 3.0
            and word[3] >= float(row.get("y0", 0.0)) - 3.0
        ]
        if not label_words:
            continue
        label_word = min(
            label_words,
            key=lambda word: abs(word[0] - float(row.get("x0", 0.0))),
        )
        anchor_y = (label_word[1] + label_word[3]) / 2.0
        nearby_words = [
            word
            for word in words
            if word[0] >= label_word[2] + 1.0
            and word[0] < clip_right
            and abs((word[1] + word[3]) / 2.0 - anchor_y) <= 18.5
        ]
        nearby_words.sort(key=lambda word: word[0])

        terms: List[List[Tuple[float, float, float, float, str]]] = [[]]
        for word in nearby_words:
            if word[4] in {"+", "＋"}:
                if terms[-1]:
                    terms.append([])
                continue
            terms[-1].append(word)
        if len(terms) != 2 or any(not term for term in terms):
            continue

        fractions: List[str] = []
        for term in terms:
            by_y = sorted(term, key=lambda word: (word[1] + word[3]) / 2.0)
            y_centers = [(word[1] + word[3]) / 2.0 for word in by_y]
            gaps = [
                (y_centers[index + 1] - y_centers[index], index)
                for index in range(len(y_centers) - 1)
            ]
            if not gaps:
                fractions = []
                break
            vertical_gap, split_index = max(gaps, key=lambda item: item[0])
            if vertical_gap < 5.0:
                fractions = []
                break

            numerator_words = sorted(by_y[:split_index + 1], key=lambda word: word[0])
            denominator_words = sorted(by_y[split_index + 1:], key=lambda word: word[0])
            numerator = "".join(word[4] for word in numerator_words)
            denominator = "".join(word[4] for word in denominator_words)
            if not numerator or not denominator:
                fractions = []
                break
            fractions.append(rf"\frac{{{numerator}}}{{{denominator}}}")

        if len(fractions) == 2:
            recovered[label] = " + ".join(fractions)

    if set(recovered) != set("ABCDE"):
        return None
    return recovered


def _looks_like_split_numeric_formula_options(options: Dict[str, str]) -> bool:
    """Sinaliza fórmulas numéricas separadas em texto nativo, como ``36 3``."""

    if set(options) != set("ABCDE"):
        return False
    values = [str(options.get(label) or "").strip() for label in "ABCDE"]
    if any(not value for value in values):
        return False
    numeric_values = [
        value
        for value in values
        if re.fullmatch(r"[%\d\s.,/+\-−°√π()xX×=]+", value)
    ]
    split_formula_count = sum(
        bool(re.search(r"\d{1,3}\s+\d{1,2}", value))
        for value in numeric_values
    )
    return len(numeric_values) >= 4 and split_formula_count >= 1


def _ocr_native_option_rows(
    page: fitz.Page,
    marker_rows: List[Dict[str, Any]],
    clip: fitz.Rect,
) -> Optional[Dict[str, str]]:
    """Lê somente as cinco linhas de alternativas sem rasterizar a página toda."""

    from .layout.layout_detector import extract_ocr_lines_from_page

    ocr_lines = extract_ocr_lines_from_page(
        page,
        dpi=300,
        clip=clip,
        min_score=0.20,
    )
    if not ocr_lines:
        return None

    recovered: Dict[str, str] = {}
    for marker in marker_rows:
        row_lines = [
            line
            for line in ocr_lines
            if abs(
                float(
                    line.get(
                        "mid_y",
                        (float(line.get("y0", 0.0)) + float(line.get("y1", 0.0))) / 2.0,
                    )
                )
                - marker["mid_y"]
            ) <= 13.0
        ]
        pieces = []
        for line in sorted(
            row_lines,
            key=lambda item: (
                float(item.get("y0", 0.0)),
                float(item.get("x0", 0.0)),
            ),
        ):
            text = str(line.get("text") or "").strip()
            if not text:
                continue
            if re.fullmatch(r"[A-E?][1Il]?", text, re.IGNORECASE):
                continue
            prefixed = re.match(r"^([A-E])\s*[.):\-]+\s*(\S.*)$", text, re.IGNORECASE)
            if prefixed:
                pieces.append(prefixed.group(2))
            else:
                pieces.append(text)
        if (
            len(pieces) == 2
            and re.fullmatch(r"\d{1,3}", pieces[0])
            and re.fullmatch(r"\d{1,3}", pieces[1])
        ):
            pieces = [f"{pieces[0]}/{pieces[1]}"]
        value = " ".join(pieces).strip()
        if value:
            recovered[marker["label"]] = value

    if set(recovered) != set("ABCDE"):
        return None
    return recovered


def _recover_native_text_options_with_local_ocr(
    doc: fitz.Document,
    questions: List[Dict[str, Any]],
    q_spatial_map: Dict[int, Tuple[int, float, float]],
    expected_option_count: int = 5,
) -> List[int]:
    """Recupera fórmulas ambíguas com OCR de até oito faixas de alternativas."""

    targets: List[Tuple[Dict[str, Any], Optional[Tuple[fitz.Page, List[Dict[str, Any]], fitz.Rect]]]] = []
    for question in questions:
        options = question.get("opcoes") or {}
        math_issue = _looks_like_split_numeric_formula_options(options)
        missing_expected_options = bool(
            expected_option_count == 5
            and (
                set(options) != set("ABCDE")
                or any(not str(options.get(label) or "").strip() for label in "ABCDE")
            )
        )
        if not math_issue and not missing_expected_options:
            continue
        try:
            question_number = int(question.get("numero_questao"))
        except (TypeError, ValueError):
            continue
        marker_target = _native_option_marker_rows(doc, question_number, q_spatial_map)
        # Não rasterizar alternativas desenhadas como imagens: o vínculo
        # espacial de imagens continua responsável por esse tipo de questão.
        if marker_target:
            targets.append((question, marker_target))

    unresolved: List[int] = []
    for question, target in targets[:8]:
        question_number = int(question["numero_questao"])
        page, marker_rows, clip = target
        recovered = _ocr_native_option_rows(page, marker_rows, clip)
        if not recovered:
            if _has_dense_vector_option_rows(page, marker_rows, clip):
                print(
                    f"[OCR local] Questão {question_number}: alternativas visuais "
                    "preservadas para vínculo espacial de imagens.",
                    flush=True,
                )
                continue
            unresolved.append(question_number)
            continue
        formatted_options: Dict[str, str] = {}
        for label in "ABCDE":
            value = restore_exam_typography(recovered[label], is_option=True)
            formatted_value, _ = format_latex_formulas(value)
            formatted_options[label] = formatted_value
        question["opcoes"] = formatted_options
        print(
            f"[OCR local] Fórmulas recuperadas na questão {question_number} "
            f"(página {page.number + 1}, recorte de alternativas).",
            flush=True,
        )
    return unresolved


def _spatial_fast_enabled() -> bool:
    value = os.getenv("PDF_PIPELINE_FAST_SPATIAL_MAP")
    if value is None:
        return True
    return value.strip().lower() not in {"0", "false", "off", "no"}


def _build_question_spatial_map_legacy(
    doc: fitz.Document,
    start_page: int,
    total_pages: int,
) -> Tuple[Dict[int, Tuple[int, float, float]], Dict[int, List[Any]]]:
    """Mapa anterior, preservado para rollback operacional."""
    q_spatial_map: Dict[int, Tuple[int, float, float]] = {}
    page_text_blocks: Dict[int, List[Any]] = {}

    for p_idx in range(start_page, total_pages):
        page = doc[p_idx]
        blocks = page.get_text('blocks')
        page_text_blocks[p_idx] = blocks
        for q_num in range(1, 201):
            if q_num in q_spatial_map:
                continue
            queries = [
                f"Questão {q_num:02d}", f"Questão {q_num}",
                f"QUESTÃO {q_num:02d}", f"QUESTÃO {q_num}",
                f"ITEM {q_num:02d}", f"ITEM {q_num}",
                f"Questão\n{q_num:02d}", f"Questão\n{q_num}",
            ]
            for query in queries:
                rects = page.search_for(query)
                if rects:
                    rects.sort(key=lambda r: r.y0)
                    rect = rects[0]
                    q_spatial_map[q_num] = (p_idx, rect.x0, rect.y0)
                    break

    for p_idx, blocks in page_text_blocks.items():
        for block in blocks:
            bx0, by0, _bx1, _by1, block_text = block[:5]
            for match in re.finditer(
                r'(?:^|\n)\s*(0*\d{1,3})\s*[\.\-\–\—\)]\s+(?=[A-Z\u00C0-\u00DC"\'\(])',
                block_text,
            ):
                number = int(match.group(1))
                if 1 <= number <= 200 and number not in q_spatial_map:
                    q_spatial_map[number] = (p_idx, bx0, by0)

            clean_text = block_text.strip()
            if clean_text.isdigit():
                number = int(clean_text)
                if 1 <= number <= 200 and number not in q_spatial_map:
                    q_spatial_map[number] = (p_idx, bx0, by0)
            else:
                for match in re.finditer(
                    r'(?:^|\n)\s*(0*\d{1,3})\s*(?:\n|\s{2,})(?=[A-Z\u00C0-\u00DC"\'\(\«\“\‘]|$)',
                    block_text,
                ):
                    number = int(match.group(1))
                    if 1 <= number <= 200 and number not in q_spatial_map:
                        q_spatial_map[number] = (p_idx, bx0, by0)

    return q_spatial_map, page_text_blocks


def _build_question_spatial_map_fast(
    doc: fitz.Document,
    start_page: int,
    total_pages: int,
) -> Tuple[Dict[int, Tuple[int, float, float]], Dict[int, List[Any]]]:
    """Lê blocos uma vez e chama ``search_for`` apenas para candidatos reais."""
    explicit_re = re.compile(
        r'(?:^|\n)\s*(?:(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+)|ITEM\s+)(0*\d{1,3})\b',
        re.IGNORECASE,
    )
    punctuated_re = re.compile(
        r'(?:^|\n)\s*(0*\d{1,3})\s*[\.\-\–\—\)]\s+(?=[A-Z\u00C0-\u00DC"\'\(])',
    )
    separated_re = re.compile(
        r'(?:^|\n)\s*(0*\d{1,3})\s*(?:\n|\s{2,})(?=[A-Z\u00C0-\u00DC"\'\(\«\“\‘]|$)',
    )
    q_spatial_map: Dict[int, Tuple[int, float, float]] = {}
    page_text_blocks: Dict[int, List[Any]] = {}
    explicit_candidates: Dict[int, List[Tuple[int, float, float, str]]] = {}

    for p_idx in range(start_page, total_pages):
        blocks = doc[p_idx].get_text('blocks')
        page_text_blocks[p_idx] = blocks
        for block in blocks:
            bx0, by0, _bx1, _by1, raw_text = block[:5]
            block_text = str(raw_text or '')
            for match in explicit_re.finditer(block_text):
                number = int(match.group(1))
                if 1 <= number <= 200:
                    prefix = block_text[match.start():match.end()].upper()
                    kind = 'ITEM' if prefix.lstrip().startswith('ITEM') else 'QUESTAO'
                    explicit_candidates.setdefault(number, []).append((p_idx, bx0, by0, kind))
            for pattern in (punctuated_re, separated_re):
                for match in pattern.finditer(block_text):
                    number = int(match.group(1))
                    if 1 <= number <= 200 and number not in q_spatial_map:
                        q_spatial_map[number] = (p_idx, bx0, by0)
            if block_text.strip().isdigit():
                number = int(block_text.strip())
                if 1 <= number <= 200 and number not in q_spatial_map:
                    q_spatial_map[number] = (p_idx, bx0, by0)

    for number, candidates in explicit_candidates.items():
        candidates.sort(key=lambda item: (item[0], item[2], item[1]))
        p_idx, bx0, by0, kind = candidates[0]
        label = 'ITEM' if kind == 'ITEM' else 'Questão'
        found = None
        for query in (
            f'{label} {number:02d}', f'{label} {number}',
            f'{label.upper()} {number:02d}', f'{label.upper()} {number}',
        ):
            rects = doc[p_idx].search_for(query)
            if rects:
                rects.sort(key=lambda r: r.y0)
                found = rects[0]
                break
        q_spatial_map[number] = (
            p_idx,
            found.x0 if found is not None else bx0,
            found.y0 if found is not None else by0,
        )

    return q_spatial_map, page_text_blocks


def _build_question_spatial_map(
    doc: fitz.Document,
    start_page: int,
    total_pages: int,
) -> Tuple[Dict[int, Tuple[int, float, float]], Dict[int, List[Any]]]:
    if not _spatial_fast_enabled():
        return _build_question_spatial_map_legacy(doc, start_page, total_pages)
    return _build_question_spatial_map_fast(doc, start_page, total_pages)


def parse_exam_document(
    pdf_bytes_or_path: Any,
    exam_id: Optional[int] = None,
    extract_images: bool = True,
    gabarito_override: Optional[str] = None,
    force_ocr: bool = False,
    layout_config: Optional[LayoutConfig] = None,
    allow_ocr: bool = True,
) -> List[Dict[str, Any]]:
    """
    Motor híbrido avançado de processamento de exames:
    1. Detecção geométrica e remoção de marcas d'água e ruídos estatísticos.
    2. Ordenação adaptativa de colunas com suporte a tabelas Markdown nativas.
    3. Scanner global de cabeçalhos de questões com programação dinâmica (elimina abortos prematuros).
    4. Parser estrito de alternativas A..E e Certo/Errado com proteção contra corte de enunciados.
    5. Recorte e vinculação em 2 fases de figuras/diagramas espaciais (Trigger Word + Gap Visual Scan).
    6. Formatação KaTeX e pareamento com gabarito oficial.
    """
    timing = _PipelineTiming()
    parse_source, cache_key = prepare_parse_source(
        pdf_bytes_or_path,
        exam_id=exam_id,
        extract_images=extract_images,
        gabarito_override=gabarito_override,
        force_ocr=force_ocr,
        layout_config=layout_config,
    )
    cached_result = load_parse_cache(cache_key)
    timing.mark("parse_cache_lookup")
    if cached_result is not None:
        cached_questions, cached_pages = cached_result
        timing.finish(pages=cached_pages, questions=len(cached_questions))
        return cached_questions

    document_sha256 = None
    if isinstance(parse_source, (bytes, bytearray)):
        document_sha256 = hashlib.sha256(bytes(parse_source)).hexdigest()
        doc = fitz.open(stream=parse_source, filetype='pdf')
    else:
        doc = fitz.open(parse_source)
    timing.mark("open_document")

    total_pages = len(doc)
    if total_pages == 0:
        timing.finish(pages=0, questions=0)
        doc.close()
        return []

    document_native_text = "\n".join(page.get_text() for page in doc)
    image_counts = [len(page.get_images(full=True)) for page in doc]
    native_question_chunks = _extract_native_question_chunks(doc)

    # 1. Identificação de marcas d'água e inicialização do extrator de imagens
    image_extractor = ExamImageExtractor(
        output_dir="static/images/questions",
        dpi=160,
        padding=8,
        min_cluster_size=25,
        min_cluster_area=400,
        watermark_page_threshold=3
    )
    watermarks = image_extractor.detect_watermarks_and_headers(doc)
    if not watermarks:
        watermarks = detect_watermarks(doc)

    # 2. Extração de Gabarito Embutido
    master_gabarito = {}
    if gabarito_override:
        from services.gabarito.gabarito_service import parse_gabarito_from_text
        master_gabarito = parse_gabarito_from_text(gabarito_override)
    if not master_gabarito:
        master_gabarito = _extract_gabarito_from_doc(doc)
    timing.mark("watermarks_and_embedded_key")

    # 3. Localização do início real do caderno
    start_page = 0
    for p_idx in range(min(6, total_pages)):
        p_text = doc[p_idx].get_text()
        if is_instruction_or_cover_page(p_text):
            start_page = p_idx + 1
        else:
            start_page = p_idx
            break
    start_page = min(start_page, max(0, total_pages - 1))
    timing.mark("locate_exam_start")

    # 4. Extração dos blocos ordenados por coluna e clusters de diagramas
    raw_blocks = []
    page_diagrams = {}
    q_spatial_map, page_text_blocks = _build_question_spatial_map(
        doc,
        start_page,
        total_pages,
    )
    timing.mark("question_spatial_map")

    # Classifica o documento antes de montar os blocos. Em um scan de página
    # inteira os blocos nativos servem apenas para coordenadas de diagramas; o
    # OCR estruturado abaixo é a fonte canônica. Evitar o fallback OCR do
    # detector aqui impede duas extrações completas da mesma página.
    from .media.scan_pipeline import scan_document_profile, extract_scan_questions
    scan_profile = scan_document_profile(doc)
    native_text_question_chunks = (
        _extract_native_text_question_chunks(doc)
        if not scan_profile.get("scan_like")
        else {}
    )

    doc_topology = infer_document_topology(doc, watermarks)
    effective_layout_config = layout_config or LayoutConfig(topology=doc_topology)
    if not effective_layout_config.topology or effective_layout_config.topology == 'AUTO':
        effective_layout_config.topology = doc_topology

    for p_idx in range(start_page, total_pages):
        page = doc[p_idx]
        p_text = page.get_text()
        
        # Ignora última página se for exclusivamente tabela de gabarito sem enunciado
        if p_idx >= max(1, total_pages - 2) and re.search(r'\b(gabarito|folha\s+de\s+respostas?)\b', p_text, re.IGNORECASE):
            if not re.search(r'\b[A-E]\)\s+[A-Z\u00C0-\u00DC]', p_text):
                continue

        page_raw_blocks = page_text_blocks.get(p_idx)
        if page_raw_blocks is None:
            page_raw_blocks = page.get_text('blocks')

        ordered_blocks = detect_layout_and_ordered_blocks(
            page,
            watermarks,
            force_ocr=bool(force_ocr and not scan_profile.get("scan_like")),
            config=effective_layout_config,
            allow_ocr_fallback=bool(
                allow_ocr and not scan_profile.get("scan_like")
            ),
        )
        for b in ordered_blocks:
            raw_blocks.append(b['text'])

        if extract_images:
            clusters = image_extractor.find_diagram_clusters(page, watermarks, text_blocks=page_raw_blocks)
            if clusters:
                page_diagrams[p_idx] = clusters

    timing.mark("layout_and_diagrams")

    full_text = '\n\n'.join(raw_blocks)

    # Detecção automática se o documento necessita de Vision OCR de alta
    # fidelidade. A quantidade de caracteres não é suficiente: PDFs escaneados
    # podem conter uma camada OCR extensa, porém sem a estrutura das questões.
    native_quality = _assess_native_text_quality(
        full_text,
        document_text=document_native_text,
        total_pages=total_pages,
        image_page_count=sum(1 for count in image_counts if count > 0),
        total_image_count=sum(image_counts),
        full_page_scan_detected=bool(scan_profile.get("scan_like")),
    )
    native_declared_count = int(
        native_quality.get("declared_question_count")
        or _declared_question_count(document_native_text)
        or 0
    )
    native_chunk_count = len(native_question_chunks)
    # Alguns PDFs são digitalizações visuais, mas carregam uma camada OCR
    # nativa suficientemente completa para estruturar o caderno. Nesses casos
    # a ingestão padrão deve continuar sendo a fonte canônica; a rota de scan
    # geométrico fica reservada aos documentos sem camada aproveitável.
    native_layer_usable = bool(
        scan_profile.get("scan_like")
        and native_declared_count >= 5
        and native_chunk_count >= max(5, math.ceil(native_declared_count * 0.95))
        and len(document_native_text.strip()) >= 1000
        and not native_quality.get("reasons")
    )
    if native_layer_usable:
        print(
            f"[Ingestão padrão] Camada OCR nativa utilizável: "
            f"{native_chunk_count}/{native_declared_count} questões; "
            "seguindo o mesmo pós-processamento e gate da rota comum.",
            flush=True,
        )
    # Um scan de página inteira precisa de uma rota estruturada. O OCR textual
    # legado devolve um ``full_text`` linear e perde justamente a relação entre
    # enunciado, alternativas e figuras; para esses PDFs a decisão é feita por
    # coordenada, em uma passada visual por página.
    needs_vision_ocr = len(full_text.strip()) < 500 or force_ocr or native_quality["needs_vision_ocr"]
    avg_chars_per_page = len(full_text.strip()) / max(1, total_pages)
    if not needs_vision_ocr and avg_chars_per_page < 150 and total_pages >= 3:
        test_rq = rust_process_exam_text(full_text)
        if not test_rq or len(test_rq) < 2:
            needs_vision_ocr = True

    ocr_route_required = bool(
        needs_vision_ocr
        or (scan_profile.get("scan_like") and not native_layer_usable)
    )
    if not allow_ocr and ocr_route_required:
        print(
            "[OCR bloqueado] Documento não reprocessado porque o pipeline "
            "solicitaria OCR.",
            flush=True,
        )
        timing.mark("ocr_blocked")
        timing.finish(pages=total_pages, questions=0)
        doc.close()
        return []

    if scan_profile.get("scan_like") and not native_layer_usable:
        print(
            "[Scan OCR] Documento identificado como scan de página inteira; "
            "extraindo linhas, contexto e regiões visuais por coordenada.",
            flush=True,
        )
        scan_result = extract_scan_questions(
            doc,
            start_page=start_page,
            exam_id=exam_id or 0,
            extract_images=extract_images,
            image_extractor=image_extractor,
            ocr_dpi=300,
        )
        scan_questions = scan_result.get("questions") or []
        scan_quality = scan_result.get("quality") or {}
        declared_count = (
            scan_quality.get("declared_question_count")
            or native_quality.get("declared_question_count")
        )
        scan_count = len(scan_questions)
        option_ready = int(scan_quality.get("questions_with_four_or_more_options", 0))
        text_integrity_ready = int(scan_quality.get("questions_with_text_integrity", 0))
        min_expected = int(declared_count or native_quality.get("question_count") or 0)
        count_ready = scan_count >= max(5, math.ceil(min_expected * 0.95)) if min_expected else scan_count >= 5
        options_ready = option_ready >= max(5, math.ceil(scan_count * 0.90))
        text_ready = text_integrity_ready == scan_count and scan_count > 0
        if count_ready and options_ready and text_ready:
            for q in scan_questions:
                try:
                    q_num = int(q.get("numero_questao"))
                except (TypeError, ValueError):
                    continue
                q["resposta"] = normalize_answer_or_empty(
                    master_gabarito.get(q_num) or q.get("resposta")
                )
                q["has_embedded_answer"] = bool(master_gabarito.get(q_num))
                inferred_subject = rust_classify_subject(q.get("enunciado", ""))
                if inferred_subject:
                    q["disciplina"] = inferred_subject
                q["enunciado"] = format_markdown_tables_in_text(q.get("enunciado", ""))
                q["enunciado"] = strip_embedded_answer_marker(q.get("enunciado", ""))
                _repair_image_only_option_question(q)
                q.pop("_page", None)
                q.pop("_x", None)
                q.pop("_y", None)

            scan_questions.sort(
                key=lambda item: int(item.get("numero_questao", 9999))
                if str(item.get("numero_questao", "")).isdigit()
                else 9999
            )
            print(
                f"[Scan OCR] {scan_count} questões estruturadas; "
                f"{option_ready} com quatro ou mais alternativas; "
                f"{text_integrity_ready} com integridade textual; "
                f"{scan_quality.get('ocr_readings', 0)} leituras OCR; "
                f"{scan_quality.get('images_attached', 0)} imagem(ns) vinculada(s).",
                flush=True,
            )
            timing.mark("scan_ocr")
            save_parse_cache(cache_key, scan_questions, pages=total_pages)
            timing.mark("parse_cache_store")
            timing.finish(pages=total_pages, questions=len(scan_questions))
            doc.close()
            return scan_questions
        print(
            f"[Scan OCR] Gate de qualidade não aprovado "
            f"(questões={scan_count}/{min_expected or '?'}, "
            f"alternativas completas={option_ready}, "
            f"integridade textual={text_integrity_ready}/{scan_count}, "
            f"problemas={scan_quality.get('text_integrity_issues') or {}}); "
            "a prova não será salva com texto incompleto.",
            flush=True,
        )
        # Um scan de página inteira não possui uma camada nativa confiável
        # para servir de fallback. Prosseguir aqui permitiria que o parser
        # linear salvasse um resultado estruturalmente menor ou com palavras
        # coladas. O worker converte a lista vazia em estado de erro e deixa a
        # prova disponível para reprocessamento após uma nova correção OCR.
        timing.mark("scan_ocr_rejected")
        timing.finish(pages=total_pages, questions=0)
        doc.close()
        return []

    # A camada nativa completa não precisa de uma segunda OCR global; ainda
    # assim, ela passa pelo gate textual abaixo para não aceitar mojibake,
    # ruído ou alternativas incompletas.
    quality_gate_required = bool(needs_vision_ocr or force_ocr or native_layer_usable)

    if needs_vision_ocr and not native_layer_usable:
        from .media.vision_pipeline import extract_exam_via_vision_ocr

        reasons = native_quality["reasons"] or (["force_ocr"] if force_ocr else ["low_native_text"])
        print(
            f"[Vision OCR] Acionado para o documento: {', '.join(reasons)}",
            flush=True,
        )
        ocr_text = extract_exam_via_vision_ocr(
            doc,
            dpi=200,
            watermarks=watermarks,
            document_sha256=document_sha256,
        )
        if len(ocr_text.strip()) > 50:
            full_text = ocr_text
        else:
            print("[Vision OCR] Nenhum texto OCR confiável foi retornado; mantendo a camada nativa.", flush=True)
        timing.mark("vision_ocr")
    else:
        timing.mark("vision_ocr_skipped")

    if len(full_text.strip()) < 50:
        timing.finish(pages=total_pages, questions=0)
        doc.close()
        return []

    # 4.1 Normalização resiliente de cabeçalhos gerados por OCR degradado e remoção de rodapés institucionais
    full_text = re.sub(r'(?m)^[ \t]*pcimarkpci[^\n]*$\n?', '', full_text)
    full_text = re.sub(r'(?m)^[ \t]*www\.pciconcursos\.com\.br[^\n]*$\n?', '', full_text)
    full_text = re.sub(r'(?m)^[ \t]*(?:PREFEITURA|CÂMARA|GOVERNO|ESTADO|CONCURSO\s+PÚBLICO|PROVA\s+OBJETIVA|EDITAL|[A-Z0-9_\-]+\s*[-–—]\s*P[áa]gina\s*\d+)[^\n]*$\n?', '', full_text, flags=re.IGNORECASE)
    full_text = re.sub(r'(?m)^\s*[A-Za-z\u00C0-\u00DC\s\-\/\(\)]{3,35}\s*[-–—]\s*\d+\s*$', '', full_text)
    full_text = re.sub(r'(?:\b|(?<=[\s\n]))(\d{1,3})\s*[\,\"\']+[ \t]*(?=[\.\,\:\'\`\~\s]*[A-Za-z\u00C0-\u00DC\"\'\(\[])', r'\n\1. ', full_text)
    full_text = re.sub(r'(?:\b|(?<=[\s\n]))[íI!|](\d)\s*[\.\,\:\-\"\']+[ \t]*(?=[\.\,\:\'\`\~\s]*[A-Za-z\u00C0-\u00DC\"\'\(\[])', r'\n1\1. ', full_text)
    full_text = re.sub(r'(?:\b|(?<=[\s\n]))3[üuU]\s*[\.\,\:\-\"\']+[ \t]*(?=[\.\,\:\'\`\~\s]*[A-Za-z\u00C0-\u00DC\"\'\(\[])', r'\n30. ', full_text)
    full_text = re.sub(r'(?:\b|(?<=[\s\n]))[íI!|]0\s*[\.\,\:\-\"\']+[ \t]*(?=[\.\,\:\'\`\~\s]*[A-Za-z\u00C0-\u00DC\"\'\(\[])', r'\n10. ', full_text)
    full_text = re.sub(r'(?m)^[ \t]*1\.\s+(?=A\s*pesar|A\s*rea|A\s*ssegurar|Pagou|Um\s+professor)', 'I. ', full_text)
    full_text = re.sub(r'(?m)^([ \t]*\d{1,2}\.)([^\s\d])', r'\1 \2', full_text)
    # Sanitização de rodapés institucionais residuais entre blocos (ex: ADMINISTRADOR - 1)
    full_text = re.sub(r'(?m)^[ \t]*[A-Za-z\u00C0-\u00DC\s\-\/\(\)]{3,}\s*[-–—]\s*\d+[ \t]*$\n*', '\n', full_text)
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)

    # 5. Execução Unificada em Rust (Zero Ping-Pong) com Fallback Resiliente
    rust_questions = rust_process_exam_text(full_text)
    if rust_questions and len(rust_questions) >= 3:
        rust_questions = _reconcile_rust_question_chain(
            rust_questions,
            full_text,
        )
        # Reconciliação automática de questões com cabeçalho explícito 'QUESTÃO N' ausentes no output nativo
        existing_q_nums = {int(rq['numero_questao']) for rq in rust_questions if str(rq.get('numero_questao', '')).isdigit()}
        explicit_headers = re.findall(r'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)0*(\d{1,3})\b', full_text, re.IGNORECASE)
        for h_num_str in explicit_headers:
            h_num = int(h_num_str)
            if h_num not in existing_q_nums and 1 <= h_num <= 250:
                m_h = re.search(rf'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)0*{h_num}\b', full_text, re.IGNORECASE)
                if m_h:
                    m_next_h = re.search(rf'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)0*{h_num + 1}\b', full_text[m_h.end():], re.IGNORECASE)
                    chunk_missing = full_text[m_h.start():m_h.end() + m_next_h.start()] if m_next_h else full_text[m_h.start():]
                    missing_opts, missing_stmt = extract_options_from_chunk(chunk_missing)
                    missing_stmt_clean = re.sub(rf'^(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)0*{h_num}\b[ \t]*[:\.\-]?[ \t]*', '', missing_stmt or chunk_missing, flags=re.IGNORECASE).strip()
                    rust_questions.append({
                        'numero_questao': str(h_num),
                        'enunciado': missing_stmt_clean,
                        'opcoes': missing_opts,
                        'resposta': normalize_answer_or_empty(master_gabarito.get(h_num)),
                        'has_embedded_answer': h_num in master_gabarito,
                        'disciplina': 'Geral'
                    })
                    existing_q_nums.add(h_num)

        # Índice canônico da Cadeia de Encadeamento (ordem documental imutável, 0-based),
        # atribuído ANTES da ordenação por rótulo para preservar a posição física na prova.
        for _cidx, _rq in enumerate(rust_questions):
            _rq['_chain_idx'] = _cidx

        rust_questions.sort(key=lambda q: int(q['numero_questao']) if str(q.get('numero_questao', '')).isdigit() else 999)

        rust_found_positions = []
        for rq in rust_questions:
            try:
                qn = int(rq['numero_questao'])
                # O Rust já devolve a posição do cabeçalho escolhido pela
                # cadeia global. Rebuscar apenas pelo número reintroduz
                # falsos cabeçalhos: em provas com textos numerados, ``2``
                # pode ser o parágrafo de um texto de apoio ou uma página de
                # instruções anterior à questão 2 real.
                start_char = int(rq.get('start_char'))
                end_char = int(rq.get('end_char'))
                if 0 <= start_char < end_char <= len(full_text):
                    rust_found_positions.append((qn, start_char, end_char))
                    continue
                m_h = re.search(
                    rf'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)0*{qn}\b',
                    full_text,
                    re.IGNORECASE,
                )
                if m_h:
                    rust_found_positions.append((qn, m_h.start(), m_h.end()))
            except Exception:
                pass
        rust_context_blocks = extract_context_blocks(full_text, rust_found_positions)
        numbered_context_blocks = _extract_numbered_source_context_blocks(
            full_text,
            rust_found_positions,
        )
        for numbered_context in numbered_context_blocks:
            if not any(
                numbered_context[0] == existing[0]
                and numbered_context[1] == existing[1]
                and numbered_context[3] == existing[3]
                for existing in rust_context_blocks
            ):
                rust_context_blocks.append(numbered_context)

        questions = []
        for rq in rust_questions:
            q_num = int(rq['numero_questao'])
            formatted_enunciado = rq['enunciado']
            uses_native_text_candidate = False

            # Injeção de Texto de Apoio Compartilhado em rust_questions
            matching_context = None
            for q_min, q_max, ctx_text, _ in rust_context_blocks:
                if q_min <= q_num <= q_max:
                    matching_context = (q_min, q_max, ctx_text)
                    break

            if matching_context:
                q_min, q_max, ctx_text = matching_context
                cleaned_ctx = _prepare_numbered_source_context(
                    ctx_text,
                    preserve_native_word_boundaries=not scan_profile.get("scan_like"),
                )
                if cleaned_ctx[:30] not in formatted_enunciado:
                    formatted_enunciado = f"📖 **Texto de Apoio (Questões {q_min} a {q_max}):**\n\n{cleaned_ctx}\n\n---\n\n{formatted_enunciado}"

            formatted_enunciado, has_latex_enunciado = format_latex_formulas(formatted_enunciado)
            formatted_enunciado = restore_exam_typography(
                formatted_enunciado,
                preserve_native_word_boundaries=not scan_profile.get("scan_like"),
            )
            formatted_enunciado = format_markdown_tables_in_text(formatted_enunciado)
            
            raw_options = rq.get('opcoes', {})
            # Detecta se alguma alternativa foi truncada pelo motor nativo ou se faltam opções
            needs_recovery = False
            if re.search(r'(?:^|\n|\s+)[a-eA-E]\)\s*[A-ZÁ-Ú]', formatted_enunciado):
                needs_recovery = True
            else:
                for let, opt_val in raw_options.items():
                    v_str = str(opt_val).strip()
                    if len(v_str) <= 3 or v_str.endswith(('de.', 'em.', 'para.', 'com.', 'A.', 'B.', 'C.', 'D.', 'E.')):
                        needs_recovery = True
                        break
                    if re.match(r'^\s*[A-Ea-e]\s+[A-Za-zÀ-ÿ]', v_str):
                        needs_recovery = True
                        break
                    if re.search(
                        r'(?:conhecida\s+como\s*:|correto\s+afirmar|'
                        r'correta\s+em\s+qual|área\s+destinada)',
                        v_str,
                        re.IGNORECASE,
                    ):
                        needs_recovery = True
                        break
            
            # O parser Rust também possui um fallback por cauda. Em uma prova
            # escaneada ele pode devolver quatro alternativas válidas, porém
            # escolhidas do desenho, de um rodapé ou de um bloco deslocado.
            # Reavalie sempre o bloco OCR quando ele não contém uma sequência
            # explícita A..D/A..E; caso contrário a quantidade de opções
            # mascararia uma extração incorreta.
            chunk_q = None
            # Use the same physical span selected by the global Rust chain.
            # This is essential when the document contains numbered
            # paragraphs, years or instruction pages before the real item.
            try:
                anchored_start = int(rq.get('start_char'))
                anchored_end = min(
                    len(full_text),
                    max(anchored_start + 1, int(rq.get('end_char'))),
                )
                if 0 <= anchored_start < anchored_end <= len(full_text):
                    later_starts = []
                    for candidate in rust_questions:
                        candidate_start = candidate.get('start_char')
                        if candidate_start is None:
                            continue
                        candidate_start = int(candidate_start)
                        if candidate_start > anchored_start:
                            later_starts.append(candidate_start)
                    if later_starts:
                        anchored_end = min(later_starts)
                    # The span must still begin with this question header;
                    # otherwise retain the defensive regex fallback below.
                    probe = full_text[anchored_start:anchored_start + 80]
                    if re.match(
                        rf'\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)?0*{q_num}\b',
                        probe,
                        re.IGNORECASE,
                    ):
                        chunk_q = full_text[anchored_start:anchored_end]
            except (TypeError, ValueError):
                chunk_q = None

            if chunk_q is None:
                m_curr = re.search(
                    rf'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)0*{q_num}\b',
                    full_text,
                    re.IGNORECASE,
                )
                if not m_curr:
                    m_curr = re.search(
                        rf'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+|0*)0*{q_num}\b',
                        full_text,
                        re.IGNORECASE,
                    )
                if m_curr:
                    m_next = re.search(
                        rf'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)0*{q_num + 1}\b',
                        full_text[m_curr.end():],
                        re.IGNORECASE,
                    )
                    if not m_next:
                        m_next = re.search(
                            rf'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+|0*)0*{q_num + 1}\b',
                            full_text[m_curr.end():],
                            re.IGNORECASE,
                        )
                    chunk_q = (
                        full_text[m_curr.start():m_curr.end() + m_next.start()]
                        if m_next
                        else full_text[m_curr.start():]
                    )

            if chunk_q is not None:
                recovered_opts, clean_stmt = extract_options_from_chunk(
                    chunk_q,
                    preserve_native_word_boundaries=not scan_profile.get("scan_like"),
                )
                heuristic_opts, heuristic_stmt = extract_heuristic_options(chunk_q)
                candidates = [
                    (recovered_opts, clean_stmt),
                    (heuristic_opts or {}, heuristic_stmt),
                ]

                native_text_candidate = None
                native_text_chunk = native_text_question_chunks.get(q_num)
                if native_text_chunk:
                    text_opts, text_stmt = extract_options_from_chunk(
                        native_text_chunk,
                        preserve_native_word_boundaries=True,
                    )
                    if (
                        set(text_opts) == set("ABCDE")
                        and all(str(text_opts.get(label) or "").strip() for label in "ABCDE")
                        and len(str(text_stmt or "").strip()) > 15
                    ):
                        native_text_candidate = (text_opts, text_stmt)
                        candidates.append(native_text_candidate)

                native_candidate = None
                # A camada nativa deste scan contém texto completo em várias
                # alternativas, embora perca as letras dentro dos círculos.
                # Usa-a somente quando a heurística reconstrói exatamente
                # quatro opções; assim não troca uma questão de cinco opções
                # por um bloco nativo ambíguo.
                native_chunk = native_question_chunks.get(q_num)
                if native_chunk:
                    native_opts, native_stmt = extract_heuristic_options(native_chunk)
                    if native_opts and len(native_opts) == 4:
                        native_candidate = (native_opts, native_stmt)
                        candidates.append(native_candidate)

                native_candidate_score = (
                    _score_option_map(native_candidate[0])
                    if native_candidate
                    else float('-inf')
                )
                has_five_option_candidate = any(
                    len(candidate[0]) == 5
                    for candidate in candidates
                    if candidate[0]
                )
                if native_text_candidate:
                    # Em PDFs textuais, as alternativas completas do bloco
                    # nativo preservam melhor colunas e marcadores tabulados
                    # do que o texto linear remontado pelo detector de layout.
                    selected_opts, selected_stmt = native_text_candidate
                    uses_native_text_candidate = True
                elif (
                    not scan_profile.get("scan_like")
                    and set(recovered_opts) == set("ABCDE")
                    and all(
                        str(recovered_opts.get(label) or "").strip()
                        for label in "ABCDE"
                    )
                ):
                    # Em PDFs textuais, a primeira sequência explícita A--E
                    # dentro do span ancorado é a sequência da própria
                    # questão. A heurística por cauda pode encontrar outra
                    # sequência A--E em um texto de apoio que começa antes da
                    # questão seguinte e deslocar todo o conteúdo.
                    selected_opts, selected_stmt = recovered_opts, clean_stmt
                elif (
                    native_candidate
                    and native_candidate_score >= 80.0
                    and has_five_option_candidate
                    and scan_profile.get("scan_like")
                ):
                    # Em scans de provas com quatro alternativas, a
                    # heurística às vezes cruza o enunciado seguinte e cria
                    # uma quinta opção. Um bloco nativo completo de quatro é
                    # mais confiável nesse caso.
                    selected_opts, selected_stmt = native_candidate
                elif native_candidate and scan_profile.get("scan_like") and (
                    len(raw_options) != 4
                    or needs_recovery
                    or len(formatted_enunciado.strip()) < 25
                ) and native_candidate_score >= 80.0:
                    selected_opts, selected_stmt = native_candidate
                else:
                    selected_opts, selected_stmt = max(
                        candidates,
                        key=lambda candidate: _score_option_map(candidate[0]),
                        default=({}, ""),
                    )

                should_replace = (
                    len(selected_opts) >= 4
                    or needs_recovery
                    or len(raw_options) < 4
                )
                if should_replace and (
                    len(selected_opts) >= max(4, len(raw_options))
                ):
                    if len(selected_opts) >= 4:
                        raw_options = selected_opts
                    if selected_stmt and len(selected_stmt) > 10:
                        selected_stmt = re.sub(
                            rf'^(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+|0*)0*{q_num}\b'
                            r'[ \t]*[:\.\-,]?[ \t]*',
                            '',
                            selected_stmt,
                            flags=re.IGNORECASE,
                        ).strip()
                        formatted_enunciado = selected_stmt
                        if matching_context:
                            q_min, q_max, ctx_text = matching_context
                            cleaned_ctx = _prepare_numbered_source_context(
                                ctx_text,
                                preserve_native_word_boundaries=not scan_profile.get("scan_like"),
                            )
                            if cleaned_ctx[:30] not in formatted_enunciado:
                                formatted_enunciado = f"📖 **Texto de Apoio (Questões {q_min} a {q_max}):**\n\n{cleaned_ctx}\n\n---\n\n{formatted_enunciado}"
                        formatted_enunciado, has_latex_enunciado = format_latex_formulas(formatted_enunciado)
                        formatted_enunciado = restore_exam_typography(
                            formatted_enunciado,
                            preserve_native_word_boundaries=(
                                not scan_profile.get("scan_like")
                                or uses_native_text_candidate
                            ),
                        )
            formatted_enunciado = format_markdown_tables_in_text(formatted_enunciado)
            formatted_enunciado = _unprotect_source_paragraph_markers(formatted_enunciado)

            options = {}
            for let, opt_text in raw_options.items():
                opt_clean = str(opt_text).strip()
                opt_clean = re.sub(r'^[A-Ea-e]\s*[\(\[]\s*[\)\]]\s*', '', opt_clean)
                opt_clean = re.sub(r'^\(?[A-Ea-e]\s*[\)\.\-–—:]\s*', '', opt_clean)
                opt_clean = re.sub(r'^\(\s*\)\s*', '', opt_clean)
                opt_lines = opt_clean.splitlines()
                while opt_lines and SUBJECT_REGEX.match(opt_lines[-1].strip()):
                    opt_lines.pop()
                opt_clean = '\n'.join(opt_lines).strip()
                opt_clean = _normalize_roman_list_option(opt_clean)
                opt_clean = re.sub(r'\s*(?:<[^\s>]+>|\*{1,3}|_{1,3})+\s*(?:Conhecimentos\s+Espec[íi\ufffd\?]?ficos|Conhecimentos\s+Gerais|Conhecimentos\s+B[áa\ufffd\?]?sicos|L[íi\ufffd\?]?ngua\s+Portuguesa|Portugu[êe]s|Matem[áa]tica|No[çc\ufffd\?][õo\ufffd\?]?es\s+de\s+[^\n<]+|Racioc[íi\ufffd\?]?nio\s+L[óo\ufffd\?]?gico[^\n<]*|Legisla[çc\ufffd\?][ãa\ufffd\?]?o\s+Espec[íi\ufffd\?]?fica|Inform[áa\ufffd\?]?tica|Direito\s+[^\n<]+|TEXTO:\s*[^\n<]+)(?:<[^\s>]+>|\*{1,3}|_{1,3})+\s*$', '', opt_clean, flags=re.IGNORECASE)
                opt_clean = restore_exam_typography(
                    opt_clean,
                    is_option=True,
                    preserve_native_word_boundaries=(
                        not scan_profile.get("scan_like")
                        or uses_native_text_candidate
                    ),
                )
                opt_formatted, _ = format_latex_formulas(opt_clean)
                options[let] = opt_formatted

            has_embedded_answer = bool(
                rq.get('has_embedded_answer')
                or master_gabarito.get(q_num)
            )
            final_answer = normalize_answer_or_empty(
                master_gabarito.get(q_num) or rq.get('resposta')
            )
            approx_page, q_x, q_y = q_spatial_map.get(q_num, (start_page, 0.0, 0.0))
            
            questions.append({
                'numero_questao': str(q_num),
                'enunciado': formatted_enunciado,
                'opcoes': options,
                'resposta': final_answer,
                'has_embedded_answer': has_embedded_answer,
                'disciplina': rq.get('disciplina', 'Geral'),
                'images': None,
                'latex_support': 1 if has_latex_enunciado else 0,
                'question_index': rq.get('_chain_idx'),
                '_page': approx_page,
                '_x': q_x,
                '_y': q_y
            })
        
        # Remove artefatos de rodapé antes de decidir se alternativas nativas
        # estão completas. Alguns cadernos deixam o código PCI na posição de E,
        # o que ocultava a falta real da alternativa no gate de recuperação.
        for question in questions:
            question["enunciado"] = _strip_exam_watermark_token(
                _strip_trailing_pdf_section_header(
                    _strip_pdf_page_code_tail(
                        strip_embedded_answer_marker(question.get("enunciado", ""))
                    )
                )
            )
            question["opcoes"] = {
                label: _strip_trailing_exam_banner(
                    _strip_trailing_pdf_section_header(
                        _strip_pdf_page_code_tail(value)
                    ).strip()
                )
                for label, value in (question.get("opcoes") or {}).items()
            }

        # Última recuperação direcionada para alternativas curtas de scans.
        # Executa antes do fechamento do documento e antes do vínculo de
        # diagramas, preservando o restante da extração já validada.
        # OCR de precisão é uma segunda passada cara. Só pode ser acionado
        # quando a avaliação de qualidade realmente pediu Vision OCR; um PDF
        # textual saudável não deve entrar aqui por não ser um "scan-like".
        if _should_run_precision_recovery(
            needs_vision_ocr=needs_vision_ocr,
            native_layer_usable=native_layer_usable,
        ):
            _recover_scan_options_at_high_resolution(
                doc=doc,
                questions=questions,
                q_spatial_map=q_spatial_map,
            )

        native_ocr_unresolved: List[int] = []
        if not scan_profile.get("scan_like"):
            option_count_distribution = Counter(
                len(question.get("opcoes") or {})
                for question in questions
                if len(question.get("opcoes") or {}) in (4, 5)
            )
            expected_option_count = (
                max((5, 4), key=lambda count: option_count_distribution[count])
                if option_count_distribution
                else 0
            )
            for question in questions:
                options = question.get("opcoes") or {}
                math_issue = _looks_like_split_numeric_formula_options(options)
                missing_expected_options = bool(
                    expected_option_count == 5
                    and (
                        set(options) != set("ABCDE")
                        or any(
                            not str(options.get(label) or "").strip()
                            for label in "ABCDE"
                        )
                    )
                )
                if not math_issue and not missing_expected_options:
                    continue
                try:
                    question_number = int(question.get("numero_questao"))
                except (TypeError, ValueError):
                    continue
                marker_target = _native_option_marker_rows(
                    doc,
                    question_number,
                    q_spatial_map,
                )
                if not marker_target:
                    continue
                page, marker_rows, clip = marker_target
                recovered = _recover_native_geometric_options(
                    marker_rows,
                    page.get_text("words"),
                    clip.x1,
                )
                if not recovered:
                    continue
                formatted_options = {}
                for label, value in recovered.items():
                    formatted_options[label], _ = format_latex_formulas(value)
                question["opcoes"] = formatted_options
                print(
                    f"[Texto nativo] Alternativas reconstruídas por posição na "
                    f"questão {question_number} (página {page.number + 1}).",
                    flush=True,
                )
            if allow_ocr:
                native_ocr_unresolved = _recover_native_text_options_with_local_ocr(
                    doc=doc,
                    questions=questions,
                    q_spatial_map=q_spatial_map,
                    expected_option_count=expected_option_count,
                )
        if native_ocr_unresolved:
            print(
                "[OCR local] Gate de integridade não aprovado: "
                f"fórmulas não recuperadas nas questões {native_ocr_unresolved}.",
                flush=True,
            )
            timing.finish(pages=total_pages, questions=0)
            doc.close()
            return []

        # Anexamento espacial de imagens/diagramas em 2 fases
        if extract_images and page_diagrams:
            questions = image_extractor.attach_images_to_questions(
                doc=doc,
                questions=questions,
                page_diagrams=page_diagrams,
                exam_id=exam_id or 0
            )
        for question in questions:
            question["enunciado"] = _strip_exam_watermark_token(
                _strip_trailing_pdf_section_header(
                    _strip_pdf_page_code_tail(
                        strip_embedded_answer_marker(question.get("enunciado", ""))
                    )
                )
            )
            question["opcoes"] = {
                label: _strip_trailing_exam_banner(
                    _strip_trailing_pdf_section_header(
                        _strip_pdf_page_code_tail(value)
                    ).strip()
                )
                for label, value in (question.get("opcoes") or {}).items()
            }
            _repair_image_only_option_question(question)

        if (
            not scan_profile.get("scan_like")
            and re.search(r"\bTRANSPETRO\b", document_native_text, re.IGNORECASE)
        ):
            transpetro_integrity = _strict_native_question_integrity(
                questions,
                expected_count=native_declared_count or 70,
                expected_option_labels="ABCDE",
            )
            if transpetro_integrity:
                print(
                    "[Transpetro] Gate de integridade textual não aprovado: "
                    f"{transpetro_integrity}",
                    flush=True,
                )
                timing.finish(pages=total_pages, questions=0)
                doc.close()
                return []
            print(
                f"[Transpetro] Integridade textual aprovada: "
                f"{len(questions)}/{native_declared_count or 70} questões; "
                "5/5 alternativas por questão.",
                flush=True,
            )

        if quality_gate_required:
            from .media.scan_pipeline import assess_question_text_integrity

            text_quality = assess_question_text_integrity(
                questions,
                native_text=document_native_text,
                minimum_options=2,
            )
            if text_quality["questions_with_text_integrity"] != len(questions):
                print(
                    "[Vision OCR] Gate de integridade não aprovado "
                    f"({text_quality['questions_with_text_integrity']}/"
                    f"{len(questions)} questões): "
                    f"{text_quality['text_integrity_issues']}",
                    flush=True,
                )
                timing.finish(pages=total_pages, questions=0)
                doc.close()
                return []
            print(
                f"[Vision OCR] Integridade textual aprovada: "
                f"{text_quality['questions_with_text_integrity']}/"
                f"{len(questions)} (100%).",
                flush=True,
            )

        # Limpeza de atributos internos temporários
        for q in questions:
            q.pop('_page', None)
            q.pop('_x', None)
            q.pop('_y', None)

        timing.mark("question_structuring_and_image_linking")
        save_parse_cache(cache_key, questions, pages=total_pages)
        timing.mark("parse_cache_store")
        timing.finish(pages=total_pages, questions=len(questions))
        doc.close()
        return questions

    # 6. Scanner Global de Cabeçalhos de Questões (Fallback Python)
    rust_headers = rust_scan_question_headers(full_text)
    found_positions = []

    header_pat = re.compile(
        r'(?i)(?:^|\n|\.\s+|\s{2,})(?:(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)(0*\d{1,3})[ \t]*(?:[\.\-–—:\)]|\n+|[ \t]+)|(0*\d{1,3})[ \t]*(?:[\.\-–—:\)]|\n+[ \t]*(?=[A-Za-z\u00C0-\u00DC\"\'\u201c\u201d\u2018\u2019\(\[«])|[ \t]+(?=[A-Za-z\u00C0-\u00DC\"\'\u201c\u201d\u2018\u2019\(\[«]))[ \t]*|\((0*\d{1,3})\)[ \t]+)'
    )

    py_found_positions = []
    candidates = []
    for m in header_pat.finditer(full_text):
        q_str = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        if not q_str:
            continue
        try:
            q_num = int(q_str)
        except ValueError:
            continue

        if not (1 <= q_num <= 200):
            continue

        # Verifica se não é parte de uma alternativa (ex: "(A) 84.") na mesma linha
        match_str = m.group(0)
        if not match_str.startswith('\n'):
            start_line = full_text.rfind('\n', 0, m.start())
            start_line = 0 if start_line == -1 else start_line + 1
            line_prefix = full_text[start_line:m.start()].strip()
            if re.search(r'^[A-Ea-e]\s*[\)\.\-–]\s*$', line_prefix):
                continue

        preview = full_text[m.end():m.end() + 150].upper()
        if any(bad in preview for bad in ['RECEBEU DO FISCAL', 'CARTÃO-RESPOSTA', 'PREENCHA O CART', 'TEMPO DISPONÍVEL', 'CONFIDENCIAL ATÉ']):
            continue

        is_explicit = bool(m.group(1))

        if not is_explicit:
            prefix_slice = full_text[max(0, m.start() - 40):m.start()]
            last_nl = prefix_slice.rfind('\n')
            same_line_prefix = prefix_slice[last_nl + 1:] if last_nl != -1 else prefix_slice
            same_line_upper = same_line_prefix.upper()
            if any(bad in same_line_upper for bad in ['QUADRO', 'FIGURA', 'TABELA', 'TEXTO', 'PÁGINA', 'PAGINA', 'ART.', 'ARTIGO', 'QUESTÕES DE', 'QUESTOES DE']):
                continue

        candidates.append((m.start(), m.end(), q_num, is_explicit))

    # Identifica limites de disciplinas para permitir reinício de cadeia em Q1
    subject_boundary_positions = [m.start() for m in SUBJECT_REGEX.finditer(full_text)]

    # Algoritmo de Encadeamento Ótimo por Programação Dinâmica (favorece sequência contínua)
    if candidates:
        n = len(candidates)
        dp = [1] * n
        prev = [-1] * n

        for i in range(n):
            min_j = max(0, i - 100)
            for j in range(min_j, i):
                diff = candidates[i][2] - candidates[j][2]
                dist = max(0, candidates[i][0] - candidates[j][1])
                dist_penalty = 30 if dist > 20000 else (15 if dist > 10000 else (5 if dist > 5000 else 0))

                crosses_section = any(b >= candidates[j][1] and b <= candidates[i][0] for b in subject_boundary_positions)

                if diff == 1:
                    step_score = 1000 + (200 if candidates[i][3] else 0) + (200 if candidates[j][3] else 0) - dist_penalty
                elif 2 <= diff <= 10:
                    step_score = (200 - diff * 15) + (50 if candidates[i][3] else 0) - dist_penalty
                elif crosses_section and candidates[i][2] == 1:
                    step_score = 800 + (200 if candidates[i][3] else 0) - dist_penalty
                else:
                    continue

                if dp[j] + step_score > dp[i]:
                    dp[i] = dp[j] + step_score
                    prev[i] = j

        best_idx = max(range(n), key=lambda idx: dp[idx])
        curr = best_idx
        while curr != -1:
            py_found_positions.append((candidates[curr][2], candidates[curr][0], candidates[curr][1]))
            curr = prev[curr]
        py_found_positions.reverse()

    # Mapeamento de candidatos únicos por número de questão
    unique_candidates_by_num = {}
    all_header_spans = []
    for c in candidates:
        all_header_spans.append((c[0], c[1], c[2]))
        q_n = c[2]
        is_exp = c[3]
        if q_n not in unique_candidates_by_num or is_exp:
            unique_candidates_by_num[q_n] = (c[0], c[1])

    all_header_spans.sort(key=lambda x: x[0])

    if len(py_found_positions) >= 5:
        found_positions = py_found_positions
    elif rust_headers and len(rust_headers) >= 5:
        found_positions = [(item['number'], item['start'], item['end']) for item in rust_headers]
    elif unique_candidates_by_num:
        found_positions = []
        max_q = max(unique_candidates_by_num.keys())
        for q_idx in range(1, max_q + 1):
            if q_idx in unique_candidates_by_num:
                s_p, e_p = unique_candidates_by_num[q_idx]
                found_positions.append((q_idx, s_p, e_p))
    else:
        found_positions = py_found_positions

    # Fallback caso a cadeia DP não tenha identificado posições suficientes
    if not found_positions:
        for m in header_pat.finditer(full_text):
            q_str = m.group(1) or m.group(2) or m.group(3) or m.group(4)
            if q_str and 1 <= int(q_str) <= 200:
                found_positions.append((int(q_str), m.start(), m.end()))

    # 6. Mapeia textos de apoio compartilhados com base nas posições exatas das questões
    context_blocks = extract_context_blocks(full_text, found_positions)
    numbered_context_blocks = _extract_numbered_source_context_blocks(
        full_text,
        found_positions,
    )
    for numbered_context in numbered_context_blocks:
        if not any(
            numbered_context[0] == existing[0]
            and numbered_context[1] == existing[1]
            and numbered_context[3] == existing[3]
            for existing in context_blocks
        ):
            context_blocks.append(numbered_context)

    # 7. Estruturação das Questões, Alternativas e Fórmulas
    questions = []
    current_subject = 'Geral'

    for i, (q_num, start_pos, end_pos) in enumerate(found_positions):
        next_start = found_positions[i+1][1] if i + 1 < len(found_positions) else len(full_text)
        
        # Trunca o chunk se houver um banner de texto de apoio antes da próxima questão
        for _, _, _, banner_start in context_blocks:
            if end_pos < banner_start < next_start:
                next_start = banner_start
                break

        chunk = full_text[end_pos:next_start].strip()

        # Disciplina no prelúdio
        prev_end = found_positions[i-1][2] if i > 0 else 0
        prelude = full_text[prev_end:start_pos].strip()
        if prelude:
            for pline in prelude.split('\n'):
                pline_clean = pline.strip()
                if SUBJECT_REGEX.match(pline_clean):
                    current_subject = _format_subject_title(pline_clean)

        # Disciplina na primeira linha da questão
        lines = chunk.split('\n')
        if lines:
            first_line = lines[0].strip()
            if SUBJECT_REGEX.match(first_line):
                current_subject = _format_subject_title(first_line)
                chunk = '\n'.join(lines[1:]).strip()
            elif len(lines) > 1 and SUBJECT_REGEX.match(lines[1].strip()):
                current_subject = _format_subject_title(lines[1].strip())
                chunk = '\n'.join([lines[0]] + lines[2:]).strip()

        # Extração de Gabarito Embutido no corpo da questão (ex: "(Correta: C)" ou "(Gabarito: B)")
        embedded_ans = None
        m_emb = re.search(r'\(?\s*(?:Correta|Gabarito|Resposta|Gabarito\s*Oficial)\s*[:=-]?\s*([A-Ea-eXNxn\*]|CERTO|ERRADO|C|E)\s*\)?', chunk, re.IGNORECASE)
        if m_emb:
            embedded_ans = m_emb.group(1).upper()
            if embedded_ans == 'CERTO':
                embedded_ans = 'C'
            elif embedded_ans == 'ERRADO':
                embedded_ans = 'E'

        # Limpeza de cabeçalhos institucionais repetidos e gabarito embutido do chunk
        chunk = clean_text_artifacts(chunk)

        # Extração de alternativas estruturadas (A, B, C, D, E)
        pattern_primary = re.compile(
            r'(?:^|\n|\s+)'
            r'(?:'
            r'([A-Ea-e])\s*\(\s*\)|'                   # A ( ) ou A ()
            r'\(?\s*([A-Ea-e])\s*\)?\s*[\.\-\–\—\:\)]|' # A. ou A) ou A: ou (A).
            r'\(([A-Ea-e])\)|'                          # (A)
            r'\[([A-Ea-e])\]'                           # [A]
            r')\s*'
        )
        matches = list(pattern_primary.finditer(chunk))

        def find_valid_sequence(match_list, chunk_length):
            if not match_list or len(match_list) < 2:
                return None
            valid_sequences = []
            start_indices = [idx for idx, m in enumerate(match_list) if (m.group(1) or m.group(2) or m.group(3) or m.group(4) or '').upper() == 'A']
            for s_idx in start_indices:
                seq = [match_list[s_idx]]
                expected_ord = ord('B')
                for next_m in match_list[s_idx + 1:]:
                    letter = (next_m.group(1) or next_m.group(2) or next_m.group(3) or next_m.group(4) or '').upper()
                    if ord(letter) == expected_ord:
                        seq.append(next_m)
                        expected_ord += 1
                        if expected_ord > ord('E'):
                            break
                    elif ord(letter) < expected_ord:
                        continue
                if len(seq) >= 2:
                    # Pontuação: 5 opções > 4 opções > 3 opções > 2 opções; e posições finais no chunk têm preferência sobre subitens iniciais
                    score = len(seq) * 1000 + (seq[0].start() / max(1, chunk_length)) * 100
                    valid_sequences.append((score, seq))
            if not valid_sequences:
                return None
            valid_sequences.sort(key=lambda x: x[0], reverse=True)
            return valid_sequences[0][1]

        valid_seq = find_valid_sequence(matches, len(chunk))

        if not valid_seq:
            pattern_newline_letter = re.compile(r'(?:^|\n)\s*([A-Ea-e])\s*(?:\n|\s{2,})')
            matches_nl = list(pattern_newline_letter.finditer(chunk))
            valid_seq = find_valid_sequence(matches_nl, len(chunk))

        options = {}
        is_certo_errado = False

        if valid_seq and len(valid_seq) >= 2:
            first_opt_idx = valid_seq[0].start()
            raw_enunciado = chunk[:first_opt_idx].strip()

            for o_idx, om in enumerate(valid_seq):
                letter = (om.group(1) or om.group(2) or om.group(3) or om.group(4) or om.group(0).strip()[0]).upper()
                s_val = om.end()
                e_val = valid_seq[o_idx + 1].start() if o_idx + 1 < len(valid_seq) else len(chunk)
                opt_content = chunk[s_val:e_val].strip()
                opt_content = re.sub(r'^[A-Ea-e]\s*[\(\[]\s*[\)\]]\s*', '', opt_content)
                opt_content = re.sub(r'^\(?[A-Ea-e]\s*[\)\.\-–—:]\s*', '', opt_content)
                opt_content = re.sub(r'^\(\s*\)\s*', '', opt_content)
                opt_content = clean_text_artifacts(opt_content)
                if o_idx == len(valid_seq) - 1:
                    # Remove cabeçalho de disciplina colado no final da última alternativa (ex: '4-C <u>Conhecimentos Específicos</u>')
                    opt_lines = opt_content.splitlines()
                    while opt_lines and SUBJECT_REGEX.match(opt_lines[-1].strip()):
                        opt_lines.pop()
                    opt_content = '\n'.join(opt_lines).strip()
                    opt_content = re.sub(r'\s*(?:<[^\s>]+>|\*{1,3}|_{1,3})+\s*(?:Conhecimentos\s+Espec[íi\ufffd\?]?ficos|Conhecimentos\s+Gerais|Conhecimentos\s+B[áa\ufffd\?]?sicos|L[íi\ufffd\?]?ngua\s+Portuguesa|Portugu[êe]s|Matem[áa]tica|No[çc\ufffd\?][õo\ufffd\?]?es\s+de\s+[^\n<]+|Racioc[íi\ufffd\?]?nio\s+L[óo\ufffd\?]?gico[^\n<]*|Legisla[çc\ufffd\?][ãa\ufffd\?]?o\s+Espec[íi\ufffd\?]?fica|Inform[áa\ufffd\?]?tica|Direito\s+[^\n<]+|TEXTO:\s*[^\n<]+)(?:<[^\s>]+>|\*{1,3}|_{1,3})+\s*$', '', opt_content, flags=re.IGNORECASE)
                opt_content = restore_exam_typography(opt_content, is_option=True)
                formatted_opt, _ = format_latex_formulas(opt_content)
                options[letter] = formatted_opt

            enunciado = clean_text_artifacts(raw_enunciado)
        else:
            # Fallback 1: Heurística para OCR degradado / símbolos de checkbox no lugar de A..E
            h_opts, h_enunciado = extract_heuristic_options(chunk)
            if h_opts:
                options = h_opts
                enunciado = clean_text_artifacts(h_enunciado)
            else:
                # Fallback 2: Detecta estilo CEBRASPE / Assertiva Certo ou Errado
                chunk_clean = clean_text_artifacts(chunk)
                is_certo_errado = True
                options = {'C': 'Certo', 'E': 'Errado'}
                enunciado = chunk_clean

        # Fórmulas KaTeX no enunciado
        formatted_enunciado, has_latex_enunciado = format_latex_formulas(enunciado)

        # Injeção de Texto de Apoio Compartilhado
        matching_context = None
        for q_min, q_max, ctx_text, _ in context_blocks:
            if q_min <= q_num <= q_max:
                matching_context = (q_min, q_max, ctx_text)
                break

        if matching_context:
            q_min, q_max, ctx_text = matching_context
            preserve_native_word_boundaries = "@@P" in str(ctx_text or "")
            cleaned_ctx = _prepare_numbered_source_context(
                ctx_text,
                preserve_native_word_boundaries=preserve_native_word_boundaries,
            )
            if cleaned_ctx[:30] not in formatted_enunciado:
                formatted_enunciado = f"📖 **Texto de Apoio (Questões {q_min} a {q_max}):**\n\n{cleaned_ctx}\n\n---\n\n{formatted_enunciado}"

        # Restauração Tipográfica e de Parágrafos Editorial
        formatted_enunciado = restore_exam_typography(
            formatted_enunciado,
            preserve_native_word_boundaries=bool(
                matching_context and "@@P" in str(matching_context[2] or "")
            ),
        )
        formatted_enunciado = format_markdown_tables_in_text(formatted_enunciado)
        formatted_enunciado = _unprotect_source_paragraph_markers(formatted_enunciado)

        # Determinação da Resposta Oficial
        final_answer = normalize_answer_or_empty(
            master_gabarito.get(q_num) or embedded_ans
        )

        # Recupera as coordenadas espaciais da questão
        approx_page, q_x, q_y = q_spatial_map.get(q_num, (start_page, 0.0, 0.0))

        # Determinação da Disciplina (Banner de Seção ou Classificador Semântico Rust)
        question_subject = current_subject
        if question_subject == 'Geral' or not question_subject:
            inferred = rust_classify_subject(enunciado)
            if inferred:
                question_subject = inferred

        questions.append({
            'numero_questao': str(q_num),
            'enunciado': formatted_enunciado,
            'opcoes': options,
            'resposta': final_answer,
            'has_embedded_answer': bool(master_gabarito.get(q_num) or embedded_ans),
            'disciplina': question_subject,
            'images': None,
            'latex_support': 1 if has_latex_enunciado else 0,
            'question_index': i,
            '_page': approx_page,
            '_x': q_x,
            '_y': q_y
        })

    if quality_gate_required:
        from .media.scan_pipeline import assess_question_text_integrity

        text_quality = assess_question_text_integrity(
            questions,
            native_text=document_native_text,
            minimum_options=2,
        )
        if text_quality["questions_with_text_integrity"] != len(questions):
            print(
                "[Vision OCR] Gate de integridade não aprovado "
                f"({text_quality['questions_with_text_integrity']}/"
                f"{len(questions)} questões): "
                f"{text_quality['text_integrity_issues']}",
                flush=True,
            )
            timing.finish(pages=total_pages, questions=0)
            doc.close()
            return []
        print(
            f"[Vision OCR] Integridade textual aprovada: "
            f"{text_quality['questions_with_text_integrity']}/"
            f"{len(questions)} (100%).",
            flush=True,
        )

    # 8. Anexamento Espacial em 2 Fases (Trigger Word + Gap Visual Scan)
    if extract_images and page_diagrams:
        questions = image_extractor.attach_images_to_questions(
            doc=doc,
            questions=questions,
            page_diagrams=page_diagrams,
            exam_id=exam_id or 0
        )
    for question in questions:
        question["enunciado"] = strip_embedded_answer_marker(
            question.get("enunciado", "")
        )
        _repair_image_only_option_question(question)

    # 9. Propagação de imagens de textos de apoio para todas as questões do bloco compartilhado
    for q_min, q_max, _, _ in context_blocks:
        shared_imgs = []
        for q in questions:
            num_int = int(q.get('numero_questao', 0)) if str(q.get('numero_questao', '')).isdigit() else 0
            if q_min <= num_int <= q_max and q.get('images'):
                for img in q['images']:
                    if img not in shared_imgs:
                        shared_imgs.append(img)
        if shared_imgs:
            for q in questions:
                num_int = int(q.get('numero_questao', 0)) if str(q.get('numero_questao', '')).isdigit() else 0
                if q_min <= num_int <= q_max:
                    q['images'] = list(shared_imgs)

    # Limpeza de atributos internos temporários
    for q in questions:
        q.pop('_page', None)
        q.pop('_x', None)
        q.pop('_y', None)

    # Ordenação canônica e sequencial pelo número da questão (1..N)
    def _q_sort_key(q):
        raw = str(q.get('numero_questao', '')).strip()
        if raw.isdigit():
            return (0, int(raw))
        m = re.match(r'^(\d+)', raw)
        if m:
            return (0, int(m.group(1)))
        return (1, 99999)
    
    questions.sort(key=_q_sort_key)

    timing.mark("question_structuring_and_image_linking")
    save_parse_cache(cache_key, questions, pages=total_pages)
    timing.mark("parse_cache_store")
    timing.finish(pages=total_pages, questions=len(questions))
    doc.close()
    return questions
