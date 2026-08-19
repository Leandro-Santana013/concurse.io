import os
import sys
import json
import fitz

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from services.pdf_inspector import inspect_pdf_document
from services.pdf_parser import parse_exam_pdf_deterministic, _extract_gabarito_from_doc
from services.gabarito_service import parse_gabarito_from_text, parse_gabarito_from_pdf, merge_exam_with_gabarito

def test_real_exams_suite():
    print("=" * 75)
    print("🏆 SUÍTE DE TESTES DETERMINÍSTICOS - PADRÃO DE OURO PARA LEITURA DE PROVAS")
    print("=" * 75)

    # 1. Prova Unisul 806 (50 questões + Chico Buarque + Gabarito 50 itens)
    print("\n--- TESTE 1: Prova Unisul / OGMO (806) + Gabarito com Anulações ---")
    p806 = os.path.join(BASE_DIR, 'pdfs', '806_1787145607.pdf')
    p806_gab = os.path.join(BASE_DIR, 'pdfs', '806_gab_1787145607.pdf')
    
    if os.path.exists(p806) and os.path.exists(p806_gab):
        qs_806 = parse_exam_pdf_deterministic(p806, extract_images=False)
        gab_806 = parse_gabarito_from_pdf(p806_gab)
        
        print(f" [OK] Questões extraídas: {len(qs_806)} (esperado: 50)")
        print(f" [OK] Gabarito extraído: {len(gab_806)} itens (esperado: 50)")
        assert len(qs_806) == 50, f"Esperava 50 questões, obteve {len(qs_806)}"
        assert len(gab_806) == 50, f"Esperava 50 itens de gabarito, obteve {len(gab_806)}"
        assert gab_806[41] == 'X', f"Esperava questão 41 anulada ('X'), obteve {gab_806[41]}"
        
        # Verifica se Q1 começa com a citação e tem as 5 opções A-E
        assert "Era como se ele, cansado" in qs_806[0]['enunciado']
        assert set(qs_806[0]['opcoes'].keys()) == {'A', 'B', 'C', 'D', 'E'}
        assert qs_806[0]['disciplina'] == 'Língua Portuguesa'
        print(f" [OK] Q1 validada com sucesso: {repr(qs_806[0]['enunciado'][:60])}")

    # 2. Prova Fundatec 791 (80 questões + Numeração de linhas + Auditoria)
    print("\n--- TESTE 2: Prova Fundatec Auditor-Fiscal (791) - 80 Questões ---")
    p791 = os.path.join(BASE_DIR, 'pdfs', '791_1787144037.pdf')
    if os.path.exists(p791):
        qs_791 = parse_exam_pdf_deterministic(p791, extract_images=False)
        print(f" [OK] Questões extraídas: {len(qs_791)} (esperado: 80)")
        assert len(qs_791) == 80, f"Esperava 80 questões, obteve {len(qs_791)}"
        assert "Considerando o exposto no texto" in qs_791[0]['enunciado']
        assert qs_791[0]['disciplina'] == 'Língua Portuguesa'
        print(f" [OK] Q1 da Fundatec validada com sucesso: {repr(qs_791[0]['enunciado'][:60])}")

    # 3. Prova Cesgranrio 674 (60 questões + Capa com tabela de distribuição)
    print("\n--- TESTE 3: Prova Cesgranrio Transpetro (674) - 60 Questões ---")
    p674 = os.path.join(BASE_DIR, 'pdfs', '674_1786976361.pdf')
    if os.path.exists(p674):
        qs_674 = parse_exam_pdf_deterministic(p674, extract_images=False)
        print(f" [OK] Questões extraídas: {len(qs_674)} (esperado: 60)")
        assert len(qs_674) == 60, f"Esperava 60 questões, obteve {len(qs_674)}"
        assert "O trecho que explica os objetivos" in qs_674[0]['enunciado']
        assert qs_674[0]['disciplina'] == 'Língua Portuguesa'
        print(f" [OK] Q1 Cesgranrio validada com sucesso: {repr(qs_674[0]['enunciado'][:60])}")

    # 4. Teste Sintético: Textos de Apoio Compartilhados e Assertivas Romanas
    print("\n--- TESTE 4: Teste de Texto de Apoio Compartilhado & Assertivas Romanas ---")
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    p.insert_text((50, 50), """LÍNGUA PORTUGUESA

Instrução: As questões de 1 a 2 referem-se ao texto a seguir.

A Importância da Leitura
A leitura expande os horizontes do pensamento crítico e constrói a cidadania.

QUESTÃO 1
Em relação ao texto acima, analise as assertivas:
I. A leitura é fundamental para o pensamento crítico.
II. O texto defende o isolamento intelectual.
Está correto o que se afirma em:
(A) Apenas I.
(B) Apenas II.
(C) I e II.
(D) Nenhuma.
(E) Todas.

QUESTÃO 2
A palavra "cidadania" no texto expressa:
(A) Dever cívico.
(B) Exclusão.
(C) Alienação.
(D) Omissão.
(E) Resignação.
""", fontsize=10)
    pdf_bytes = doc.tobytes()
    doc.close()

    qs_synthetic = parse_exam_pdf_deterministic(pdf_bytes, extract_images=False)
    print(f" [OK] Questões sintéticas extraídas: {len(qs_synthetic)}")
    assert len(qs_synthetic) == 2
    assert "Texto de Apoio (Questões 1 a 2)" in qs_synthetic[0]['enunciado']
    assert "A Importância da Leitura" in qs_synthetic[0]['enunciado']
    assert "I. A leitura é fundamental" in qs_synthetic[0]['enunciado']
    assert set(qs_synthetic[0]['opcoes'].keys()) == {'A', 'B', 'C', 'D', 'E'}
    print(" [OK] Texto de apoio compartilhado injetado e assertivas I, II preservadas no enunciado com perfeição!")

    print("\n" + "=" * 75)
    print("🎉 TODAS AS VALIDAÇÕES DO NOVO PADRÃO DE LEITURA FORAM CONCLUÍDAS COM 100% DE ÊXITO!")
    print("=" * 75)

if __name__ == '__main__':
    test_real_exams_suite()
