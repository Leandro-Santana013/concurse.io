import os
from dotenv import load_dotenv
load_dotenv()
from models.database import Session, Exam, Question

db = Session()
exam76 = db.query(Exam).filter(Exam.id == 76).first()
print(f"Exam 76 gabarito_text: {exam76.gabarito_text}")
db.close()



