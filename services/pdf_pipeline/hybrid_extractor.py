import os
import re
import io
import fitz
from typing import List, Dict, Any, Optional, Tuple, Set

from .layout.layout_detector import (
    detect_watermarks,
    detect_layout_and_ordered_blocks,
    extract_context_blocks,
    is_instruction_or_cover_page,
)
from .media.diagram_cropper import (
    ExamImageExtractor,
)
from .formatters.formula_formatter import format_latex_formulas
from .fallbacks.subject_classifier import SUBJECT_REGEX, format_subject_title, _format_subject_title, rust_classify_subject
from services.gabarito.gabarito_service import extract_gabarito_from_doc, _extract_gabarito_from_doc
from services.crawlers.html_exam_parser import clean_text_artifacts
from .native.rust_bridge import rust_scan_question_headers, rust_process_exam_text, is_rust_available
from .formatters.banca_clusterizer import detect_banca_family, get_specialized_patterns, BancaFamily
from .fallbacks.typography_restorer import restore_exam_typography

def extract_heuristic_options(chunk: str) -> Tuple[Optional[Dict[str, str]], str]:
    """
    Quando as alternativas não possuem letras (A), (B), (C), (D) explícitas
    porque o scanner da banca transformou as letras em símbolos (@, §, (â, 6) ou removeu,
    detecta as 4 ou 5 opções verticais finais e atribui A, B, C, D, E.
    """
    if not chunk or len(chunk.strip()) < 20:
        return None, chunk

    lines = [l.strip() for l in chunk.split('\n') if l.strip()]
    
    # Se temos poucas linhas separadas por newline, tenta quebrar por períodos após o comando da questão
    if len(lines) < 4:
        # Tenta isolar o comando (ex: "assinale a alternativa correta:")
        m_cmd = re.search(r'(?:assinale|marque|indique|identifique|correto|incorreto|podemos\s+afirmar|conclui-se|qual\s+alternativa)[^\.\:\?]*[\.\:\?]\s*', chunk, re.IGNORECASE)
        if m_cmd:
            cmd_end = m_cmd.end()
            enunc_part = chunk[:cmd_end].strip()
            rest_part = chunk[cmd_end:].strip()
            sub_lines = [l.strip() for l in re.split(r'(?:\n+|\.(?=\s+[A-Z\u00C0-\u00DC]))', rest_part) if l.strip()]
            if len(sub_lines) in [4, 5]:
                lines = [enunc_part] + sub_lines

    if len(lines) < 4:
        return None, chunk

    cleaned_lines = []
    for l in lines:
        c = re.sub(r'^(?:[\@\§\©\®\•\*\#\(\[\{]{1,3}[A-Za-z0-9\s]*[\)\]\}]?|[A-Za-z]\s*[\.\,\)]|[\(]?\s*[\â\ã\ä\ö\ü\ç\§\©\®\d]\s*[\)]?)\s*', '', l).strip()
        cleaned_lines.append(c if c else l)

    for num_opts in [5, 4]:
        if len(cleaned_lines) >= num_opts + 1:
            candidate_opts = cleaned_lines[-num_opts:]
            candidate_enunciado = '\n'.join(lines[:-num_opts]).strip()

            if all(len(opt) >= 1 for opt in candidate_opts) and len(candidate_enunciado) >= 15:
                letters = ['A', 'B', 'C', 'D', 'E'][:num_opts]
                options_dict = {}
                for idx, opt_txt in enumerate(candidate_opts):
                    opt_clean = restore_exam_typography(opt_txt, is_option=True)
                    formatted_opt, _ = format_latex_formulas(opt_clean)
                    options_dict[letters[idx]] = formatted_opt
                return options_dict, candidate_enunciado

    return None, chunk

def parse_exam_document(
    pdf_bytes_or_path: Any,
    exam_id: Optional[int] = None,
    extract_images: bool = True,
    gabarito_override: Optional[str] = None,
    force_ocr: bool = False
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
        from services.gabarito.gabarito_service import parse_gabarito_from_text
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

        ordered_blocks = detect_layout_and_ordered_blocks(page, watermarks, force_ocr=force_ocr)
        for b in ordered_blocks:
            raw_blocks.append(b['text'])

        if extract_images:
            clusters = image_extractor.find_diagram_clusters(page, watermarks, text_blocks=page_raw_blocks)
            if clusters:
                page_diagrams[p_idx] = clusters

    full_text = '\n\n'.join(raw_blocks)
    if len(full_text.strip()) < 500 or force_ocr:
        from .media.vision_pipeline import extract_exam_via_vision_ocr
        ocr_text = extract_exam_via_vision_ocr(doc, dpi=200, watermarks=watermarks)
        if len(ocr_text.strip()) > len(full_text.strip()):
            full_text = ocr_text

    if len(full_text.strip()) < 50:
        doc.close()
        return []

    # 4.1 Normalização resiliente de cabeçalhos gerados por OCR degradado
    full_text = re.sub(r'(?:\b|(?<=[\s\n]))(\d{1,3})\s*[\,\"\']+[ \t]*(?=[\.\,\:\'\`\~\s]*[A-Za-z\u00C0-\u00DC\"\'\(\[])', r'\n\1. ', full_text)
    full_text = re.sub(r'(?:\b|(?<=[\s\n]))[íI!|](\d)\s*[\.\,\:\-\"\']+[ \t]*(?=[\.\,\:\'\`\~\s]*[A-Za-z\u00C0-\u00DC\"\'\(\[])', r'\n1\1. ', full_text)
    full_text = re.sub(r'(?:\b|(?<=[\s\n]))3[üuU]\s*[\.\,\:\-\"\']+[ \t]*(?=[\.\,\:\'\`\~\s]*[A-Za-z\u00C0-\u00DC\"\'\(\[])', r'\n30. ', full_text)
    full_text = re.sub(r'(?:\b|(?<=[\s\n]))[íI!|]0\s*[\.\,\:\-\"\']+[ \t]*(?=[\.\,\:\'\`\~\s]*[A-Za-z\u00C0-\u00DC\"\'\(\[])', r'\n10. ', full_text)
    full_text = re.sub(r'(?m)^[ \t]*1\.\s+(?=A\s*pesar|A\s*rea|A\s*ssegurar|Pagou|Um\s+professor)', 'I. ', full_text)
    full_text = re.sub(r'(?m)^([ \t]*\d{1,2}\.)([^\s\d])', r'\1 \2', full_text)

    # 5. Execução Unificada em Rust (Zero Ping-Pong) com Fallback Resiliente
    rust_questions = rust_process_exam_text(full_text)
    if rust_questions and len(rust_questions) >= 3:
        questions = []
        for rq in rust_questions:
            q_num = int(rq['numero_questao'])
            formatted_enunciado = rq['enunciado']
            formatted_enunciado, has_latex_enunciado = format_latex_formulas(formatted_enunciado)
            formatted_enunciado = restore_exam_typography(formatted_enunciado)
            
            raw_options = rq.get('opcoes', {})
            options = {}
            for let, opt_text in raw_options.items():
                opt_clean = restore_exam_typography(opt_text, is_option=True)
                opt_formatted, _ = format_latex_formulas(opt_clean)
                options[let] = opt_formatted

            final_answer = master_gabarito.get(q_num) or rq.get('resposta', 'A')
            approx_page, q_x, q_y = q_spatial_map.get(q_num, (start_page, 0.0, 0.0))
            
            questions.append({
                'numero_questao': str(q_num),
                'enunciado': formatted_enunciado,
                'opcoes': options,
                'resposta': final_answer,
                'disciplina': rq.get('disciplina', 'Geral'),
                'images': None,
                'latex_support': 1 if has_latex_enunciado else 0,
                '_page': approx_page,
                '_x': q_x,
                '_y': q_y
            })
        
        # Anexamento espacial de imagens/diagramas em 2 fases
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

    # 6. Scanner Global de Cabeçalhos de Questões (Fallback Python)
    rust_headers = rust_scan_question_headers(full_text)
    found_positions = []

    header_pat = re.compile(
        r'(?i)(?:^|\n|\.\s+|\s{2,})(?:(?:QUEST[AÃ\?]?O\s+|ITEM\s+)(0*\d{1,3})[ \t]*(?:[\.\-–—:\)]|\n+|[ \t]+)|(0*\d{1,3})[ \t]*(?:[\.\-–—:\)]|\n+|\t+|[ \t]+(?=[A-Za-z\u00C0-\u00DC\"\'\(\[]))[ \t]*|\((0*\d{1,3})\)[ \t]+|(?<=\n)\s*(0*\d{1,3})\s*(?=\n|\t))'
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

                if diff == 1:
                    step_score = 1000 + (200 if candidates[i][3] else 0) + (200 if candidates[j][3] else 0) - dist_penalty
                elif 2 <= diff <= 10:
                    step_score = (200 - diff * 15) + (50 if candidates[i][3] else 0) - dist_penalty
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
                opt_content = re.sub(r'^\(\s*\)\s*', '', opt_content)
                opt_content = clean_text_artifacts(opt_content)
                if o_idx == len(valid_seq) - 1:
                    # Remove cabeçalho de disciplina colado no final da última alternativa (ex: '4-C Conhecimentos Específicos')
                    opt_content = re.sub(r'\s*(?:Conhecimentos\s+Espec[íi\ufffd\?]?ficos|Conhecimentos\s+Gerais|L[íi\ufffd\?]?ngua\s+Portuguesa|No[çc\ufffd\?][õo\ufffd\?]?es\s+de\s+[^\n]+|Racioc[íi\ufffd\?]?nio\s+L[óo\ufffd\?]?gico[^\n]*)\s*$', '', opt_content, flags=re.IGNORECASE)
                    opt_lines = opt_content.splitlines()
                    while opt_lines and SUBJECT_REGEX.match(opt_lines[-1].strip()):
                        opt_lines.pop()
                    opt_content = '\n'.join(opt_lines).strip()
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

        # Determinação da Resposta Oficial
        final_answer = master_gabarito.get(q_num) or embedded_ans
        if not final_answer:
            final_answer = 'C' if is_certo_errado else 'A'

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
            'disciplina': question_subject,
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

    doc.close()
    return questions
