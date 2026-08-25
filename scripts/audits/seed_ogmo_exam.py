import os, sys, json
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from models.database import Session, Exam, Question, User
from services.pdf_pipeline import parse_exam_document

db = Session()

# Ensure demo user exists
user = db.query(User).first()
if not user:
    user = User(google_id="demo_admin", email="admin@concurse.io", name="Administrador")
    db.add(user)
    db.commit()

pdf_path = "pdfs/19_1787612141.pdf"
title = "[2025] OGMO/SANTOS - TRABALHADOR PORTUÁRIO AVULSO - CATEGORIA CAPATAZIA/SINTRAPORT"

exam = db.query(Exam).filter_by(title=title).first()
if not exam:
    exam = Exam(
        title=title,
        status="Pronto",
        progress=100,
        progress_message="Concluído com Sucesso",
        source_url=pdf_path,
        user_id=user.id
    )
    db.add(exam)
    db.commit()
else:
    exam.status = "Pronto"
    exam.progress = 100
    exam.progress_message = "Concluído com Sucesso"
    db.commit()

print(f"Exam ID {exam.id}: '{exam.title}'")

# Clear existing questions
db.query(Question).filter_by(exam_id=exam.id).delete()
db.commit()

parsed_questions = parse_exam_document(pdf_path, exam_id=exam.id, extract_images=True)
print(f"Total parsed questions: {len(parsed_questions)}")

for pq in parsed_questions:
    q = Question(
        exam_id=exam.id,
        numero_questao=str(pq['numero_questao']),
        statement=pq['enunciado'],
        options=json.dumps(pq['opcoes'], ensure_ascii=False),
        correct_answer=pq.get('resposta', 'A'),
        subject=pq.get('disciplina', 'Geral'),
        images=json.dumps(pq.get('images', []), ensure_ascii=False) if pq.get('images') else None,
        latex_support=pq.get('latex_support', 0)
    )
    db.add(q)

db.commit()
print(f"Successfully seeded {len(parsed_questions)} clean questions into Exam ID {exam.id}!")
db.close()
