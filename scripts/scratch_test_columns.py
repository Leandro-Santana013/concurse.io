import sys, os, fitz, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from services.pdf_pipeline.layout.layout_detector import extract_ocr_lines_from_page
from services.pdf_pipeline.media.vision_pipeline import segment_ocr_text

doc = fitz.open('pdfs/54_1788073221.pdf')

all_pages_stitched = []
for p_idx in range(len(doc)):
    page = doc[p_idx]
    lines = extract_ocr_lines_from_page(page, dpi=200)
    if not lines:
        continue
    
    clean_lines = []
    for l in lines:
        txt = l['text'].strip()
        if not txt or re.search(r'pcimarkpci|www\.pciconcursos\.com\.br|qconcursos\.com', txt, re.IGNORECASE):
            continue
        clean_lines.append({
            'x0': l['x0'], 'y0': l['y0'], 'x1': l['x1'], 'y1': l['y1'],
            'mid_x': l['mid_x'],
            'text': segment_ocr_text(txt)
        })
        
    page_w = page.rect.width
    mid_x = page_w / 2.0
    left = [l for l in clean_lines if l['mid_x'] < mid_x]
    right = [l for l in clean_lines if l['mid_x'] >= mid_x]
    
    def stitch_col(col_lines):
        col_lines.sort(key=lambda b: (round(b['y0'] / 6.0) * 6.0, b['x0']))
        stitched = []
        skip = set()
        for i in range(len(col_lines)):
            if i in skip:
                continue
            cur = dict(col_lines[i])
            for j in range(i + 1, min(i + 4, len(col_lines))):
                if j in skip:
                    continue
                nxt = col_lines[j]
                if abs(cur['y0'] - nxt['y0']) < 7 and (nxt['x0'] - cur['x1']) < 30:
                    cur['text'] = cur['text'].strip() + ' ' + nxt['text'].strip()
                    cur['x1'] = max(cur['x1'], nxt['x1'])
                    skip.add(j)
            stitched.append(cur)
        return stitched
        
    ordered = stitch_col(left) + stitch_col(right)
    all_pages_stitched.append((p_idx + 1, ordered))

q_header_re = re.compile(r'^\s*0*([1-9]|[1-4][0-9]|50)\s*[\.\-\–\—\)]\s*(.*)$')
blocks = []
cur_b = {'num': 0, 'lines': []}
for p_num, lines in all_pages_stitched:
    for l in lines:
        txt = l['text'].strip()
        m = q_header_re.match(txt)
        if m:
            if cur_b['lines'] or cur_b['num'] > 0:
                blocks.append(cur_b)
            cur_b = {'num': int(m.group(1)), 'lines': [m.group(2).strip()] if m.group(2).strip() else []}
        else:
            cur_b['lines'].append(txt)
if cur_b['lines'] or cur_b['num'] > 0:
    blocks.append(cur_b)

valid_blocks = [b for b in blocks if b['num'] > 0]
print(f"Total de questões detectadas com o novo algoritmo: {len(valid_blocks)}")
for b in valid_blocks[:12]:
    n = b['num']
    print(f"\n================ QUESTÃO {n} ================")
    for l in b['lines'][:6]:
        print("  >", l)
