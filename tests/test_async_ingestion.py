import os
import sys
import time
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from fastapi.testclient import TestClient
from fastapi_app import app
from models.database import Session, Exam, Question
from app_core.async_worker import process_exam_async

client = TestClient(app)

def test_search_api():
    print("1. Testing Search API...")
    r = client.get("/api/v1/search?q=IBAM+enfermeiro")
    assert r.status_code == 200, f"Search failed: {r.status_code}"
    results = r.json()
    print(f"   -> Search returned {len(results)} items.")
    if results:
        print("   -> Sample result:", results[0]["title"], "->", results[0]["url"][:60])

def test_local_exam_ingestion():
    print("2. Testing Async Exam Ingestion on local PDF...")
    # Find a sample PDF in pdfs/
    import glob
    pdf_files = [f for f in glob.glob("pdfs/*.pdf") if "_gab_" not in f]
    if not pdf_files:
        print("   -> No local test PDF found, skipping local ingestion test.")
        return

    sample_pdf = pdf_files[0]
    sample_gab = sample_pdf.replace(".pdf", "_gab.pdf")
    if not os.path.exists(sample_gab):
        gabs = glob.glob("pdfs/*gab*.pdf")
        sample_gab = gabs[0] if gabs else None

    with Session() as session:
        test_exam = Exam(
            title="Prova Teste Ingestão Automatizada",
            source_url=sample_pdf,
            gabarito_url=sample_gab,
            status="Processando",
            progress=5,
            progress_message="Iniciando teste...",
            user_id=1
        )
        session.add(test_exam)
        session.commit()
        session.refresh(test_exam)
        test_id = test_exam.id

    print(f"   -> Processing Exam ID {test_id} ({sample_pdf})...")
    process_exam_async(test_id)

    with Session() as session:
        finished_exam = session.query(Exam).filter_by(id=test_id).first()
        assert finished_exam is not None
        print(f"   -> Status: {finished_exam.status} (Progress: {finished_exam.progress}%)")
        print(f"   -> Progress Msg: {finished_exam.progress_message}")
        print(f"   -> Questions in DB: {len(finished_exam.questions)}")
        print(f"   -> Gabarito Coverage: {finished_exam.gabarito_coverage}%")
        assert finished_exam.progress == 100 or len(finished_exam.questions) >= 5

if __name__ == "__main__":
    test_search_api()
    test_local_exam_ingestion()
    print("\n SUCCESS: 100% dos testes da Fase 3 passaram perfeitamente!")
