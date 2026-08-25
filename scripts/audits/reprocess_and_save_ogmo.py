import os, sys, json
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from models.database import Session, Exam, Question
from services.pdf_pipeline import parse_exam_document

db = Session()
exam = db.query(Exam).filter_by(id=19).first()
if not exam:
    print("Exam 19 not found!")
    db.close()
    sys.exit(1)

pdf_path = "pdfs/19_1787612141.pdf"
print(f"Reprocessing exam {exam.id}: {exam.title} from {pdf_path}...")
parsed_questions = parse_exam_document(pdf_path, exam_id=19, extract_images=True)
print(f"Total parsed questions: {len(parsed_questions)}")

# Delete existing questions for exam 19
db.query(Question).filter_by(exam_id=19).delete()
db.commit()

# Insert clean questions
for pq in parsed_questions:
    q = Question(
        exam_id=19,
        numero_questao=pq['numero_questao'],
        enunciado=pq['enunciado'],
        opcoes=json.dumps(pq['opcoes'], ensure_ascii=False),
        resposta_correta=pq.get('resposta', 'A'),
        disciplina=pq.get('disciplina', 'Geral'),
        images=json.dumps(pq.get('images', []), ensure_ascii=False) if pq.get('images') else None
    )
    db.add(q)

db.commit()
print(f"Successfully saved {len(parsed_questions)} questions to database for Exam 19!")
db.close()
