import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
from services.pdf_pipeline.media import ExamImageExtractor
from services.pdf_pipeline.layout import detect_watermarks, detect_layout_and_ordered_blocks

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

page_raw_blocks = doc[3].get_text('blocks')
clusters = extractor.find_diagram_clusters(doc[3], watermarks, text_blocks=page_raw_blocks)
print(f"Page 4 (doc[3]) clusters found with default extractor settings: {clusters}")
