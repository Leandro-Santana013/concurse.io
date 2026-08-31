import sys
import os
import json

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from models.database import Session, Exam, Question

high_fidelity_q = {
    '1': {
        'statement': """📖 **Texto de Apoio (Questões 1 a 5):**

**AS FLORES**
*Leon Eliachar*

Há dois meses que Iracema recebia flores, sem cartão. Colocava tudo nas jarras, vasos, copos; mesas, janelas, banheiro e até na cozinha. Quando o marido lhe perguntava por que tantas flores, todos os dias, ela sorria:
— Deixe de brincadeira, Epitácio...
Ele não percebia bem o que ela queria dizer, até que um dia:
— Epitácio, acho bom você parar de comprar tantas flores, já não tenho mais onde colocar.
Foi aí que ele compreendeu tudo:
— O quê? Você quer insinuar que não sabia que não sou eu quem manda essas flores?
Foi o diabo. Ela não sabia explicar quem mandava; ele não conseguia convencê-la de que não era ele.
— Um de nós dois está mentindo — gritou, furioso.
— Então é você — rebateu ela.
No dia seguinte, de manhã, ele decidiu não sair, para desvendar o mistério. Assim que as flores chegassem, a pessoa que as trouxesse seria interpelada. Mas não veio ninguém:
— Já são duas horas da tarde e as flores não chegaram, Epitácio. É muita coincidência. Vai me dizer que não era você?
Meia hora depois, a mulher saiu e foi ao florista:
— Como vai, Dona Iracema? A senhora ontem não veio, hein? Aconteceu alguma coisa?
À noite, Epitácio viu as flores e não disse uma palavra, mas a mulher não parou. Nessa noite ele teve insônia.

---

"Há dois meses que Iracema recebia flores, sem cartão". A respeito do emprego do verbo **"haver"**, analise as sentenças a seguir:

I. Nas praias de Santos, houveram muitas pessoas presentes na queima de fogos em comemoração ao Ano Novo.
II. Há meses em que tudo parece dar errado, mas é preciso manter a calma para que uma solução seja possível.
III. Felizmente, os festejos correram bem e não houve incidentes graves.

Está correto o que se afirma em:""",
        'options': {
            'A': 'I e II, apenas.',
            'B': 'I e III, apenas.',
            'C': 'II e III, apenas.',
            'D': 'I, II e III.'
        }
    },
    '2': {
        'statement': """"— Epitácio, acho bom você parar de comprar tantas flores, já não tenho mais onde colocar".

Respeitando as regras de colocação pronominal e a norma-padrão da língua escrita, o trecho acima foi reescrito corretamente em qual alternativa?""",
        'options': {
            'A': 'Acho bom você parar de comprar tantas flores, Epitácio, já não tenho mais onde colocar elas.',
            'B': 'Epitácio, acho bom você parar de comprar tantas flores, já não as tenho mais onde colocar.',
            'C': 'Acho bom você parar de comprar tantas flores, Epitácio, já não tenho mais onde colocá-las.',
            'D': 'Epitácio, acho bom você parar de comprar tantas flores, já não tenho mais onde colocar-lhes.'
        }
    },
    '3': {
        'statement': """No conto "As Flores", o fato de Iracema acreditar que era o marido quem lhe enviava os buquês é explicado em qual alternativa?""",
        'options': {
            'A': 'A esposa estava gastando muito dinheiro comprando flores para si mesma.',
            'B': 'Ela tentava encobrir a compra das flores simulando surpresa para provocar ciúmes no marido.',
            'C': 'Incomodava-o ver flores por todos os cantos da casa — até mesmo no banheiro e na cozinha.',
            'D': 'O marido costumava ser muito romântico no início do casamento e ela pensava ser uma reconciliação.'
        }
    },
    '4': {
        'statement': """"No dia seguinte, de manhã, ele decidiu não sair, para **desvendar** o mistério. Assim que as flores chegassem, a pessoa que as trouxesse seria **interpelada**."

Para que seja preservado o sentido original do trecho acima, as palavras destacadas podem ser substituídas, na ordem em que aparecem, por:""",
        'options': {
            'A': 'descobrir e agredida.',
            'B': 'esconder e espancada.',
            'C': 'esclarecer e interrogada.',
            'D': 'aumentar e ignorada.'
        }
    },
    '5': {
        'statement': """Ao final da história de Leon Eliachar, fica claro para o leitor que:""",
        'options': {
            'A': 'A própria dona Iracema comprava as flores no florista e fingia que as recebia de um admirador secreto.',
            'B': 'A esposa de Epitácio estava vivendo um romance extraconjugal com o florista.',
            'C': 'Epitácio realmente comprava as flores, mas sofria de lapsos de memória e insônia.',
            'D': 'O entregador da floricultura entregava as flores por engano no endereço do casal.'
        }
    },
    '7': {
        'statement': """📖 **Texto de Apoio (Questões 6 a 8):**

**CRIANÇAS, CRUELDADE E JUSTIÇA**
*(Sobre o Bullying e Convivência Escolar)*

Segundo dados e pesquisas do IBGE citados no texto sobre violência e intimidação sistemática no ambiente escolar:""",
        'options': {
            'A': 'Vinte vírgula oito por cento dos alunos do ensino fundamental, na faixa etária entre 13 e 15 anos, foram vítimas de agressão em virtude do bullying nas escolas.',
            'B': 'O bullying afeta apenas crianças na primeira infância, deixando de existir na adolescência.',
            'C': 'O ambiente virtual e a internet reduziram drasticamente os traumas psicológicos dos jovens.',
            'D': 'A maioria absoluta dos casos de intimidação é resolvida exclusivamente com medidas penais.'
        }
    },
    '8': {
        'statement': """Analise as afirmações a seguir a respeito do texto sobre o bullying:

I. Assegurar que "a internet amplia seus efeitos" equivale a afirmar que o meio digital multiplica o alcance e a intensidade do assédio.
II. As vítimas de bullying são assediadas exclusivamente por características de ordem física, tais como altura, cor da pele ou excesso de peso.
III. O autor afirma que a solução duradoura para o problema reside em políticas preventivas, familiares e educacionais concretas, e não apenas em leis punitivas formais.

Está correto o que se afirma em:""",
        'options': {
            'A': 'Apenas um dos itens apresentados.',
            'B': 'Apenas dois dos itens apresentados.',
            'C': 'Apenas três dos itens apresentados.',
            'D': 'Todos os itens apresentados.'
        }
    },
    '9': {
        'statement': """No que se refere à concordância verbal e nominal segundo a norma-padrão da Língua Portuguesa, assinale a alternativa que apresenta a frase **incorreta**:""",
        'options': {
            'A': 'Sofrem bullying em razão da aparência de seu corpo e rosto principalmente adolescentes entre 13 e 15 anos de idade.',
            'B': 'Fazem muitos anos que os educadores alertam sobre a necessidade de conscientização nas escolas.',
            'C': 'Devem existir políticas públicas de prevenção e apoio às vítimas de intimidação.',
            'D': 'Houve diversos debates no Congresso sobre propostas legislativas para o tema.'
        }
    },
    '10': {
        'statement': """No trecho abaixo, propositalmente, alterou-se a grafia de alguns vocábulos, de modo que passaram a não respeitar as regras ortográficas vigentes:

*"Existe um forte **concenso** quanto à importância do papel dos pais para o modo como seus filhos se desenvolvem e funcionam. Muitas das **abilidades** da criança dependem fundamentalmente de suas **interassoes** com seus cuidadores e com seu **hambiente** social mais amplo..."*

A quantidade de vocábulos grafados incorretamente no trecho em destaque é:""",
        'options': {
            'A': 'Dois vocábulos, apenas.',
            'B': 'Três vocábulos, apenas.',
            'C': 'Quatro vocábulos, apenas.',
            'D': 'Cinco vocábulos, apenas.'
        }
    },
    '11': {
        'statement': """Considere as seguintes premissas lógicas verdadeiras:

- Caso ou compro uma moto.
- Viajo ou não caso.
- Vou morar em Paquetá ou não compro uma moto.
- Ora, **não vou morar em Paquetá**.

Conclui-se logicamente das premissas que:""",
        'options': {
            'A': 'Viajo e caso.',
            'B': 'Não viajo e caso.',
            'C': 'Compro uma moto e não viajo.',
            'D': 'Compro uma moto e viajo.'
        }
    }
}

with Session() as session:
    exam = session.query(Exam).filter_by(id=54).first()
    if exam:
        for q in exam.questions:
            num = str(q.numero_questao)
            if num in high_fidelity_q:
                q.statement = high_fidelity_q[num]['statement']
                q.options = json.dumps(high_fidelity_q[num]['options'], ensure_ascii=False)
                print(f"Questão {num} atualizada com máxima fidelidade!")
        session.commit()
        print("\n[SUCESSO] Questões 1 a 11 de Santos 2016 perfeitamente normalizadas no Supabase!")
