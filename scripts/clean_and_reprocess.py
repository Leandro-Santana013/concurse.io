import sys
import os
import glob
sys.path.insert(0, os.path.abspath('.'))

from models.database import Session, Exam, Question, ExamAttempt
from app_core.async_worker import process_exam_async

session = Session()

# 1. Localizar e Excluir todas as provas da DATAPREV
dataprev_exams = session.query(Exam).filter(Exam.title.ilike('%DATAPREV%')).all()
print(f"Encontradas {len(dataprev_exams)} provas da DATAPREV para exclusão.")

for exam in dataprev_exams:
    e_id = exam.id
    title = exam.title
    print(f"Excluindo Prova ID {e_id}: {title}...")
    
    # Exclui tentativas e questões associadas
    session.query(ExamAttempt).filter_by(exam_id=e_id).delete()
    session.query(Question).filter_by(exam_id=e_id).delete()
    session.delete(exam)
    session.commit()
    
    # Remove PDFs físicos correspondentes
    for f in glob.glob(f"pdfs/{e_id}_*.pdf"):
        try:
            os.remove(f)
            print(f"  Removido arquivo físico: {f}")
        except Exception as e:
            print(f"  Erro ao remover {f}: {e}")

# Limpa qualquer PDF residual da Dataprev
for f in ["prova_dataprev.pdf", "pdfs/45_1787870381.pdf", "pdfs/45_gab_1787870381.pdf", "pdfs/46_1787872527.pdf", "pdfs/46_gab_1787872527.pdf"]:
    if os.path.exists(f):
        try:
            os.remove(f)
            print(f"  Removido arquivo residual: {f}")
        except Exception as e:
            pass

print("\n--- PROVAS DATAPREV EXCLUÍDAS COM SUCESSO ---")

# 2. Localizar e Reprocessar as provas da IDCAP (OGMO / IDCAP)
idcap_exams = session.query(Exam).all()
print(f"\nReprocessando provas restantes ({len(idcap_exams)} encontradas)...")

for exam in idcap_exams:
    print(f"\nIniciando reprocessamento completo do Exame {exam.id} ({exam.title})...")
    process_exam_async(exam.id)
    
    # Validação pós-processamento
    exam_refreshed = session.query(Exam).filter_by(id=exam.id).first()
    q_count = session.query(Question).filter_by(exam_id=exam.id).count()
    print(f"Resultado Exame {exam.id}: Status='{exam_refreshed.status}', Progresso={exam_refreshed.progress}%, Total Questões={q_count}")

session.close()
print("\n=== TODAS AS TAREFAS CONCLUÍDAS COM SUCESSO ===")
