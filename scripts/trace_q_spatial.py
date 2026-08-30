import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
from services.pdf_pipeline.media import ExamImageExtractor
from services.pdf_pipeline.layout import detect_watermarks, detect_layout_and_ordered_blocks
from services.pdf_pipeline.hybrid_extractor import parse_exam_document

doc = fitz.open('pdfs/56_1788095849.pdf')
watermarks = detect_watermarks(doc)
extractor = ExamImageExtractor(
    output_dir="static/images/questions",
    dpi=160,
    padding=8,
    min_cluster_size=25,
    min_cluster_area=400,
    watermark_page_threshold=3
)

# Let's inspect q_spatial_map
q_spatial_map = {}
for p_idx in range(len(doc)):
    page = doc[p_idx]
    for b in page.get_text('blocks'):
        bx0, by0, bx1, by1, b_text = b[:5]
        import re
        for hm in re.finditer(r'(?:^|\n)\s*(?:QUEST[AÃ\ufffd\?]?O|ITEM)\s*(0*\d{1,3})\b', b_text, re.IGNORECASE):
            num_val = int(hm.group(1))
            if num_val not in q_spatial_map:
                q_spatial_map[num_val] = (p_idx, bx0, by0)

for q_n in [11, 12, 13, 14, 15, 16, 17, 18]:
    print(f"Q#{q_n} spatial map: {q_spatial_map.get(q_n)}")

p3_clusters = extractor.find_diagram_clusters(doc[3], watermarks, text_blocks=doc[3].get_text('blocks'))
print("\nClusters on page 4 (doc[3]):")
for c in p3_clusters:
    print("Cluster:", c, "Center:", (c.x0+c.x1)/2, (c.y0+c.y1)/2)
