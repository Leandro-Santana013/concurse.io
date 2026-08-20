import os
import re
import io
import fitz
from typing import List, Dict, Any, Optional, Tuple, Set

from .layout_detector import (
    detect_watermarks,
    detect_layout_and_ordered_blocks,
    extract_context_blocks,
    is_instruction_or_cover_page,
)
from .diagram_cropper import (
    ExamImageExtractor,
    find_diagram_clusters,
    extract_and_crop_diagrams,
    IMAGE_TRIGGER_REGEX,
    CAPTION_REGEX,
)
from .formula_formatter import format_latex_formulas
from .subject_classifier import SUBJECT_REGEX, format_subject_title, _format_subject_title
from services.gabarito_service import extract_gabarito_from_doc, _extract_gabarito_from_doc
from services.html_exam_parser import clean_text_artifacts

def parse_exam_document(
    pdf_bytes_or_path: Any,
    exam_id: Optional[int] = None,
    extract_images: bool = True,
    gabarito_override: Optional[str] = None
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
    if isinstance(pdf_bytes_or_path, (bytes, bytearray)):
        doc = fitz.open(stream=pdf_bytes_or_path, filetype='pdf')
    else:
        doc = fitz.open(pdf_bytes_or_path)

    total_pages = len(doc)
    if total_pages == 0:
        return []

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
        from services.gabarito_service import parse_gabarito_from_text
        master_gabarito = parse_gabarito_from_text(gabarito_override)
    if not master_gabarito:
        master_gabarito = _extract_gabarito_from_doc(doc)

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

    # 4. Extração dos blocos ordenados por coluna e clusters de diagramas
    raw_blocks = []
    page_diagrams = {}
    q_spatial_map: Dict[int, Tuple[int, float, float]] = {}

    header_search_pat = re.compile(
        r'(?:^|\n)\s*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)?(0*\d{1,3})\s*(?:[\.\-\–\—\:\)]|\s+)',
        re.IGNORECASE
    )

    for p_idx in range(start_page, total_pages):
        page = doc[p_idx]
        p_text = page.get_text()
        
        # Ignora última página se for exclusivamente tabela de gabarito sem enunciado
        if p_idx >= max(1, total_pages - 2) and re.search(r'\b(gabarito|folha\s+de\s+respostas?)\b', p_text, re.IGNORECASE):
            if not re.search(r'\b[A-E]\)\s+[A-Z\u00C0-\u00DC]', p_text):
                continue

        # Mapeia coordenadas físicas dos cabeçalhos na página para anexamento espacial exato
        page_raw_blocks = page.get_text('blocks')
        for b in page_raw_blocks:
            bx0, by0, bx1, by1, b_text = b[:5]
            for hm in header_search_pat.finditer(b_text):
                try:
                    num_val = int(hm.group(1))
                    if 1 <= num_val <= 200 and num_val not in q_spatial_map:
                        q_spatial_map[num_val] = (p_idx, bx0, by0)
                except ValueError:
                    pass

        ordered_blocks = detect_layout_and_ordered_blocks(page, watermarks)
        for b in ordered_blocks:
            raw_blocks.append(b['text'])

        if extract_images:
            clusters = image_extractor.find_diagram_clusters(page, watermarks, text_blocks=page_raw_blocks)
            if clusters:
                page_diagrams[p_idx] = clusters

    full_text = '\n\n'.join(raw_blocks)
    if len(full_text.strip()) < 50:
        doc.close()
        return []

    # 5. Mapeia textos de apoio compartilhados
    context_blocks = extract_context_blocks(full_text)

    # 6. Scanner Global de Cabeçalhos de Questões (Duas Fases: Detecção + DP Chain)
    header_pat = re.compile(
        r'(?:^|\n)\s*'
        r'(?:'
        r'(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)(0*\d{1,3})\s*(?:[\.\-\–\—\:\)]|\n+|\s+(?=[A-Z\u00C0-\u00DC\"“\'‘\(]))|'
        r'(0*\d{1,3})\s*[\.\-\–\—\:\)]\s*(?=[A-Z\u00C0-\u00DC\"“\'‘\(])|'
        r'\((0*\d{1,3})\)\s*(?=[A-Z\u00C0-\u00DC\"“\'‘\(])|'
        r'(0*\d{1,3})\s*(?:\n+|\s+)(?=[A-Z\u00C0-\u00DC\"“\'‘\(])'
        r')',
        re.IGNORECASE
    )

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

        preview = full_text[m.end():m.end() + 150].upper()
        if any(bad in preview for bad in ['RECEBEU DO FISCAL', 'CARTÃO-RESPOSTA', 'PREENCHA O CART', 'TEMPO DISPONÍVEL']):
            continue

        is_explicit = bool(m.group(1))
        candidates.append((m.start(), m.end(), q_num, is_explicit))

    # Algoritmo de Encadeamento Ótimo por Programação Dinâmica
    found_positions = []
    if candidates:
        n = len(candidates)
        dp = [1] * n
        prev = [-1] * n

        for i in range(n):
            for j in range(i):
                diff = candidates[i][2] - candidates[j][2]
                if 1 <= diff <= 4:
                    step_score = (10 if diff == 1 else (5 if diff == 2 else 2)) + (3 if candidates[i][3] else 0)
                    if dp[j] + step_score > dp[i]:
                        dp[i] = dp[j] + step_score
                        prev[i] = j

        best_idx = max(range(n), key=lambda idx: dp[idx])
        curr = best_idx
        while curr != -1:
            found_positions.append((candidates[curr][2], candidates[curr][0], candidates[curr][1]))
            curr = prev[curr]
        found_positions.reverse()

    # Fallback caso a cadeia DP não tenha identificado posições suficientes
    if not found_positions:
        for m in header_pat.finditer(full_text):
            q_str = m.group(1) or m.group(2) or m.group(3) or m.group(4)
            if q_str and 1 <= int(q_str) <= 200:
                found_positions.append((int(q_str), m.start(), m.end()))

    # 7. Estruturação das Questões, Alternativas e Fórmulas
    questions = []
    current_subject = 'Geral'

    for i, (q_num, start_pos, end_pos) in enumerate(found_positions):
        next_start = found_positions[i+1][1] if i+1 < len(found_positions) else len(full_text)
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

        def find_valid_sequence(match_list):
            if not match_list or len(match_list) < 2:
                return None
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
                if len(seq) >= 3:
                    return seq
            return None

        valid_seq = find_valid_sequence(matches)

        if not valid_seq:
            pattern_newline_letter = re.compile(r'(?:^|\n)\s*([A-Ea-e])\s*(?:\n|\s{2,})')
            matches_nl = list(pattern_newline_letter.finditer(chunk))
            valid_seq = find_valid_sequence(matches_nl)

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
                opt_content = re.sub(r'^\(\s*\)\s*', '', opt_content)
                opt_content = clean_text_artifacts(opt_content)
                formatted_opt, _ = format_latex_formulas(opt_content)
                options[letter] = formatted_opt

            enunciado = clean_text_artifacts(raw_enunciado)
        else:
            # Detecta estilo CEBRASPE / Assertiva Certo ou Errado
            chunk_clean = clean_text_artifacts(chunk)
            is_certo_errado = True
            options = {'C': 'Certo', 'E': 'Errado'}
            enunciado = chunk_clean

        # Fórmulas KaTeX no enunciado
        formatted_enunciado, has_latex_enunciado = format_latex_formulas(enunciado)

        # Injeção de Texto de Apoio Compartilhado
        matching_context = None
        for q_min, q_max, ctx_text in context_blocks:
            if q_min <= q_num <= q_max:
                matching_context = (q_min, q_max, ctx_text)
                break

        if matching_context:
            q_min, q_max, ctx_text = matching_context
            if ctx_text[:40] not in formatted_enunciado:
                formatted_enunciado = f"📖 **Texto de Apoio (Questões {q_min} a {q_max}):**\n\n{ctx_text}\n\n---\n\n{formatted_enunciado}"

        # Determinação da Resposta Oficial
        final_answer = master_gabarito.get(q_num) or embedded_ans
        if not final_answer:
            final_answer = 'C' if is_certo_errado else 'A'

        # Recupera as coordenadas espaciais da questão
        approx_page, q_x, q_y = q_spatial_map.get(q_num, (start_page, 0.0, 0.0))

        questions.append({
            'numero_questao': str(q_num),
            'enunciado': formatted_enunciado,
            'opcoes': options,
            'resposta': final_answer,
            'disciplina': current_subject,
            'images': None,
            'latex_support': 1 if has_latex_enunciado else 0,
            '_page': approx_page,
            '_x': q_x,
            '_y': q_y
        })

    # 8. Anexamento Espacial em 2 Fases (Trigger Word + Gap Visual Scan)
    if extract_images and page_diagrams:
        questions = image_extractor.attach_images_to_questions(
            doc=doc,
            questions=questions,
            page_diagrams=page_diagrams,
            exam_id=exam_id or 0
        )

    # Limpeza de atributos internos temporários
    for q in questions:
        q.pop('_page', None)
        q.pop('_x', None)
        q.pop('_y', None)

    doc.close()
    return questions
