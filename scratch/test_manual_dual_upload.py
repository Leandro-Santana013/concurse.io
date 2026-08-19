import os
import sys
import io
import fitz

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app import app
from models import Session, User, Exam, Folder, init_db

def create_mock_exam_pdf():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "CADERNO DE QUESTÕES - PROVA OBJETIVA\n\nQUESTÃO 01\nEnunciado da primeira questão...\nA) Opção A\nB) Opção B\nC) Opção C\nD) Opção D\nE) Opção E\n\nQUESTÃO 02\nEnunciado da segunda questão...\nA) Opção A\nB) Opção B\nC) Opção C\nD) Opção D\nE) Opção E")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def create_mock_gabarito_pdf():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "GABARITO OFICIAL DEFINITIVO\n\n1-B\n2-D")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes

def test_manual_dual_upload_flow():
    print("=== Testando Ingestão Manual de Prova + Gabarito (create_manual) ===")
    init_db()
    
    with Session() as s:
        # Garante um usuário de teste
        user = s.query(User).filter_by(google_id="test_user_dual").first()
        if not user:
            user = User(google_id="test_user_dual", email="test@concurse.io", name="Test User")
            s.add(user)
            s.commit()
        user_id = user.id

    client = app.test_client()
    
    # Simula autenticação com Flask-Login session
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    exam_pdf_data = create_mock_exam_pdf()
    gab_pdf_data = create_mock_gabarito_pdf()

    data = {
        'title': 'Capatazia - OGMO - Porto Alegre/RS',
        'pdf_file': (io.BytesIO(exam_pdf_data), 'prova_capatazia.pdf'),
        'gabarito_file': (io.BytesIO(gab_pdf_data), 'gabarito_definitivo.pdf')
    }

    response = client.post('/api/exams/create_manual', data=data, content_type='multipart/form-data')
    print(f"Status HTTP: {response.status_code}", flush=True)
    print(f"Resposta JSON: {response.get_json()}", flush=True)
    
    assert response.status_code == 200
    res_json = response.get_json()
    assert res_json.get('success') is True
    exam_id = res_json.get('exam_id')
    assert exam_id is not None
    print(f"[OK] Endpoint /api/exams/create_manual respondeu com sucesso para Prova #{exam_id}!", flush=True)
    
    # Limpeza
    with Session() as s:
        e = s.query(Exam).filter_by(id=exam_id).first()
        if e:
            s.delete(e)
            s.commit()

    print("[SUCESSO] TESTE DE UPLOAD MANUAL DE PROVA E GABARITO PASSOU COM 100%!", flush=True)
    sys.exit(0)

if __name__ == '__main__':
    test_manual_dual_upload_flow()
