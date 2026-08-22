import sys
import os

sys.path.insert(0, os.path.abspath("."))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from services.pdf_pipeline.hybrid_extractor import parse_exam_document

pdf_path = os.path.join("provas_bancas", "AVANCA-SP", "[AVANCA-SP] [2025] Avanca Sp 2025 Camara De Cacapava Sp Agente Administrativo Prova.pdf")

print("PDF:", pdf_path)
print("Existe?", os.path.exists(pdf_path))

questions = parse_exam_document(pdf_path, extract_images=False)
print("=" * 60)
print(f"Total de questões extraídas: {len(questions)}")
print("=" * 60)

if questions:
    print(f"Primeira questão: Q{questions[0]['numero_questao']}")
    print(f"Enunciado Q1: {questions[0]['enunciado'][:100]}...")
    print(f"Opções Q1: {questions[0]['opcoes']}")
    print(f"Disciplina Q1: {questions[0]['disciplina']}")
    print("-" * 60)
    print(f"Última questão: Q{questions[-1]['numero_questao']}")
    print(f"Enunciado Q40: {questions[-1]['enunciado'][:100]}...")
    print(f"Opções Q40: {questions[-1]['opcoes']}")
    print(f"Disciplina Q40: {questions[-1]['disciplina']}")
    print("-" * 60)
    seq = [q['numero_questao'] for q in questions]
    print(f"Sequência completa ({len(seq)} questões):", seq)
    expected_seq = list(range(1, 41))
    print(f"Sequência é exatamente 1 a 40? {seq == expected_seq}")
