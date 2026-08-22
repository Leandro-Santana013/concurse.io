import os
import sys
import json

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath('.'))
from models.database import Session, Exam, Question, Folder, User
from services.pdf_pipeline.hybrid_extractor import parse_exam_document

def insert_exam():
    pdf_path = os.path.join("pdfs", "prova_teste_download.pdf")
    source_url = "https://anexos.cdn.selecao.net.br/uploads/227/concursos/210/anexos/88e63355-79f7-4c00-ae31-c9f73541120f.pdf"
    exam_title = "[IDCAP] Trabalhador Portuário Avulso - Categoria Capatazia (SINTRAPORT)"
    
    print(f"⚙️ Processando PDF para inserção no banco: {pdf_path}")
    questions_data = parse_exam_document(pdf_path, exam_id=227, extract_images=True)
    print(f"📊 Total de Questões Extraídas com Sucesso: {len(questions_data)}")
    
    db = Session()
    try:
        # Garante usuário default
        user = db.query(User).first()
        if not user:
            user = User(google_id="default_user", email="user@concurse.io", name="Concurseiro")
            db.add(user)
            db.commit()
            db.refresh(user)

        # Pasta IDCAP
        folder = db.query(Folder).filter_by(name="IDCAP").first()
        if not folder:
            folder = Folder(name="IDCAP", user_id=user.id)
            db.add(folder)
            db.commit()
            db.refresh(folder)

        # Verifica se a prova já existe pelo source_url ou título
        existing_exam = db.query(Exam).filter(
            (Exam.source_url == source_url) | (Exam.title == exam_title)
        ).first()

        if existing_exam:
            print(f"♻️ Prova existente encontrada (ID: {existing_exam.id}). Atualizando dados...")
            exam = existing_exam
            exam.title = exam_title
            exam.status = 'Aprovada'
            exam.folder_id = folder.id
            exam.user_id = user.id
            exam.has_official_answers = 1
            exam.answer_key_source = 'embedded'
            exam.gabarito_coverage = 100.0
            exam.progress = 100
            exam.progress_message = 'Processada com sucesso'
            
            # Limpa questões anteriores
            db.query(Question).filter_by(exam_id=exam.id).delete()
            db.commit()
        else:
            print("✨ Criando nova prova no banco de dados...")
            exam = Exam(
                title=exam_title,
                status='Aprovada',
                folder_id=folder.id,
                user_id=user.id,
                source_url=source_url,
                has_official_answers=1,
                answer_key_source='embedded',
                gabarito_coverage=100.0,
                progress=100,
                progress_message='Processada com sucesso'
            )
            db.add(exam)
            db.commit()
            db.refresh(exam)

        print(f"💾 Inserindo {len(questions_data)} questões associadas ao Exam ID: {exam.id}...")
        
        for q in questions_data:
            q_num = str(q.get('numero_questao', ''))
            statement = q.get('enunciado', '').strip()
            options = q.get('opcoes', {})
            correct_answer = q.get('resposta', 'A')
            subject = q.get('disciplina', 'Geral')
            images = q.get('images')
            latex_support = q.get('latex_support', 0)

            question_obj = Question(
                exam_id=exam.id,
                numero_questao=q_num,
                statement=statement,
                options=json.dumps(options, ensure_ascii=False) if isinstance(options, (dict, list)) else str(options),
                correct_answer=correct_answer,
                subject=subject,
                images=json.dumps(images, ensure_ascii=False) if images else None,
                latex_support=latex_support,
                difficulty_level='Média'
            )
            db.add(question_obj)

        db.commit()
        print(f"🎉 Prova salva no banco de dados com Sucesso!")
        print(f"📌 Exam ID: {exam.id}")
        print(f"📁 Pasta: {folder.name}")
        print(f"📝 Título: {exam.title}")
        print(f"🔢 Total de Questões: {len(questions_data)}")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Erro ao salvar prova no banco: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    insert_exam()
