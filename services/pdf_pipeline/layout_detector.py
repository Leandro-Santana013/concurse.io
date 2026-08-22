import fitz
import re
from typing import List, Dict, Set, Tuple, Any

CONTEXT_TEXT_HEADER_REGEX = re.compile(
    r'(?:^|\n|\.\s+|\s+)'
    r'('
    r'(?:'
    r'Instru[çc][ãa\ufffd\?]?o\s*[:\.\-]?\s*|'
    r'[Oo]\s+texto\s+(?:a\s+seguir|abaixo|seguinte|1|2|I|II)?\s*(?:servir[aá\ufffd\?]?\s+de\s+base\s+para\s+responder|refere-se|para\s+responder|para)?|'
    r'[Pp]ara\s+(?:responder\s+(?:[àa\ufffd\?]?s\s+)?|as\s+)?quest[oõa\ufffd\?]?es|'
    r'[Ll]eia\s+o\s+texto(?:\s+\d+)?\s*(?:para\s+responder|(?:a\s+seguir|abaixo))?|'
    r'[Aa]s\s+quest[oõa\ufffd\?]?es(?:\s+de)?|'
    r'[Cc]onsidere\s+(?:o\s+texto|a\s+situa[cç][aã\ufffd\?]?o\s+hipot[eé\ufffd\?]?tica|o\s+caso)\s*(?:(?:a\s+seguir|abaixo))?|'
    r'[Cc]om\s+base\s+no\s+texto\s*(?:(?:abaixo|a\s+seguir))?\s*,\s*responda|'
    r'[Tt]exto\s+(?:I|II|III|1|2|3)?\s*(?:\(?[^)]*\))?\s*[-–—:]?\s*(?:para\s+(?:as\s+)?quest[oõa\ufffd\?]?es|base\s+para\s+as\s+quest[oõa\ufffd\?]?es)'
    r')'
    r'[^\.\:]{0,100}?'
    r'quest[oõa\ufffd\?]?es?\s*(?:de\s+n[úu]meros?\s+|de\s+)?(0*\d{1,3})\s*(?:a|e|ao?|at[eé\ufffd\?]?|\be\b|,|\-)\s*(?:a\s+)?(0*\d{1,3})'
    r'[\.\:\–\—]?'
    r')',
    re.IGNORECASE
)

def detect_watermarks(doc: fitz.Document) -> Set[Tuple[int, int, int, int]]:
    """
    Identifica elementos que se repetem na mesma posição em 3 ou mais páginas
    (marcas d'água, rodapés de sites de concursos e cabeçalhos fixos).
    """
    rect_counts = {}
    for page in doc:
        for d in page.get_drawings():
            r = d['rect']
            if r.width < 5 or r.height < 5:
                continue
            key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
            rect_counts[key] = rect_counts.get(key, 0) + 1
            
        for img_info in page.get_images():
            for r in page.get_image_rects(img_info[0]):
                key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
                rect_counts[key] = rect_counts.get(key, 0) + 1

    return {k for k, v in rect_counts.items() if v >= 3}

def clean_marginal_line_numbers(text_str: str) -> str:
    """
    Remove números de linha verticais que são comuns nas margens de textos de apoio
    (ex: '01\n02\n03...' ou '05\n10\n15...'), prevenindo que sejam interpretados como questões.
    """
    lines = text_str.splitlines()
    if len(lines) >= 3:
        digit_lines = [l.strip() for l in lines if l.strip().isdigit() and 1 <= int(l.strip()) <= 150]
        if len(digit_lines) >= 3 and len(digit_lines) >= len(lines) * 0.6:
            return ""
            
    cleaned_lines = []
    for l in lines:
        cleaned_lines.append(re.sub(r'^(?:0\d|\d{2})\s{2,}', '', l))
    return '\n'.join(cleaned_lines)

def is_instruction_or_cover_page(page_text: str) -> bool:
    """Detecta se uma página é capa de prova, folha de rosto ou instruções gerais."""
    clean = re.sub(r'pcimarkpci[^\n]*|www\.pciconcursos\.com\.br|qconcursos\.com', '', page_text, flags=re.IGNORECASE).strip()
    if len(clean) < 80:
        return True
    
    clean_norm = re.sub(r'\s+', ' ', clean).upper()
    clean_norm = re.sub(r'[\ufffd\?]', 'C', clean_norm)
    
    if len(clean) < 600 and ('[DIGITE UMA CITA' in clean_norm or 'FOLHA DE ROSTO' in clean_norm or ('EDITAL DE PROCESSO' in clean_norm and 'QUESTAO' not in clean_norm)):
        return True

    has_instruction_title = bool(re.search(
        r'\b(?:LEIA\s+ATENTAMENTE|INSTRU[ÇC]OES|FOLHA\s+DE\s+INSTRU[ÇC]OES|AVALIA[ÇC]AO\s+ESCRITA\s+OBJETIVA|AVALIA[ÇC]AO\s+OBJETIVA|CADERNO\s+DE\s+PROVA)\b',
        clean_norm
    ))
    
    has_admin_terms = bool(re.search(
        r'\b(?:FISCAL|CART[ÃA]O|CARTAO|GRADE\s+DE\s+RESPOSTAS|FOLHA\s+DE\s+RESPOSTAS|PERTENCES|BOA\s+PROVA|CUMPRA\s+RIGOROSAMENTE|TEMPO\s+DISPON[ÍI]VEL|TEMPO\s+DISPONIVEL|SER[ÁA]\s+ELIMINADO|SERA\s+ELIMINADO|CADERNO\s+DE\s+QUEST[ÕO]ES|CADERNO\s+DE\s+PROVAS|PREENCHA\s+O\s+CART)\b',
        clean_norm
    ))
    
    if has_instruction_title and has_admin_terms:
        if 'QUESTAO 01' in clean_norm or 'QUESTAO 1' in clean_norm:
            if re.search(r'\b[A-E]\)\s+[A-Z\u00C0-\u00DC]', clean):
                return False
        return True

    return False

def normalize_paragraph_flow(text_str: str) -> str:
    """
    Reconstitui o fluxo contínuo de parágrafos e frases que foram quebradas artificialmente
    por diagramação em colunas ou fontes justificadas com quebras linha-a-linha no PDF.
    Preserva quebras de linha reais (cabeçalhos de questões, alternativas, listas e títulos).
    """
    if not text_str:
        return ""

    # Normaliza quebras de linha com espaços excessivos entre palavras
    text_str = re.sub(r'[ \t]+', ' ', text_str)
    raw_lines = [l.strip() for l in text_str.splitlines() if l.strip()]
    if not raw_lines:
        return ""

    # Padrões que representam INÍCIO de novo bloco lógico (não devem ser colados à linha anterior)
    block_start_pat = re.compile(
        r'^(?:'
        r'QUEST[AÃ\ufffd\?]?O\s+\d+|'
        r'ITEM\s+\d+|'
        r'\d{1,3}\s*[\.\-\–\—\:\)]|'
        r'\d{1,3}\s+[A-Z\u00C0-\u00DC\"“\'‘\(]|'
        r'^\d{1,3}$|'
        r'\(?[A-Ea-e]\s*[\.\-\–\—\:\)]|'
        r'\([A-Ea-e]\)|'
        r'\[[A-Ea-e]\]|'
        r'[I|V|X\d]+\s*[\.\-\–\—\:\)]|'
        r'[•\-\*]\s+|'
        r'\|\s*|'
        r'📖|'
        r'Texto\s+|'
        r'Instru[çc][ãa]o|'
        r'Considere\s+|'
        r'Leia\s+|'
        r'Com\s+base\s+'
        r')',
        re.IGNORECASE
    )

    combined_lines = []
    current_buf = []

    for line in raw_lines:
        if block_start_pat.match(line):
            if current_buf:
                combined_lines.append(' '.join(current_buf))
                current_buf = []
            current_buf.append(line)
        else:
            if not current_buf:
                current_buf.append(line)
            else:
                prev = current_buf[-1]
                if prev.endswith('-') and len(prev) > 1 and prev[-2].isalpha() and line and line[0].isalpha():
                    current_buf[-1] = prev[:-1] + line
                elif prev.endswith(('.', ':', '?', '!', ';')) and len(prev) > 30 and (line[0].isupper() or block_start_pat.match(line)):
                    combined_lines.append(' '.join(current_buf))
                    current_buf = [line]
                else:
                    current_buf.append(line)

    if current_buf:
        combined_lines.append(' '.join(current_buf))

    result = '\n'.join(combined_lines)
    result = re.sub(r'[ \t]+', ' ', result)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()

def extract_tables_from_page(page: fitz.Page) -> List[Dict[str, Any]]:
    """
    Localiza tabelas nativas de dados na página via PyMuPDF e converte para representação Markdown estruturada.
    Filtra bordas decorativas e molduras de página que não sejam tabelas de conteúdo.
    Retorna: [{'bbox': (x0, y0, x1, y1), 'markdown': '| Col 1 | Col 2 |\n|---|---|...'}, ...]
    """
    tables_found = []
    if not hasattr(page, 'find_tables'):
        return tables_found

    p_w, p_h = page.rect.width, page.rect.height

    try:
        tabs = page.find_tables()
        for tab in tabs.tables:
            tb_rect = tab.bbox
            tb_w = tb_rect[2] - tb_rect[0]
            tb_h = tb_rect[3] - tb_rect[1]

            # Filtra molduras de página inteira (ex: borda de layout da banca IBAM)
            if tb_h > p_h * 0.55 and tb_w > p_w * 0.70:
                continue

            extracted = tab.extract()
            if not extracted or len(extracted) < 2:
                continue

            # Se qualquer célula contiver "Questão 01" ou mais de 200 caracteres, é uma moldura de coluna
            is_layout_frame = False
            for r in extracted:
                for c in r:
                    c_str = str(c or '')
                    if re.search(r'\b(?:QUEST[AÃ\ufffd\?]?O\s+\d+|ITEM\s+\d+)\b', c_str, re.IGNORECASE) or len(c_str) > 220:
                        is_layout_frame = True
                        break
                if is_layout_frame:
                    break

            if is_layout_frame:
                continue

            # Filtra tabelas vazias ou com menos de 2 colunas úteis
            valid_rows = []
            for r in extracted:
                r_clean = [str(c or '').strip().replace('\n', ' ') for c in r]
                if any(r_clean):
                    valid_rows.append(r_clean)

            if len(valid_rows) < 2:
                continue

            num_cols = max(len(r) for r in valid_rows)
            if num_cols < 2:
                continue

            norm_rows = []
            for r in valid_rows:
                row_padded = r + [''] * (num_cols - len(r))
                norm_rows.append(row_padded)

            header = '| ' + ' | '.join(norm_rows[0]) + ' |'
            separator = '| ' + ' | '.join(['---'] * num_cols) + ' |'
            body_rows = ['| ' + ' | '.join(row) + ' |' for row in norm_rows[1:]]

            md_table = '\n\n' + '\n'.join([header, separator] + body_rows) + '\n\n'
            tables_found.append({
                'bbox': tb_rect,
                'markdown': md_table
            })
    except Exception as e:
        print(f"[Table Extraction Warning] {e}")

    return tables_found

def detect_layout_and_ordered_blocks(page: fitz.Page, watermarks: Set[Tuple[int, int, int, int]]) -> List[Dict[str, Any]]:
    """
    Algoritmo adaptativo multi-coluna (PyMuPDF Layout-Aware em nível de linha).
    Reorganiza o texto respeitando a ordem natural e espacial de leitura:
    1. Filtra margens, marcas d'água e ruídos.
    2. Agrupa linhas por cabeçalho superior, coluna esquerda, coluna direita e rodapé.
    """
    width, height = page.rect.width, page.rect.height
    mid_x_page = width * 0.5

    # 1. Extração de tabelas na página
    page_tables = extract_tables_from_page(page)

    def is_inside_table(bbox):
        bx0, by0, bx1, by1 = bbox
        for t in page_tables:
            tx0, ty0, tx1, ty1 = t['bbox']
            if not (bx1 < tx0 or bx0 > tx1 or by1 < ty0 or by0 > ty1):
                return True
        return False

    # 2. Extração precisa em nível de linha via dict de spans do PyMuPDF
    text_page = page.get_text('dict')
    lines_extracted = []

    for block in text_page.get('blocks', []):
        if block.get('type') != 0:
            continue
        for line in block.get('lines', []):
            line_text = ' '.join([span.get('text', '').strip() for span in line.get('spans', []) if span.get('text', '').strip()]).strip()
            if not line_text:
                continue
            lx0, ly0, lx1, ly1 = line['bbox']

            # Filtros de margem e ruídos institucionais
            if ly0 < 18 or ly1 > height - 32:
                continue
            lt_lower = line_text.lower()
            if 'pcimarkpci' in lt_lower or 'pciconcursos.com.br' in lt_lower or 'qconcursos.com' in lt_lower or 'confidencial at' in lt_lower or 'tjsp2301' in lt_lower:
                continue
            if 'PROVA' in line_text.upper() and len(line_text) < 25 and any(f'PROVA {k}' in line_text.upper() for k in range(10)):
                continue

            cleaned = clean_marginal_line_numbers(line_text)
            if not cleaned.strip():
                continue

            if is_inside_table((lx0, ly0, lx1, ly1)):
                continue

            mid_x = (lx0 + lx1) / 2
            lines_extracted.append({
                'page': page.number,
                'x0': lx0, 'y0': ly0, 'x1': lx1, 'y1': ly1,
                'mid_x': mid_x,
                'width': lx1 - lx0,
                'text': cleaned
            })

    # Insere as tabelas detectadas como blocos estruturados
    for t in page_tables:
        tx0, ty0, tx1, ty1 = t['bbox']
        lines_extracted.append({
            'page': page.number,
            'x0': tx0, 'y0': ty0, 'x1': tx1, 'y1': ty1,
            'mid_x': (tx0 + tx1) / 2,
            'width': tx1 - tx0,
            'text': t['markdown']
        })

    if not lines_extracted:
        return []

    # Detecta se há 2 colunas paralelas
    text_only_lines = [l for l in lines_extracted if not l['text'].startswith('\n|')]
    left_lines = [l for l in text_only_lines if l['mid_x'] < mid_x_page]
    right_lines = [l for l in text_only_lines if l['mid_x'] >= mid_x_page]

    has_columns = len(left_lines) >= 3 and len(right_lines) >= 3

    if not has_columns:
        lines_extracted.sort(key=lambda l: (round(l['y0'], -1), l['x0']))
        raw_full = '\n'.join(l['text'] for l in lines_extracted)
        norm_text = normalize_paragraph_flow(raw_full)
        return [{'page': page.number, 'x0': 0, 'y0': 0, 'x1': width, 'y1': height, 'text': norm_text}]

    top_headers = []
    col_left = []
    col_right = []
    footers = []

    for l in lines_extracted:
        # Um cabeçalho de página inteira precisa cruzar o centro da página
        is_page_header = (l['y1'] <= 60 and l['x0'] < width * 0.35 and l['x1'] > width * 0.65)
        # Um rodapé de página inteira precisa cruzar o centro da página
        is_page_footer = (l['y0'] >= height - 35 and l['x0'] < width * 0.35 and l['x1'] > width * 0.65)
        
        if is_page_header:
            top_headers.append(l)
        elif is_page_footer:
            footers.append(l)
        elif l['mid_x'] < mid_x_page:
            col_left.append(l)
        else:
            col_right.append(l)

    top_headers.sort(key=lambda l: l['y0'])
    col_left.sort(key=lambda l: l['y0'])
    col_right.sort(key=lambda l: l['y0'])
    footers.sort(key=lambda l: l['y0'])

    ordered_groups = []
    if top_headers:
        t_raw = '\n'.join(l['text'] for l in top_headers)
        ordered_groups.append({'page': page.number, 'x0': 0, 'y0': 0, 'x1': width, 'y1': 60, 'text': normalize_paragraph_flow(t_raw)})
    if col_left:
        t_raw = '\n'.join(l['text'] for l in col_left)
        ordered_groups.append({'page': page.number, 'x0': 0, 'y0': 60, 'x1': mid_x_page, 'y1': height, 'text': normalize_paragraph_flow(t_raw)})
    if col_right:
        t_raw = '\n'.join(l['text'] for l in col_right)
        ordered_groups.append({'page': page.number, 'x0': mid_x_page, 'y0': 60, 'x1': width, 'y1': height, 'text': normalize_paragraph_flow(t_raw)})
    if footers:
        t_raw = '\n'.join(l['text'] for l in footers)
        ordered_groups.append({'page': page.number, 'x0': 0, 'y0': height - 40, 'x1': width, 'y1': height, 'text': normalize_paragraph_flow(t_raw)})

    return ordered_groups

def extract_context_blocks(full_text: str) -> List[Tuple[int, int, str, int]]:
    """
    Identifica blocos de textos de apoio compartilhados ('Texto para as questões X a Y')
    e mapeia os intervalos de questões afetados. Retorna: [(q_min, q_max, text_content, banner_start_pos), ...]
    """
    context_blocks = []
    matches = list(CONTEXT_TEXT_HEADER_REGEX.finditer(full_text))
    
    for m in matches:
        try:
            q_min = int(m.group(2))
            q_max = int(m.group(3))
            if q_min > q_max or q_max - q_min > 50:
                continue
                
            banner_start = m.start()
            banner_end = m.end()
            q_pattern = rf'(?:^|\n)[ \t]*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)?0*{q_min}\s*(?:[\.\-\–\—\:\)]|\n+|[ \t]+(?=[A-Z\u00C0-\u00DC\"“\'‘\(]))'
            m_q = re.search(q_pattern, full_text[banner_end:], re.IGNORECASE)
            
            if m_q:
                text_body = full_text[banner_end:banner_end + m_q.start()].strip()
                if len(text_body) >= 20:
                    context_blocks.append((q_min, q_max, text_body, banner_start))
        except Exception:
            continue
            
    return context_blocks
