import os
import sys
import json
import fitz

# Garante que o diretório raiz do projeto esteja no sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from services.pdf_inspector import inspect_pdf_document, is_administrative_document
from services.gabarito_service import parse_gabarito_from_text, parse_gabarito_from_pdf, merge_exam_with_gabarito, format_gabarito_summary
from services.scraper_service import is_administrative_document as scraper_is_admin
from models import Session, Exam, Question, init_db

def create_mock_edital_pdf():
    """Gera um PDF sintético de Edital de Concurso."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "ESTADO DO ESPÍRITO SANTO\nEDITAL DE ABERTURA Nº 01/2024\nCONCURSO PÚBLICO PARA PROVIMENTO DE VAGAS\n\n1. DAS DISPOSIÇÕES PRELIMINARES\n1.1 O concurso será regido por este edital e seus anexos.\n2. DO CRONOGRAMA PREVISTO\nInscrições: 01/01 a 31/01\nData da Prova: 15/03\n3. DO CONTEÚDO PROGRAMÁTICO\nLíngua Portuguesa, Raciocínio Lógico.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def create_mock_gabarito_only_pdf():
    """Gera um PDF sintético que é apenas uma folha de gabarito."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "GABARITO OFICIAL DEFINITIVO - CARGO: AGENTE ADMINISTRATIVO\n\n1-A  2-B  3-C  4-D  5-E\n6-A  7-B  8-C  9-D 10-E\n11-A 12-B 13-C 14-D 15-E\n16-A 17-B 18-C 19-D 20-E\n21-A 22-B 23-C 24-D 25-E\n26-A 27-B 28-C 29-D 30-E")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def create_mock_exam_pdf():
    """Gera um PDF sintético de Caderno de Questões com enunciados e alternativas."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "CADERNO DE QUESTÕES - PROVA OBJETIVA\n\nLÍNGUA PORTUGUESA\n\nQUESTÃO 01\nAssinale a alternativa correta quanto à concordância verbal:\nA) Havia muitos alunos na sala de aula.\nB) Haviam muitas pessoas no evento.\nC) Fazem dez anos que não o vejo.\nD) Devem haver outras saídas para a crise.\nE) Tratam-se de questões fundamentais.\n\nQUESTÃO 02\nO termo sublinhado exerce função de adjunto adnominal em:\nA) O livro de Maria é novo.\nB) Ela mora em São Paulo.\nC) Chegamos cedo ontem.\nD) O carro foi vendido ontem.\nE) Falamos sobre política.\n\nQUESTÃO 03\nEm relação ao uso da crase, assinale a opção correta:\nA) Fui à praia ontem de manhã.\nB) Fui a pé para a escola.\nC) Entreguei o documento à ele.\nD) Começou à correr imediatamente.\nE) Fomos à uma festa linda.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def run_tests():
    print("=" * 70)
    print("🚀 INICIANDO TESTES DO NOVO PIPELINE ORGANIZADO DO CONCURSE.IO")
    print("=" * 70)

    # -------------------------------------------------------------
    # TESTE 1: PDF INSPECTOR & CLASSIFICAÇÃO DETERMINÍSTICA
    # -------------------------------------------------------------
    print("\n--- TESTE 1: Inspeção Rápida de Documentos (PDF Inspector) ---")
    
    # 1.1 Edital
    edital_bytes = create_mock_edital_pdf()
    res_edital = inspect_pdf_document(edital_bytes)
    assert res_edital['doc_type'] == 'ADMINISTRATIVE_DOC', f"Falha: Esperado ADMINISTRATIVE_DOC, obteve {res_edital['doc_type']}"
    assert res_edital['is_valid_exam'] is False, "Falha: Edital não deve ser considerado prova válida"
    print(f" [OK] 1.1 Edital detectado e rejeitado com sucesso: {res_edital['reason']}")

    # 1.2 Gabarito Avulso
    gab_bytes = create_mock_gabarito_only_pdf()
    res_gab = inspect_pdf_document(gab_bytes)
    assert res_gab['doc_type'] == 'ANSWER_KEY_ONLY', f"Falha: Esperado ANSWER_KEY_ONLY, obteve {res_gab['doc_type']}"
    assert res_gab['has_embedded_gabarito'] is True, "Falha: Folha de gabarito deve ter flag de gabarito"
    print(f" [OK] 1.2 Folha de gabarito identificada com sucesso: {res_gab['reason']}")

    # 1.3 Caderno de Prova Real
    exam_bytes = create_mock_exam_pdf()
    res_exam = inspect_pdf_document(exam_bytes)
    assert res_exam['doc_type'] == 'EXAM_QUESTIONS', f"Falha: Esperado EXAM_QUESTIONS, obteve {res_exam['doc_type']}"
    assert res_exam['is_valid_exam'] is True, "Falha: Caderno de prova deve ser validado"
    print(f" [OK] 1.3 Caderno de prova aprovado para extração: {res_exam['reason']}")

    # -------------------------------------------------------------
    # TESTE 2: SERVIÇO DE GABARITOS & PAREAMENTO (GABARITO SERVICE)
    # -------------------------------------------------------------
    print("\n--- TESTE 2: Módulo de Gabarito (Gabarito Service) ---")
    
    # 2.1 Parsing de texto formatado
    raw_text = "1-A, 2-C, 3-B, 4-E, 5-D, 6-A, 7-B, 8-C, 9-D, 10-E"
    parsed_text_gab = parse_gabarito_from_text(raw_text)
    assert parsed_text_gab[1] == 'A' and parsed_text_gab[2] == 'C' and parsed_text_gab[3] == 'B'
    print(f" [OK] 2.1 Parsing de gabarito em texto (vírgula/hífen): {len(parsed_text_gab)} respostas mapeadas.")

    # 2.2 Parsing CEBRASPE (Certo/Errado)
    cebraspe_text = "1-CERTO 2-ERRADO 3-C 4-E 5-CERTO"
    parsed_cebraspe = parse_gabarito_from_text(cebraspe_text)
    assert parsed_cebraspe[1] == 'C' and parsed_cebraspe[2] == 'E' and parsed_cebraspe[5] == 'C'
    print(f" [OK] 2.2 Parsing de gabarito CEBRASPE (Certo/Errado): {parsed_cebraspe}")

    # 2.3 Parsing de Gabarito a partir de PDF
    pdf_gab_result = parse_gabarito_from_pdf(gab_bytes)
    assert len(pdf_gab_result) >= 20, f"Falha: Esperado pelo menos 20 respostas do PDF, obteve {len(pdf_gab_result)}"
    assert pdf_gab_result[1] == 'A' and pdf_gab_result[2] == 'B'
    print(f" [OK] 2.3 Parsing de gabarito direto de PDF: {len(pdf_gab_result)} respostas extraídas com precisão.")

    # 2.4 Merge de Gabarito com Questões
    mock_questions = [
        {'numero_questao': 1, 'enunciado': 'Questão 1', 'opcoes': {'A': 'Op1', 'B': 'Op2'}, 'resposta': 'X'},
        {'numero_questao': 2, 'enunciado': 'Questão 2', 'opcoes': {'A': 'Op1', 'B': 'Op2'}, 'resposta': 'X'},
        {'numero_questao': 3, 'enunciado': 'Questão 3', 'opcoes': {'A': 'Op1', 'B': 'Op2'}, 'resposta': 'X'}
    ]
    gabarito_map = {1: 'B', 2: 'A', 3: 'C'}
    updated_q, stats = merge_exam_with_gabarito(mock_questions, gabarito_map)
    assert updated_q[0]['resposta'] == 'B' and updated_q[1]['resposta'] == 'A' and updated_q[2]['resposta'] == 'C'
    assert stats['coverage_pct'] == 100.0
    assert stats['has_official_answers'] is True
    print(f" [OK] 2.4 Pareamento e merge de respostas: 100% de cobertura confirmada.")

    # -------------------------------------------------------------
    # TESTE 3: FILTROS DO SCRAPER & PREVENÇÃO DE RESULTADOS INDESEJADOS
    # -------------------------------------------------------------
    print("\n--- TESTE 3: Filtros Estritos do Scraper ---")
    
    # Documentos que DEVEM ser descartados
    invalid_titles = [
        "Edital de Abertura Concurso PM 2024",
        "Resultado Preliminar da Prova Objetiva",
        "Convocação para Avaliação Psicológica e TAF",
        "Retificação do Cronograma do Concurso",
        "Homologação Final dos Aprovados",
        "Anexo I - Quadro de Vagas e Salários",
        "Parecer da Banca sobre os Recursos"
    ]
    for title in invalid_titles:
        assert is_administrative_document(title) is True, f"Falha: '{title}' deveria ter sido descartado"
    print(f" [OK] 3.1 Todos os {len(invalid_titles)} títulos administrativos de teste foram descartados com sucesso.")

    # Documentos que DEVEM ser aceitos
    valid_titles = [
        "Caderno de Questões - Escriturário Banco do Brasil",
        "Prova Objetiva - Analista Judiciário TJSP 2023",
        "Prova de Conhecimentos Específicos - Polícia Federal"
    ]
    for title in valid_titles:
        assert is_administrative_document(title) is False, f"Falha: '{title}' não deveria ter sido descartado"
    print(f" [OK] 3.2 Todos os {len(valid_titles)} cadernos legítimos de teste foram aceitos.")

    # -------------------------------------------------------------
    # TESTE 4: BANCO DE DADOS & NOVOS CAMPOS
    # -------------------------------------------------------------
    print("\n--- TESTE 4: Migração e Modelos de Banco de Dados ---")
    init_db()
    
    with Session() as s:
        # Cria um exame de teste com campos novos
        test_exam = Exam(
            title="Prova Teste Pipeline Integrado",
            status="Aprovada",
            has_official_answers=1,
            answer_key_source="attached_pdf",
            doc_type="caderno_questoes",
            gabarito_coverage=100.0,
            gabarito_text="1-A | 2-B | 3-C"
        )
        s.add(test_exam)
        s.commit()
        
        saved_id = test_exam.id
        loaded_exam = s.query(Exam).filter_by(id=saved_id).first()
        assert loaded_exam is not None
        assert loaded_exam.has_official_answers == 1
        assert loaded_exam.answer_key_source == "attached_pdf"
        assert loaded_exam.gabarito_coverage == 100.0
        assert loaded_exam.gabarito_text == "1-A | 2-B | 3-C"
        
        # Limpeza
        s.delete(loaded_exam)
        s.commit()
    print(" [OK] 4.1 Persistência de campos de gabarito e métricas validada com sucesso no banco de dados.")

    print("\n" + "=" * 70)
    print("🎉 PARABÉNS! TODOS OS TESTES DO NOVO PIPELINE PASSARAM COM 100% DE SUCESSO!")
    print("=" * 70)

if __name__ == '__main__':
    run_tests()
