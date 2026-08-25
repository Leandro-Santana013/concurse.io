import os, sys
sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from models.database import Session, Exam, Question, User

db = Session()
exams = db.query(Exam).all()
print(f"Total exams in DB: {len(exams)}")
for e in exams:
    q_count = db.query(Question).filter_by(exam_id=e.id).count()
    qs = db.query(Question).filter_by(exam_id=e.id).order_by(Question.id).all()
    q_nums = [q.numero_questao for q in qs]
    print(f"Exam ID {e.id}: '{e.title}' | Questions: {q_count} | Numbers: {q_nums[:10]} ... {q_nums[-5:] if len(q_nums) > 5 else []}")
db.close()
