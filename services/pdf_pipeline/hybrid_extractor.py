import os
import re
import io
import math
import hashlib
import json
import time
import fitz
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


_NATIVE_QUESTION_HEADER_RE = re.compile(
    r"(?im)^\s*(?:(?:quest(?:[ãa]o|ao)|item)\s*)?"
    # Scans antigos às vezes convertem o ponto de ``19.`` em aspas.
    r"0*(\d{1,3})\s*[\.\)\-–—,:\"'](?=\s|$)"
)
_NATIVE_OPTION_MARKER_RE = re.compile(
    r"(?im)^\s*(?:\(?[A-Ea-e]\s*\)|[A-Ea-e]\s*[\.\-:])\s+"
)
_DECLARED_QUESTION_COUNT_PATTERNS = (
    re.compile(
        r"(?i)\b(?:composto|cont[eé]m|contendo|total(?:iza|de)?)"
        r"\D{0,30}(\d{1,3})\s+quest(?:[õo]es|oes)\b"
    ),
    re.compile(r"(?i)\b(\d{1,3})\s+quest(?:[õo]es|oes)\b"),
)


def _native_question_numbers(text: str) -> List[int]:
    """Retorna os rótulos numéricos que parecem cabeçalhos de questões."""
    numbers = {
        int(match.group(1))
        for match in _NATIVE_QUESTION_HEADER_RE.finditer(str(text or ""))
        if 1 <= int(match.group(1)) <= 250
    }
    return sorted(numbers)


def _declared_question_count(text: str) -> Optional[int]:
    """Encontra uma quantidade de questões declarada no caderno/capa."""
    candidates = []
    source = str(text or "")
    for pattern in _DECLARED_QUESTION_COUNT_PATTERNS:
        candidates.extend(int(match.group(1)) for match in pattern.finditer(source))
    plausible = [value for value in candidates if 5 <= value <= 250]
    return max(plausible) if plausible else None


def _assess_native_text_quality(
    full_text: str,
    *,
    document_text: str = "",
    total_pages: int = 1,
    image_page_count: int = 0,
    total_image_count: int = 0,
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
    option_marker_count = len(_NATIVE_OPTION_MARKER_RE.findall(text))
    replacement_count = text.count("\ufffd")
    mojibake_count = len(
        re.findall(r"(?:Ã[\x80-\xbf]|Â[\x80-\xbf]|â(?:[\x80-\xbf]|[€™œ]))", text)
    )
    page_count = max(1, int(total_pages or 1))
    image_ratio = float(image_page_count or 0) / page_count
    average_images = float(total_image_count or 0) / page_count
    scan_like = image_ratio >= 0.75 and average_images >= 2.0

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
                match = _NATIVE_QUESTION_HEADER_RE.match(text)
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

def extract_options_from_chunk(chunk: str) -> Tuple[Dict[str, str], Optional[str]]:
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
    matches = []
    for m in pattern_primary.finditer(chunk):
        letter = None
        for g in m.groups():
            if g:
                letter = g.upper()
                break
        if letter:
            matches.append((letter, m.start(), m.end()))

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
        opt_content = clean_text_artifacts(opt_content)
        if o_idx == len(seq) - 1:
            opt_lines = opt_content.splitlines()
            while opt_lines and SUBJECT_REGEX.match(opt_lines[-1].strip()):
                opt_lines.pop()
            opt_content = '\n'.join(opt_lines).strip()
            opt_content = re.sub(r'\s*(?:<[^\s>]+>|\*{1,3}|_{1,3})+\s*(?:Conhecimentos\s+Espec[íi\ufffd\?]?ficos|Conhecimentos\s+Gerais|Conhecimentos\s+B[áa\ufffd\?]?sicos|L[íi\ufffd\?]?ngua\s+Portuguesa|Portugu[êe]s|Matem[áa]tica|No[çc\ufffd\?][õo\ufffd\?]?es\s+de\s+[^\n<]+|Racioc[íi\ufffd\?]?nio\s+L[óo\ufffd\?]?gico[^\n<]*|Legisla[çc\ufffd\?][ãa\ufffd\?]?o\s+Espec[íi\ufffd\?]?fica|Inform[áa\ufffd\?]?tica|Direito\s+[^\n<]+|TEXTO:\s*[^\n<]+)(?:<[^\s>]+>|\*{1,3}|_{1,3})+\s*$', '', opt_content, flags=re.IGNORECASE)
        opt_content = restore_exam_typography(opt_content, is_option=True)
        formatted_opt, _ = format_latex_formulas(opt_content)
        options[letter] = formatted_opt

    short_non_numeric = sum(
        1
        for value in options.values()
        if len(re.sub(r'\s+', '', str(value or ''))) <= 3
        and not re.search(r'\d', str(value or ''))
    )
    if short_non_numeric >= 2:
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
        r'(?i)(?<![A-Za-z0-9])([ivx]+)e(?=\s*[ivx])',
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


def _recover_scan_options_at_high_resolution(
    doc: fitz.Document,
    questions: List[Dict[str, Any]],
    q_spatial_map: Dict[int, Tuple[int, float, float]],
    dpi: int = 400,
) -> None:
    """Recupera alternativas curtas que o OCR padrão confundiu no scan.

    A passada normal é suficiente para a maior parte do caderno. Se uma
    questão ainda tiver uma expressão numérica corrompida, uma lista romana
    ambígua ou quantidade diferente de quatro alternativas, repete somente a
    página correspondente em alta resolução e substitui o mapa apenas quando
    a nova estrutura for claramente melhor.
    """
    from .media.vision_pipeline import _supplement_native_question_headers
    from services.pdf_pipeline.layout.layout_detector import (
        _get_ocr_engine,
        extract_ocr_lines_three_passes,
    )

    roman_confusion_re = re.compile(
        r"(?i)(?<![A-Za-z0-9])(?:i1|il|ill|ivl?|vll|vlll|lx)(?![A-Za-z0-9])"
    )

    def needs_precision(question: Dict[str, Any]) -> bool:
        options = question.get('opcoes') or {}
        if len(options) != 4:
            return True
        for value in options.values():
            text = str(value or '').strip()
            compact = re.sub(r'\s+', '', text)
            if roman_confusion_re.search(text):
                return True
            if (
                len(compact) <= 12
                and re.search(r'\d', text)
                and not re.fullmatch(r'[\d\s.,%()+\-×*/^]+', text)
            ):
                return True
        return False

    targets = {
        int(question.get('numero_questao'))
        for question in questions
        if str(question.get('numero_questao', '')).isdigit()
        and needs_precision(question)
    }
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
    layout_config: Optional[LayoutConfig] = None
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
            allow_ocr_fallback=not bool(scan_profile.get("scan_like")),
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
                m_h = re.search(rf'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)0*{qn}\b', full_text, re.IGNORECASE)
                if m_h:
                    rust_found_positions.append((qn, m_h.start(), m_h.end()))
            except Exception:
                pass
        rust_context_blocks = extract_context_blocks(full_text, rust_found_positions)

        questions = []
        for rq in rust_questions:
            q_num = int(rq['numero_questao'])
            formatted_enunciado = rq['enunciado']

            # Injeção de Texto de Apoio Compartilhado em rust_questions
            matching_context = None
            for q_min, q_max, ctx_text, _ in rust_context_blocks:
                if q_min <= q_num <= q_max:
                    matching_context = (q_min, q_max, ctx_text)
                    break

            if matching_context:
                q_min, q_max, ctx_text = matching_context
                cleaned_ctx = restore_exam_typography(ctx_text)
                if cleaned_ctx[:30] not in formatted_enunciado:
                    formatted_enunciado = f"📖 **Texto de Apoio (Questões {q_min} a {q_max}):**\n\n{cleaned_ctx}\n\n---\n\n{formatted_enunciado}"

            formatted_enunciado, has_latex_enunciado = format_latex_formulas(formatted_enunciado)
            formatted_enunciado = restore_exam_typography(formatted_enunciado)
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
                recovered_opts, clean_stmt = extract_options_from_chunk(chunk_q)
                heuristic_opts, heuristic_stmt = extract_heuristic_options(chunk_q)
                candidates = [
                    (recovered_opts, clean_stmt),
                    (heuristic_opts or {}, heuristic_stmt),
                ]

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
                if native_candidate and native_candidate_score >= 80.0 and has_five_option_candidate:
                    # Em scans de provas com quatro alternativas, a
                    # heurística às vezes cruza o enunciado seguinte e cria
                    # uma quinta opção. Um bloco nativo completo de quatro é
                    # mais confiável nesse caso.
                    selected_opts, selected_stmt = native_candidate
                elif native_candidate and (
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
                    len(selected_opts) >= 4
                    or len(selected_opts) >= len(raw_options)
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
                            cleaned_ctx = restore_exam_typography(ctx_text)
                            if cleaned_ctx[:30] not in formatted_enunciado:
                                formatted_enunciado = f"📖 **Texto de Apoio (Questões {q_min} a {q_max}):**\n\n{cleaned_ctx}\n\n---\n\n{formatted_enunciado}"
                        formatted_enunciado, has_latex_enunciado = format_latex_formulas(formatted_enunciado)
                        formatted_enunciado = restore_exam_typography(formatted_enunciado)
                        formatted_enunciado = format_markdown_tables_in_text(formatted_enunciado)

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
                opt_clean = restore_exam_typography(opt_clean, is_option=True)
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
        
        # Última recuperação direcionada para alternativas curtas de scans.
        # Executa antes do fechamento do documento e antes do vínculo de
        # diagramas, preservando o restante da extração já validada.
        if not native_layer_usable:
            _recover_scan_options_at_high_resolution(
                doc=doc,
                questions=questions,
                q_spatial_map=q_spatial_map,
            )

        # Anexamento espacial de imagens/diagramas em 2 fases
        if extract_images and page_diagrams:
            questions = image_extractor.attach_images_to_questions(
                doc=doc,
                questions=questions,
                page_diagrams=page_diagrams,
                exam_id=exam_id or 0
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
            cleaned_ctx = restore_exam_typography(ctx_text)
            if cleaned_ctx[:30] not in formatted_enunciado:
                formatted_enunciado = f"📖 **Texto de Apoio (Questões {q_min} a {q_max}):**\n\n{cleaned_ctx}\n\n---\n\n{formatted_enunciado}"

        # Restauração Tipográfica e de Parágrafos Editorial
        formatted_enunciado = restore_exam_typography(formatted_enunciado)
        formatted_enunciado = format_markdown_tables_in_text(formatted_enunciado)

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
