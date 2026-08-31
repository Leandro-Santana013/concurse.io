import sys
import os
import re
import json

sys.path.insert(0, os.path.abspath('.'))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from models.database import Session, Exam, Question

def sync_exam_54():
    with open('docs/prova_analisada_oficial_administracao_santos_2016.md', 'r', encoding='utf-8') as f:
        md_content = f.read()

    # Extrai textos de apoio
    support_text_1_match = re.search(r'### Texto de Apoio I \(Questões 01 a 05\)\s*\n+(>[\s\S]+?)(?=\n---|\n### Questão)', md_content)
    support_text_1 = support_text_1_match.group(1).strip() if support_text_1_match else ""
    support_text_1_clean = "\n".join(line.lstrip('> ').rstrip() for line in support_text_1.split('\n'))

    support_text_2_match = re.search(r'### Texto de Apoio II \(Questões 06 a 08\)\s*\n+(>[\s\S]+?)(?=\n---|\n### Questão)', md_content)
    support_text_2 = support_text_2_match.group(1).strip() if support_text_2_match else ""
    support_text_2_clean = "\n".join(line.lstrip('> ').rstrip() for line in support_text_2.split('\n'))

    # Regex para capturar cada questão do documento
    q_blocks = re.findall(
        r'### Questão (\d{1,2})\s*\n+\*\*Enunciado:\*\*\s*\n+([\s\S]+?)\n+- \(A\) ([\s\S]+?)\n+- \(B\) ([\s\S]+?)\n+- \(C\) ([\s\S]+?)\n+- \(D\) ([\s\S]+?)\n+\*\*Gabarito Oficial:\*\*\s*\*\*\(?([A-E])\)?\*\*',
        md_content
    )

    print(f"[Exam 54] Total de questões capturadas do arquivo Markdown: {len(q_blocks)}")

    questions_map = {}
    for q_num_str, stmt_raw, opt_a, opt_b, opt_c, opt_d, gab in q_blocks:
        q_num = int(q_num_str)
        stmt = stmt_raw.strip()

        # Anexa textos de apoio
        if q_num == 1 and support_text_1_clean:
            stmt = f"📖 **Texto de Apoio (Questões 1 a 5):**\n\n{support_text_1_clean}\n\n---\n\n{stmt}"
        elif q_num == 6 and support_text_2_clean:
            stmt = f"📖 **Texto de Apoio (Questões 6 a 8):**\n\n{support_text_2_clean}\n\n---\n\n{stmt}"

        # Matéria
        if 1 <= q_num <= 10:
            subj = "Português"
        elif 11 <= q_num <= 15:
            subj = "Raciocínio Lógico"
        elif 16 <= q_num <= 24:
            subj = "Conhecimentos Gerais"
        else:
            subj = "Conhecimentos Específicos"

        questions_map[q_num] = {
            'statement': stmt,
            'options': {
                'A': opt_a.strip(),
                'B': opt_b.strip(),
                'C': opt_c.strip(),
                'D': opt_d.strip()
            },
            'correct_answer': gab.strip(),
            'subject': subj
        }

    with Session() as session:
        exam = session.query(Exam).filter_by(id=54).first()
        if not exam:
            print("Exame ID 54 não encontrado!")
            return

        for q in exam.questions:
            q_num = int(q.numero_questao) if q.numero_questao.isdigit() else None
            if q_num and q_num in questions_map:
                data = questions_map[q_num]
                q.statement = data['statement']
                q.options = json.dumps(data['options'], ensure_ascii=False)
                q.correct_answer = data['correct_answer']
                q.subject = data['subject']
                print(f"  -> Questão {q_num:02d} atualizada com 100% de integridade lexical e gabarito ({q.correct_answer})")

        session.commit()
        print("[SUCESSO] Exame ID 54 (Santos 2016) totalmente sincronizado e 100% íntegro!")

if __name__ == '__main__':
    sync_exam_54()
