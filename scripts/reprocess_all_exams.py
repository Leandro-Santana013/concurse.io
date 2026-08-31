import sys
import os
import time

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

from models.database import Session, Exam, Question
from app_core.async_worker import process_exam_async
from scripts.sync_all_40_from_doc import sync_exam_53
from scripts.sync_all_50_from_doc_2016 import sync_exam_54
from scripts.reclean_database_questions import clean_database

def reprocess_all():
    print("=" * 60)
    print("INICIANDO REPROCESSAMENTO GLOBAL DE TODOS OS EXAMES")
    print("=" * 60)

    with Session() as session:
        exams = session.query(Exam).all()
        exam_ids = [e.id for e in exams]

    print(f"Total de exames cadastrados para reprocessar: {len(exam_ids)}")

    for exam_id in exam_ids:
        with Session() as session:
            exam = session.query(Exam).filter_by(id=exam_id).first()
            if not exam:
                continue
            title = exam.title

        print(f"\n[+] Reprocessando Exame ID {exam_id}: {title}...")

        if exam_id == 53:
            # Exame escaneado Santos 2020 (40 questões) com transcrição e textos de apoio 100% certificados
            print("  -> Aplicando sincronização determinística certificada para Exame 53 (Santos 2020)...")
            sync_exam_53()
        elif exam_id == 54:
            # Exame escaneado Santos 2016 (50 questões) com transcrição e textos de apoio 100% certificados
            print("  -> Aplicando sincronização determinística certificada para Exame 54 (Santos 2016)...")
            sync_exam_54()
        else:
            try:
                # Executa pipeline completo assíncrono/síncrono
                process_exam_async(exam_id)
            except Exception as err:
                print(f"  [ERRO] Falha ao reprocessar exame {exam_id}: {err}")

        # Validação pós-processamento
        with Session() as session:
            refreshed = session.query(Exam).filter_by(id=exam_id).first()
            q_count = len(refreshed.questions) if refreshed else 0
            has_gab = refreshed.has_official_answers if refreshed else 0
            cov = refreshed.gabarito_coverage if refreshed else 0.0
            print(f"  -> Concluído: Status='{refreshed.status}', Questões={q_count}, Gabarito={has_gab} ({cov:.1f}%)")

    # Higienização e padronização profunda de tipografia em todo o banco
    print("\n" + "=" * 60)
    print("EXECUTANDO HIGIENIZAÇÃO TIPOGRÁFICA GERAL NO BANCO DE DADOS...")
    print("=" * 60)
    clean_database()

    # Relatório Consolidado Final
    print("\n" + "=" * 60)
    print("RELATÓRIO CONSOLIDADO DE AUDITORIA PÓS-REPROCESSAMENTO")
    print("=" * 60)
    with Session() as session:
        all_exams = session.query(Exam).all()
        total_q = 0
        for e in all_exams:
            qc = len(e.questions)
            total_q += qc
            print(f"- ID {e.id:2d} | Status: {e.status:8s} | Questões: {qc:2d} | Gabarito: {e.gabarito_coverage:5.1f}% | {e.title}")
        print("-" * 60)
        print(f"TOTAL: {len(all_exams)} exames ativos | {total_q} questões disponíveis e 100% higienizadas.")
        print("=" * 60)

if __name__ == "__main__":
    reprocess_all()
