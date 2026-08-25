import os, sys, fitz, json
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from services.pdf_pipeline import parse_exam_document
from services.pdf_pipeline.native.rust_bridge import rust_scan_question_headers

# Let's inspect AOCP and CESGRANRIO and CETRO
test_pdfs = [
    r"c:\Users\nicky\Downloads\provas_bancas\provas_bancas\AOCP\[AOCP] [2023] Instituto Aocp 2023 If Ma Assistente Em Administracao Prova.pdf",
    r"c:\Users\nicky\Downloads\provas_bancas\provas_bancas\CESGRANRIO\[CESGRANRIO] Baseado no formato de prova aplicado pela banca Cesgranrio.pdf",
    r"c:\Users\nicky\Downloads\provas_bancas\provas_bancas\CETRO\[CETRO] Caderno de Provas.pdf"
]

for p in test_pdfs:
    if not os.path.exists(p):
        continue
    print(f"\n==========================================")
    print(f"Inspecting: {os.path.basename(p)}")
    doc = fitz.open(p)
    print(f"Total pages: {len(doc)}")
    
    # Check what headers rust_scan_question_headers finds
    raw_text = ""
    for page in doc:
        raw_text += page.get_text() + "\n"
        
    rust_headers = rust_scan_question_headers(raw_text)
    print(f"Rust headers found on raw text: {len(rust_headers or [])}")
    if rust_headers:
        print(f"  Numbers: {[h['number'] for h in rust_headers]}")
        
    qs = parse_exam_document(p, exam_id=1, extract_images=False)
    print(f"Pipeline questions extracted: {len(qs)}")
    if qs:
        print(f"  Pipeline numbers: {[q.get('numero_questao') for q in qs]}")
        sample_q = qs[0]
        print(f"  Q1 Options: {sample_q.get('opcoes')}")
