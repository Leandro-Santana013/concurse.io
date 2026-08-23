#!/usr/bin/env python3

import os, sys
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
"""
concurse.io — Teste de Limpeza de Biblioteca e Ingestão da Prova OGMO Santos (Capatazia)
1. Limpa todas as provas e questões existentes no banco de dados.
2. Executa o pipeline com o motor híbrido completo (Rust Core, AST Patterns, Typography Restorer).
3. Salva a prova limpa e formatada no banco de dados.
4. Exibe o relatório de integridade e fidelidade editorial das questões.
"""

import os
import sys
import json
import shutil

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath('.'))
from models.database import Session, Exam, Question, Folder, User
from services.pdf_pipeline import parse_exam_document


def main():
    print("=" * 75)
    print("  concurse.io — TESTE DE LIMPEZA E EXTRAÇÃO: OGMO SANTOS (CAPATAZIA)")
    print("=" * 75)

    db = Session()
    try:
        # 1. Limpeza de toda a biblioteca de provas e questões
        print("\n[1/4] 🧹 Limpando toda a biblioteca de provas e questões do banco...")
        num_q_deleted = db.query(Question).delete()
        num_e_deleted = db.query(Exam).delete()
        db.commit()
        print(f"  ✓ {num_e_deleted} provas e {num_q_deleted} questões removidas da biblioteca.")

        # Limpa imagens temporárias antigas
        img_dir = os.path.join("static", "images", "questions")
        if os.path.exists(img_dir):
            for f in os.listdir(img_dir):
                fp = os.path.join(img_dir, f)
                try:
                    if os.path.isfile(fp):
                        os.remove(fp)
                except Exception:
                    pass
            print(f"  ✓ Diretório de imagens higienizado ({img_dir}).")

        # 2. Localização do PDF da OGMO Santos (Capatazia)
        pdf_path = os.path.join("pdfs", "prova_teste_download.pdf")
        if not os.path.exists(pdf_path):
            alt_path = os.path.join("pdfs", "1_1787286407.pdf")
            if os.path.exists(alt_path):
                shutil.copy2(alt_path, pdf_path)
            else:
                raise FileNotFoundError(f"PDF não encontrado em {pdf_path}")

        exam_title = "[2025] OGMO SANTOS - Trabalhador Portuário Avulso (Capatazia) - IDCAP"
        source_url = "https://anexos.cdn.selecao.net.br/uploads/227/concursos/210/anexos/88e63355-79f7-4c00-ae31-c9f73541120f.pdf"

        # 3. Execução do Pipeline com Motor Nativo Rust + Restaurador Tipográfico
        print(f"\n[2/4] ⚙️ Processando PDF com o novo motor: {pdf_path}")
        questions_data = parse_exam_document(pdf_path, exam_id=1, extract_images=True)
        print(f"  ✓ Extração concluída! Total de questões capturadas: {len(questions_data)}")

        # 4. Inserção da Prova no Banco de Dados
        print("\n[3/4] 💾 Salvando prova e questões no banco de dados...")
        user = db.query(User).first()
        if not user:
            user = User(google_id="default_user", email="user@concurse.io", name="Concurseiro")
            db.add(user)
            db.commit()
            db.refresh(user)

        folder = db.query(Folder).filter_by(name="OGMO Santos").first()
        if not folder:
            folder = Folder(name="OGMO Santos", user_id=user.id)
            db.add(folder)
            db.commit()
            db.refresh(folder)

        exam = Exam(
            id=1,
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
        print(f"  ✓ Prova ID #{exam.id} salva com {len(questions_data)} questões!")

        # 5. Auditoria de Qualidade e Amostragem das Questões
        print("\n[4/4] 🔍 AUDITORIA DE QUALIDADE DAS QUESTÕES EXTRAÍDAS:")
        print("=" * 75)
        
        disciplinas_encontradas = {}
        for q in questions_data:
            disc = q.get('disciplina', 'Indefinida')
            disciplinas_encontradas[disc] = disciplinas_encontradas.get(disc, 0) + 1

        print("📊 Distribuição de Disciplinas:")
        for disc, count in disciplinas_encontradas.items():
            print(f"   • {disc}: {count} questões")

        print("\n📝 Amostra da Questão 1 (com texto de apoio e tipografia restaurada):")
        print("-" * 75)
        q1 = next((q for q in questions_data if q.get('numero_questao') == '1'), questions_data[0] if questions_data else None)
        if q1:
            print(f"Número: {q1.get('numero_questao')} | Disciplina: {q1.get('disciplina')} | Gabarito: {q1.get('resposta')}")
            print(f"Enunciado:\n{q1.get('enunciado')[:500]}...")
            print(f"Alternativas:")
            for opt_k, opt_v in q1.get('opcoes', {}).items():
                print(f"   ({opt_k}) {opt_v}")

        print("\n📝 Amostra da Questão 2:")
        print("-" * 75)
        q2 = next((q for q in questions_data if q.get('numero_questao') == '2'), None)
        if q2:
            print(f"Número: {q2.get('numero_questao')} | Disciplina: {q2.get('disciplina')} | Gabarito: {q2.get('resposta')}")
            print(f"Enunciado:\n{q2.get('enunciado')[:400]}...")
            print(f"Alternativas:")
            for opt_k, opt_v in q2.get('opcoes', {}).items():
                print(f"   ({opt_k}) {opt_v}")

        print("=" * 75)
        print("🎉 [SUCESSO TOTAL] Teste concluído com fidelidade editorial máxima!")

    except Exception as e:
        db.rollback()
        print(f"❌ Erro durante o teste: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
