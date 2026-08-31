import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
from services.pdf_pipeline.media import ExamImageExtractor
from services.pdf_pipeline.layout import detect_watermarks

doc = fitz.open('pdfs/56_1788095849.pdf')
watermarks = detect_watermarks(doc)
extractor = ExamImageExtractor(
    output_dir="static/images/questions",
    dpi=160,
    padding=8,
    min_cluster_size=10,
    min_cluster_area=200
)

for p_idx in range(len(doc)):
    page = doc[p_idx]
    clusters = extractor.find_diagram_clusters(page, watermarks, text_blocks=page.get_text('blocks'))
    print(f"=== Page {p_idx+1} Clusters: {len(clusters)} ===")
    for c in clusters:
        print(f"   Cluster: {c}")

print("\n--- Direct Drawings on Page 4 ---")
p4 = doc[3] # 0-indexed page 4
drawings = p4.get_drawings()
print(f"Page 4 has {len(drawings)} drawings:")
for d_i, d in enumerate(drawings):
    r = d['rect']
    print(f"  Drawing {d_i}: rect={r}, items={len(d.get('items', []))}")
