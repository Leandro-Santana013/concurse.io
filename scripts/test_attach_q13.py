import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
from services.pdf_pipeline.media import ExamImageExtractor
from services.pdf_pipeline.layout import detect_watermarks
from services.pdf_pipeline import parse_exam_document

doc = fitz.open('pdfs/56_1788095849.pdf')
qs = parse_exam_document('pdfs/56_1788095849.pdf', extract_images=True)
for q in qs:
    if int(q['numero_questao']) in [12, 13, 14, 17, 18, 20]:
        print(f"Q#{q['numero_questao']} images: {q.get('images')}")
        print(f"Statement snippet: {repr(q.get('enunciado')[:120])}")
        print()
