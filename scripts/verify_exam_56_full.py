import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
from services.pdf_pipeline import parse_exam_document
from services.gabarito import parse_gabarito_from_pdf, merge_exam_with_gabarito

pdf_path = 'pdfs/56_1788095849.pdf'
gab_path = 'pdfs/56_gab_1788095849.pdf'

gab_dict = parse_gabarito_from_pdf(gab_path, cargo_or_title='Agente Comunitário de Saúde')
print(f"Gabarito parsed: {len(gab_dict)} answers")
print(gab_dict)

qs = parse_exam_document(pdf_path, exam_id=56, extract_images=True)
updated_qs, stats = merge_exam_with_gabarito(qs, gab_dict)

print(f"\nStats: {stats}")
print(f"Total extracted questions: {len(updated_qs)}")

for q in updated_qs:
    q_num = q['numero_questao']
    has_text = "Texto de Apoio" in q['enunciado']
    imgs = q.get('images')
    opts = q.get('opcoes', {})
    print(f"Q#{q_num:2s} | Gab: {q['resposta']} | Imgs: {imgs} | TextApoio: {has_text} | Opt keys: {list(opts.keys())}")
    for opt_k, opt_v in opts.items():
        if opt_v.startswith(('A (', 'B (', 'C (', 'D (', '(A)', '(B)')) or 'PORTUGUÊS' in opt_v or 'MATEMÁTICA' in opt_v:
            print(f"   [WARNING] Option ({opt_k}): {repr(opt_v[:80])}")

print("\n--- Detailed checks on key questions ---")
for target in [13, 17, 18, 20, 21, 28]:
    for q in updated_qs:
        if int(q['numero_questao']) == target:
            print(f"\n==================== QUESTÃO {target} ====================")
            print("ENUNCIADO:")
            print(q['enunciado'])
            print("OPÇÕES:")
            for k, v in q['opcoes'].items():
                print(f"  ({k}) {v}")
            print("IMAGES:", q.get('images'))
            print("GABARITO:", q.get('resposta'))
