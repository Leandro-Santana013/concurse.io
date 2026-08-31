import sys
import os
import json
import re

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8')

from models.database import Session, Exam, Question
from services.pdf_pipeline.fallbacks.typography_restorer import restore_exam_typography

def clean_text_full(s: str, is_option: bool = False) -> str:
    if not s:
        return ""
    
    t = s
    # 1. Punctuation & spaces
    t = re.sub(r'[ \t]+([,.:;?!])', r'\1', t)
    t = re.sub(r'([,;:?!])([a-zA-Z\u00C0-\u00DC])', r'\1 \2', t)
    t = re.sub(r'"\s+([^"]+?)\s+"', r'"\1"', t)
    t = re.sub(r'([a-zA-Z0-9\u00C0-\u00DC])\s*"\s*-\s*', r'\1" – ', t)
    t = re.sub(r',\s*s\s+em\b', ', sem', t, flags=re.IGNORECASE)

    # 2. Clitics (ênclises)
    t = re.sub(r'(\b[a-zA-Z\u00C0-\u00DC]+)\s*-\s*(se|nos|lhe|lhes|me|te|vos|o|a|os|as|lo|la|los|las|no|na|nas)\b', r'\1-\2', t, flags=re.IGNORECASE)
    t = re.sub(r'(\b[a-zA-Z\u00C0-\u00DC]+)\s*-\s*([smln])\s+([eao])\b', r'\1-\2\3', t, flags=re.IGNORECASE)
    t = re.sub(r'([a-zA-Z0-9\u00C0-\u00DC])\s+–\s+([a-zA-Z\u00C0-\u00DC])', r'\1 – \2', t)

    # 3. Correções lexicais de OCR
    ocr_word_fixes = [
        (r'\bL\s+e\s+i\s+aos\b', 'Leia os'),
        (r'\bL\s+e\s+i\s+a\b', 'Leia'),
        (r'\bE\s+i\s+a\b', 'Ela'),
        (r'\bautor\s+a\b', 'autora'),
        (r'\bconclusoes\b', 'conclusões'),
        (r'\bconclusao\b', 'conclusão'),
        (r'\bsem\s+alterar\b', 'sem alterar'),
        (r'\bengorda\s+rd\s+e\b|\bengorda\s+r\s+de\b', 'engordar de'),
        (r'\bi\s+e\s+ga\s+do\b|\bi\s+e\s+gado\b', 'legado'),
        (r'\bcom\s+ou\s+so\b', 'como uso'),
        (r'\bCP\s+U\b', 'CPU'),
        (r'\bu\s+ti\s+liz\s*a\s*r\b|\bu\s+ti\s+liz\s*a\s*ra\b', 'utilizar'),
        (r'\bac\s+essa\s+do\b', 'acessado'),
        (r'\bn\s*o\s+pa\s*i\s*nel\b', 'no painel'),
        (r'\bna\s+vegac\s*a\s*o\b', 'navegação'),
        (r'\bEste\s+Com\s+put\s+a\s+do\s+r\b', 'Este Computador'),
        (r'\bSm\s*a\s*rt\s+A\s*rt\b', 'SmartArt'),
        (r'\bCaix\s*a\s+de\s+Texto\b', 'Caixa de Texto'),
        (r'\bRe\s*a\s*lc\s*e\b', 'Realce'),
        (r'\bRef\s*e\s*renc\s*i\s*a\s+Cruz\s*a\s*da\b', 'Referência Cruzada'),
        (r'\bCome\s*nt\s*a\s*rios\b', 'Comentários'),
        (r'\bMa\s*la\s+Dir\s*e\s*ta\b', 'Mala Direta'),
        (r'\bRev\s*i\s*sao\b|\bRev\s*i\s*são\b', 'Revisão'),
        (r'\bRef\s*e\s*renc\s*i\s*as\b', 'Referências'),
        (r'\bLay\s*o\s*ut\s+da\s+Pag\s*i\s*na\b', 'Layout da Página'),
        (r'\bpr\s*a\s*ti\s*ca\s*-\s*l\s*o\b', 'praticá-lo'),
        (r'\btayl\s*o\s*rism\s*o\b', 'taylorismo'),
        (r'\bCien\s*ti\s*fic\s*a\b', 'Científica'),
        (r'\bEstr\s*u\s*tu\s*ral\s*i\s*st\s*a\b', 'Estruturalista'),
        (r'\bBur\s*o\s*cr\s*a\s*ti\s*ca\b', 'Burocrática'),
        (r'\bS\s*E\s*i\s*so\b', 'SEISO'),
        (r'\btr\s*a\s*ta\s*do\b', 'tratado'),
        (r'\bfix\s*a\s*-\s*l\s*a\b', 'fixá-la'),
        (r'\bvi\s*si\s*vel\b', 'visível'),
        (r'\bser\s*ve\b', 'serve'),
        (r'\bnovop\s*a\s*dr\s*ao\b', 'novo padrão'),
        (r'\blimp\s*e\s*za\b', 'limpeza'),
        (r'\bdever\s*a\b', 'deverá'),
        (r'\bdis\s*sem\s*i\s*na\s*ca\s*o\b', 'disseminação'),
        (r'\bpadr\s*o\s*es\b', 'padrões'),
        (r'\bro\s*ti\s*nas\b', 'rotinas'),
        (r'\bpr\s*o\s*gr\s*a\s*ma\s*das\b', 'programadas'),
        (r'\bper\s*i\s*o\s*di\s*cidade\s*s\b', 'periodicidades'),
        (r'\bcl\s*a\s*rez\s*a\b', 'clareza'),
        (r'\bpr\s*e\s*ci\s*sao\b|\bprec\s*i\s*sao\b', 'precisão'),
        (r'\bconc\s*i\s*sao\b', 'concisão'),
        (r'\bco\s*e\s*sao\b', 'coesão'),
        (r'\bBr\s*a\s*sao\b', 'Brasão'),
        (r'\blin\s*ha\s*s\b', 'linhas'),
        (r'\bdu\s*pl\s*o\b', 'duplo'),
        (r'\btop\s*o\b', 'topo'),
        (r'\bpag\s*i\s*na\b', 'página'),
        (r'\bneces\s*si\s*da\s*de\b', 'necessidade'),
        (r'\ba\s*pl\s*i\s*cac\s*a\s*o\b', 'aplicação'),
        (r'\bma\s*rcas\b', 'marcas'),
        (r'\bi\s*ns\s*ti\s*tu\s*ic\s*a\s*o\b', 'instituição'),
        (r'\bpu\s*de\s*r\b', 'puder'),
        (r'\ba\s*tras\s*a\s*do\b', 'atrasado'),
        (r'\ba\s*in\s*da\b', 'ainda'),
        (r'\bpe\s*de\b', 'pede'),
        (r'\bfi\s*que\b', 'fique'),
        (r'\ba\s*gu\s*ardan\s*do\b', 'aguardando'),
        (r'\bes\s*ti\s*veb\s*u\s*scan\s*do\b|\bes\s*ti\s*ve\s+b\s*u\s*scan\s*do\b', 'estive buscando'),
        (r'\be\s*nc\s*o\s*ntr\s*e\s*i\b', 'encontrei'),
        (r'\bcorreta\s*me\s*nt\s*e\b', 'corretamente'),
        (r'\bnao\b', 'não'),
        (r'\bdeverao\b', 'deverão'),
        (r'\bpopulacao\b', 'população'),
        (r'\bfamilias\b', 'famílias'),
        (r'\bperiodos\b', 'períodos'),
        (r'\bregencia\b', 'regência'),
        (r'\bconcordancia\b', 'concordância'),
        (r'\bdificil\b', 'difícil'),
        (r'\bpasteis\b', 'pastéis'),
        (r'\bpropensao\b', 'propensão'),
        (r'\bpedacos\b', 'pedaços'),
        (r'\bIIe\b', 'II e'),
        (r'\bIe\b', 'I e'),
        (r'\bIIIe\b', 'III e'),
        (r'\bAno\s+No\s*vo\b', 'Ano Novo'),
        (r'\bFeliz\s*me\s*nt\s*e\b', 'Felizmente'),
        (r'\bf\s*este\s*jos\b', 'festejos'),
        (r'\bcorr\s*eram\b', 'correram'),
        (r'\binci\s*de\s*ntes\b', 'incidentes'),
        (r'\bgr\s*a\s*ves\b', 'graves'),
        (r'\bpos\s*si\s*vel\b|\bpos\s*si\s*ve\s*l\b', 'possível'),
        (r'\bsa\s+s\s+s\s+s\s+l\s+possivel\b', 'seja possível'),
        (r'\bE\s*pit\s*a\s*ci\s*o\b', 'Epitácio'),
        (r'\ba\s*ch\s*o\b', 'acho'),
        (r'\bvoc\s*e\b', 'você'),
        (r'\bpara\s*r\b', 'parar'),
        (r'\bcompra\s*r\b', 'comprar'),
        (r'\bfl\s*o\s*res\b', 'flores'),
        (r'\bte\s*nh\s*o\b', 'tenho'),
        (r'\bcoloca\s*r\b', 'colocar'),
        (r'\bcoloca\s*r\s*-\s*l\s*a\s*s\b', 'colocá-las'),
        (r'\bcoloca\s*r\s*-\s*l\s*h\s*e\s*s\b', 'colocar-lhes'),
        (r'\bba\s*nh\s*e\s*ir\s*o\b', 'banheiro'),
        (r'\bcozin\s*ha\b', 'cozinha'),
        (r'\bdinh\s*e\s*ir\s*o\b', 'dinheiro'),
        (r'\bIn\s*como\s*da\s*va\s*-\s*o\b', 'Incomodava-o'),
        (r'\bWh\s*a\s*ts\s*A\s*pp\b', 'WhatsApp'),
        (r'\bSky\s*p\s*e\b', 'Skype'),
        (r'\bLink\s*e\s*din\b', 'LinkedIn'),
        (r'\ba\s*rqui\s*te\s*tu\s*ra\b', 'arquitetura'),
        (r'\bcol\s*o\s*nial\b', 'colonial'),
        (r'\bIr\s*ma\s*nd\s*a\s*de\b', 'Irmandade'),
        (r'\bTer\s*ce\s*ira\b', 'Terceira'),
        (r'\bMa\s*rti\s*m\s+A\s*fon\s*so\b', 'Martim Afonso'),
        (r'\bCas\s*a\s+do\s+Tr\s*em\s+Belic\s*o\b', 'Casa do Trem Bélico'),
        (r'\bConjunt\s*o\s+do\s+Carm\s*o\b', 'Conjunto do Carmo'),
        (r'\bCONH\s*E\s*CI\s*ME\s*NTOS\s+E\s*SP\s*E\s*CIFICOS\b', 'CONHECIMENTOS ESPECÍFICOS'),
        (r'\ba\s*rquiv\s*a\s*me\s*nt\s*o\b', 'arquivamento'),
        (r'\bas\s*si\s*na\s*le\b', 'assinale'),
        (r'\bHenri\s*que\b', 'Henrique'),
        (r'\bPr\s*e\s*si\s*de\s*nt\s*e\b', 'Presidente'),
        (r'\bSI\s*LV\s*A\b', 'SILVA'),
        (r'\bJ\s*o\s*se\b', 'José'),
        (r'\bPaul\s*o\b', 'Paulo'),
        (r'\bContr\s*o\s*lar\s*Al\s*ter\s*acoes\b', 'Controlar Alterações'),
        (r'\bse\s*leci\s*o\s*na\s*das\b|\bse\s*leci\s*o\s*na\s*da\b|\bse\s*leci\s*o\s*nar\b', 'selecionadas'),
        (r'\bcom\s*par\s*ti\s*lhe\b', 'compartilhe'),
        (r'\bin\s*ter\s*val\s*o\b', 'intervalo'),
        (r'\bver\s*ti\s*cal\b', 'vertical'),
        (r'\bhoriz\s*o\s*nt\s*a\s*l\b', 'horizontal'),
        (r'\bvic\s*e\s*-\s*v\s*e\s*rsa\b', 'vice-versa'),
        (r'\bu\s*ti\s*liz\s*a\s*r\b|\bu\s*ti\s*liz\s*a\s*ra\b', 'utilizar'),
        (r'\bfunc\s*ao\b|\bfunc\s*ão\b', 'função'),
        (r'\bTR\s*A\s*NS\s*POR\b', 'TRANSPOR'),
        (r'\bTR\s*A\s*NSF\s*E\s*RIR\b', 'TRANSFERIR'),
        (r'\bin\s*ter\s*se\s*cc\s*ao\b', 'intersecção'),
        (r'\bti\s*tu\s*lo\b', 'título'),
        (r'\bcolu\s*nas\b', 'colunas'),
        (r'\blin\s*ha\s*sd\s*a\b', 'linhas da'),
        (r'\bOb\s*serve\b', 'Observe'),
        (r'\btab\s*ela\s+ver\s*da\s*de\b', 'tabela-verdade'),
        (r'\brespec\s*ti\s*va\s*me\s*nt\s*e\b', 'respectivamente'),
        (r'\bde\s*ci\s*sao\b', 'decisão'),
        (r'\bVar\s*a\b', 'Vara'),
        (r'\bSao\s+Ber\s*na\s*rd\s*o\s+do\s+Camp\s*o\b', 'São Bernardo do Campo'),
        (r'\bim\s*por\s*tan\s*te\b', 'importante'),
        (r'\ba\s*plic\s*a\s*ti\s*vo\b', 'aplicativo'),
        (r'\bcomunicacao\b', 'comunicação'),
        (r'\bop\s*era\s*ca\s*o\b', 'operação'),
        (r'\bsusp\s*e\s*ns\s*a\b', 'suspensa')
    ]
    for pat, rep in ocr_word_fixes:
        t = re.sub(pat, rep, t, flags=re.IGNORECASE)

    # 4. Numerais romanos em enunciados e opções
    t = re.sub(r'\b(?:I\s+II|I\s+ll|lIl|llI)\.\s*', 'III. ', t)
    t = re.sub(r'\b(?:I\s+I|ll|11)\.\s*', 'II. ', t)
    t = re.sub(r'(?:^|\s+)(?:l|1)\.\s*', 'I. ', t)

    if is_option:
        # Remove prefixo de alternativa
        t = re.sub(r'^[ \t]*(?:(?:\([a-eA-E]\)|[a-eA-E]\s*[\)\.\-–—:])|[a-eA-E]\s+(?=[I|V|X\d\?\|\-–—])|[\?\|]\s+)\s*', '', t)
        # Remove sufixo residual
        t = re.sub(r'\s*[\.\-–—:,]\s*[a-eA-E]\s*$', '', t)
        # Normaliza numerais romanos em opções
        t = re.sub(r'(^|;\s*|\s+)(?:\||1|l|I)\s*-\s*', r'\1I - ', t)
        t = re.sub(r'(^|;\s*|\s+)(?:ll|11|Il|lI|II)\s*-\s*', r'\1II - ', t)
        t = re.sub(r'(^|;\s*|\s+)(?:lll|111|Ill|lIl|llI|III|I\s+ll|I\s+lI|Ill)\s*-\s*', r'\1III - ', t)
        t = re.sub(r'\bfor\s+ao\b', 'foram', t)
        t = re.sub(r'\bapoia\s+o\b', 'apoia', t)
        t = re.sub(r'\bI\s+I\b', 'II', t)
        t = re.sub(r'\bI\s+II\b', 'III', t)
        t = re.sub(r'\bII\s+I\b', 'III', t)
        t = re.sub(r'\bsao\b', 'são', t)
        t = re.sub(r"\s*\n+\s*", " ", t)
        t = re.sub(r"[ \t]{2,}", " ", t)
        return t.strip()

    # Estruturação de listas de itens romanos no enunciado
    t = re.sub(r'(\n|^|\s+)(I{1,3}|IV|V|VI|VII|VIII|IX|X)\.\s+', r'\n\n\2. ', t)
    t = re.sub(r'\n{3,}', '\n\n', t).strip()
    return t

def clean_database():
    with Session() as session:
        exams = session.query(Exam).all()
        print(f"Total de exames a processar: {len(exams)}")
        
        total_questions_cleaned = 0
        
        for e in exams:
            print(f"Limpando Exame ID {e.id}: '{e.title}' ({len(e.questions)} questões)...")
            for q in e.questions:
                # 1. Limpa Enunciado
                old_stmt = q.statement or ""
                new_stmt = clean_text_full(old_stmt, is_option=False)
                
                # Ajuste de lacunas ausentes em questões de preenchimento
                if "homenageados pelos alunos" in new_stmt and "_____" not in new_stmt:
                    new_stmt = new_stmt.replace("homenageados pelos alunos.", "_____ homenageados pelos alunos.")
                    new_stmt = new_stmt.replace("a iniciativa da Prefeitura", "_____ a iniciativa da Prefeitura")
                    new_stmt = new_stmt.replace("sete horas", "_____ sete horas")

                q.statement = new_stmt

                # 2. Limpa Opções
                if q.options:
                    try:
                        opts = json.loads(q.options) if isinstance(q.options, str) else q.options
                        if isinstance(opts, dict):
                            cleaned_opts = {}
                            for k, v in opts.items():
                                cleaned_v = clean_text_full(v, is_option=True)
                                cleaned_opts[k] = cleaned_v
                            q.options = json.dumps(cleaned_opts, ensure_ascii=False)
                    except Exception as err:
                        print(f"  Erro ao processar opções da Q{q.numero_questao}: {err}")

                total_questions_cleaned += 1

            session.commit()
            print(f"  -> Exame ID {e.id} atualizado e persistido com sucesso!")

        print(f"\n[SUCESSO] Total de {total_questions_cleaned} questões totalmente limpas e normalizadas no banco de dados!")

if __name__ == "__main__":
    clean_database()
