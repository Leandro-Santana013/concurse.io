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
    topology: str = "AUTO"                   # 'AUTO' | 'N_ORDER' | 'Z_ORDER'


def infer_document_topology(doc: fitz.Document, watermarks: Optional[Set[Tuple[int, int, int, int]]] = None) -> str:
    """
    Herança Topológica de Caderno (ADR 0002):
    Analisa páginas com 2+ questões para determinar a topologia predominante do caderno ('N_ORDER' vs 'Z_ORDER').
    """
    z_votes = 0
    n_votes = 0
    q_header_pat = re.compile(r'(?:^|\n)\s*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+|0*)(\d{1,3})\b', re.IGNORECASE)

    for p_idx in range(min(12, len(doc))):
        page = doc[p_idx]
        width = page.rect.width
        mid_x = width * 0.5
        text_page = page.get_text('dict')
        
        left_headers = []
        right_headers = []
        
        for block in text_page.get('blocks', []):
            if block.get('type') != 0:
                continue
            for line in block.get('lines', []):
                lx0, ly0, lx1, ly1 = line['bbox']
                if ly0 < 30 or ly1 > page.rect.height - 40:
                    continue
                line_text = ' '.join(s.get('text', '') for s in line.get('spans', [])).strip()
                m = q_header_pat.search(line_text)
                if m:
                    try:
                        q_num = int(m.group(1))
                        if 1 <= q_num <= 200:
                            if (lx0 + lx1) / 2.0 < mid_x:
                                left_headers.append((q_num, ly0))
                            else:
                                right_headers.append((q_num, ly0))
                    except ValueError:
                        pass
        
        for q_l, y_l in left_headers:
            for q_r, y_r in right_headers:
                if q_r == q_l + 1 and abs(y_r - y_l) < 120.0:
                    z_votes += 1
                elif q_r > q_l and y_l < y_r:
                    n_votes += 1

    return "Z_ORDER" if z_votes > n_votes and z_votes >= 2 else "N_ORDER"


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
    r'[Cc]onsidere\s+(?:o\s+texto|a\s+frase|a\s+situa[cç][aã\ufffd\?]?o\s+hipot[eé\ufffd\?]?tica|o\s+caso)\s*(?:(?:a\s+seguir|abaixo))?|'
    r'[Cc]om\s+base\s+n[oa]\s+(?:texto|frase|situa[cç][aã\ufffd\?]?o|artigo)\s*(?:(?:abaixo|a\s+seguir))?\s*,\s*responda(?:\s+[àa\ufffd\?]?s)?|'
    r'[Tt]exto\s+(?:I|II|III|1|2|3)?\s*(?:\(?[^)]*\))?\s*[-–—:]?\s*(?:para\s+(?:as\s+)?quest[oõa\ufffd\?]?es|base\s+para\s+as\s+quest[oõa\ufffd\?]?es)'
    r')'
    r'[^\.\:]{0,100}?'
    r'quest[oõa\ufffd\?]?es?\s*(?:de\s+(?:n[úu]meros?|n[º°\.\s]*\s*|num\.?)\s*|de\s+)?((?:0*\d{1,3}\s*(?:,|e|a|ao?|at[eé\ufffd\?]?|-)\s*)+0*\d{1,3})'
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
    Identifica elementos que se repetem na mesma posição em 3 ou mais páginas distintas
    (marcas d'água, rodapés de sites de concursos e cabeçalhos fixos).
    """
    import collections
    rect_pages = collections.defaultdict(set)
    for p_idx, page in enumerate(doc):
        for d in page.get_drawings():
            r = d['rect']
            if r.width < 5 or r.height < 5:
                continue
            key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
            rect_pages[key].add(p_idx)
            
        seen_xrefs = set()
        for img_info in page.get_images():
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            for r in page.get_image_rects(xref):
                key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
                rect_pages[key].add(p_idx)

    return {k for k, pages in rect_pages.items() if len(pages) >= 3}

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
            
        if line_clean.startswith('|'):
            if current_buf:
                combined_lines.append(' '.join(current_buf))
                current_buf = []
            combined_lines.append(line_clean)
            continue
        elif current_buf and current_buf[-1].startswith('|'):
            combined_lines.append(current_buf[-1])
            current_buf = [line_clean]
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

            # Filtra se for falso positivo de alternativas de questão (A, B, C, D, E) ou comandos de questão
            opt_count = 0
            has_question_keywords = False
            for r in valid_rows:
                for c in r:
                    if re.search(r'\b\(?[a-eA-E]\)[\.\s]', c) or re.search(r'^\s*\(?[a-eA-E]\)\s*', c):
                        opt_count += 1
                    c_lower = c.lower()
                    if any(kw in c_lower for kw in ['exceto', 'assinale', 'incorret', 'corret', 'alternativa', 'todas abaixo', 'podemos afirmar', 'é correto', 'é incorreto']):
                        has_question_keywords = True
            if opt_count >= 1 or has_question_keywords:
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
                if ly0 < 18 or ly0 >= height - 48 or ly1 > height - 38:
                    continue
                lt_lower = line_text.lower()
                if 'pcimarkpci' in lt_lower or 'pciconcursos.com.br' in lt_lower or 'qconcursos.com' in lt_lower or 'confidencial at' in lt_lower or 'tjsp2301' in lt_lower:
                    continue
                if 'enem2024' in lt_lower or 'enem20e4' in lt_lower or re.search(r'(?:enem\d{4}){2,}', lt_lower) or re.match(r'^\s*\*\d{6,}[A-Z0-9]*\*\s*$', line_text.strip()):
                    continue
                if (lx1 - lx0 < 6 or ly1 - ly0 > height * 0.5) and ('enem' in lt_lower or len(line_text) > 30):
                    continue
                if 'PROVA' in line_text.upper() and len(line_text) < 25 and any(f'PROVA {k}' in line_text.upper() for k in range(10)):
                    continue
                if ly1 > height - 60 or ly0 > height - 52:
                    if any(kw in lt_lower for kw in ['tipo ', 'página', 'pagina', 'tarde', 'manhã', 'manha', 'noite', 'ati -', 'fgv', 'dataprev', 'analista', 'cargo', 'ibam', 'enem', 'linguagens, códigos', 'ciências humanas', 'ciências da natureza', 'matemática e suas tecnologias', 'caderno 1', 'caderno 2', 'caderno 3', 'caderno 4', 'caderno azul', 'caderno amarelo', 'caderno branco', 'caderno rosa']):
                        continue
                    if re.match(r'^\s*(?:p[aá]g(?:ina)?\.?\s*)?\d+(?:\s*(?:de|\/|\-)\s*\d+)?\s*$', line_text.strip(), re.IGNORECASE):
                        continue
                    if re.match(r'^[A-Za-z\u00C0-\u00DC\s\-\/\(\)]+\s*[-–—]\s*\d+\s*$', line_text.strip()):
                        continue
                if ly0 < 52:
                    if any(kw in lt_lower for kw in ['dataprev', 'empresa de tecnologia', 'fgv conhecimento', 'caderno de prova']):
                        continue
                    if re.match(r'^\s*\d+\s*$', line_text.strip()):
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

    # Extrai linhas de texto (excluindo tabelas Markdown e linhas de largura total)
    text_only_lines = [l for l in lines_extracted if not l['text'].startswith('\n|')]
    left_lines = [l for l in text_only_lines if l['x1'] <= mid_x_page + 25 and l['width'] < width * 0.55]
    right_lines = [l for l in text_only_lines if l['x0'] >= mid_x_page - 25 and l['width'] < width * 0.55]

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

    for l in lines_extracted:
        # Linha na faixa superior antes do início das 2 colunas paralelas (apenas se cruzar o centro ou tiver largura de página inteira)
        if l['y1'] <= y_col_start and (l['width'] > width * 0.45 or (l['x0'] < mid_x_page - 20 and l['x1'] > mid_x_page + 20)):
            top_headers.append(l)
        # Rodapé de página
        elif l['y0'] >= height - 48 or l['y1'] >= height - 38:
            continue
        elif l['mid_x'] < mid_x_page:
            col_left.append(l)
        else:
            col_right.append(l)

    # 3. Detecção Two-Pass da Topologia da Página (Z-order vs N-order)
    # Se os cabeçalhos de questões progredirem horizontalmente (Q1 à esquerda, Q2 à direita na mesma altura),
    # a página é lida em Z-order (linha a linha cruzando colunas).
    is_z_order = False
    if getattr(cfg, 'topology', 'AUTO') == 'Z_ORDER':
        is_z_order = True
    elif getattr(cfg, 'topology', 'AUTO') == 'AUTO':
        # Localiza candidatos a cabeçalhos nas linhas da esquerda e da direita
        q_header_pat = re.compile(r'(?:^|\n)\s*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+|0*)(\d{1,3})\b', re.IGNORECASE)
        left_q_headers = []
        for l in left_cands:
            m = q_header_pat.search(l['text'])
            if m:
                try:
                    left_q_headers.append((int(m.group(1)), l['y0']))
                except ValueError:
                    pass

        right_q_headers = []
        for l in right_cands:
            m = q_header_pat.search(l['text'])
            if m:
                try:
                    right_q_headers.append((int(m.group(1)), l['y0']))
                except ValueError:
                    pass

        # Se temos Q1 na esquerda e Q2 na direita na mesma faixa Y (ou Q_k e Q_k+1 concorrentes em Y)
        for q_num_l, y_l in left_q_headers:
            for q_num_r, y_r in right_q_headers:
                if q_num_r == q_num_l + 1 and abs(y_r - y_l) < 120.0:
                    is_z_order = True
                    break
            if is_z_order:
                break

    # Costura horizontal estritamente DENTRO de cada grupo de coluna
    if not force_ocr:
        top_headers = stitch_lines_within_group(top_headers)
        col_left = stitch_lines_within_group(col_left)
        col_right = stitch_lines_within_group(col_right)

    top_headers.sort(key=lambda l: (round(l['y0'], -1), l['x0']))
    col_left.sort(key=lambda l: (round(l['y0'], -1), l['x0']))
    col_right.sort(key=lambda l: (round(l['y0'], -1), l['x0']))

    ordered_groups = []
    if top_headers:
        t_raw = '\n'.join(l['text'] for l in top_headers)
        ordered_groups.append({'page': page.number, 'x0': 0, 'y0': 0, 'x1': width, 'y1': y_col_start, 'text': normalize_paragraph_flow(t_raw)})

    if is_z_order:
        # Modo Z-order: interleaving ordenado por faixas horizontais de leitura
        all_col_lines = col_left + col_right
        all_col_lines.sort(key=lambda l: (round(l['y0'] / 15.0) * 15.0, l['x0']))
        t_raw = '\n'.join(l['text'] for l in all_col_lines)
        ordered_groups.append({'page': page.number, 'x0': 0, 'y0': y_col_start, 'x1': width, 'y1': height, 'text': normalize_paragraph_flow(t_raw)})
    else:
        # Modo N-order: coluna esquerda completa, depois coluna direita
        if col_left:
            t_raw = '\n'.join(l['text'] for l in col_left)
            ordered_groups.append({'page': page.number, 'x0': 0, 'y0': y_col_start, 'x1': mid_x_page, 'y1': height, 'text': normalize_paragraph_flow(t_raw)})
        if col_right:
            t_raw = '\n'.join(l['text'] for l in col_right)
            ordered_groups.append({'page': page.number, 'x0': mid_x_page, 'y0': y_col_start, 'x1': width, 'y1': height, 'text': normalize_paragraph_flow(t_raw)})

    return ordered_groups

def extract_context_blocks(full_text: str, found_positions: Optional[List[Tuple[int, int, int]]] = None) -> List[Tuple[int, int, str, int]]:
    """
    Identifica blocos de textos de apoio compartilhados ('Texto para as questões X a Y', 'Com base na frase... responda às questões X, Y e Z')
    e textos motivadores de abertura de seção ('TEXTO: <TÍTULO>').
    Retorna: [(q_min, q_max, text_content, banner_start_pos), ...]
    """
    context_blocks = []
    matches = list(CONTEXT_TEXT_HEADER_REGEX.finditer(full_text))
    q_map = {item[0]: item[1] for item in (found_positions or [])}
    
    for m in matches:
        try:
            banner_text = m.group(0)
            nums = [int(n) for n in re.findall(r'\b\d{1,3}\b', banner_text) if 1 <= int(n) <= 200]
            if len(nums) >= 2:
                q_min = min(nums)
                q_max = max(nums)
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
                
                # 2. Fallback por regex estrito de início de questão
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

    # 3. Padrão de seção com TEXTO: <TÍTULO> antes de uma questão (ex: "PORTUGUÊS TEXTO: FURACÃO IRMA...")
    section_text_pat = re.compile(
        r'(?:^|\n)\s*(?:(?:PORTUGU[ÊE]S|L[ÍI]NGUA\s+PORTUGUESA)\s+)?TEXTO\s*(?:\([^\)]*\)|[I|V|X\d]+)?\s*[:\-–—]\s*([A-ZÁ-Ú\s0-9\-\.\,]{4,60})(?=\n|$)',
        re.IGNORECASE
    )
    for sm in section_text_pat.finditer(full_text):
        b_start = sm.start()
        m_next_q = re.search(r'(?:^|\n)\s*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)(0*\d{1,3})\b', full_text[sm.end():], re.IGNORECASE)
        if m_next_q:
            first_q_num = int(m_next_q.group(1))
            text_body = full_text[sm.start():sm.end() + m_next_q.start()].strip()
            text_body = re.sub(r'^(?:PORTUGU[ÊE]S|L[ÍI]NGUA\s+PORTUGUESA)\s+', '', text_body, flags=re.IGNORECASE).strip()
            
            max_q = first_q_num + 6
            for c in context_blocks:
                if c[0] > first_q_num and c[0] <= max_q:
                    max_q = c[0] - 1
            if len(text_body) >= 50 and not any(c[0] == first_q_num for c in context_blocks):
                context_blocks.append((first_q_num, max_q, text_body, b_start))
            
    return context_blocks
