import os, sys
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import os
import sys
import re
import fitz

sys.path.insert(0, os.path.abspath('.'))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from services.pdf_pipeline import parse_exam_document
from services.gabarito import parse_gabarito_from_pdf, parse_gabarito_from_text, merge_exam_with_gabarito

def validate_ibam_fidelity_loop(max_iterations: int = 3):
    """
    Ciclo de teste contínuo em looping de fidelidade contra prova oficial real da banca IBAM:
    Avalia a extração da prova IBAM, compara enunciados, alternativas, gabarito e formatação.
    """
    exam_pdf = os.path.join('pdfs', 'ibam_prof_ii.pdf')
    gab_pdf = os.path.join('pdfs', 'ibam_gab_ac02.pdf')

    if not os.path.exists(exam_pdf) or not os.path.exists(gab_pdf):
        print("Arquivos de validação não encontrados localmente.")
        return False

    for iteration in range(1, max_iterations + 1):
        print(f"\n=======================================================")
        print(f"🔄 LOOP DE VALIDAÇÃO DE FIDELIDADE IBAM (Iteração #{iteration})")
        print(f"=======================================================")

        # 1. Extração do Gabarito Oficial
        gab_dict = parse_gabarito_from_pdf(gab_pdf)
        print(f"📊 Gabarito Oficial Extraído: {len(gab_dict)} respostas mapeadas.")
        print(f"   Amostra do Gabarito (Q1..Q10): {list(gab_dict.items())[:10]}")

        # 2. Extração das Questões pelo Motor Híbrido
        questions = parse_exam_document(
            pdf_bytes_or_path=exam_pdf,
            exam_id=777,
            extract_images=True
        )
        print(f"\n📝 Questões Extraídas do Caderno IBAM: {len(questions)}")

        # 3. Pareamento com o Gabarito Oficial
        updated_questions, stats = merge_exam_with_gabarito(questions, gab_dict)

        # 4. Auditoria de Qualidade e Fidelidade Questão a Questão
        errors = []
        for q in updated_questions:
            q_num = q['numero_questao']
            statement = q['enunciado']
            options = q['opcoes']
            ans = q['resposta']
            has_official = q.get('has_official_answer', False)

            # Validação 1: Enunciado não vazio e sem ruídos
            if len(statement.strip()) < 10:
                errors.append(f"Q{q_num}: Enunciado muito curto ou vazio.")

            # Validação 2: Presença de alternativas estruturadas (A, B, C, D)
            if len(options) < 4:
                errors.append(f"Q{q_num}: Menos de 4 alternativas encontradas ({len(options)}).")

            # Validação 3: Resposta oficial preenchida e válida
            if not ans or ans not in ['A', 'B', 'C', 'D', 'E', 'X', 'N']:
                errors.append(f"Q{q_num}: Resposta inválida '{ans}'.")

        # 5. Relatório de Fidelidade
        print(f"\n📈 RELATÓRIO DE AUDITORIA:")
        print(f"   • Total de Questões: {len(updated_questions)}")
        print(f"   • Cobertura do Gabarito Oficial: {stats['coverage_pct']}% ({stats['matched_answers']}/{stats['total_questions']})")
        print(f"   • Falhas Estruturais Detectadas: {len(errors)}")

        if errors:
            print("   ⚠️ Detalhes das Falhas:")
            for err in errors[:5]:
                print(f"      - {err}")

        # Amostras de questão com validação de fidelidade
        for sample_idx in [0, 19, 39]:
            if sample_idx < len(updated_questions):
                sample_q = updated_questions[sample_idx]
                print(f"\n🔍 INSPEÇÃO DETALHADA DA QUESTÃO {sample_q['numero_questao']}:")
                print(f"   • Disciplina: {sample_q['disciplina']}")
                print(f"   • Enunciado: {sample_q['enunciado'][:120]}...")
                print(f"   • Alternativas ({len(sample_q['opcoes'])}):")
                for k, v in sample_q['opcoes'].items():
                    print(f"     [{k}] {v[:70]}")
                print(f"   • Gabarito Oficial: {sample_q['resposta']}")

        # Critério de Parada com Sucesso: 40/40 questões, 100% de gabarito e 0 falhas
        if len(updated_questions) == 40 and stats['coverage_pct'] == 100.0 and len(errors) == 0:
            print(f"\n🎉 SUCESSO ABSOLUTO NO LOOPING!")
            print(f"   A prova da banca IBAM atingiu 100% DE FIDELIDADE (40/40 questões e 100% gabarito oficial vinculado).")
            return True
        elif iteration < max_iterations:
            print(f"\n⚡ Refinando para o próximo ciclo de looping...")

    return False

if __name__ == '__main__':
    success = validate_ibam_fidelity_loop()
    if not success:
        sys.exit(1)
