import re
import fitz

GABARITO_HEADER_REGEX = re.compile(r'\b(gabarito|folha\s+de\s+respostas?|quadro\s+de\s+respostas?|respostas?\s+das?\s+quest[õo]es|gabarito\s+oficial|gabarito\s+preliminar|gabarito\s+definitivo)\b', re.IGNORECASE)

def extract_gabarito_from_doc(doc):
    """
    Varre o documento em busca de tabelas, seções ou linhas de gabarito (incluindo páginas escaneadas).
    Retorna um dicionário {numero_questao_int: 'A'|'B'|'C'|'D'|'E'|'X'|'C'|'E'}.
    """
    from services.pdf_pipeline.media.diagram_cropper import ocr_page_fallback
    gabarito_map = {}
    total_pages = len(doc)
    if total_pages == 0:
        return gabarito_map

    pages_to_scan = list(range(total_pages - 1, -1, -1))

    for p_idx in pages_to_scan:
        page = doc[p_idx]
        text = page.get_text()
        if len(text.strip()) < 30:
            ocr_b = ocr_page_fallback(page)
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

# Alias
_extract_gabarito_from_doc = extract_gabarito_from_doc

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
      - Marcações de anulação: X, N, *, ANULADA, CANCELADA, NULA
      
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

    if len(gabarito) >= 1:
        return gabarito

    # 5. Padrão sequencial de letras em coluna (banca IBAM / Vunesp / FCC)
    # Detecta blocos contínuos de letras únicas (ex: 40 respostas A..E de um cargo)
    current_chunk = []
    best_chunk = []
    for line in lines:
        t = line.strip().upper()
        if len(t) == 1 and t in ['A', 'B', 'C', 'D', 'E', 'X', 'N', '*']:
            current_chunk.append('X' if t in ['*', 'N'] else t)
        else:
            if len(current_chunk) > len(best_chunk):
                best_chunk = current_chunk
            current_chunk = []
    if len(current_chunk) > len(best_chunk):
        best_chunk = current_chunk

    if len(best_chunk) >= 10:
        for idx_seq, l_ans in enumerate(best_chunk, start=1):
            gabarito[idx_seq] = l_ans

    return gabarito

def parse_gabarito_from_pdf(pdf_input):
    """
    Extrai gabarito oficial de um arquivo PDF avulso ou folha de respostas.
    Utiliza primeiramente extração estruturada de tabelas nativa (find_tables),
    seguida por layout parser e OCR caso seja escaneado.
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
        gabarito = {}

        # 1. Extração Estruturada via PyMuPDF Table Extractor (find_tables)
        for page in doc:
            if hasattr(page, 'find_tables'):
                try:
                    tabs = page.find_tables()
                    for table in tabs.tables:
                        extracted = table.extract()
                        if not extracted or len(extracted) < 2:
                            continue

                        # A) Extração Matricial Horizontal (Padrão IBAM: cabeçalho '01 02 ... 40', linhas com cargos e respostas)
                        header_row = extracted[0]
                        q_cols = []
                        for col_i, cell in enumerate(header_row):
                            if cell and str(cell).strip().isdigit():
                                q_cols.append((col_i, int(str(cell).strip())))

                        if len(q_cols) >= 5:
                            for row in extracted[1:]:
                                row_answers = {}
                                for col_i, q_num in q_cols:
                                    if col_i < len(row) and row[col_i]:
                                        ans_val = str(row[col_i]).strip().upper()
                                        if ans_val in ['A', 'B', 'C', 'D', 'E', 'X', 'N', '*', 'CERTO', 'ERRADO', 'C', 'E']:
                                            norm_ans = 'C' if ans_val == 'CERTO' else ('E' if ans_val == 'ERRADO' else ('X' if ans_val in ['*', 'N'] else ans_val))
                                            row_answers[q_num] = norm_ans
                                if len(row_answers) >= len(gabarito):
                                    gabarito = row_answers

                        # B) Extração Vertical Multi-Coluna (Padrão [Q1, R1, Q21, R21])
                        for row in extracted:
                            if not row or len(row) < 2:
                                continue
                            for c_idx in range(0, len(row) - 1, 2):
                                col_q = str(row[c_idx] or '').strip()
                                col_a = str(row[c_idx + 1] or '').strip().upper()
                                
                                if col_q.isdigit():
                                    q_num = int(col_q)
                                    if col_a in ['A', 'B', 'C', 'D', 'E', 'X', 'N', '*', 'CERTO', 'ERRADO', 'C', 'E']:
                                        norm_ans = 'C' if col_a == 'CERTO' else ('E' if col_a == 'ERRADO' else ('X' if col_a in ['*', 'N'] else col_a))
                                        gabarito[q_num] = norm_ans
                except Exception as e:
                    print(f"[Gabarito Table Warning] {e}")

        if gabarito and len(gabarito) >= 5:
            return gabarito

        # 2. Tenta extrair com o extrator determinístico integrado
        gabarito_fallback = _extract_gabarito_from_doc(doc)
        if gabarito_fallback and len(gabarito_fallback) >= 5:
            return gabarito_fallback

        # 3. Se não encontrou, faz varredura textual direta em todas as páginas
        full_text = ""
        for page in doc:
            full_text += "\n" + page.get_text()

        text_gabarito = parse_gabarito_from_text(full_text)
        if text_gabarito and len(text_gabarito) >= 5:
            return text_gabarito

        # 4. Se for PDF escaneado (sem texto), aplica RapidOCR
        from services.pdf_pipeline.media.diagram_cropper import _get_rapidocr_engine
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
    """
    if not questions:
        return [], {"total_questions": 0, "matched_answers": 0, "coverage_pct": 0.0, "has_official_answers": False}

    gabarito_dict = gabarito_dict or {}
    matched_count = 0
    updated_questions = []

    for idx, q in enumerate(questions, start=1):
        q_copy = dict(q)
        q_num = q_copy.get('numero_questao') or idx
        try:
            q_num_int = int(q_num)
        except Exception:
            q_num_int = idx
            
        official_ans = gabarito_dict.get(q_num_int) or gabarito_dict.get(idx) or gabarito_dict.get(str(q_num))
        
        if official_ans:
            q_copy['resposta'] = str(official_ans).upper()
            q_copy['has_official_answer'] = True
            matched_count += 1
        else:
            q_copy['has_official_answer'] = False
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
    sorted_items = sorted(gabarito_dict.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999)
    return " | ".join([f"{num}-{ans}" for num, ans in sorted_items])
