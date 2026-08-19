import re
import fitz
from services.pdf_parser import _extract_gabarito_from_doc, _get_rapidocr_engine

def parse_gabarito_from_text(raw_text):
    """
    Interpreta gabaritos inseridos como texto ou extraídos de PDF em múltiplos formatos:
      - "1-A, 2-B, 3-C, 4-D, 5-E"
      - "1.A 2.B 3.C 4.D"
      - "Questão 01: A\nQuestão 02: B"
      - "01 A\n02 B\n03 C"
      - "1 C 21 A 41 X\n2 D 22 C 42 E" (Tabelas multi-coluna)
      - "1 C 2 E 3 C 4 E" (CEBRASPE)
      - "1 CERTO 2 ERRADO"
      - Marcações de anulação: X, N, *, ANULADA
      
    Retorna um dicionário: {1: 'A', 2: 'B', 3: 'C', ..., 40: 'X'} com números inteiros e respostas padronizadas.
    """
    if not raw_text or not isinstance(raw_text, str):
        return {}

    gabarito = {}
    clean_text = raw_text.strip()

    # Normalizações para Certo / Errado e Anulações
    clean_text = re.sub(r'\bCERTO\b', 'C', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\bERRADO\b', 'E', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\b(?:ANULAD[AO]|NUL[AO]|CANCELAD[AO])\b', 'X', clean_text, flags=re.IGNORECASE)

    # 1. Padrão com separador explícito: 1-A, 1:A, 1.A, 1) A, Questão 1: A, 01 - X, 1: *
    matches = re.findall(r'(?:QUEST[ÃA]O\s*|ITEM\s*)?(\d{1,3})\s*(?:[\.\-–—:\)]|\s+)\s*([A-Ea-eXNxn\*])(?![A-Za-z0-9])', clean_text)
    for num_str, ans in matches:
        try:
            num = int(num_str)
            if 1 <= num <= 200:
                gabarito[num] = ans.upper() if ans != '*' else 'X'
        except ValueError:
            pass

    if len(gabarito) >= 1:
        return gabarito

    # 2. Padrão de blocos tabulares ou sequenciais (ex: "1 C 21 A 41 X 2 D 22 C 42 E")
    tokens = [t.strip('.-:()[]') for t in clean_text.split() if t.strip('.-:()[]')]
    i = 0
    while i < len(tokens) - 1:
        tok1 = tokens[i]
        tok2 = tokens[i+1].upper()
        if tok1.isdigit() and (tok2 in ['A', 'B', 'C', 'D', 'E', 'X', 'N', '*'] or tok2 in ['CERTO', 'ERRADO']):
            num = int(tok1)
            if 1 <= num <= 200:
                ans_norm = 'C' if tok2 == 'CERTO' else ('E' if tok2 == 'ERRADO' else ('X' if tok2 in ['*', 'N'] else tok2))
                gabarito[num] = ans_norm
            i += 2
        else:
            i += 1

    if len(gabarito) >= 1:
        return gabarito

    # 3. Padrão matricial horizontal: Linha com números seguida por linha com letras
    lines = [l.strip() for l in clean_text.splitlines() if l.strip()]
    for idx_l in range(len(lines) - 1):
        row_nums = re.findall(r'\b\d{1,3}\b', lines[idx_l])
        row_ans = re.findall(r'\b[A-Ea-eXNxn]\b', lines[idx_l+1])
        if len(row_nums) >= 2 and len(row_nums) == len(row_ans):
            for n_str, a_str in zip(row_nums, row_ans):
                n_val = int(n_str)
                if 1 <= n_val <= 200:
                    gabarito[n_val] = a_str.upper()

    if len(gabarito) >= 1:
        return gabarito

    # 4. Padrão sequencial de linhas isoladas ('01\tA' ou '01   C')
    for line in lines:
        parts = re.split(r'[\t\s,;]+', line.strip())
        if len(parts) >= 2 and parts[0].isdigit():
            ans_cand = parts[1].upper()
            if ans_cand in ['A', 'B', 'C', 'D', 'E', 'X', 'N', '*']:
                gabarito[int(parts[0])] = 'X' if ans_cand in ['*', 'N'] else ans_cand

    return gabarito

def parse_gabarito_from_pdf(pdf_input):
    """
    Extrai gabarito oficial de um arquivo PDF avulso ou folha de respostas.
    Suporta tabelas estruturadas, layout em colunas e OCR caso o PDF seja escaneado.
    """
    doc = None
    should_close = False
    
    if isinstance(pdf_input, fitz.Document):
        doc = pdf_input
    elif isinstance(pdf_input, (bytes, bytearray)):
        doc = fitz.open(stream=pdf_input, filetype="pdf")
        should_close = True
    elif isinstance(pdf_input, str):
        doc = fitz.open(pdf_input)
        should_close = True
    else:
        return {}

    try:
        # 1. Tenta extrair com o extrator determinístico integrado
        gabarito = _extract_gabarito_from_doc(doc)
        if gabarito and len(gabarito) >= 5:
            return gabarito

        # 2. Se não encontrou, faz varredura textual direta em todas as páginas
        full_text = ""
        for page in doc:
            full_text += "\n" + page.get_text()

        text_gabarito = parse_gabarito_from_text(full_text)
        if text_gabarito and len(text_gabarito) >= 5:
            return text_gabarito

        # 3. Se for PDF escaneado (sem texto), aplica RapidOCR
        engine = _get_rapidocr_engine()
        if engine and len(doc) <= 5:
            ocr_text = ""
            for page in doc:
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                results, _ = engine(img_bytes)
                if results:
                    for item in results:
                        _, text, score = item
                        if score >= 0.35 and text.strip():
                            ocr_text += " " + text
            
            ocr_gabarito = parse_gabarito_from_text(ocr_text)
            if ocr_gabarito:
                return ocr_gabarito

        return gabarito or {}
    finally:
        if should_close and doc:
            doc.close()

def merge_exam_with_gabarito(questions, gabarito_dict):
    """
    Cruza a lista de questões extraídas do caderno com o gabarito oficial.
    
    Parâmetros:
      - questions: lista de dicts de questões [{'numero_questao': 1, 'enunciado': '...', 'opcoes': {...}, 'resposta': 'A'}, ...]
      - gabarito_dict: dict {1: 'A', 2: 'C', 3: 'B', ...}
      
    Retorna:
      - updated_questions: lista de questões atualizadas com o gabarito real e flags de cobertura.
      - stats: dict {
            "total_questions": int,
            "matched_answers": int,
            "coverage_pct": float,
            "has_official_answers": bool
        }
    """
    if not questions:
        return [], {"total_questions": 0, "matched_answers": 0, "coverage_pct": 0.0, "has_official_answers": False}

    gabarito_dict = gabarito_dict or {}
    matched_count = 0
    updated_questions = []

    for idx, q in enumerate(questions, start=1):
        q_copy = dict(q)
        q_num = q_copy.get('numero_questao') or idx
        
        # Tenta casar pelo número da questão ou pelo índice sequencial
        official_ans = gabarito_dict.get(q_num) or gabarito_dict.get(idx)
        
        if official_ans:
            q_copy['resposta'] = str(official_ans).upper()
            q_copy['has_official_answer'] = True
            matched_count += 1
        else:
            q_copy['has_official_answer'] = False
            # Mantém resposta original se já existia, ou 'A' se não definida
            if not q_copy.get('resposta'):
                q_copy['resposta'] = 'A'

        updated_questions.append(q_copy)

    total = len(questions)
    coverage = round((matched_count / total) * 100, 1) if total > 0 else 0.0
    has_official = coverage >= 50.0

    stats = {
        "total_questions": total,
        "matched_answers": matched_count,
        "coverage_pct": coverage,
        "has_official_answers": has_official
    }

    return updated_questions, stats

def format_gabarito_summary(gabarito_dict):
    """Gera uma representação textual concisa do gabarito (ex: 1-A | 2-B | 3-C)."""
    if not gabarito_dict:
        return ""
    sorted_items = sorted(gabarito_dict.items(), key=lambda x: x[0])
    return " | ".join([f"{num}-{ans}" for num, ans in sorted_items])
