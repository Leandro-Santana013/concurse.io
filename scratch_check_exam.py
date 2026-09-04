import os
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['DATABASE_URL'])
from models.database import Session, Exam, Question

db = Session()
exams = db.query(Exam).filter(Exam.title.ilike('%indaiatuba%')).all()
print(f"Found {len(exams)} exams with indaiatuba:")
for e in exams:
    print(f"ID={e.id}, title='{e.title}', status='{e.status}', questions_count={len(e.questions)}")

oficial_exams = db.query(Exam).filter(Exam.title.ilike('%oficial%')).all()
print(f"Found {len(oficial_exams)} exams with oficial:")
for e in oficial_exams:
    print(f"ID={e.id}, title='{e.title}', status='{e.status}', questions_count={len(e.questions)}")
db.close()


