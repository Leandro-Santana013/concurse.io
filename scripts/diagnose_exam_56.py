import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz
from services.gabarito import parse_gabarito_from_pdf
from models.database import Session, Exam, Question
import json

print("=== INSPECTING GABARITO PDF ===")
doc_gab = fitz.open('pdfs/56_gab_1788095849.pdf')
for p in range(len(doc_gab)):
    print(f"--- Gabarito Page {p+1} ---")
    print(doc_gab[p].get_text())

print("=== PARSED GABARITO DICT ===")
gab = parse_gabarito_from_pdf('pdfs/56_gab_1788095849.pdf')
print(f"Gabarito extracted: {len(gab)} entries:")
print(gab)

print("\n=== CURRENT QUESTIONS IN DATABASE FOR EXAM 56 ===")
with Session() as s:
    exam = s.query(Exam).filter_by(id=56).first()
    print(f"Exam: {exam.title} | Coverage: {exam.gabarito_coverage}%")
    qs = s.query(Question).filter_by(exam_id=56).order_by(Question.id).all()
    print(f"Total questions in DB: {len(qs)}")
    for q in qs:
        opts = json.loads(q.options)
        imgs = json.loads(q.images) if q.images else None
        print(f"Q#{q.numero_questao} (ID: {q.id}) | Gab: {q.correct_answer} | Opts: {list(opts.keys())} | Imgs: {imgs}")
        lines = q.statement.strip().splitlines()
        for l in lines[:4]:
            print(f"   {l[:100]}")
        if len(lines) > 4:
            print("   ...")
        print()
