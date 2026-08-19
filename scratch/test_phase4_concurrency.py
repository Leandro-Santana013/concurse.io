import sys
import os
import time
import json
import threading
import concurrent.futures

# Adicionar pasta raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models import Session, init_db, Exam, User
from app import set_exam_progress, get_exam_progress

def test_progress_persistence_across_sessions():
    print("=== Teste 1: Persistencia de Progresso em Banco de Dados ===")
    init_db()
    
    # Cria um exame de teste
    exam_id = None
    with Session() as s:
        test_exam = Exam(
            title="PROVA DE TESTE CONCORRENCIA",
            status="Pendente",
            source_url="https://example.com/teste_concorrencia.pdf"
        )
        s.add(test_exam)
        s.commit()
        exam_id = test_exam.id

    assert exam_id is not None
    
    # 1. Simula worker 1 atualizando progresso para 35%
    set_exam_progress(exam_id, "Baixando PDF...", 35)
    
    # 2. Simula worker 2 (outra sessão isolada) lendo o progresso
    prog = get_exam_progress(exam_id)
    print(f"Worker 2 leu do banco: {prog}")
    assert prog["progress"] == 35
    assert "Baixando" in prog["status"]
    
    # 3. Simula avanço para 80%
    set_exam_progress(exam_id, "Extraindo questoes...", 80)
    prog = get_exam_progress(exam_id)
    assert prog["progress"] == 80
    
    # 4. Simula conclusão em 100%
    set_exam_progress(exam_id, "Concluido com sucesso!", 100)
    prog = get_exam_progress(exam_id)
    assert prog["progress"] == 100
    
    # Verifica que o status no banco mudou para 'Aprovada'
    with Session() as s:
        e = s.query(Exam).filter_by(id=exam_id).first()
        assert e.status == 'Aprovada'
        # Limpeza
        s.delete(e)
        s.commit()
        
    print("[OK] Teste 1 passou com sucesso! Progresso e status persistidos de forma segura.\n")

def test_concurrent_progress_updates_multi_threaded():
    print("=== Teste 2: Atualizacoes Concorrentes e Isolamento de Sessoes ===")
    
    # Cria 5 exames
    exam_ids = []
    with Session() as s:
        for i in range(5):
            e = Exam(title=f"PROVA CONCORRENTE {i}", status="Pendente")
            s.add(e)
        s.commit()
        exams = s.query(Exam).filter(Exam.title.ilike("PROVA CONCORRENTE%")).all()
        exam_ids = [e.id for e in exams]

    def update_task(e_id):
        for pct in [10, 25, 50, 75, 100]:
            set_exam_progress(e_id, f"Processando etapa {pct}%", pct)
            time.sleep(0.02)
        return True

    # Executa atualizações concorrentes em 5 threads simultâneas
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(update_task, eid) for eid in exam_ids]
        for fut in concurrent.futures.as_completed(futures):
            assert fut.result() is True

    # Valida que todos os 5 exames chegaram a 100% no banco
    with Session() as s:
        for eid in exam_ids:
            e = s.query(Exam).filter_by(id=eid).first()
            assert e.progress == 100
            assert e.status == 'Aprovada'
            s.delete(e)
        s.commit()

    print("[OK] Teste 2 passou com sucesso! Nao houve deadlocks nem vazamentos de sessao em paralelo.\n")

def test_error_state_handling():
    print("=== Teste 3: Tratamento e Persistencia de Estados de Erro (-1) ===")
    exam_id = None
    with Session() as s:
        test_exam = Exam(title="PROVA COM ERRO", status="Pendente")
        s.add(test_exam)
        s.commit()
        exam_id = test_exam.id

    # Simula erro de download
    set_exam_progress(exam_id, "Falha no download", -1, error_type="download_blocked")
    
    prog = get_exam_progress(exam_id)
    assert prog["progress"] == -1
    assert prog["error_type"] == "download_blocked"
    
    with Session() as s:
        e = s.query(Exam).filter_by(id=exam_id).first()
        assert e.status == 'Erro'
        assert e.error_type == 'download_blocked'
        s.delete(e)
        s.commit()

    print("[OK] Teste 3 passou com sucesso! Estados de erro persistidos corretamente.\n")

if __name__ == '__main__':
    test_progress_persistence_across_sessions()
    test_concurrent_progress_updates_multi_threaded()
    test_error_state_handling()
    print("[SUCESSO] TODOS OS TESTES DA FASE 4 PASSARAM COM 100% DE SUCESSO!")
    sys.exit(0)
