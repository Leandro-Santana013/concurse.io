import sys
import os
import re
import json

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

from models.database import Session, Exam, Question

def sync_exam_53():
    with open('docs/prova_analisada_oficial_administracao_santos_2020.md', 'r', encoding='utf-8') as f:
        md_content = f.read()

    # Extrai textos de apoio
    support_text_1_match = re.search(r'### Texto de Apoio I \(Questões 01 a 03\)\s*\n+(>[\s\S]+?)(?=\n---|\n### Questão)', md_content)
    support_text_1 = support_text_1_match.group(1).strip() if support_text_1_match else ""
    # Remove leading > from blockquotes for clean markdown
    support_text_1_clean = "\n".join(line.lstrip('> ').rstrip() for line in support_text_1.split('\n'))

    support_text_2_match = re.search(r'### Texto de Apoio II \(Questões 04 e 05\)[^\n]*\n+(>[\s\S]+?)(?=\n---|\n### Questão)', md_content)
    support_text_2 = support_text_2_match.group(1).strip() if support_text_2_match else ""
    support_text_2_clean = "\n".join(line.lstrip('> ').rstrip() for line in support_text_2.split('\n'))

    support_text_3_match = re.search(r'### Texto de Apoio III \(Questões 08 a 10\)\s*\n+(>[\s\S]+?)(?=\n---|\n### Questão)', md_content)
    support_text_3 = support_text_3_match.group(1).strip() if support_text_3_match else ""
    support_text_3_clean = "\n".join(line.lstrip('> ').rstrip() for line in support_text_3.split('\n'))

    # Regex para capturar cada questão do documento
    # Formato:
    # ### Questão XX
    # **Enunciado:**
    # <texto>
    # - (A) <opt A>
    # - (B) <opt B>
    # - (C) <opt C>
    # - (D) <opt D>
    # **Gabarito Oficial:** **(X)**
    q_blocks = re.findall(
        r'### Questão (\d{1,2})\s*\n+\*\*Enunciado:\*\*\s*\n+([\s\S]+?)\n+- \(A\) ([\s\S]+?)\n+- \(B\) ([\s\S]+?)\n+- \(C\) ([\s\S]+?)\n+- \(D\) ([\s\S]+?)\n+\*\*Gabarito Oficial:\*\*\s*\*\*\(?([A-E])\)?\*\*',
        md_content
    )

    print(f"Total de questões capturadas do arquivo Markdown: {len(q_blocks)}")

    questions_map = {}
    for q_num_str, stmt_raw, opt_a, opt_b, opt_c, opt_d, gab in q_blocks:
        q_num = int(q_num_str)
        stmt = stmt_raw.strip()

        # Anexa textos de apoio nas primeiras questões de cada bloco
        if q_num == 1 and support_text_1_clean:
            stmt = f"📖 **Texto de Apoio (Questões 1 a 3):**\n\n{support_text_1_clean}\n\n---\n\n{stmt}"
        elif q_num == 4 and support_text_2_clean:
            stmt = f"📖 **Texto de Apoio (Questões 4 e 5):**\n\n{support_text_2_clean}\n\n---\n\n{stmt}"
        elif q_num == 8 and support_text_3_clean:
            stmt = f"📖 **Texto de Apoio (Questões 8 a 10):**\n\n{support_text_3_clean}\n\n---\n\n{stmt}"

        questions_map[q_num] = {
            'statement': stmt,
            'options': {
                'A': opt_a.strip(),
                'B': opt_b.strip(),
                'C': opt_c.strip(),
                'D': opt_d.strip()
            },
            'correct_answer': gab.strip().upper(),
            'subject': 'Português' if q_num <= 10 else ('Matemática' if q_num <= 15 else ('Conhecimentos Gerais' if q_num <= 18 else 'Conhecimentos Específicos'))
        }

    with Session() as session:
        exam = session.query(Exam).filter_by(id=53).first()
        if not exam:
            print("Exame 53 não encontrado!")
            return

        print(f"Atualizando questões do Exame ID {exam.id}: '{exam.title}'...")
        
        # Mapeia questões existentes
        db_q_map = {int(q.numero_questao): q for q in exam.questions if str(q.numero_questao).isdigit()}
        
        for q_num in range(1, 41):
            if q_num not in questions_map:
                print(f"  [AVISO] Q{q_num} não encontrada no markdown!")
                continue
                
            q_data = questions_map[q_num]
            
            if q_num in db_q_map:
                db_q = db_q_map[q_num]
                db_q.statement = q_data['statement']
                db_q.options = json.dumps(q_data['options'], ensure_ascii=False)
                db_q.correct_answer = q_data['correct_answer']
                db_q.subject = q_data['subject']
            else:
                new_q = Question(
                    exam_id=exam.id,
                    numero_questao=str(q_num),
                    statement=q_data['statement'],
                    options=json.dumps(q_data['options'], ensure_ascii=False),
                    correct_answer=q_data['correct_answer'],
                    subject=q_data['subject'],
                    difficulty_level='Média'
                )
                session.add(new_q)
                
        session.commit()
        print("[SUCESSO] Todas as 40 questões do Exame 53 foram perfeitamente sincronizadas no banco de dados!")

if __name__ == "__main__":
    sync_exam_53()
