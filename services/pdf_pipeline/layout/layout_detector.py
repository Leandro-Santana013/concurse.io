import fitz
import re
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple, Any, Optional

@dataclass
class LayoutConfig:
    """Configuração de hiperparâmetros geométricos para detecção e segmentação de layout."""
    full_width_threshold: float = 0.50       # Limiar de largura para considerar texto de apoio/cabeçalho de página inteira
    y_overlap_tolerance: float = 5.0         # Tolerância vertical máxima (pt) para costurar palavras na mesma linha horizontal
    column_gutter_margin: float = 25.0       # Margem de segurança central ao redor do divisor de colunas (pt)
    min_overlapping_pairs: int = 2           # Mínimo de pares de linhas concorrentes para confirmar modo 2 colunas
    stitch_gap_max: float = 20.0             # Distância horizontal máxima (pt) para juntar spans adjacentes
    line_height_multiplier: float = 1.2      # Fator de altura de linha para agrupamento de parágrafos


CONTEXT_TEXT_HEADER_REGEX = re.compile(
    r'(?:^|\n|\.\s+|\s+)'
    r'(?:<[^>]+>|\*{1,3}|_{1,3})*\s*'
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

_OCR_ENGINE = None

def _get_ocr_engine():
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR_ENGINE = RapidOCR()
        except Exception:
            _OCR_ENGINE = False
    return _OCR_ENGINE

def extract_ocr_lines_from_page(page: fitz.Page, dpi: int = 150) -> List[Dict[str, Any]]:
    engine = _get_ocr_engine()
    if not engine:
        return []
    try:
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        result, _ = engine(img_bytes)
        if not result:
            return []
        
        scale = 72.0 / dpi
        lines_extracted = []
        
        for r in result:
            bbox_img, text, score = r
            text_clean = text.strip()
            if not text_clean or score < 0.4:
                continue
            
            lx0 = bbox_img[0][0] * scale
            ly0 = bbox_img[0][1] * scale
            lx1 = bbox_img[2][0] * scale
            ly1 = bbox_img[2][1] * scale
            
            lines_extracted.append({
                'page': page.number,
                'x0': lx0, 'y0': ly0, 'x1': lx1, 'y1': ly1,
                'mid_x': (lx0 + lx1) / 2.0,
                'width': lx1 - lx0,
                'text': text_clean
            })
        return lines_extracted
    except Exception:
        return []

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
    if len(clean) < 30:
        return False
    
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
        if 'QUESTAO 01' in clean_norm or 'QUESTAO 1' in clean_norm or '01.' in clean_norm or '01 ' in clean_norm:
            if re.search(r'\b[A-Ea-e][\.\)\:\-]\s+[A-Z\u00C0-\u00DC0-9]|\([A-Ea-e]\)|\[[A-Ea-e]\]', clean):
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
        r'Com\s+base\s+|'
        r'Pre[çc]o\s+Custo|'
        r'[A-Za-z\u00C0-\u00DC\w\s\-\/\(\)\.]{2,30}?\s+\d+(?:[\,\.]\d+)?\s+\d+(?:[\,\.]\d+)?|'
        r'\([0-9\,\.]+\)\s*\d+\s*=\s*[0-9\,\.]+'
        r')',
        re.IGNORECASE
    )

    combined_lines = []
    current_buf = []

    for line in raw_lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        if block_start_pat.match(line_clean):
            if current_buf:
                combined_lines.append(' '.join(current_buf))
                current_buf = []
            current_buf.append(line_clean)
        else:
            if not current_buf:
                current_buf.append(line_clean)
            else:
                prev = current_buf[-1]
                # Hifenização explícita no fim da linha anterior
                if prev.endswith('-') and len(prev) > 1 and prev[-2].isalpha() and line_clean[0].isalpha():
                    current_buf[-1] = prev[:-1] + line_clean
                elif prev.endswith(('.', ':', '?', '!', ';')):
                    combined_lines.append(' '.join(current_buf))
                    current_buf = [line_clean]
                # Se a linha atual começa com maiúscula e a anterior tem comprimento substancial, trata como nova linha/opção
                elif len(prev) > 20 and (line_clean[0].isupper() or re.match(r'^(?:[A-Za-z0-9\(\[\@\§\•\-])', line_clean)):
                    combined_lines.append(' '.join(current_buf))
                    current_buf = [line_clean]
                else:
                    current_buf.append(line_clean)

    if current_buf:
        combined_lines.append(' '.join(current_buf))

    result = '\n'.join(combined_lines)
    result = re.sub(r'[ \t]+', ' ', result)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()

def extract_tables_from_page(page: fitz.Page) -> List[Dict[str, Any]]:
    """
    Localiza tabelas nativas de dados na página via PyMuPDF e converte para representação Markdown estruturada.
    Filtra bordas decorativas, molduras de alternativas e blocos de instrução que não sejam tabelas de conteúdo.
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

            # Filtra molduras de página inteira ou cabeçalhos/rodapés de margem extrema
            if tb_h > p_h * 0.55 and tb_w > p_w * 0.70:
                continue
            if tb_rect[1] < 30 or tb_rect[3] > p_h - 30:
                continue

            extracted = tab.extract()
            if not extracted or len(extracted) < 2:
                continue

            # Se qualquer célula contiver cabeçalho de questão ou texto longo de parágrafo, é moldura de layout
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

            # Filtra blocos de instrução de prova (ex: capa)
            all_tab_text = ' '.join(' '.join(r) for r in valid_rows).lower()
            if any(kw in all_tab_text for kw in [
                'cartão de respostas', 'folha de respostas', 'fiscal de sala', 'fiscal de prova',
                'caderno de questões', 'caneta esferográfica', 'impressões digitais',
                'detecção de metais', 'tempo disponível', 'tempo para a marcação', 'candidato'
            ]):
                continue

            # Filtra se for falso positivo de alternativas de questão (A, B, C, D, E)
            opt_count = 0
            for r in valid_rows:
                for c in r:
                    if re.match(r'^\s*\(?[A-Ea-e]\)[\.\s]*', c):
                        opt_count += 1
            if opt_count >= 2:
                continue

            # Filtra se a primeira linha tiver palavras soltas de continuação sintática
            first_row_non_empty = [c for c in valid_rows[0] if c]
            if not first_row_non_empty or any(re.match(r'^\(?[A-Ea-e]\)?$', w) for w in first_row_non_empty):
                continue
            if len(first_row_non_empty) == 1 and first_row_non_empty[0].lower() in ['para', 'tipo', 'de', 'do', 'da', 'com', 'em', 'por', 'que', 'se']:
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

def format_styled_span(text: str, is_bold: bool, is_italic: bool, is_underlined: bool) -> str:
    """Aplica marcações ricas de tipografia (HTML/Markdown) ao núcleo textual, preservando pontuação."""
    text = text.strip()
    if not text:
        return ""
    
    if re.match(r'^[.,;:!?()\[\]{}—–\-\"\'“”‘’]+$', text):
        return text

    m = re.match(r'^([.,;:!?()\[\]{}—–\-\"\'“”‘’]*)(.*?)([.,;:!?()\[\]{}—–\-\"\'“”‘’]*)$', text)
    if not m:
        return text
    lead_punct, core_text, trail_punct = m.groups()
    if not core_text:
        return text

    styled_core = core_text
    if is_bold and is_italic:
        styled_core = f"***{styled_core}***"
    elif is_bold:
        styled_core = f"**{styled_core}**"
    elif is_italic:
        styled_core = f"*{styled_core}*"

    if is_underlined:
        styled_core = f"<u>{styled_core}</u>"

    return f"{lead_punct}{styled_core}{trail_punct}"


def extract_rich_line_spans(line: Dict[str, Any], page_drawings: Optional[List[Dict[str, Any]]] = None) -> str:
    """Extrai os spans de uma linha preservando grifados vetoriais (underlines), negritos pontuais e itálicos."""
    spans = line.get('spans', [])
    if not spans:
        return ""

    # Se a linha inteira for bold (títulos, cabeçalhos de matérias, banners), não aplica ** em cada palavra
    all_bold = all(
        ((s.get('flags', 0) & 16 != 0) or ('bold' in s.get('font', '').lower()) or ('black' in s.get('font', '').lower()))
        for s in spans if s.get('text', '').strip()
    )

    formatted_spans = []
    for span in spans:
        t = span.get('text', '')
        if not t.strip():
            continue
        flags = span.get('flags', 0)
        font = span.get('font', '').lower()
        bbox = span.get('bbox')
        
        is_italic = (flags & 2 != 0) or ('italic' in font) or ('oblique' in font)
        # Bold somente se for destaque específico no meio do texto e não uma linha inteira em negrito
        is_bold = ((flags & 16 != 0) or ('bold' in font) or ('black' in font)) and not all_bold
        
        # Detecção geométrica de linha de grifado (sublinhado) imediatamente sob a palavra
        is_underlined = False
        if bbox and page_drawings:
            for dr in page_drawings:
                rect = dr.get('rect')
                if rect and rect.height <= 3.5 and abs(rect.y0 - bbox[3]) <= 4.5:
                    if rect.x0 <= bbox[0] + 5 and rect.x1 >= bbox[2] - 5:
                        is_underlined = True
                        break
        
        txt = t.strip()
        # Não adiciona marcadores de formatação ao número da questão, letra de alternativa ou gabarito embutido
        is_q_header = bool(re.match(r'^(?:Quest[aã]o|Item)?\s*\d+[\.\-–—:\)]?$', txt, re.IGNORECASE))
        is_opt_label = bool(re.match(r'^\(?[A-E]\)[\.\-–—:]?$', txt))
        is_ans_marker = bool(re.search(r'(?i)\(?\s*(?:Correta|Gabarito|Resposta)\s*[:=-]?\s*[A-Ea-eXNxn\*]\s*\)?', txt))
        
        if not (is_q_header or is_opt_label or is_ans_marker):
            txt = format_styled_span(txt, is_bold, is_italic, is_underlined)
                
        formatted_spans.append(txt)
        
    return ' '.join(formatted_spans).strip()

def detect_layout_and_ordered_blocks(
    page: fitz.Page,
    watermarks: Set[Tuple[int, int, int, int]],
    force_ocr: bool = False,
    config: Optional[LayoutConfig] = None
) -> List[Dict[str, Any]]:
    """
    Algoritmo adaptativo multi-coluna (PyMuPDF Layout-Aware em nível de linha).
    Reorganiza o texto respeitando a ordem natural e espacial de leitura:
    1. Filtra margens, marcas d'água e ruídos.
    2. Agrupa linhas por cabeçalho superior, coluna esquerda, coluna direita e rodapé.
    """
    cfg = config or LayoutConfig()
    width, height = page.rect.width, page.rect.height
    mid_x_page = width * 0.5

    if force_ocr:
        ocr_lines = extract_ocr_lines_from_page(page, dpi=150)
        if ocr_lines:
            lines_extracted = ocr_lines
        else:
            lines_extracted = []
    else:
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
        page_drawings = page.get_drawings()
        lines_extracted = []

        for block in text_page.get('blocks', []):
            if block.get('type') != 0:
                continue
            for line in block.get('lines', []):
                line_text = extract_rich_line_spans(line, page_drawings)
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
                if ly1 > height - 52 and any(kw in lt_lower for kw in ['tipo ', 'página', 'pagina', 'tarde', 'manhã', 'manha', 'noite', 'ati -', 'fgv', 'dataprev', 'analista', 'cargo']):
                    continue
                if ly0 < 52 and any(kw in lt_lower for kw in ['dataprev', 'empresa de tecnologia', 'fgv conhecimento', 'caderno de prova']):
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

        # 2.1 Fallback para OCR caso a página seja scan ou tenha pouquíssimo texto nativo
        if len(lines_extracted) < 4:
            ocr_lines = extract_ocr_lines_from_page(page, dpi=150)
            if ocr_lines:
                lines_extracted = ocr_lines

    if not lines_extracted:
        return []

    def stitch_lines_within_group(group_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not group_lines:
            return []
        group_lines.sort(key=lambda l: (round(l['y0'] / 5.0) * 5.0, l['x0']))
        stitched = []
        skip_idx = set()
        for i in range(len(group_lines)):
            if i in skip_idx:
                continue
            cur = group_lines[i]
            for j in range(i + 1, min(i + 5, len(group_lines))):
                if j in skip_idx:
                    continue
                nxt = group_lines[j]
                if abs(cur['y0'] - nxt['y0']) < cfg.y_overlap_tolerance and nxt['x0'] >= cur['x0'] and (nxt['x0'] - cur['x1']) < cfg.stitch_gap_max:
                    if len(cur['text'].strip()) < 15 or cur['text'].strip().endswith(('-', ':', 'Afi', 'fi', 'fl', 'Obs', '(')):
                        cur['text'] = cur['text'].strip() + ' ' + nxt['text'].strip()
                        cur['x1'] = max(cur['x1'], nxt['x1'])
                        cur['width'] = cur['x1'] - cur['x0']
                        cur['mid_x'] = (cur['x0'] + cur['x1']) / 2.0
                        skip_idx.add(j)
            stitched.append(cur)
        return stitched

    # Extrai linhas de texto (excluindo tabelas Markdown)
    text_only_lines = [l for l in lines_extracted if not l['text'].startswith('\n|')]
    left_lines = [l for l in text_only_lines if l['mid_x'] < mid_x_page]
    right_lines = [l for l in text_only_lines if l['mid_x'] >= mid_x_page]

    # Detecta se há realmente 2 colunas paralelas concorrentes na mesma faixa Y
    overlapping_y_pairs = 0
    for l in left_lines:
        if any(abs(r['y0'] - l['y0']) < 20 for r in right_lines):
            overlapping_y_pairs += 1
            if overlapping_y_pairs >= cfg.min_overlapping_pairs:
                break

    has_columns = overlapping_y_pairs >= cfg.min_overlapping_pairs and len(left_lines) >= 3 and len(right_lines) >= 3

    if not has_columns:
        stitched_all = stitch_lines_within_group(lines_extracted) if not force_ocr else lines_extracted
        stitched_all.sort(key=lambda l: (round(l['y0'], -1), l['x0']))
        raw_full = '\n'.join(l['text'] for l in stitched_all)
        norm_text = normalize_paragraph_flow(raw_full)
        return [{'page': page.number, 'x0': 0, 'y0': 0, 'x1': width, 'y1': height, 'text': norm_text}]

    # Detecta candidatas a colunas paralelas na esquerda e direita com base na margem de gutter
    left_cands = [l for l in text_only_lines if l['x1'] < mid_x_page + cfg.column_gutter_margin and l['mid_x'] < mid_x_page]
    right_cands = [l for l in text_only_lines if l['x0'] > mid_x_page - cfg.column_gutter_margin and l['mid_x'] >= mid_x_page]

    # Encontra faixa Y inicial onde coexistem colunas paralelas
    two_col_y_min = None
    for l in left_cands:
        if any(abs(r['y0'] - l['y0']) < 40 for r in right_cands):
            if two_col_y_min is None or l['y0'] < two_col_y_min:
                two_col_y_min = l['y0']

    # Se não houver início detectável de colunas paralelas, usa 60pt como padrão
    y_col_start = two_col_y_min if two_col_y_min is not None else 60.0

    top_headers = []
    col_left = []
    col_right = []
    footers = []

    for l in lines_extracted:
        # Linha na faixa superior antes do início das 2 colunas paralelas
        if l['y1'] <= y_col_start:
            top_headers.append(l)
        # Rodapé de página inteira
        elif l['y0'] >= height - 35 and l['x0'] < width * 0.35 and l['x1'] > width * 0.65:
            footers.append(l)
        elif l['mid_x'] < mid_x_page:
            col_left.append(l)
        else:
            col_right.append(l)

    # Costura horizontal estritamente DENTRO de cada grupo de coluna
    if not force_ocr:
        top_headers = stitch_lines_within_group(top_headers)
        col_left = stitch_lines_within_group(col_left)
        col_right = stitch_lines_within_group(col_right)
        footers = stitch_lines_within_group(footers)

    top_headers.sort(key=lambda l: (round(l['y0'], -1), l['x0']))
    col_left.sort(key=lambda l: (round(l['y0'], -1), l['x0']))
    col_right.sort(key=lambda l: (round(l['y0'], -1), l['x0']))
    footers.sort(key=lambda l: (round(l['y0'], -1), l['x0']))

    ordered_groups = []
    if top_headers:
        t_raw = '\n'.join(l['text'] for l in top_headers)
        ordered_groups.append({'page': page.number, 'x0': 0, 'y0': 0, 'x1': width, 'y1': y_col_start, 'text': normalize_paragraph_flow(t_raw)})
    if col_left:
        t_raw = '\n'.join(l['text'] for l in col_left)
        ordered_groups.append({'page': page.number, 'x0': 0, 'y0': y_col_start, 'x1': mid_x_page, 'y1': height, 'text': normalize_paragraph_flow(t_raw)})
    if col_right:
        t_raw = '\n'.join(l['text'] for l in col_right)
        ordered_groups.append({'page': page.number, 'x0': mid_x_page, 'y0': y_col_start, 'x1': width, 'y1': height, 'text': normalize_paragraph_flow(t_raw)})
    if footers:
        t_raw = '\n'.join(l['text'] for l in footers)
        ordered_groups.append({'page': page.number, 'x0': 0, 'y0': height - 40, 'x1': width, 'y1': height, 'text': normalize_paragraph_flow(t_raw)})

    return ordered_groups

def extract_context_blocks(full_text: str, found_positions: Optional[List[Tuple[int, int, int]]] = None) -> List[Tuple[int, int, str, int]]:
    """
    Identifica blocos de textos de apoio compartilhados ('Texto para as questões X a Y')
    e mapeia os intervalos de questões afetados. Retorna: [(q_min, q_max, text_content, banner_start_pos), ...]
    """
    context_blocks = []
    matches = list(CONTEXT_TEXT_HEADER_REGEX.finditer(full_text))
    q_map = {item[0]: item[1] for item in (found_positions or [])}
    
    for m in matches:
        try:
            q_min = int(m.group(2))
            q_max = int(m.group(3))
            if q_min > q_max or q_max - q_min > 50:
                continue
                
            banner_start = m.start()
            banner_end = m.end()

            # 1. Se temos a posição exata da questão de início do bloco via scanner de cabeçalhos
            q_target_start = q_map.get(q_min)
            if q_target_start and q_target_start > banner_end:
                text_body = full_text[banner_end:q_target_start].strip()
                if len(text_body) >= 10:
                    context_blocks.append((q_min, q_max, text_body, banner_start))
                    continue
            
            # 2. Fallback por regex estrito de início de questão (exigindo prefixo QUESTÃO ou início de linha isolado)
            q_pattern = rf'(?:^|\n)[ \t]*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)0*{q_min}\b'
            m_q = re.search(q_pattern, full_text[banner_end:], re.IGNORECASE)
            if not m_q:
                q_pattern = rf'(?:^|\n)[ \t]*0*{q_min}\s*[\.\-\–\—\:\)]'
                m_q = re.search(q_pattern, full_text[banner_end:], re.IGNORECASE)
            
            if m_q:
                text_body = full_text[banner_end:banner_end + m_q.start()].strip()
                if len(text_body) >= 10:
                    context_blocks.append((q_min, q_max, text_body, banner_start))
        except Exception:
            continue
            
    return context_blocks
