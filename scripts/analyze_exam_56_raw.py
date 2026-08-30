import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
import re
from services.pdf_pipeline.layout import detect_layout_and_ordered_blocks, detect_watermarks
from services.pdf_pipeline.media import ExamImageExtractor

doc = fitz.open('pdfs/56_1788095849.pdf')
watermarks = detect_watermarks(doc)

print(f"Total pages: {len(doc)}")
for p_idx in range(len(doc)):
    page = doc[p_idx]
    print(f"\n==================== PAGE {p_idx+1} ====================")
    print(f"Rect: {page.rect}")
    drawings = page.get_drawings()
    images = page.get_images()
    print(f"Drawings: {len(drawings)} | Images: {len(images)}")
    
    # Check tables
    if hasattr(page, 'find_tables'):
        tabs = page.find_tables()
        table_list = tabs.tables if hasattr(tabs, 'tables') else list(tabs)
        print(f"Tables found by PyMuPDF: {len(table_list)}")
        for t_idx, tab in enumerate(table_list):
            print(f"   Table {t_idx} bbox: {tab.bbox}")
            print(f"   Table {t_idx} markdown:\n{tab.to_markdown()}")
            
    blocks = detect_layout_and_ordered_blocks(page, watermarks)
    print(f"Ordered text blocks ({len(blocks)}):")
    for b_idx, b in enumerate(blocks):
        print(f"--- Block {b_idx} (bbox: {b.get('bbox', 'N/A')}) ---")
        print(b['text'])
