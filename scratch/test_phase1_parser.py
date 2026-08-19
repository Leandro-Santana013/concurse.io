import sys
import os
import io
import fitz
import json

# Adicionar pasta raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.pdf_parser import parse_exam_pdf_deterministic, _extract_gabarito_from_doc

def test_gabarito_extraction_from_pdf():
    print("=== Teste 1: Extração de Gabarito no Final do Documento ===")
    doc = fitz.open()
    
    # Página 1: Questões
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50), "LÍNGUA PORTUGUESA\n\nQUESTÃO 1\nO texto expressa uma ideia de coerência.\n(A) Verdadeiro\n(B) Falso\n(C) Nulo\n(D) Parcial\n(E) Neutro\n\nQUESTÃO 2\nAssinale a opção correta.\n(A) Primeira\n(B) Segunda\n(C) Terceira\n(D) Quarta\n(E) Quinta", fontsize=11)
    
    # Página 2: Gabarito
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 50), "GABARITO OFICIAL PRELIMINAR\n\n01 - B\n02 - D\n03 - E\n04 - A\n05 - C\n", fontsize=12)
    
    pdf_bytes = doc.write()
    doc.close()
    
    questions = parse_exam_pdf_deterministic(pdf_bytes, extract_images=False)
    print(f"Total de questões extraídas: {len(questions)}")
    for q in questions:
        print(f"Q{q['numero_questao']} | Matéria: {q['disciplina']} | Resposta Real: {q['resposta']} | Opções: {list(q['opcoes'].keys()) if q['opcoes'] else 'Sem opções'}")
    
    assert len(questions) == 2, f"Esperava 2 questões, obteve {len(questions)}"
    assert questions[0]['resposta'] == 'B', f"Esperava resposta 'B' para Q1, obteve {questions[0]['resposta']}"
    assert questions[1]['resposta'] == 'D', f"Esperava resposta 'D' para Q2, obteve {questions[1]['resposta']}"
    assert questions[0]['disciplina'] == 'Língua Portuguesa'
    print("[OK] Teste 1 passou com sucesso!\n")

def test_multi_column_ordering():
    print("=== Teste 2: Ordenacao Multi-Coluna (PyMuPDF Layout-Aware) ===")
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    
    # Banner superior (largura total)
    p.insert_text((50, 50), "DIREITO CONSTITUCIONAL\nInstrucoes: Leia as questoes abaixo com atencao.", fontsize=11)
    
    # Coluna Esquerda (x=50 a 250)
    p.insert_text((50, 100), "QUESTAO 1\nSobre os direitos e garantias fundamentais:\n(A) Sao absolutos.\n(B) Sao relativos.\n(C) Inaplicaveis.\n(D) Extintos.\n(E) Derrogados.", fontsize=10)
    
    # Coluna Direita (x=320 a 520)
    p.insert_text((320, 100), "QUESTAO 2\nA soberania popular sera exercida por:\n(A) Sufragio universal.\n(B) Decreto.\n(C) Portaria.\n(D) Alvara.\n(E) Resolucao.", fontsize=10)
    
    # Gabarito Inline
    p.insert_text((50, 700), "GABARITO: 1-B, 2-A", fontsize=10)
    
    pdf_bytes = doc.write()
    doc.close()
    
    questions = parse_exam_pdf_deterministic(pdf_bytes, extract_images=False)
    print(f"Total de questoes: {len(questions)}")
    for q in questions:
        print(f"Q{q['numero_questao']}: {q['enunciado'][:40]}... -> Resposta: {q['resposta']}")
    
    assert len(questions) == 2
    assert questions[0]['numero_questao'] == '1'
    assert "direitos e garantias" in questions[0]['enunciado'].lower()
    assert questions[0]['resposta'] == 'B'
    
    assert questions[1]['numero_questao'] == '2'
    assert "soberania popular" in questions[1]['enunciado'].lower()
    assert questions[1]['resposta'] == 'A'
    print("[OK] Teste 2 passou com sucesso!\n")

def test_certo_errado_cebraspe():
    print("=== Teste 3: Suporte a Questoes Certo / Errado (CEBRASPE) ===")
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    
    text = """NOCOES DE INFORMATICA

Acerca de seguranca da informacao, julgue os itens a seguir.

QUESTAO 1
O protocolo HTTPS garante a confidencialidade da comunicacao entre o cliente e o servidor por meio de criptografia.
(Gabarito: C)

QUESTAO 2
O phishing e um tipo de malware que criptografa os arquivos do usuario e exige resgate em criptomoedas.
(Gabarito: E)
"""
    p.insert_text((50, 50), text, fontsize=10)
    pdf_bytes = doc.write()
    doc.close()
    
    questions = parse_exam_pdf_deterministic(pdf_bytes, extract_images=False)
    print(f"Total de questoes CEBRASPE: {len(questions)}")
    for q in questions:
        print(f"Q{q['numero_questao']}: {q['enunciado'][:50]}... | Opcoes: {q['opcoes']} | Resposta: {q['resposta']}")
    
    assert len(questions) == 2
    assert questions[0]['opcoes'] == {'C': 'Certo', 'E': 'Errado'}
    assert questions[0]['resposta'] == 'C'
    assert questions[1]['opcoes'] == {'C': 'Certo', 'E': 'Errado'}
    assert questions[1]['resposta'] == 'E'
    print("[OK] Teste 3 passou com sucesso!\n")

def test_table_gabarito_and_inline_options():
    print("=== Teste 4: Gabarito em Tabela e Opcoes em Linhas Multiplas ===")
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    
    text = """MATEMÁTICA E RACIOCÍNIO LÓGICO

QUESTÃO 1
Considere a proposição lógica P: 'Se chover, então levarei o guarda-chuva'. A negação dessa proposição é:
(A) Choveu e não levei o guarda-chuva.
(B) Não choveu ou levei o guarda-chuva.
(C) Se não chover, não levo o guarda-chuva.
(D) Choveu ou levarei o guarda-chuva.
(E) Nenhuma das anteriores.

QUESTÃO 2
Em uma progressão aritmética onde a1 = 3 e r = 4, o décimo termo é igual a:
(A) 39
(B) 43
(C) 37
(D) 40
(E) 45

QUADRO DE RESPOSTAS
1 - A
2 - A
"""
    p.insert_text((50, 50), text, fontsize=10)
    pdf_bytes = doc.write()
    doc.close()
    
    questions = parse_exam_pdf_deterministic(pdf_bytes, extract_images=False)
    print(f"Total de questoes extraidas: {len(questions)}")
    for q in questions:
        print(f"Q{q['numero_questao']}: {q['enunciado'][:40]}... | Disciplina: {repr(q['disciplina'])} | Opcoes: {len(q['opcoes'])} | Resposta: {q['resposta']}")
    
    assert 'Matemática' in questions[0]['disciplina'] or 'Matem' in questions[0]['disciplina']
    assert len(questions[0]['opcoes']) == 5
    assert questions[0]['resposta'] == 'A'
    assert len(questions[1]['opcoes']) == 5
    assert questions[1]['resposta'] == 'A'
    print("[OK] Teste 4 passou com sucesso!\n")

if __name__ == '__main__':
    test_gabarito_extraction_from_pdf()
    test_multi_column_ordering()
    test_certo_errado_cebraspe()
    test_table_gabarito_and_inline_options()
    print("[SUCESSO] TODOS OS TESTES DA FASE 1 PASSARAM COM 100% DE SUCESSO!")
