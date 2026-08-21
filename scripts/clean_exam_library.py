import os
import glob
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from models.database import Session, Exam, Folder, Question, ExamAttempt, ExamCatalog, engine

def clean_exam_library(clean_catalog: bool = True):
    print("=" * 70)
    print("🗑️  CONCURSE.IO — LIMPEZA DA BIBLIOTECA DE PROVAS BAIXADAS")
    print("=" * 70)

    db = Session()
    try:
        # 1. Contagens prévias
        q_count = db.query(Question).count()
        att_count = db.query(ExamAttempt).count()
        ex_count = db.query(Exam).count()
        fld_count = db.query(Folder).count()
        cat_count = db.query(ExamCatalog).count()

        print(f"[1/4] Limpando registros do Banco de Dados...")
        print(f"  • Questões associadas: {q_count}")
        print(f"  • Tentativas de simulado: {att_count}")
        print(f"  • Provas baixadas: {ex_count}")
        print(f"  • Pastas da biblioteca: {fld_count}")
        if clean_catalog:
            print(f"  • Catálogo de busca em cache: {cat_count}")

        # Deleção em cascata / direta
        db.query(ExamAttempt).delete()
        db.query(Question).delete()
        db.query(Exam).delete()
        db.query(Folder).delete()
        if clean_catalog:
            db.query(ExamCatalog).delete()
        
        db.commit()
        print("  ✓ Banco de dados limpo com sucesso!")

        # 2. Limpeza de PDFs em pdfs/
        print("\n[2/4] Removendo arquivos PDF baixados em 'pdfs/'...")
        pdf_files = glob.glob(os.path.join("pdfs", "*.pdf"))
        removed_pdfs = 0
        for pdf_file in pdf_files:
            try:
                os.remove(pdf_file)
                removed_pdfs += 1
            except Exception as e:
                print(f"  [!] Falha ao remover {pdf_file}: {e}")
        print(f"  ✓ {removed_pdfs} PDFs removidos.")

        # 3. Limpeza de imagens extraídas
        print("\n[3/4] Removendo imagens extraídas de questões...")
        img_dirs = [
            os.path.join("static", "images", "questions"),
            os.path.join("static", "extracted_images"),
            os.path.join("static", "pdfs", "images"),
        ]
        removed_imgs = 0
        for d in img_dirs:
            if os.path.exists(d):
                for img_file in glob.glob(os.path.join(d, "*.*")):
                    try:
                        os.remove(img_file)
                        removed_imgs += 1
                    except Exception as e:
                        print(f"  [!] Falha ao remover {img_file}: {e}")
        print(f"  ✓ {removed_imgs} imagens de questões removidas.")

        # 4. Limpeza no SQLite local caso exista
        if os.path.exists("concurse.db"):
            try:
                import sqlite3
                conn = sqlite3.connect("concurse.db")
                cur = conn.cursor()
                for tbl in ["exam_attempts", "questions", "exams", "folders", "exam_catalog"]:
                    try:
                        cur.execute(f"DELETE FROM {tbl};")
                    except Exception:
                        pass
                conn.commit()
                cur.execute("VACUUM;")
                conn.close()
                print("  ✓ Arquivo local 'concurse.db' SQLite limpo e compactado.")
            except Exception as e:
                print(f"  [!] Aviso SQLite local: {e}")

        print("\n" + "=" * 70)
        print("✨ BIBLIOTECA DE PROVAS TOTALMENTE LIMPA E PRONTA PARA NOVO USO!")
        print("=" * 70)

    except Exception as err:
        db.rollback()
        print(f"\n❌ Erro durante a limpeza: {err}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    clean_exam_library(clean_catalog=True)
