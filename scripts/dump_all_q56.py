import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
from services.pdf_pipeline import parse_exam_document

qs = parse_exam_document('pdfs/56_1788095849.pdf', extract_images=True)
print(f"Total extracted questions: {len(qs)}")
for q in qs:
    print(f"==================== Q#{q['numero_questao']} ====================")
    print("ENUNCIADO:")
    print(q['enunciado'])
    print("OPÇÕES:")
    for k, v in q.get('opcoes', {}).items():
        print(f"  ({k}) {v}")
    print("IMAGES:", q.get('images'))
    print("GABARITO:", q.get('resposta'))
    print()
