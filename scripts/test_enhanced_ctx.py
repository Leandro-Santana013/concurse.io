import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
import re
from services.pdf_pipeline.layout import detect_layout_and_ordered_blocks, detect_watermarks

doc = fitz.open('pdfs/56_1788095849.pdf')
watermarks = detect_watermarks(doc)
raw_blocks = []
for p in range(len(doc)):
    blocks = detect_layout_and_ordered_blocks(doc[p], watermarks)
    for b in blocks:
        raw_blocks.append(b['text'])
full_text = '\n\n'.join(raw_blocks)

full_text = re.sub(r'(?m)^\s*(?:[A-ZÁ-Ú\s\-]+[–—\-]\s*)?\d{1,2}\s*$', '', full_text)
full_text = re.sub(r'(?m)^\s*[A-ZÁ-Ú\s]{3,35}\s*[-–—]\s*\d+\s*$', '', full_text)
full_text = re.sub(r'\n{3,}', '\n\n', full_text)

# Let's test enhanced context blocks
from services.pdf_pipeline.layout.layout_detector import CONTEXT_TEXT_HEADER_REGEX

def enhanced_extract_context_blocks(full_text, found_positions=None):
    context_blocks = []
    matches = list(CONTEXT_TEXT_HEADER_REGEX.finditer(full_text))
    q_map = {item[0]: item[1] for item in (found_positions or [])}
    
    # 1. Padrão explícito com indicação de questões
    for m in matches:
        banner_text = m.group(0)
        nums = [int(n) for n in re.findall(r'\b\d{1,3}\b', banner_text) if 1 <= int(n) <= 200]
        if len(nums) >= 2:
            q_min = min(nums)
            q_max = max(nums)
            if q_min > q_max or q_max - q_min > 50:
                continue
            banner_start = m.start()
            banner_end = m.end()
            
            q_target_start = q_map.get(q_min)
            if q_target_start and q_target_start > banner_end:
                text_body = full_text[banner_end:q_target_start].strip()
                if len(text_body) >= 10:
                    context_blocks.append((q_min, q_max, text_body, banner_start))
                    continue
            
            q_pattern = rf'(?:^|\n)[ \t]*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)0*{q_min}\b'
            m_q = re.search(q_pattern, full_text[banner_end:], re.IGNORECASE)
            if not m_q:
                q_pattern = rf'(?:^|\n)[ \t]*0*{q_min}\s*[\.\-\–\—\:\)]'
                m_q = re.search(q_pattern, full_text[banner_end:], re.IGNORECASE)
            if m_q:
                text_body = full_text[banner_end:banner_end + m_q.start()].strip()
                if len(text_body) >= 10:
                    context_blocks.append((q_min, q_max, text_body, banner_start))

    # 2. Padrão de seção com TEXTO: <TÍTULO> antes de uma questão (ex: "PORTUGUÊS TEXTO: FURACÃO IRMA...")
    section_text_pat = re.compile(
        r'(?:^|\n)\s*(?:(?:PORTUGU[ÊE]S|L[ÍI]NGUA\s+PORTUGUESA)\s+)?TEXTO\s*(?:\([^\)]*\)|[I|V|X\d]+)?\s*[:\-–—]\s*([A-ZÁ-Ú\s0-9\-\.\,]{4,60})(?=\n|$)',
        re.IGNORECASE
    )
    for sm in section_text_pat.finditer(full_text):
        b_start = sm.start()
        # Encontra a primeira questão logo após este texto
        m_next_q = re.search(r'(?:^|\n)\s*(?:QUEST[AÃ\ufffd\?]?O\s+|ITEM\s+)(0*\d{1,3})\b', full_text[sm.end():], re.IGNORECASE)
        if m_next_q:
            first_q_num = int(m_next_q.group(1))
            text_body = full_text[sm.start():sm.end() + m_next_q.start()].strip()
            # Remove o cabeçalho inicial de matéria se houver
            text_body = re.sub(r'^(?:PORTUGU[ÊE]S|L[ÍI]NGUA\s+PORTUGUESA)\s+', '', text_body, flags=re.IGNORECASE).strip()
            
            # Limite superior: até o próximo contexto ou +7 questões
            max_q = first_q_num + 6
            for c in context_blocks:
                if c[0] > first_q_num and c[0] <= max_q:
                    max_q = c[0] - 1
            if len(text_body) >= 50 and not any(c[0] == first_q_num for c in context_blocks):
                context_blocks.append((first_q_num, max_q, text_body, b_start))

    return context_blocks

ctx_res = enhanced_extract_context_blocks(full_text)
print(f"Total context blocks: {len(ctx_res)}")
for c in ctx_res:
    print(f"Range: Q{c[0]} - Q{c[1]}")
    print(f"Text snippet: {repr(c[2][:160])}")
    print("---")
