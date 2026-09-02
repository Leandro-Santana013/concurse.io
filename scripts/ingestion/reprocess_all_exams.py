import os, sys
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import os
import re
import sys
import json
import glob
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from models.database import AnswerKeyMatchAudit, Session, Exam, Question, Folder
from services.pdf_pipeline import parse_exam_document
from services.gabarito import (
    AnswerKeyMatchResult,
    build_exam_answer_key_profile,
    extract_exam_code_ranges_from_pdf,
    format_gabarito_summary,
    match_gabarito_from_pdf,
    merge_exam_with_gabarito,
    parse_gabarito_from_text,
)

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
            exam_code_ranges = extract_exam_code_ranges_from_pdf(pdf_path)
            exam_profile = build_exam_answer_key_profile(
                pdf_path,
                questions,
                title=title,
                code_ranges=exam_code_ranges,
            )
            answer_key_attempts = []
            answer_source = answer_key_source or "none"

            gab_matching = glob.glob(f"pdfs/{exam_id}_gab_*.pdf")
            if gab_matching and os.path.exists(gab_matching[0]):
                candidate_match = match_gabarito_from_pdf(
                    gab_matching[0],
                    exam_profile,
                    source_relation="paired",
                    document_hint=gabarito_url or gab_matching[0],
                )
                answer_key_attempts.append(candidate_match)
                if candidate_match.accepted:
                    gabarito_dict = candidate_match.answers
                    answer_source = "attached_pdf"
            if not gabarito_dict and gabarito_url and os.path.exists(gabarito_url):
                candidate_match = match_gabarito_from_pdf(
                    gabarito_url,
                    exam_profile,
                    source_relation="paired",
                    document_hint=gabarito_url,
                )
                answer_key_attempts.append(candidate_match)
                if candidate_match.accepted:
                    gabarito_dict = candidate_match.answers
                    answer_source = "attached_pdf"
            if not gabarito_dict and os.path.exists(pdf_path):
                candidate_match = match_gabarito_from_pdf(
                    pdf_path,
                    exam_profile,
                    source_relation="embedded",
                    document_hint=source_url or pdf_path,
                )
                answer_key_attempts.append(candidate_match)
                if candidate_match.accepted:
                    gabarito_dict = candidate_match.answers
                    answer_source = "embedded_pdf"

            accepted_match = next(
                (attempt for attempt in answer_key_attempts if attempt.accepted),
                None,
            )
            match_result = accepted_match or next(
                (attempt for attempt in answer_key_attempts if attempt.candidate),
                None,
            ) or AnswerKeyMatchResult(
                profile=exam_profile,
                status="not_found",
                conflicts=["no_answer_key_candidate"],
            )

            updated_questions, stats = merge_exam_with_gabarito(
                questions,
                gabarito_dict,
                strict=bool(match_result.accepted),
            )
            if stats.get("integrity_conflicts"):
                match_result.accepted = False
                match_result.status = "rejected"
                match_result.confidence = 0.0
                match_result.conflicts = list(dict.fromkeys([
                    *match_result.conflicts,
                    *stats["integrity_conflicts"],
                ]))
                gabarito_dict = {}
                answer_source = "none"
                updated_questions, stats = merge_exam_with_gabarito(questions, {})

            with Session() as session:
                exam = session.query(Exam).filter_by(id=exam_id).first()
                if not exam:
                    continue

                session.query(Question).filter_by(exam_id=exam_id).delete()

                def _q_sort_key(q):
                    raw = str(q.get('numero_questao', '')).strip()
                    if raw.isdigit():
                        return (0, int(raw))
                    m = re.match(r'^(\d+)', raw)
                    if m:
                        return (0, int(m.group(1)))
                    return (1, 99999)

                sorted_questions = sorted(updated_questions, key=_q_sort_key)

                for q_data in sorted_questions:
                    new_q = Question(
                        exam_id=exam_id,
                        statement=q_data['enunciado'],
                        options=json.dumps(q_data['opcoes'], ensure_ascii=False),
                        correct_answer=q_data['resposta'],
                        subject=q_data.get('disciplina', 'Geral'),
                        images=json.dumps(q_data['images'], ensure_ascii=False) if q_data.get('images') else None,
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
                session.add(AnswerKeyMatchAudit(
                    exam_id=exam.id,
                    accepted=1 if match_result.accepted else 0,
                    status=match_result.status,
                    confidence=match_result.confidence,
                    answer_source=answer_source,
                    method=match_result.method,
                    candidate_page=match_result.candidate_page,
                    decision_json=match_result.to_audit_json(),
                    created_at=datetime.now().isoformat(),
                ))

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
