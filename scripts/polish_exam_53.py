import sys
import os
import json

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

from models.database import Session, Exam, Question

with Session() as session:
    exam = session.query(Exam).filter_by(id=53).first()
    if exam:
        for q in exam.questions:
            if q.numero_questao == '2':
                q.statement = '"O passado foi duro, mas deixou o seu legado" – outra maneira de escrever a frase, sem alterar o seu significado original foi reproduzida em qual alternativa?'
                q.options = json.dumps({
                    'A': 'O passado foi duro e isso nos deixou um fardo difícil de carregar.',
                    'B': 'O legado difícil que nos deixou o passado impede-nos de ser felizes.',
                    'C': 'A despeito de o passado haver sido difícil, deixou ensinamentos.',
                    'D': 'O passado foi duro e isso tornou impossível o seu legado.'
                }, ensure_ascii=False)
            elif q.numero_questao == '3':
                q.statement = 'Ao lermos o poema podemos tirar algumas conclusões sobre a autora. Uma delas está representada em qual alternativa?'
                q.options = json.dumps({
                    'A': 'As lutas e contradições por que passou serviram-lhe de lições de vida.',
                    'B': 'Ela não se orgulha do fato de ser uma mulher.',
                    'C': 'As pedras em seu caminho foram obstáculos que limitaram o seu aprendizado.',
                    'D': 'Os tempos rudes em que nasceu a impediram de aceitar contradições.'
                }, ensure_ascii=False)
            elif q.numero_questao == '4':
                q.statement = 'Observando as imagens e o texto dos quadrinhos, concluímos que:'
                q.options = json.dumps({
                    'A': 'Mônica, a amiga de Magali, come muito e não engorda.',
                    'B': 'Magali comeu dois pedaços de pizza.',
                    'C': 'as garotas desistiram de comer pastéis, pois é um alimento que engorda.',
                    'D': 'a propensão a engordar de Magali origina-se no fato dela comer muito.'
                }, ensure_ascii=False)
            elif q.numero_questao == '6':
                q.statement = """Analise as frases seguintes

I. Pagou à conta de luz que havia vencido uma semana antes.

II. O rapaz pagou à amiga uma antiga dívida.

III. Chegou à cidade bastante cansado – a viagem havia sido longa.

Observamos que a regência verbal não respeitou a gramática normativa em:"""
                q.options = json.dumps({
                    'A': 'I, apenas.',
                    'B': 'I e III, apenas.',
                    'C': 'II e III, apenas.',
                    'D': 'A regência verbal está correta em I, II e III.'
                }, ensure_ascii=False)
            elif q.numero_questao == '7':
                q.statement = """Leia os períodos a seguir

I. Um professor e uma professora _____ homenageados pelos alunos.

II. 1% da população _____ a iniciativa da Prefeitura de distribuir alimentos às famílias carentes.

III. Já _____ sete horas, estamos atrasados!

Para que a concordância verbal se realize em conformidade com a norma culta, as lacunas acima deverão ser preenchidas como indicado em qual alternativa?"""
                q.options = json.dumps({
                    'A': 'I - foi; II - apoiaram; III - é.',
                    'B': 'I - forão; II - apoião; III - são.',
                    'C': 'I - foram; II - apoiaram; III - é.',
                    'D': 'I - foram; II - apoia; III - são.'
                }, ensure_ascii=False)
        session.commit()
        print("Successfully polished exam 53 questions in SQLite database!")
