import fitz
import re
import os
import json
import io
import hashlib

# Dicionário de matérias conhecidas em concursos públicos brasileiros (com e sem acento / tolerante a encoding)
SUBJECT_PATTERNS = [
    r'L[ÍI\ufffd\?]NGUA\s+PORTUGUESA', r'PORTUGU[ÊE\ufffd\?]S', r'PORTUGUES',
    r'INTERPRETA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+DE\s+TEXTO', r'GRAM[ÁA\ufffd\?]TICA', r'REDA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+OFICIAL',
    r'MATEM[ÁA\ufffd\?]TICA\s+E\s+RACIOC[ÍI\ufffd\?]NIO\s+L[ÓO\ufffd\?]GICO', r'MATEMATICA\s+E\s+RACIOCINIO\s+LOGICO',
    r'MATEM[ÁA\ufffd\?]TICA', r'MATEMATICA', r'MATEM[ÁA\ufffd\?]TICA\s+FINANCEIRA',
    r'RACIOC[ÍI\ufffd\?]NIO\s+L[ÓO\ufffd\?]GICO', r'RACIOCINIO\s+LOGICO',
    r'RACIOC[ÍI\ufffd\?]NIO\s+L[ÓO\ufffd\?]GICO-MATEM[ÁA\ufffd\?]TICO', r'RACIOCINIO\s+LOGICO-MATEMATICO',
    r'CONHECIMENTOS\s+B[ÁA\ufffd\?]SICOS', r'CONHECIMENTOS\s+BASICOS',
    r'CONHECIMENTOS\s+GERAIS', r'CONHECIMENTOS\s+ESPEC[ÍI\ufffd\?]FICOS', r'CONHECIMENTOS\s+ESPECIFICOS',
    r'CONHECIMENTOS\s+REGIONAIS',
    r'INFORM[ÁA\ufffd\?]TICA', r'INFORMATICA',
    r'NO[ÇC\ufffd\?][ÕO\ufffd\?]ES\s+DE\s+INFORM[ÁA\ufffd\?]TICA', r'NOCOES\s+DE\s+INFORMATICA',
    r'TECNOLOGIA\s+DA\s+INFORM[ÁA\ufffd\?]O', r'SEGURAN[ÇC\ufffd\?]A\s+DA\s+INFORM[ÁA\ufffd\?]O',
    r'BANCO\s+DE\s+DADOS', r'REDES\s+DE\s+COMPUTADORES', r'ENGENHARIA\s+DE\s+SOFTWARE',
    r'DIREITO\s+CONSTITUCIONAL', r'DIREITO\s+ADMINISTRATIVO', r'DIREITO\s+PENAL', r'DIREITO\s+CIVIL',
    r'DIREITO\s+PROCESSUAL', r'DIREITO\s+PROCESSUAL\s+CIVIL', r'DIREITO\s+PROCESSUAL\s+PENAL',
    r'DIREITO\s+TRIBUT[ÁA\ufffd\?]RIO', r'DIREITO\s+TRIBUTARIO',
    r'DIREITO\s+PREVIDENCI[ÁA\ufffd\?]RIO', r'DIREITO\s+PREVIDENCIARIO',
    r'DIREITO\s+DO\s+TRABALHO', r'DIREITO\s+PROCESSUAL\s+DO\s+TRABALHO',
    r'DIREITO\s+FINANCEIRO', r'DIREITO\s+AMBIENTAL', r'DIREITOS\s+HUMANOS',
    r'DIREITO\s+ELEITORAL', r'DIREITO\s+EMPRESARIAL',
    r'LEGISLA[ÇC\ufffd\?][ÃA\ufffd\?]O', r'LEGISLACAO', r'LEGISLA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+ESPEC[ÍI\ufffd\?]FICA', r'LEGISLACAO\s+ESPECIFICA',
    r'LEGISLA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+APLICADA', r'LEGISLA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+INSTITUCIONAL',
    r'[ÉE]TICA\s+NO\s+SERVI[ÇC]O\s+P[ÚU]BLICO', r'REGIMENTO\s+INTERNO', r'ESTATUTO\s+DOS\s+SERVIDORES',
    r'BLOCO\s+[I|V|X\d]+', r'M[ÓO]DULO\s+[I|V|X\d]+', r'PARTE\s+[I|V|X\d]+', r'ATUALIDADES',
    r'HIST[ÓO]RIA\s+E\s+GEOGRAFIA', r'GEOGRAFIA', r'HIST[ÓO]RIA',
    r'ADMINISTRA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+P[ÚU\ufffd\?]BLICA', r'ADMINISTRACAO\s+PUBLICA',
    r'ADMINISTRA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+GERAL', r'ADMINISTRACAO\s+GERAL',
    r'GEST[ÃA\ufffd\?]O\s+P[ÚU\ufffd\?]BLICA', r'GESTAO\s+PUBLICA',
    r'ADMINISTRA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+FINANCEIRA\s+E\s+OR[ÇC]AMENT[ÁA]RIA', r'AFO',
    r'OR[ÇC]AMENTO\s+P[ÚU]BLICO', r'POL[ÍI]TICAS\s+P[ÚU]BLICAS',
    r'CONTABILIDADE', r'CONTABILIDADE\s+GERAL',
    r'CONTABILIDADE\s+P[ÚU\ufffd\?]BLICA', r'CONTABILIDADE\s+PUBLICA',
    r'AUDITORIA', r'ESTAT[ÍI\ufffd\?]STICA', r'ESTATISTICA', r'ECONOMIA', r'FINAN[ÇC]AS\s+P[ÚU]BLICAS',
    r'ENGENHARIA\s+CIVIL', r'ENGENHARIA\s+MEC[ÂA]NICA', r'ENGENHARIA\s+EL[ÉE]TRICA', r'ENGENHARIA',
    r'F[ÍI\ufffd\?]SICA', r'FISICA', r'QU[ÍI\ufffd\?]MICA', r'QUIMICA', r'BIOLOGIA',
    r'L[ÍI\ufffd\?]NGUA\s+INGLESA', r'INGL[ÊE\ufffd\?]S', r'INGLES',
    r'L[ÍI\ufffd\?]NGUA\s+ESPANHOLA', r'ESPANHOL',
    r'SEGURAN[ÇC\ufffd\?]A\s+P[ÚU\ufffd\?]BLICA', r'SEGURANCA\s+PUBLICA',
    r'CRIMINOLOGIA', r'MEDICINA\s+LEGAL',
    r'ARQUIVOLOGIA', r'RECURSOS\s+HUMANOS', r'GEST[ÃA]O\s+DE\s+PESSOAS',
    r'PEDAGOGIA', r'ENFERMAGEM', r'MEDICINA', r'SERVI[ÇC]O\s+SOCIAL', r'PSICOLOGIA'
]
SUBJECT_REGEX = re.compile(r'^\s*(?:' + '|'.join(SUBJECT_PATTERNS) + r')(?:\s*[-–—:]\s*.*)?\s*$', re.IGNORECASE)

IMAGE_TRIGGER_REGEX = re.compile(r'\b(figura|gr[áa]fico|quadro|tabela|diagrama|circuito|desenho|ilustra[çc][ãa]o|mapa|esquema|imagem|paqu[íi]metro|circunfer[êe]ncia|tetraedro|planta|fluxograma)\b', re.IGNORECASE)
CAPTION_REGEX = re.compile(r'^\s*(?:figura|gr[áa]fico|quadro|tabela|diagrama|circuito|mapa|esquema|imagem)\b(?:\s*(?:\d+|[A-Za-z]|I|II|III|IV|V))?\s*[-–—:]?', re.IGNORECASE)

GABARITO_HEADER_REGEX = re.compile(r'\b(gabarito|folha\s+de\s+respostas?|quadro\s+de\s+respostas?|respostas?\s+das?\s+quest[õo]es|gabarito\s+oficial|gabarito\s+preliminar|gabarito\s+definitivo)\b', re.IGNORECASE)

# Padrão para detecção de textos de apoio compartilhados (ex: "Instrução: As questões 1 a 4 referem-se ao texto...")
CONTEXT_TEXT_HEADER_REGEX = re.compile(
    r'(?:^|\n)\s*'
    r'(?:Instru[çc][ãa]o\s*[:\.\-]?\s*)?'
    r'(?:(?:Texto(?:\s+[I|V|X\d]+)?|Considere\s+o\s+texto|Leia\s+o\s+texto|Com\s+base\s+no\s+texto|Para\s+responder\s+[àa]s?)[^\n]{0,60}?\s+)?'
    r'(?:As\s+|Os\s+)?(?:quest[õo]es?|itens?)\s*(?:de\s+n[úu]meros?\s+|de\s+)?(\d{1,3})\s*(?:a|e|ao?|at[ée]|\be\b|,|\.)\s*(?:a\s+)?(\d{1,3})'
    r'[^\n]*',
    re.IGNORECASE
)

# Instância Singleton do motor de OCR
_RAPID_OCR_ENGINE = None

def _get_rapidocr_engine():
    """Inicializa preguiçosamente o motor RapidOCR ONNX."""
    global _RAPID_OCR_ENGINE
    if _RAPID_OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID_OCR_ENGINE = RapidOCR()
        except Exception as e:
            print(f"[PDF Parser] RapidOCR indisponível: {e}")
            _RAPID_OCR_ENGINE = False
    return _RAPID_OCR_ENGINE if _RAPID_OCR_ENGINE is not False else None

def _ocr_page_fallback(page):
    """
    Executa OCR em uma página de PDF escaneada/rasterizada,
    retornando blocos no formato idêntico ao page.get_text('blocks').
    """
    engine = _get_rapidocr_engine()
    if not engine:
        return []

    try:
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        
        results, _ = engine(img_bytes)
        if not results:
            return []

        scale_x = page.rect.width / pix.width
        scale_y = page.rect.height / pix.height
        
        ocr_blocks = []
        for i, item in enumerate(results):
            box, text, score = item
            if score < 0.30 or not text.strip():
                continue
            
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            
            x0 = min(xs) * scale_x
            y0 = min(ys) * scale_y
            x1 = max(xs) * scale_x
            y1 = max(ys) * scale_y
            
            ocr_blocks.append((x0, y0, x1, y1, text.strip(), i, 0))
            
        return ocr_blocks
    except Exception as e:
        print(f"[PDF Parser] Erro no OCR da página {page.number}: {e}")
        return []

def _detect_watermarks_and_headers(doc):
    """
    Analisa todas as páginas do PDF e detecta retângulos / desenhos que se repetem
    em 3 ou mais páginas nas mesmas posições (marcas d'água, rodapés e cabeçalhos).
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

def _find_diagram_clusters(page, watermarks, text_blocks=None):
    """
    Agrupa elementos visuais (desenhos vetoriais + imagens raster) adjacentes
    em clusters coerentes de figuras/diagramas e inclui legendas textuais explicativas.
    """
    useful_rects = []
    page_w, page_h = page.rect.width, page.rect.height

    # 1. Desenhos vetoriais (geometria, circuitos, gráficos)
    for d in page.get_drawings():
        r = d['rect']
        if r.width < 10 or r.height < 10:
            continue
        if r.y0 < 30 or r.y1 > page_h - 30:
            continue
        if r.height > page_h * 0.75:
            continue
        key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
        if key in watermarks:
            continue
        useful_rects.append(r)

    # 2. Imagens raster embutidas
    for img_info in page.get_images():
        for r in page.get_image_rects(img_info[0]):
            if r.width < 10 or r.height < 10:
                continue
            if r.y0 < 30 or r.y1 > page_h - 30:
                continue
            key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
            if key in watermarks:
                continue
            useful_rects.append(r)

    if not useful_rects:
        return []

    # 3. Agrupamento por proximidade espacial (na mesma coluna ou bloco)
    clusters = []
    for r in useful_rects:
        merged = False
        for c in clusters:
            if abs(r.x0 - c.x0) < page_w * 0.45 and (r.y0 <= c.y1 + 25 and r.y1 >= c.y0 - 25):
                c.include_rect(r)
                merged = True
                break
        if not merged:
            clusters.append(fitz.Rect(r))

    # 4. Captura e Inclusão de Legendas Adjacentes (ex: 'Figura 1 - Circuito elétrico')
    if text_blocks:
        for c in clusters:
            for b in text_blocks:
                x0, y0, x1, y1, text = b[:5]
                text_clean = text.strip()
                if CAPTION_REGEX.search(text_clean):
                    is_below = (0 <= y0 - c.y1 <= 25) and (abs(x0 - c.x0) < page_w * 0.4)
                    is_above = (0 <= c.y0 - y1 <= 25) and (abs(x0 - c.x0) < page_w * 0.4)
                    if is_below or is_above:
                        c.include_rect(fitz.Rect(x0, y0, x1, y1))

    return [c for c in clusters if c.width > 25 and c.height > 25]

def _extract_gabarito_from_doc(doc):
    """
    Varre o documento em busca de tabelas, seções ou linhas de gabarito (incluindo páginas escaneadas).
    Retorna um dicionário {numero_questao_int: 'A'|'B'|'C'|'D'|'E'|'X'|'C'|'E'}.
    """
    from services.gabarito_service import parse_gabarito_from_text
    gabarito_map = {}
    total_pages = len(doc)
    if total_pages == 0:
        return gabarito_map

    pages_to_scan = list(range(total_pages - 1, -1, -1))

    for p_idx in pages_to_scan:
        page = doc[p_idx]
        text = page.get_text()
        if len(text.strip()) < 30:
            ocr_b = _ocr_page_fallback(page)
            if ocr_b:
                text = '\n'.join(b[4] for b in ocr_b)

        has_gabarito_header = bool(GABARITO_HEADER_REGEX.search(text))
        
        if has_gabarito_header or p_idx == total_pages - 1:
            found_gab = parse_gabarito_from_text(text)
            if len(found_gab) >= 1:
                gabarito_map.update(found_gab)
                if len(gabarito_map) >= 10:
                    break

    return gabarito_map

def _is_instruction_or_blank_page(page_text):
    """Detecta páginas de capa, instruções gerais aos candidatos ou páginas em branco."""
    clean = re.sub(r'pcimarkpci[^\n]*|www\.pciconcursos\.com\.br|qconcursos\.com', '', page_text, flags=re.IGNORECASE).strip()
    if len(clean) < 80:
        return True
    
    clean_norm = re.sub(r'\s+', ' ', clean).upper()
    clean_norm = re.sub(r'[\ufffd\?]', 'C', clean_norm)
    
    # Capas de modelos / folhas de rosto sem questões
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
        # Se contiver questão com alternativas reais de prova (ex: "QUESTÃO 01" ou "(A)" e "(B)"), não é apenas capa
        if 'QUESTAO 01' in clean_norm or 'QUESTAO 1' in clean_norm:
            if re.search(r'\b[A-E]\)\s+[A-Z\u00C0-\u00DC]', clean):
                return False
        return True

    return False

def _clean_marginal_line_numbers(text_str):
    """
    Remove números de linha verticais que são comuns nas margens de textos literários/jurídicos
    (ex: '01\n02\n03...' ou '05\n10\n15...'), prevenindo que sejam interpretados como questões.
    """
    lines = text_str.splitlines()
    if len(lines) >= 3:
        # Se mais de 60% das linhas forem apenas dígitos isolados de 1 a 100
        digit_lines = [l.strip() for l in lines if l.strip().isdigit() and 1 <= int(l.strip()) <= 150]
        if len(digit_lines) >= 3 and len(digit_lines) >= len(lines) * 0.6:
            return "" # Bloco puro de contagem de linhas
            
    # Remove sequências de dígitos no início das linhas de um poema/artigo se formatadas como número de linha
    cleaned_lines = []
    for l in lines:
        cleaned_lines.append(re.sub(r'^(?:0\d|\d{2})\s{2,}', '', l))
    return '\n'.join(cleaned_lines)

def _extract_page_ordered_blocks(page, watermarks):
    """
    Algoritmo adaptativo multi-coluna (PyMuPDF Layout-Aware com suporte a OCR Fallback).
    Reorganiza os blocos de texto respeitando a ordem natural de leitura:
    1. Filtra margens, marcas d'água e ruídos.
    2. Identifica se a página possui colunas paralelas simultâneas.
    3. Se houver 2 colunas:
       - Header superior (qualquer bloco antes do split de colunas)
       - Coluna Esquerda (Top-Down)
       - Coluna Direita (Top-Down)
       - Footer inferior (qualquer bloco após o split de colunas)
    4. Se for página de 1 coluna, ordena direto por y0 (Top-Down).
    """
    width, height = page.rect.width, page.rect.height
    blocks = page.get_text('blocks')
    
    # Detecção de página escaneada (sem texto vetorial nativo)
    raw_text = page.get_text('text').strip()
    if len(raw_text) < 30:
        ocr_blocks = _ocr_page_fallback(page)
        if ocr_blocks:
            blocks = ocr_blocks

    mid_x_page = width * 0.5
    valid_blocks = []
    
    for b in blocks:
        if b[6] != 0: # Ignora imagens/gráficos nos blocos de texto
            continue
        x0, y0, x1, y1, text = b[:5]
        text_str = text.strip()
        if not text_str:
            continue
        
        # Filtro de ruídos de margem e rodapés institucionais
        if y0 < 22 or y1 > height - 22:
            continue
        if 'pcimarkpci' in text_str.lower() or 'pciconcursos.com.br' in text_str.lower() or 'qconcursos.com' in text_str.lower():
            continue
        if 'PROVA' in text_str.upper() and len(text_str) < 30 and any(f'PROVA {k}' in text_str.upper() for k in range(10)):
            continue
        
        # Limpa numerações marginais de linhas de texto
        text_cleaned = _clean_marginal_line_numbers(text_str)
        if not text_cleaned.strip():
            continue

        mid_x = (x0 + x1) / 2
        block_w = x1 - x0
        
        valid_blocks.append({
            'page': page.number,
            'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
            'text': text_cleaned,
            'mid_x': mid_x,
            'width': block_w
        })

    if not valid_blocks:
        return []

    # Detecta se há blocos paralelos na esquerda e na direita (2 colunas)
    left_blocks = [b for b in valid_blocks if b['mid_x'] < mid_x_page and b['width'] <= width * 0.60]
    right_blocks = [b for b in valid_blocks if b['mid_x'] >= mid_x_page and b['width'] <= width * 0.60]
    
    has_parallel_columns = False
    col_split_y_min = height
    col_split_y_max = 0
    
    for lb in left_blocks:
        for rb in right_blocks:
            if max(lb['y0'], rb['y0']) < min(lb['y1'], rb['y1']):
                has_parallel_columns = True
                col_split_y_min = min(col_split_y_min, lb['y0'], rb['y0'])
                col_split_y_max = max(col_split_y_max, lb['y1'], rb['y1'])

    # Se NÃO houver 2 colunas paralelas, é uma página de fluxo linear (1 coluna)
    if not has_parallel_columns or not right_blocks:
        valid_blocks.sort(key=lambda b: (round(b['y0'], -1), b['x0']))
        return valid_blocks

    # Se HOUVER 2 colunas:
    top_headers = []
    col_left = []
    col_right = []
    bottom_footers = []
    
    for b in valid_blocks:
        if b['y1'] <= col_split_y_min:
            top_headers.append(b)
        elif b['y0'] >= col_split_y_max:
            bottom_footers.append(b)
        elif b['width'] > width * 0.65:
            if b['y0'] < (col_split_y_min + col_split_y_max) / 2:
                top_headers.append(b)
            else:
                bottom_footers.append(b)
        elif b['mid_x'] < mid_x_page:
            col_left.append(b)
        else:
            col_right.append(b)

    top_headers.sort(key=lambda b: b['y0'])
    col_left.sort(key=lambda b: b['y0'])
    col_right.sort(key=lambda b: b['y0'])
    bottom_footers.sort(key=lambda b: b['y0'])
    
    return top_headers + col_left + col_right + bottom_footers

def _format_subject_title(raw_text):
    """Normaliza o nome da matéria para seu título canônico em português."""
    if not raw_text:
        return 'Geral'
    normalized = raw_text.strip()
    normalized_clean = re.sub(r'[\ufffd\?]', '', normalized)
    
    canonicos = [
        (r'L[ÍI]?NGUA\s+PORTUGUESA|PORTUGU[ÊE]?S|INTERPRETA[ÇC]?[ÃA]?O\s+DE\s+TEXTO|GRAM[ÁA]?TICA', 'Língua Portuguesa'),
        (r'MATEM[ÁA]?TICA\s+E\s+RACIOC[ÍI]?NIO\s+L[ÓO]?GICO', 'Matemática e Raciocínio Lógico'),
        (r'RACIOC[ÍI]?NIO\s+L[ÓO]?GICO-MATEM[ÁA]?TICO', 'Raciocínio Lógico-Matemático'),
        (r'RACIOC[ÍI]?NIO\s+L[ÓO]?GICO', 'Raciocínio Lógico'),
        (r'MATEM[ÁA]?TICA\s+FINANCEIRA', 'Matemática Financeira'),
        (r'MATEM[ÁA]?TICA', 'Matemática'),
        (r'CONHECIMENTOS\s+B[ÁA]?SICOS', 'Conhecimentos Básicos'),
        (r'CONHECIMENTOS\s+GERAIS', 'Conhecimentos Gerais'),
        (r'CONHECIMENTOS\s+ESPEC[ÍI]?FICOS', 'Conhecimentos Específicos'),
        (r'CONHECIMENTOS\s+REGIONAIS', 'Conhecimentos Regionais'),
        (r'NO[ÇC]?[ÕO]?ES\s+DE\s+INFORM[ÁA]?TICA', 'Noções de Informática'),
        (r'INFORM[ÁA]?TICA|TECNOLOGIA\s+DA\s+INFORM|CI[ÊE]NCIA\s+DE\s+DADOS', 'Informática'),
        (r'DIREITO\s+CONSTITUCIONAL', 'Direito Constitucional'),
        (r'DIREITO\s+ADMINISTRATIVO', 'Direito Administrativo'),
        (r'DIREITO\s+PENAL', 'Direito Penal'),
        (r'DIREITO\s+CIVIL', 'Direito Civil'),
        (r'DIREITO\s+PROCESSUAL\s+CIVIL', 'Direito Processual Civil'),
        (r'DIREITO\s+PROCESSUAL\s+PENAL', 'Direito Processual Penal'),
        (r'DIREITO\s+PROCESSUAL', 'Direito Processual'),
        (r'DIREITO\s+TRIBUT[ÁA]?RIO', 'Direito Tributário'),
        (r'DIREITO\s+PREVIDENCI[ÁA]?RIO', 'Direito Previdenciário'),
        (r'DIREITO\s+DO\s+TRABALHO', 'Direito do Trabalho'),
        (r'DIREITO\s+PROCESSUAL\s+DO\s+TRABALHO', 'Direito Processual do Trabalho'),
        (r'DIREITO\s+FINANCEIRO', 'Direito Financeiro'),
        (r'DIREITO\s+AMBIENTAL', 'Direito Ambiental'),
        (r'DIREITO\s+ELEITORAL', 'Direito Eleitoral'),
        (r'DIREITO\s+EMPRESARIAL', 'Direito Empresarial'),
        (r'DIREITOS\s+HUMANOS', 'Direitos Humanos'),
        (r'LEGISLA[ÇC]?[ÃA]?O\s+ESPEC[ÍI]?FICA', 'Legislação Específica'),
        (r'LEGISLA[ÇC]?[ÃA]?O\s+APLICADA', 'Legislação Aplicada'),
        (r'LEGISLA[ÇC]?[ÃA]?O\s+INSTITUCIONAL', 'Legislação Institucional'),
        (r'LEGISLA[ÇC]?[ÃA]?O', 'Legislação'),
        (r'[ÉE]TICA\s+NO\s+SERVI[ÇC]O\s+P[ÚU]BLICO|[ÉE]TICA', 'Ética no Serviço Público'),
        (r'REGIMENTO\s+INTERNO|ESTATUTO\s+DOS\s+SERVIDORES', 'Regimento Interno e Estatuto'),
        (r'ADMINISTRA[ÇC]?[ÃA]?O\s+P[ÚU]?BLICA', 'Administração Pública'),
        (r'ADMINISTRA[ÇC]?[ÃA]?O\s+GERAL', 'Administração Geral'),
        (r'GEST[ÃA]?O\s+P[ÚU]?BLICA', 'Gestão Pública'),
        (r'ADMINISTRA[ÇC]?[ÃA]?O\s+FINANCEIRA\s+E\s+OR[ÇC]AMENT[ÁA]RIA|AFO', 'AFO e Orçamento Público'),
        (r'OR[ÇC]AMENTO\s+P[ÚU]BLICO', 'Orçamento Público'),
        (r'CONTABILIDADE\s+P[ÚU]?BLICA', 'Contabilidade Pública'),
        (r'CONTABILIDADE\s+GERAL', 'Contabilidade Geral'),
        (r'CONTABILIDADE', 'Contabilidade'),
        (r'AUDITORIA', 'Auditoria'),
        (r'ESTAT[ÍI]?STICA', 'Estatística'),
        (r'ECONOMIA|FINAN[ÇC]AS\s+P[ÚU]BLICAS', 'Economia'),
        (r'ENGENHARIA\s+CIVIL', 'Engenharia Civil'),
        (r'ENGENHARIA\s+MEC[ÂA]NICA', 'Engenharia Mecânica'),
        (r'ENGENHARIA\s+EL[ÉE]TRICA', 'Engenharia Elétrica'),
        (r'ENGENHARIA', 'Engenharia'),
        (r'F[ÍI]?SICA', 'Física'),
        (r'QU[ÍI]?MICA', 'Química'),
        (r'BIOLOGIA', 'Biologia'),
        (r'L[ÍI]?NGUA\s+INGLESA|INGL[ÊE]?S', 'Língua Inglesa'),
        (r'L[ÍI]?NGUA\s+ESPANHOLA|ESPANHOL', 'Língua Espanhola'),
        (r'SEGURAN[ÇC]?A\s+P[ÚU]?BLICA', 'Segurança Pública'),
        (r'CRIMINOLOGIA', 'Criminologia'),
        (r'MEDICINA\s+LEGAL', 'Medicina Legal'),
        (r'ARQUIVOLOGIA', 'Arquivologia'),
        (r'RECURSOS\s+HUMANOS|GEST[ÃA]O\s+DE\s+PESSOAS', 'Recursos Humanos'),
        (r'PEDAGOGIA', 'Pedagogia'),
        (r'ENFERMAGEM', 'Enfermagem'),
        (r'MEDICINA', 'Medicina'),
        (r'SERVI[ÇC]O\s+SOCIAL', 'Serviço Social'),
        (r'PSICOLOGIA', 'Psicologia'),
        (r'ATUALIDADES', 'Atualidades'),
        (r'HIST[ÓO]RIA\s+E\s+GEOGRAFIA|HIST[ÓO]RIA|GEOGRAFIA', 'História e Geografia'),
        (r'BLOCO\s+([I|V|X\d]+)', r'Bloco \1'),
        (r'M[ÓO]DULO\s+([I|V|X\d]+)', r'Módulo \1'),
        (r'PARTE\s+([I|V|X\d]+)', r'Parte \1')
    ]
    for pat, canonical_name in canonicos:
        if re.search(pat, normalized_clean, re.IGNORECASE):
            if '\\1' in canonical_name:
                return re.sub(pat, canonical_name, normalized_clean, flags=re.IGNORECASE).strip()
            return canonical_name
    
    return normalized_clean.title() if normalized_clean else 'Geral'

def _extract_context_blocks(full_text):
    """
    Identifica blocos de textos de apoio compartilhados ('Texto para as questões X a Y')
    e mapeia os intervalos de questões afetados.
    Retorna uma lista de tuplas: (q_min, q_max, text_content)
    """
    context_blocks = []
    matches = list(CONTEXT_TEXT_HEADER_REGEX.finditer(full_text))
    
    for idx_m, m in enumerate(matches):
        try:
            q_min = int(m.group(1))
            q_max = int(m.group(2))
            if q_min > q_max or q_max - q_min > 50:
                continue
                
            header_start = m.start()
            # O texto base vai do fim do cabeçalho até o próximo cabeçalho ou primeira questão daquele bloco
            q_pattern = rf'(?:^|\n)\s*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)?0*{q_min}\s*(?:[\.\-\–\—\)]|\s+)'
            m_q = re.search(q_pattern, full_text[header_start:], re.IGNORECASE)
            
            if m_q:
                text_body = full_text[m.end():header_start + m_q.start()].strip()
                if len(text_body) >= 20:
                    context_blocks.append((q_min, q_max, text_body))
        except Exception:
            continue
            
    return context_blocks

def parse_exam_pdf_deterministic(pdf_bytes_or_path, exam_id=None, extract_images=True):
    """
    Motor determinístico avançado de extração, estruturação, leitura multi-coluna,
    deduplicação inteligente de imagens, OCR fallback e gabarito real.
    """
    if isinstance(pdf_bytes_or_path, (bytes, bytearray)):
        doc = fitz.open(stream=pdf_bytes_or_path, filetype='pdf')
    else:
        doc = fitz.open(pdf_bytes_or_path)

    total_pages = len(doc)
    if total_pages == 0:
        return []

    img_dir = os.path.join('static', 'images', 'questions')
    os.makedirs(img_dir, exist_ok=True)

    # 1. Identifica marcas d'água e rodapés repetidos
    watermarks = _detect_watermarks_and_headers(doc)

    # 2. Extrai gabarito global do documento se presente
    master_gabarito = _extract_gabarito_from_doc(doc)

    # 3. Localização dinâmica do início real da prova (descartando capas e instruções)
    start_page = 0
    for p_idx in range(min(6, total_pages)):
        p_text = doc[p_idx].get_text()
        if _is_instruction_or_blank_page(p_text):
            start_page = p_idx + 1
        else:
            # Página com conteúdo real encontrada
            start_page = p_idx
            break
            
    start_page = min(start_page, max(0, total_pages - 1))

    # 4. Extração geométrica e espacial com ordenação adaptativa de colunas
    raw_blocks = []
    page_diagrams = {} # {page_num: [Rect]}
    spatial_question_positions = []
    saved_image_hashes = {} # {md5_hash: relative_image_url}

    for p_idx in range(start_page, total_pages):
        page = doc[p_idx]
        p_text = page.get_text()
        
        # Ignora página final se for folha exclusiva de gabarito
        if p_idx >= max(1, total_pages - 2) and GABARITO_HEADER_REGEX.search(p_text):
            if not re.search(r'\b[A-E]\)\s+[A-Z\u00C0-\u00DC]', p_text):
                continue
                
        ordered_blocks = _extract_page_ordered_blocks(page, watermarks)
        
        for b in ordered_blocks:
            raw_blocks.append(b['text'])
            spatial_question_positions.append(b)

        # Agrupamento de diagramas/imagens da página com inclusão de legendas
        if extract_images:
            raw_page_blocks = page.get_text('blocks')
            clusters = _find_diagram_clusters(page, watermarks, text_blocks=raw_page_blocks)
            if clusters:
                page_diagrams[p_idx] = clusters

    full_text = '\n\n'.join(raw_blocks)

    # 5. Mapeia textos de apoio compartilhados (Textos de Apoio / Contexto)
    context_blocks = _extract_context_blocks(full_text)

    # 6. Busca sequencial rigorosa das questões (1 a 200+)
    # Padrão robusto para cabeçalho de questão com validação anti-instrução e anti-contador de linhas
    def find_question_header(target_num, search_from_pos):
        # 1. Padrão com 'QUESTÃO', 'ITEM' explícito
        pat_explicit = rf'(?:^|\n)\s*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)0*{target_num}\s*(?:[\.\-\–\—\:\)]|\n+|\s+(?=[A-Z\u00C0-\u00DC"“\'‘\(]))'
        
        # 2. Padrão numérico '1\n', '1. ', '01 - ' seguido de enunciado
        pat_num = rf'(?:^|\n)\s*0*{target_num}\s*(?:[\.\-\–\—\:\)]|\n+)\s*(?=[A-Z\u00C0-\u00DC"“\'‘\(])'
        
        candidates = []
        for m in re.finditer(pat_explicit, full_text[search_from_pos:], re.IGNORECASE):
            s_idx = search_from_pos + m.start()
            e_idx = search_from_pos + m.end()
            preview = full_text[e_idx:e_idx + 250].upper()
            if 'RECEBEU DO FISCAL' not in preview and 'CARTÃO-RESPOSTA' not in preview and 'TEMPO DISPONÍVEL' not in preview:
                candidates.append((s_idx, e_idx))
                break
                
        for m in re.finditer(pat_num, full_text[search_from_pos:]):
            s_idx = search_from_pos + m.start()
            e_idx = search_from_pos + m.end()
            preview = full_text[e_idx:e_idx + 250].upper()
            
            # Rejeita falsos positivos de instruções e blocos puros de numeração de linha
            if 'RECEBEU DO FISCAL' in preview or 'CARTÃO-RESPOSTA' in preview or 'TEMPO DISPONÍVEL' in preview:
                continue
            # Verifica se o texto após o número não é apenas outro número marginal (ex: 35 \n\n 40)
            next_lines = [l.strip() for l in full_text[e_idx:e_idx + 100].splitlines() if l.strip()]
            if next_lines and next_lines[0].isdigit() and len(next_lines[0]) <= 3:
                continue
                
            candidates.append((s_idx, e_idx))
            break
            
        if not candidates:
            return None
            
        candidates.sort(key=lambda x: x[0])
        return candidates[0]

    target = 1
    found_positions = []
    last_end = 0

    while target <= 200:
        match_info = find_question_header(target, last_end)
        if match_info:
            actual_start, actual_end = match_info
            found_positions.append((target, actual_start, actual_end))
            last_end = actual_end
            target += 1
        else:
            # Tenta tolerância de salto de 1 questão caso tenha havido falha de numeração
            match_skip = find_question_header(target + 1, last_end)
            if match_skip:
                actual_start, actual_end = match_skip
                found_positions.append((target + 1, actual_start, actual_end))
                last_end = actual_end
                target += 2
            else:
                break

    # 7. Estruturação de Enunciados, Alternativas, Disciplinas e Gabarito Real
    questions = []
    current_subject = 'Geral'
    used_diagrams = set() # {(page_idx, cluster_idx)}
    
    for i, (q_num, start_pos, end_pos) in enumerate(found_positions):
        next_start = found_positions[i+1][1] if i+1 < len(found_positions) else len(full_text)
        chunk = full_text[end_pos:next_start].strip()
        
        # Identificação de Matéria/Disciplina no prelúdio anterior à questão
        prev_end = found_positions[i-1][2] if i > 0 else 0
        prelude = full_text[prev_end:start_pos].strip()
        if prelude:
            for pline in prelude.split('\n'):
                pline_clean = pline.strip()
                if SUBJECT_REGEX.match(pline_clean):
                    current_subject = _format_subject_title(pline_clean)
        
        # Identificação de Matéria/Disciplina no topo do chunk da própria questão
        lines = chunk.split('\n')
        if lines:
            first_line = lines[0].strip()
            if SUBJECT_REGEX.match(first_line):
                current_subject = _format_subject_title(first_line)
                chunk = '\n'.join(lines[1:]).strip()
            elif len(lines) > 1 and SUBJECT_REGEX.match(lines[1].strip()):
                current_subject = _format_subject_title(lines[1].strip())
                chunk = '\n'.join([lines[0]] + lines[2:]).strip()

        # Extração de Gabarito Inline caso anotado na questão (ex: "Gabarito: C", "Resposta: A")
        inline_answer = None
        m_inline = re.search(r'\(?\s*(?:Correta|Gabarito|Resposta|Gabarito\s*Oficial)\s*[:=-]?\s*([A-Ea-eXNxn\*]|CERTO|ERRADO|C|E)\s*\)?', chunk, re.IGNORECASE)
        if m_inline:
            raw_ans = m_inline.group(1).upper()
            if raw_ans == 'CERTO':
                inline_answer = 'C'
            elif raw_ans == 'ERRADO':
                inline_answer = 'E'
            elif raw_ans in ['*', 'N']:
                inline_answer = 'X'
            else:
                inline_answer = raw_ans

        # Detectar se é questão de Múltipla Escolha (A, B, C, D, E) ou Cebraspe (Certo / Errado)
        opt_matches = list(re.finditer(r'(?:^|\n)\s*\(?\s*([A-E])\s*\)?\s*[\.\-\)]\s+', chunk))
        options = {}
        enunciado = chunk
        is_certo_errado = False
        
        if opt_matches and len(opt_matches) >= 2:
            first_opt_idx = opt_matches[0].start()
            enunciado = chunk[:first_opt_idx].strip()
            
            for o_idx, om in enumerate(opt_matches):
                letter = om.group(1).upper()
                s_val = om.end()
                e_val = opt_matches[o_idx + 1].start() if o_idx + 1 < len(opt_matches) else len(chunk)
                opt_content = chunk[s_val:e_val].strip()
                opt_content = re.sub(r'RASCUNHO.*', '', opt_content, flags=re.DOTALL).strip()
                options[letter] = opt_content
        else:
            # Estilo CEBRASPE / Assertiva Certo ou Errado
            is_certo_errado = True
            options = {'C': 'Certo', 'E': 'Errado'}

        # Limpeza de ruídos do enunciado
        enunciado = re.sub(r'RASCUNHO.*', '', enunciado, flags=re.DOTALL).strip()
        enunciado = re.sub(r'\(?\s*(?:Correta|Gabarito|Resposta|Gabarito\s*Oficial)\s*[:=-]?\s*(?:[A-Ea-eXNxn\*]|CERTO|ERRADO|C|E)\s*\)?', '', enunciado, flags=re.IGNORECASE).strip()
        
        # Injeção de Texto de Apoio / Contexto compartilhado
        matching_context = None
        for q_min, q_max, ctx_text in context_blocks:
            if q_min <= q_num <= q_max:
                matching_context = (q_min, q_max, ctx_text)
                break
                
        if matching_context:
            q_min, q_max, ctx_text = matching_context
            # Evita duplicar se o texto base já estiver presente no enunciado
            if ctx_text[:40] not in enunciado:
                enunciado = f"📖 **Texto de Apoio (Questões {q_min} a {q_max}):**\n\n{ctx_text}\n\n---\n\n{enunciado}"

        # Determinar a Resposta Real / Gabarito da Questão
        final_answer = None
        if q_num in master_gabarito:
            final_answer = master_gabarito[q_num]
        elif inline_answer:
            final_answer = inline_answer
        else:
            final_answer = 'C' if is_certo_errado else 'A'

        # 8. Vinculação Espacial de Imagens, Cropagem de Alta Definição e Deduplicação
        q_images = []
        has_trigger = bool(IMAGE_TRIGGER_REGEX.search(enunciado))
        
        approx_page = start_page
        for b in spatial_question_positions:
            if str(q_num) in b['text'][:15]:
                approx_page = b['page']
                break

        if has_trigger:
            pages_to_check = [approx_page]
            if approx_page + 1 < total_pages:
                pages_to_check.append(approx_page + 1)

            for p_target in pages_to_check:
                if p_target in page_diagrams:
                    for c_idx, cluster in enumerate(page_diagrams[p_target]):
                        diag_key = (p_target, c_idx)
                        if diag_key in used_diagrams:
                            continue

                        target_page_obj = doc[p_target]
                        pad = 8
                        crop_rect = fitz.Rect(
                            max(0, cluster.x0 - pad),
                            max(0, cluster.y0 - pad),
                            min(target_page_obj.rect.width, cluster.x1 + pad),
                            min(target_page_obj.rect.height, cluster.y1 + pad)
                        )

                        try:
                            # Renderiza com alta resolução (DPI 160)
                            pix = target_page_obj.get_pixmap(clip=crop_rect, dpi=160)
                            pix_bytes = pix.tobytes("png")
                            img_hash = hashlib.md5(pix_bytes).hexdigest()
                            
                            # Deduplicação inteligente de imagens/logos repetidos
                            if img_hash in saved_image_hashes:
                                rel_path = saved_image_hashes[img_hash]
                            else:
                                img_filename = f"qimg_exam{exam_id or 0}_q{q_num}_{len(q_images)+1}.png"
                                img_path = os.path.join(img_dir, img_filename)
                                with open(img_path, "wb") as f_img:
                                    f_img.write(pix_bytes)
                                rel_path = f"/static/images/questions/{img_filename}"
                                saved_image_hashes[img_hash] = rel_path

                            q_images.append(rel_path)
                            used_diagrams.add(diag_key)
                        except Exception as e:
                            print(f"[PDF Parser] Erro ao salvar crop do diagrama q{q_num}: {e}")

                        if len(q_images) >= 1 and not ('figura 2' in enunciado.lower() or 'quadro 2' in enunciado.lower()):
                            break

                if q_images:
                    break

        questions.append({
            'numero_questao': str(q_num),
            'enunciado': enunciado,
            'opcoes': options,
            'resposta': final_answer,
            'disciplina': current_subject,
            'images': q_images if q_images else None
        })

    doc.close()
    return questions
