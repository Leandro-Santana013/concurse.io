#!/usr/bin/env python3
"""
concurse.io — Utilitário de Preparação do Corpus a partir de PDFs Brutos
Converte PDFs colocados em 'training_corpus/pdfs/' em arquivos JSON estruturados para o otimizador genético.
"""

import os
import sys
import json
import re
from typing import List, Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERRO] PyMuPDF (fitz) não está instalado. Instale com: pip install PyMuPDF")
    sys.exit(1)


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrai todo o texto legível de um PDF folha a folha."""
    doc = fitz.open(pdf_path)
    full_text_parts = []
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text("text")
        full_text_parts.append(text)
    doc.close()
    return "\n--- PAGE BREAK ---\n".join(full_text_parts)


def detect_banca_from_filename(filename: str) -> str:
    """Detecta a banca examinadora pelo nome do arquivo."""
    name_upper = filename.upper()
    bancas = [
        "FGV", "CEBRASPE", "CESPE", "FCC", "VUNESP", "CESGRANRIO",
        "QUADRIX", "IBFC", "AOCP", "IDECAN", "IDCAP", "CONSULPAM",
        "SELECON", "FUNDATEC"
    ]
    for b in bancas:
        if b in name_upper:
            return b
    return "DESCONHECIDA"


def estimate_expected_headers(text: str) -> List[str]:
    """Extrai uma estimativa de cabeçalhos de questão para servir de baseline inicial."""
    pattern = re.compile(
        r"(?i)(?:^|\n)\s*(?:(?:QUEST[ÃA]?O|ITEM|Quest[ãa]o|Q\.)\s*|)(\d{1,3})(?:[\.\-\–\)]|\s*–\s*|\s*:\s*|\s*-\s*|(?=\s+[A-Z\u00C0-\u00DC\d\n]))"
    )
    matches = []
    for m in pattern.finditer(text):
        matched_str = m.group(0).strip()
        if matched_str not in matches:
            matches.append(matched_str)
    return matches


def process_pdf_folder(pdf_dir: str, output_dir: str):
    """Processa todos os PDFs na pasta de entrada e salva os JSONs formatados."""
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir, exist_ok=True)
        print(f"[INFO] Pasta '{pdf_dir}' criada. Coloque os PDFs das provas nesta pasta!")
        return

    os.makedirs(output_dir, exist_ok=True)

    pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print(f"[AVISO] Nenhum arquivo .pdf foi encontrado em '{pdf_dir}'.")
        print(f"-> Coloque os PDFs de provas em '{pdf_dir}' e execute este script novamente.")
        return

    print(f"[INFO] Encontrados {len(pdf_files)} arquivos PDF em '{pdf_dir}'. Processando...")

    processed_count = 0
    for fname in pdf_files:
        pdf_path = os.path.join(pdf_dir, fname)
        try:
            full_text = extract_text_from_pdf(pdf_path)
            banca = detect_banca_from_filename(fname)
            expected_headers = estimate_expected_headers(full_text)

            exam_id = os.path.splitext(fname)[0].replace(" ", "_").lower()

            payload = {
                "exam_id": exam_id,
                "banca": banca,
                "filename": fname,
                "full_text": full_text,
                "expected_headers": expected_headers,
                "total_estimated_questions": len(expected_headers),
            }

            out_json_path = os.path.join(output_dir, f"{exam_id}.json")
            with open(out_json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            print(f"  [OK] '{fname}' -> '{exam_id}.json' (Banca: {banca}, {len(expected_headers)} questões estimadas)")
            processed_count += 1
        except Exception as e:
            print(f"  [ERRO] Falha ao processar '{fname}': {e}")

    print(f"\n[SUCESSO] {processed_count} PDFs convertidos em JSON na pasta '{output_dir}'.")
    print("Agora você pode executar: python scripts/optimize_regex.py --target all")


if __name__ == "__main__":
    pdf_directory = os.path.join("training_corpus", "pdfs")
    json_directory = "training_corpus"
    process_pdf_folder(pdf_directory, json_directory)
