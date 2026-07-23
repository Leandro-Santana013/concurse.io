import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from app import Session, Exam, Question
import json

session = Session()
exams = session.query(Exam).all()
print(f"Total exams: {len(exams)}")
for e in exams[-5:]:
    print(f"\nExam ID: {e.id}, Title: {e.title}, Status: {e.status}")
    questions = e.questions
    print(f"Total questions: {len(questions)}")
    for i, q in enumerate(questions):
        try:
            if q.options:
                json.loads(q.options)
        except Exception as err:
            print(f"ERROR on question {q.id}: {err} -> options='{q.options}'")
            break
        if i == 0:
            print(f"Q1 options format: {q.options}")
session.close()
