import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
import re
from services.pdf_pipeline.layout import detect_layout_and_ordered_blocks, detect_watermarks, extract_context_blocks

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

ctxs = extract_context_blocks(full_text)
print(f"Context blocks found: {len(ctxs)}")
for c in ctxs:
    print(f"Range: Q{c[0]} - Q{c[1]} (length: {len(c[2])})")
    print(f"Text snippet: {repr(c[2][:150])}")
    print("---")
