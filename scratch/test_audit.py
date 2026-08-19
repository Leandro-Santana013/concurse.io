import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import glob
import fitz
from services.pdf_inspector import inspect_pdf_document
from services.pdf_parser import parse_exam_pdf_deterministic
from services.gabarito_service import parse_gabarito_from_pdf

pdf_files = glob.glob('pdfs/*.pdf')
print(f'Total PDFs: {len(pdf_files)}')
for p in sorted(pdf_files):
    sz = os.path.getsize(p)
    if sz < 100:
        continue
    try:
        doc = fitz.open(p)
        pages = len(doc)
        insp = inspect_pdf_document(p)
        print(f"\n[FILE] {os.path.basename(p)} ({sz} bytes, {pages} pages) -> Type: {insp['doc_type']}")
        
        if 'gab' in p.lower() or insp['doc_type'] == 'ANSWER_KEY_ONLY':
            gab = parse_gabarito_from_pdf(p)
            print(f"   -> Gabarito extraído ({len(gab)} itens): {list(gab.items())[:10]}")
        else:
            qs = parse_exam_pdf_deterministic(p, extract_images=False)
            print(f"   -> Extraiu {len(qs)} questoes.")
            if qs:
                subjects = set(q.get('disciplina', 'Geral') for q in qs)
                print(f"      Disciplinas identificadas ({len(subjects)}): {subjects}")
                print(f"      Q1 Enunciado[:80]: {repr(qs[0]['enunciado'][:80])}")
                print(f"      Q1 Opcoes: {list(qs[0]['opcoes'].keys()) if qs[0].get('opcoes') else 'N/A'}")
                print(f"      Q1 Resposta: {qs[0].get('resposta')}")
                if len(qs) > 1:
                    print(f"      Q_ult ({qs[-1]['numero_questao']}) Enunciado[:80]: {repr(qs[-1]['enunciado'][:80])}")
    except Exception as e:
        print(f"   -> Erro: {e}")
