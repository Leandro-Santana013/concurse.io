import os, sys
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import os
import sys
import time
import json
import re
import fitz

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath('.'))

from services.pdf_pipeline import parse_exam_document

def audit_pdf_extraction(pdf_path: str, banca_hint: str):
    print("=" * 80)
    print(f"📄 AUDITANDO PROVA: {os.path.basename(pdf_path)} (Banca: {banca_hint})")
    print("=" * 80)
    
    if not os.path.exists(pdf_path):
        print(f"❌ Arquivo não encontrado: {pdf_path}")
        return

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()

    t0 = time.time()
    questions = parse_exam_document(
        pdf_bytes_or_path=pdf_path,
        exam_id=999,
        extract_images=True
    )
    elapsed = time.time() - t0

    total_q = len(questions)
    print(f"⏱️ Tempo de processamento: {elapsed:.2f}s ({total_pages} páginas, ~{elapsed/max(1, total_pages):.3f}s/pág)")
    print(f"📊 Total de Questões Extraídas: {total_q}")

    if total_q == 0:
        print("❌ NENHUMA QUESTÃO EXTRAÍDA!")
        return

    def parse_num(val):
        if val is None:
            return None
        clean = re.sub(r'\D', '', str(val))
        return int(clean) if clean else None

    raw_numbers = [q.get('numero_questao') for q in questions]
    numbers = [parse_num(n) for n in raw_numbers if parse_num(n) is not None]
    min_q = min(numbers) if numbers else 0
    max_q = max(numbers) if numbers else 0
    missing = [n for n in range(min_q, max_q + 1) if n not in numbers] if numbers else []
    duplicates = [n for n in numbers if numbers.count(n) > 1]
    duplicates = sorted(list(set(duplicates)))

    print(f"🔢 Faixa de Numeração: Questão {min_q} até {max_q} (Total mapeadas com número: {len(numbers)})")
    if missing:
        print(f"⚠️ Questões Faltantes no intervalo ({len(missing)}): {missing[:15]}{'...' if len(missing) > 15 else ''}")
    else:
        print(f"✅ Sequência Contínua Perfeita (sem furos de {min_q} a {max_q})")

    if duplicates:
        print(f"⚠️ Questões Duplicadas ({len(duplicates)}): {duplicates}")
    else:
        print(f"✅ Nenhuma Duplicata Encontrada")

    # Auditoria de Alternativas
    option_counts = {}
    empty_statements = 0
    with_images = 0
    
    for q in questions:
        opts = q.get('opcoes', [])
        opt_len = len(opts)
        option_counts[opt_len] = option_counts.get(opt_len, 0) + 1
        
        stmt = q.get('enunciado', '').strip()
        if len(stmt) < 15:
            empty_statements += 1
            
        imgs = q.get('imagens', [])
        if imgs:
            with_images += 1

    print(f"\n📋 Distribuição de Alternativas:")
    for count, q_total in sorted(option_counts.items()):
        print(f"   • {count} alternativas: {q_total} questões ({(q_total/total_q)*100:.1f}%)")

    print(f"🖼️ Questões com Imagens Recortadas: {with_images}")
    if empty_statements > 0:
        print(f"⚠️ Questões com enunciado suspeito (<15 chars): {empty_statements}")
    else:
        print(f"✅ Enunciados íntegros (todos >= 15 chars)")

    def format_opts(opts):
        res = []
        for o in opts:
            if isinstance(o, dict):
                res.append(o.get('letra', str(o)[:10]))
            else:
                res.append(str(o)[:15])
        return res

    print(f"\n🔍 AMOSTRA Q{questions[0].get('numero_questao')}:")
    print(f"   Enunciado: {questions[0].get('enunciado', '')[:120]}...")
    print(f"   Alternativas: {format_opts(questions[0].get('opcoes', []))}")
    
    if len(questions) > 1:
        last_q = questions[-1]
        print(f"\n🔍 AMOSTRA Q{last_q.get('numero_questao')}:")
        print(f"   Enunciado: {last_q.get('enunciado', '')[:120]}...")
        print(f"   Alternativas: {format_opts(last_q.get('opcoes', []))}")

    print("\n")


if __name__ == "__main__":
    test_files = [
        ("provas_bancas/VUNESP/[VUNESP] [2023] 2023 Tj Sp Escrevente Prova.pdf", "VUNESP"),
        ("provas_bancas/FGV/[FGV] [2016] 2016 Mre Oficial De Chancelaria Prova.pdf", "FGV"),
        ("provas_bancas/CEBRASPE/[CEBRASPE] 092_PGEPI_001_01 - cdn.cebraspe.org.br.pdf", "CEBRASPE"),
        ("provas_bancas/IBAM/[IBAM] Assistente_Social.pdf", "IBAM"),
        ("provas_bancas/IDECAN/[IDECAN] [2023] 2023 Sefaz Rr Implementador De Software Prova.pdf", "IDECAN"),
        ("provas_bancas/IDCAP/[IDCAP] [2024] 2024 Prefeitura De Santa Leopoldina Es Assistente Social Educacional Prova.pdf", "IDCAP"),
    ]
    
    for path, banca in test_files:
        if os.path.exists(path):
            audit_pdf_extraction(path, banca)
        else:
            print(f"Não encontrado: {path}")
