import os
import sys
import json
import glob
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from models.database import Session, Exam, Question, Folder
from services.pdf_pipeline.hybrid_extractor import parse_exam_document
from services.gabarito_service import parse_gabarito_from_pdf, parse_gabarito_from_text, merge_exam_with_gabarito, format_gabarito_summary

def reprocess_all_exams():
    print("=================================================================")
    print("INICIANDO REPROCESSAMENTO EM LOTE DE PROVAS COM O NOVO PIPELINE")
    print("=================================================================\n")

    with Session() as session:
        exam_ids = [e.id for e in session.query(Exam.id).order_by(Exam.id).all()]
    
    print(f"Total de exames encontrados no banco: {len(exam_ids)}\n")

    success_count = 0
    skipped_count = 0
    error_count = 0

    for exam_id in exam_ids:
        with Session() as session:
            exam = session.query(Exam).filter_by(id=exam_id).first()
            if not exam:
                continue
            title = exam.title
            source_url = exam.source_url
            gabarito_url = exam.gabarito_url
            answer_key_source = exam.answer_key_source

        print(f"--- Processando Exame ID {exam_id}: '{title}' ---")
        pdf_path = None
        if source_url and os.path.exists(source_url):
            pdf_path = source_url
        else:
            matching = [f for f in glob.glob(f"pdfs/{exam_id}_*.pdf") if "_gab_" not in f]
            if matching:
                pdf_path = matching[0]

        # Se não achou localmente, tenta baixar da source_url
        if not pdf_path or not os.path.exists(pdf_path):
            if source_url and source_url.startswith('http'):
                print(f"   Baixando PDF da URL: {source_url}...")
                os.makedirs('pdfs', exist_ok=True)
                dest_file = f"pdfs/{exam_id}_reproc.pdf"
                from app_core.async_worker import download_pdf_file
                if download_pdf_file(source_url, dest_file):
                    pdf_path = dest_file

        if not pdf_path or not os.path.exists(pdf_path):
            print(f"   Aviso: PDF não encontrado localmente nem por download para o exame {exam_id}. Pulando...")
            skipped_count += 1
            continue

        try:
            questions = parse_exam_document(
                pdf_bytes_or_path=pdf_path,
                exam_id=exam_id,
                extract_images=True
            )

            if not questions or len(questions) < 2:
                print(f"   Aviso: PDF é scan/não possui camada textual OCR ou questões ({pdf_path}).")
                with Session() as session:
                    exam = session.query(Exam).filter_by(id=exam_id).first()
                    if exam:
                        exam.status = 'Erro'
                        exam.progress_message = 'Documento escaneado/sem texto OCR pesquisável.'
                        session.commit()
                error_count += 1
                continue

            gabarito_dict = {}
            answer_source = answer_key_source or "none"

            gab_matching = glob.glob(f"pdfs/{exam_id}_gab_*.pdf")
            if gab_matching and os.path.exists(gab_matching[0]):
                gabarito_dict = parse_gabarito_from_pdf(gab_matching[0])
                answer_source = "attached_pdf"
            elif gabarito_url and os.path.exists(gabarito_url):
                gabarito_dict = parse_gabarito_from_pdf(gabarito_url)
                answer_source = "attached_pdf"
            elif not gabarito_dict and os.path.exists(pdf_path):
                gabarito_dict = parse_gabarito_from_pdf(pdf_path)
                if gabarito_dict:
                    answer_source = "embedded_pdf"

            updated_questions, stats = merge_exam_with_gabarito(questions, gabarito_dict)

            with Session() as session:
                exam = session.query(Exam).filter_by(id=exam_id).first()
                if not exam:
                    continue

                session.query(Question).filter_by(exam_id=exam_id).delete()

                for q_data in updated_questions:
                    new_q = Question(
                        exam_id=exam_id,
                        statement=q_data['enunciado'],
                        options=json.dumps(q_data['opcoes']),
                        correct_answer=q_data['resposta'],
                        subject=q_data.get('disciplina', 'Geral'),
                        images=json.dumps(q_data['images']) if q_data.get('images') else None,
                        numero_questao=str(q_data['numero_questao']),
                        latex_support=q_data.get('latex_support', 0)
                    )
                    session.add(new_q)

                exam.status = 'Aprovada'
                exam.progress = 100
                exam.progress_message = f"Reprocessada com sucesso! ({len(updated_questions)} questões)"
                exam.has_official_answers = 1 if stats['has_official_answers'] else 0
                exam.gabarito_coverage = stats['coverage_pct']
                exam.answer_key_source = answer_source
                exam.gabarito_text = format_gabarito_summary(gabarito_dict)

                session.commit()

            print(f"   Sucesso: {len(updated_questions)} questões salvas, Gabarito: {stats['coverage_pct']}%\n")
            success_count += 1

        except Exception as e:
            print(f"   Erro ao processar exame {exam_id}: {e}\n")
            error_count += 1

    print("=================================================================")
    print(f"RESUMO: {success_count} Sucessos | {skipped_count} Ignorados | {error_count} Falhas")
    print("=================================================================")

if __name__ == '__main__':
    reprocess_all_exams()
