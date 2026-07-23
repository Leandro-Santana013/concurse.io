import os
from app import Session, Exam, _real_scrape_exam

session = Session()

test_url = "https://anexos.cdn.selecao.net.br/uploads/227/concursos/178/anexos/438c99f6-4526-4405-a5b4-c2f8bb165ec6.pdf"

# Delete old if exists
old = session.query(Exam).filter_by(source_url=test_url).first()
if old:
    session.delete(old)
    session.commit()

exam = Exam(
    title="IDCAP - Concurso Pblico Concurso Pblico - 001/2024 - SAAE Aracruz - Resultado preliminar da prova objetiva",
    source_url=test_url,
    status="Aprovada"
)
session.add(exam)
session.commit()

print(f"Testing real scrape for exam: {exam.title} - {exam.source_url}")
success, msg = _real_scrape_exam(session, exam)
print("Scrape success:", success)
print("Msg:", msg)

session.close()
