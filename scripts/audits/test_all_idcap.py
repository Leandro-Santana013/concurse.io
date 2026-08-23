import os, sys
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import os
import sys
import glob

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath('.'))
from scripts.audits.audit_live_extraction import audit_pdf_extraction

idcap_pdfs = glob.glob("provas_bancas/IDCAP/*.pdf")
print(f"Encontrados {len(idcap_pdfs)} arquivos PDF da banca IDCAP.")

for pdf_path in idcap_pdfs:
    audit_pdf_extraction(pdf_path, "IDCAP")
