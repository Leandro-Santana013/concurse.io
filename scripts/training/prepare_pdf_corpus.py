#!/usr/bin/env python3

import os, sys
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
"""
concurse.io — Utilitário de Preparação do Corpus a partir de PDFs Brutos
Converte PDFs em subpastas (ex: 'provas_bancas/' ou 'training_corpus/pdfs/')
em arquivos JSON estruturados para o otimizador genético.
"""

import os
import sys
import json
import re
import argparse
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


def detect_banca_from_path(file_path: str) -> str:
    """Detecta a banca examinadora pela estrutura de diretórios ou pelo nome do arquivo."""
    parts = os.path.normpath(file_path).split(os.sep)
    for p in parts:
        p_up = p.upper()
        if p_up in [
            "ACCESS", "ADM-TEC", "AOCP", "AVANCA-SP", "BIO-RIO", "CCV-UFC", "CEBRASPE",
            "CESPE", "CEPUERJ", "CESGRANRIO", "CETRO", "COMPERVE", "CONSULPAM",
            "CONSULPLAN", "CONTEMAX", "COPEVE", "COTEC", "CPCON", "CS-UFG", "DATAPREV",
            "FACET", "FADESP", "FAPEC", "FAURGS", "FCC", "FEPESE", "FGV", "FUMARC",
            "FUNDATEC", "FUNRIO", "GUALIMP", "IADES", "IBAM", "IBFC", "IDCAP", "IDECAN",
            "IESES", "IGECS", "INSTITUTO-MAIS", "INSTITUTO MAIS", "ITAME", "LEGIATUS",
            "METROCAPITAL", "NC-UFPR", "NOSSO-RUMO", "NUCEPE", "OBJETIVA", "QUADRIX",
            "SELECON", "SHDIAS", "VUNESP"
        ]:
            return p_up.replace("-", " ")

    name_upper = os.path.basename(file_path).upper()
    for b in [
        "FGV", "CEBRASPE", "CESPE", "FCC", "VUNESP", "CESGRANRIO",
        "QUADRIX", "IBFC", "AOCP", "IDECAN", "IDCAP", "CONSULPAM",
        "SELECON", "FUNDATEC", "IBAM", "IADES", "FUMARC"
    ]:
        if b in name_upper:
            return b
    return "OUTRA"


def estimate_expected_headers(text: str) -> List[str]:
    """Extrai uma estimativa de cabeçalhos de questão."""
    pattern = re.compile(
        r"(?i)(?:^|\n)\s*(?:(?:QUEST[ÃA]?O|ITEM|Quest[ãa]o|Q\.)\s*|)(\d{1,3})(?:[\.\-\–\)]|\s*–\s*|\s*:\s*|\s*-\s*|(?=\s+[A-Z\u00C0-\u00DC\d\n]))"
    )
    matches = []
    for m in pattern.finditer(text):
        matched_str = m.group(0).strip()
        if matched_str not in matches:
            matches.append(matched_str)
    return matches


def estimate_expected_diagram_triggers(text: str) -> List[str]:
    """Identifica termos de figuras e diagramas no texto."""
    pattern = re.compile(
        r"(?i)\b(figura|gr[áa]fico|tabela|quadro|diagrama|circuito|mapa|esquema|imagem|charge|tirinha)\b"
    )
    return list(set(m.group(0).lower() for m in pattern.finditer(text)))


def estimate_expected_subjects(text: str) -> List[str]:
    """Identifica cabeçalhos de matérias presentes no texto."""
    pattern = re.compile(
        r"(?im)^[ \t]*(?:(?:NO[ÇC\?][ÕO\?]?ES\s+DE\s+|CONHECIMENTOS\s+(?:B[ÁA\?]?SICOS|ESPEC[ÍI\?]?FICOS|GERAIS|REGIONAIS)\s*[-–—:]*\s*|BLOCO\s+[I|V|X\d]+\s*[-–—:]*\s*|PARTE\s+[I|V|X\d]+\s*[-–—:]*\s*|DISCIPLINA\s*:\s*)?(?:L[ÍI\?]?NGUA\s+PORTUGUESA|PORTUGU[ÊE\?]?S|INTERPRETA[ÇC\?][ÃA\?]?O\s+DE\s+TEXTO|GRAM[ÁA\?]?TICA|MATEM[ÁA\?]?TICA\s+E\s+RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO|RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO-MATEM[ÁA\?]?TICO|RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO|MATEM[ÁA\?]?TICA|INFORM[ÁA\?]?TICA|DIREITO\s+CONSTITUCIONAL|DIREITO\s+ADMINISTRATIVO|DIREITO\s+PENAL|DIREITO\s+CIVIL|DIREITO\s+PROCESSUAL\s+CIVIL|DIREITO\s+PROCESSUAL\s+PENAL|DIREITO\s+DO\s+TRABALHO|DIREITO\s+TRIBUT[ÁA\?]?RIO|DIREITO\s+PREVIDENCI[ÁA\?]?RIO|LEGISLA[ÇC\?][ÃA\?]?O\s+ESPEC[ÍI\?]?FICA|LEGISLA[ÇC\?][ÃA\?]?O|[ÉE\?]?TICA\s+NO\s+SERVI[ÇC\?]?O\s+P[ÚU\?]?BLICO|ADMINISTRA[ÇC\?][ÃA\?]?O\s+P[ÚU\?]?BLICA|ADMINISTRA[ÇC\?][ÃA\?]?O\s+GERAL|CONTABILIDADE\s+P[ÚU\?]?BLICA|CONTABILIDADE\s+GERAL|CONTABILIDADE|AUDITORIA|ENFERMAGEM|MEDICINA|CONHECIMENTOS\s+B[ÁA\?]?SICOS|CONHECIMENTOS\s+ESPEC[ÍI\?]?FICOS|CONHECIMENTOS\s+GERAIS|ATUALIDADES|HIST[ÓO\?]?RIA|GEOGRAFIA|L[ÍI\?]?NGUA\s+INGLESA|SEGURAN[ÇC\?]?A\s+P[ÚU\?]?BLICA))\b"
    )
    return list(set(m.group(0).strip() for m in pattern.finditer(text)))


def collect_pdf_files(root_dir: str) -> List[str]:
    """Coleta recursivamente todos os arquivos .pdf."""
    pdf_list = []
    for root, _, files in os.walk(root_dir):
        for f in files:
            if f.lower().endswith(".pdf") and "_gab_" not in f.lower():
                pdf_list.append(os.path.join(root, f))
    return sorted(pdf_list)


def process_pdf_folder(input_dir: str, output_dir: str, max_per_banca: int = 10):
    """Processa todos os PDFs recursivamente e salva os JSONs formatados."""
    if not os.path.exists(input_dir):
        print(f"[ERRO] Diretório '{input_dir}' não encontrado!")
        return

    os.makedirs(output_dir, exist_ok=True)

    all_pdfs = collect_pdf_files(input_dir)
    if not all_pdfs:
        print(f"[AVISO] Nenhum arquivo PDF encontrado em '{input_dir}'.")
        return

    print(f"[INFO] Encontrados {len(all_pdfs)} arquivos PDF em '{input_dir}'.")

    banca_counts: Dict[str, int] = {}
    processed_count = 0

    for pdf_path in all_pdfs:
        banca = detect_banca_from_path(pdf_path)
        if max_per_banca > 0 and banca_counts.get(banca, 0) >= max_per_banca:
            continue

        fname = os.path.basename(pdf_path)
        try:
            full_text = extract_text_from_pdf(pdf_path)
            if len(full_text.strip()) < 100:
                continue

            expected_headers = estimate_expected_headers(full_text)
            diagram_triggers = estimate_expected_diagram_triggers(full_text)
            subjects = estimate_expected_subjects(full_text)

            exam_id = f"{banca.lower()}_{os.path.splitext(fname)[0]}".replace(" ", "_").replace("-", "_").lower()
            exam_id = re.sub(r'[^a-z0-9_]', '', exam_id)

            payload = {
                "exam_id": exam_id,
                "banca": banca,
                "filename": fname,
                "full_text": full_text,
                "expected_headers": expected_headers,
                "expected_diagram_triggers": diagram_triggers,
                "expected_subjects": subjects,
                "total_estimated_questions": len(expected_headers),
            }

            out_json_path = os.path.join(output_dir, f"{exam_id}.json")
            with open(out_json_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            banca_counts[banca] = banca_counts.get(banca, 0) + 1
            processed_count += 1
            print(f"  [OK {processed_count:03d}] {banca}: '{fname[:45]}...' ({len(expected_headers)} questões, {len(diagram_triggers)} figuras)")

        except Exception as e:
            print(f"  [ERRO] Falha ao processar '{fname}': {e}")

    print(f"\n[SUCESSO] {processed_count} provas indexadas de {len(banca_counts)} bancas em '{output_dir}'.")
    print("Para iniciar o treinamento completo, execute:")
    print("  python scripts/optimize_regex.py --target all --generations 50 --pop-size 60")


def main():
    parser = argparse.ArgumentParser(description="Preparador de Corpus de PDFs de Provas")
    parser.add_argument("--input-dir", type=str, default="provas_bancas", help="Pasta com PDFs ou subpastas de bancas")
    parser.add_argument("--output-dir", type=str, default="training_corpus", help="Pasta de saída para os JSONs")
    parser.add_argument("--max-per-banca", type=int, default=15, help="Limite de provas por banca para balanceamento (0 = sem limite)")
    args = parser.parse_args()

    process_pdf_folder(args.input_dir, args.output_dir, max_per_banca=args.max_per_banca)


if __name__ == "__main__":
    main()
