import os, sys
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import os
import sys
import fitz

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath('.'))
from scripts.audits.audit_live_extraction import audit_pdf_extraction

test_files = [
    ("provas_bancas/IDCAP/[IDCAP] [2024] 2024 Prefeitura De Santa Leopoldina Es Assistente Social Prova.pdf", "IDCAP"),
    ("provas_bancas/IDECAN/[IDECAN] [2023] 2023 Sefaz Rr Implementador De Software Prova.pdf", "IDECAN"),
    ("provas_bancas/IBAM/[IBAM] Assistente_Social.pdf", "IBAM"),
]

for path, banca in test_files:
    if os.path.exists(path):
        audit_pdf_extraction(path, banca)
    else:
        print(f"Não encontrado: {path}")
