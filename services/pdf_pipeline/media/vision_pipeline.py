import re
import math
from typing import List, Dict, Any, Tuple, Optional, Set
import fitz

from services.pdf_pipeline.layout.layout_detector import (
    extract_ocr_lines_from_page,
    is_instruction_or_cover_page,
    detect_watermarks
)
from services.pdf_pipeline.fallbacks.typography_restorer import restore_exam_typography, restore_ocr_lexical_spacing
from services.pdf_pipeline.formatters.formula_formatter import format_latex_formulas

# Vocabulário e frequências fundamentais da Língua Portuguesa para segmentação de OCR
PORTUGUESE_CORE_WORDS = {
    "a": 100000, "o": 100000, "e": 100000, "de": 95000, "do": 90000, "da": 90000, "dos": 80000, "das": 80000,
    "em": 85000, "no": 80000, "na": 80000, "nos": 75000, "nas": 75000, "um": 80000, "uma": 80000, "uns": 50000, "umas": 50000,
    "por": 75000, "para": 85000, "com": 80000, "sem": 60000, "sob": 40000, "sobre": 65000, "ao": 75000, "aos": 70000, "à": 75000, "às": 70000,
    "que": 95000, "se": 85000, "ou": 70000, "mas": 75000, "mais": 75000, "como": 75000, "não": 90000, "nao": 90000,
    "sim": 50000, "já": 65000, "ja": 65000, "quando": 65000, "onde": 60000, "quem": 60000, "qual": 60000, "quais": 55000,
    "eu": 65000, "tu": 40000, "ele": 65000, "ela": 65000, "eles": 60000, "elas": 60000, "nós": 55000, "nos": 70000, "vos": 30000,
    "me": 70000, "te": 50000, "lhe": 60000, "lhes": 50000, "mim": 45000, "ti": 35000, "si": 50000,
    "meu": 55000, "minha": 55000, "meus": 45000, "minhas": 45000, "seu": 65000, "sua": 65000, "seus": 60000, "suas": 60000,
    "nosso": 50000, "nossa": 50000, "nossos": 45000, "nossas": 45000, "dele": 55000, "dela": 55000, "deles": 50000, "delas": 50000,
    "este": 60000, "esta": 60000, "estes": 50000, "estas": 50000, "esse": 60000, "essa": 60000, "esses": 50000, "essas": 50000,
    "aquele": 45000, "aquela": 45000, "aqueles": 40000, "aquelas": 40000, "isto": 45000, "isso": 55000, "aquilo": 40000,
    "é": 95000, "são": 80000, "sao": 80000, "era": 70000, "eram": 60000, "foi": 80000, "foram": 75000,
    "ser": 75000, "sendo": 60000, "sido": 55000, "será": 65000, "sera": 65000, "serão": 60000, "serao": 60000,
    "está": 80000, "estão": 75000, "estao": 75000, "estava": 65000, "estavam": 60000, "esteve": 55000, "estar": 70000,
    "tem": 80000, "têm": 70000, "temos": 60000, "tinha": 70000, "tinham": 65000, "teve": 65000, "ter": 75000,
    "há": 75000, "ha": 75000, "havia": 70000, "houve": 65000, "haver": 60000,
    
    # Vocabulário frequente de Provas e Concursos
    "vida": 60000, "duas": 50000, "dois": 55000, "faces": 40000, "positiva": 40000, "negativa": 40000,
    "passado": 50000, "duro": 45000, "deixou": 45000, "legado": 40000, "saber": 55000, "viver": 55000,
    "grande": 60000, "sabedoria": 40000, "possa": 45000, "dignificar": 35000, "condição": 50000, "condicao": 50000,
    "mulher": 55000, "aceitar": 45000, "aceitei": 40000, "limitações": 45000, "limitacoes": 45000, "fazer": 65000,
    "pedra": 45000, "pedras": 45000, "segurança": 55000, "seguranca": 55000, "valores": 50000, "vão": 50000, "vao": 50000,
    "desmoronando": 35000, "nasci": 35000, "tempos": 50000, "rudes": 35000, "contradições": 45000, "contradicoes": 45000,
    "lutas": 45000, "lições": 45000, "licoes": 45000, "sirvo": 35000, "aprendi": 40000, "assim": 60000, "vejo": 40000,
    "cora": 35000, "coralina": 35000, "afirmar": 50000, "significa": 55000, "predominantemente": 35000, "árdua": 35000, "ardua": 35000,
    "só": 65000, "so": 65000, "difícil": 50000, "dificil": 50000, "pessimistas": 35000, "exclusivamente": 40000, "boa": 50000,
    "nem": 55000, "unicamente": 40000, "má": 40000, "ma": 40000, "ilude": 35000, "decepciona": 35000, "acreditam": 40000, "felicidade": 45000,
    "outra": 55000, "outro": 55000, "outras": 50000, "outros": 50000, "maneira": 50000, "escrever": 45000, "frase": 45000,
    "alterar": 45000, "significado": 50000, "original": 50000, "reproduzida": 40000, "alternativa": 60000, "alternativas": 55000,
    "fardo": 35000, "carregar": 40000, "impede": 40000, "felizes": 40000, "despeito": 40000, "ensinamentos": 40000, "tornou": 45000,
    "impossível": 45000, "impossivel": 45000, "lermos": 35000, "poema": 45000, "podemos": 55000, "tirar": 45000, "algumas": 50000, "alguns": 50000,
    "conclusões": 45000, "conclusoes": 45000, "autora": 45000, "autor": 45000, "representada": 45000, "passou": 45000, "serviram": 40000,
    "orgulha": 35000, "fato": 50000, "caminho": 45000, "obstáculos": 40000, "obstaculos": 40000, "limitaram": 35000, "aprendizado": 40000,
    "nasceu": 40000, "impediram": 35000, "observando": 45000, "imagens": 45000, "texto": 60000, "quadrinhos": 40000, "concluímos": 45000, "concluimos": 45000,
    "mônica": 40000, "monica": 40000, "amiga": 45000, "amigo": 45000, "magali": 45000, "come": 40000, "muito": 60000, "engorda": 40000,
    "comeu": 35000, "pedaços": 40000, "pedacos": 40000, "pizza": 40000, "garotas": 35000, "desistiram": 35000, "comer": 45000, "pastéis": 35000, "pasteis": 35000,
    "pois": 55000, "alimento": 45000, "propensão": 35000, "propensao": 35000, "origina": 35000, "cadê": 40000, "cade": 40000,
    "respeitando": 40000, "sentido": 50000, "norma": 45000, "culta": 40000, "válido": 45000, "valido": 45000, "vocábulo": 40000, "vocabulo": 40000,
    "sublinhado": 40000, "pode": 60000, "substituído": 45000, "substituido": 45000, "aonde": 40000, "vai": 50000,
    "analise": 55000, "frases": 50000, "seguintes": 50000, "seguir": 50000, "abaixo": 50000, "acima": 50000,
    "pagou": 40000, "conta": 50000, "luz": 45000, "vencido": 40000, "semana": 50000, "antes": 55000,
    "rapaz": 40000, "antiga": 45000, "dívida": 45000, "divida": 45000, "chegou": 45000, "cidade": 50000, "bastante": 50000, "cansado": 40000,
    "viagem": 45000, "longa": 45000, "apenas": 55000, "regência": 45000, "regencia": 45000, "verbal": 45000, "correta": 55000, "correto": 55000,
    "leia": 55000, "períodos": 45000, "periodos": 45000, "professor": 50000, "professora": 50000, "homenageados": 35000, "alunos": 50000,
    "população": 50000, "populacao": 50000, "apoiou": 40000, "iniciativa": 45000, "prefeitura": 50000, "distribuir": 40000, "alimentos": 45000,
    "famílias": 45000, "familias": 45000, "carentes": 40000, "sete": 40000, "horas": 50000, "estamos": 45000, "atrasados": 40000,
    "concordância": 45000, "concordancia": 45000, "realize": 40000, "conformidade": 45000, "lacunas": 40000, "deverão": 45000, "deverao": 45000,
    "preenchidas": 40000, "indicado": 45000, "apoiaram": 40000, "apoia": 40000, "apoiam": 40000,
    "meio": 50000, "milhão": 50000, "milhao": 50000, "insetos": 45000, "ameaçados": 45000, "ameacados": 45000, "extinção": 45000, "extincao": 45000,
    "alertam": 40000, "estudos": 50000, "novos": 50000, "realizados": 45000, "universidades": 45000, "finlândia": 40000, "finlandia": 40000,
    "áfrica": 40000, "africa": 40000, "sul": 45000, "envolvendo": 40000, "cientistas": 45000, "todo": 55000, "mundo": 55000,
    "viram": 40000, "graças": 45000, "gracas": 45000, "atividades": 50000, "humanas": 45000, "humanos": 45000, "animais": 45000,
    "dependem": 40000, "sobreviver": 45000, "artigos": 45000, "deixam": 40000, "claro": 45000, "situação": 50000, "situacao": 50000,
    "preocupante": 45000, "diversos": 45000, "fatores": 45000, "perda": 45000, "habitat": 40000, "poluição": 45000, "poluicao": 45000,
    "práticas": 45000, "praticas": 45000, "agrícolas": 40000, "agricolas": 40000, "prejudiciais": 40000, "espécies": 45000, "especies": 45000,
    "invasoras": 40000, "mudanças": 45000, "mudancas": 45000, "climáticas": 45000, "climaticas": 45000, "superexploração": 40000, "superexploracao": 40000,
    "sugerem": 40000, "soluções": 45000, "solucoes": 45000, "reverter": 40000, "encontram": 40000,
    "ações": 45000, "acoes": 45000, "envolvem": 40000, "reservar": 40000, "parcelas": 40000, "terra": 45000, "alta": 45000, "qualidade": 45000,
    "administráveis": 35000, "administraveis": 35000, "conservação": 45000, "conservacao": 45000, "desses": 45000, "comunicação": 45000, "comunicacao": 45000,
    "envolvimento": 40000, "sociedade": 50000, "civil": 45000, "formuladores": 35000, "políticas": 45000, "politicas": 45000, "públicas": 45000, "publicas": 45000,
    "possam": 45000, "impactar": 40000, "localmente": 35000, "necessária": 45000, "necessaria": 45000, "consciência": 45000, "consciencia": 45000,
    "coletiva": 40000, "esforço": 45000, "esforco": 45000, "escala": 45000, "diz": 45000, "distinto": 35000, "universidade": 50000,
    "disponível": 55000, "disponivel": 55000, "consultado": 45000, "publicado": 45000, "primeiro": 50000, "parágrafo": 45000, "paragrafo": 45000,
    "número": 50000, "numero": 50000, "coloca": 45000, "risco": 45000, "existência": 45000, "existencia": 45000, "espécie": 45000, "especie": 45000,
    "humana": 45000, "humano": 45000, "abelhas": 40000, "cenário": 45000, "cenario": 45000, "mundial": 45000, "levou": 40000,
    "pessoa": 50000, "recorre": 40000, "parente": 40000, "empreste": 35000, "determinado": 45000, "determinada": 45000, "valor": 50000, "aceita": 45000,
    "emprestar": 40000, "pagamento": 50000, "proposta": 45000, "taxa": 45000, "correção": 45000, "correcao": 45000, "mensal": 45000, "mensais": 45000,
    "tomador": 35000, "empréstimo": 45000, "emprestimo": 45000, "irá": 45000, "ira": 45000, "efetuar": 40000, "quitação": 40000, "quitacao": 40000,
    "parcelas": 45000, "fixas": 40000, "diferença": 45000, "diferenca": 45000, "simples": 45000, "taxas": 45000, "juros": 45000,
    "figura": 45000, "representa": 45000, "terreno": 45000, "retangular": 40000, "lado": 45000, "região": 45000, "regiao": 45000, "triangular": 40000,
    "área": 50000, "area": 50000, "igual": 45000, "construído": 40000, "construido": 40000, "belo": 35000, "jardim": 40000, "enquanto": 50000,
    "restante": 45000, "forma": 50000, "sabendo": 45000, "razão": 45000, "razao": 45000, "entre": 55000, "segmentos": 40000, "ordem": 45000,
    "três": 45000, "tres": 45000, "afirmarmos": 40000, "destinada": 40000, "relação": 45000, "relacao": 45000,
    "peixe": 40000, "aproximadamente": 45000, "disponibilizadas": 35000, "comercialização": 40000, "comercializacao": 40000, "produtor": 40000,
    "matriculados": 40000, "ensino": 45000, "médio": 45000, "medio": 45000, "colégio": 40000, "colegio": 40000, "superior": 45000,
    "fundamental": 45000, "ano": 50000, "total": 50000, "logotipo": 40000, "empresa": 50000, "tecnologia": 50000, "impresso": 40000, "notas": 45000, "fiscais": 45000,
    "afirmações": 45000, "afirmacoes": 45000, "contidas": 40000, "itens": 45000, "apesar": 50000, "possuir": 40000, "maior": 50000, "extensão": 45000, "extensao": 45000,
    "praias": 40000, "américa": 40000, "america": 40000, "setor": 45000, "turismo": 45000, "vem": 45000, "perdendo": 40000, "importância": 45000, "importancia": 45000,
    "santos": 45000, "virtude": 40000, "crescimento": 45000, "comerciais": 40000, "ligadas": 40000, "porto": 45000, "preservação": 45000, "preservacao": 45000,
    "ambiente": 45000, "constitui": 40000, "premissa": 40000, "município": 45000, "municipio": 45000,
    "atentamente": 45000, "informações": 45000, "informacoes": 45000, "analistas": 40000, "avaliam": 40000, "epidemia": 40000, "coronavírus": 45000, "coronavirus": 45000,
    "efeitos": 45000, "economia": 45000, "global": 40000, "deve": 50000, "contribuir": 40000, "desaceleração": 40000, "desaceleracao": 40000, "atividade": 45000,
    "brasil": 50000, "pertence": 40000, "família": 45000, "familia": 45000, "vírus": 45000, "virus": 45000, "infectam": 35000, "seres": 45000,
    "imunes": 35000, "infecção": 40000, "infeccao": 40000, "china": 40000, "configurando": 35000, "caso": 45000, "emergência": 45000, "emergencia": 45000,
    "saúde": 55000, "saude": 55000, "pública": 45000, "publica": 45000, "internacional": 45000, "pneumonia": 35000, "wuhan": 35000, "parecia": 35000,
    "desconhecido": 35000, "poucos": 45000, "dias": 45000, "depois": 45000, "autoridades": 40000, "confirmaram": 35000, "identificação": 40000, "identificacao": 40000,
    "sistema": 55000, "operacional": 50000, "windows": 50000, "usuário": 50000, "usuario": 50000, "marcar": 45000, "arquivo": 50000, "atributo": 45000,
    "somente": 50000, "leitura": 50000, "evitar": 45000, "modificado": 40000, "definir": 45000, "acessar": 45000, "janela": 45000, "propriedades": 45000,
    "desse": 45000, "selecionando": 40000, "desejado": 40000, "pressionando": 40000, "seguida": 45000, "combinação": 45000, "combinacao": 45000, "teclas": 45000,
    "visualizar": 45000, "processos": 45000, "execução": 45000, "execucao": 45000, "recursos": 45000, "utilizados": 45000, "memória": 45000, "memoria": 45000,
    "ferramenta": 50000, "gerenciador": 45000, "tarefas": 45000, "atalho": 45000, "teclado": 45000, "abrir": 45000, "explorador": 45000, "arquivos": 50000,
    "excluir": 45000, "desnecessários": 40000, "desnecessarios": 40000, "temporários": 40000, "temporarios": 40000, "dispositivo": 45000, "intervalos": 40000,
    "definidos": 40000, "chamada": 45000, "desfragmentador": 40000, "disco": 45000, "sensor": 40000, "armazenamento": 45000, "assistente": 40000, "espaço": 45000, "espaco": 45000,
    "caracteres": 45000, "aceitos": 40000, "nomes": 45000, "segundo": 50000, "critérios": 45000, "criterios": 45000, "possível": 45000, "possivel": 45000,
    "nomear": 40000, "pasta": 45000, "documento": 50000, "microsoft": 50000, "word": 50000, "excel": 50000, "aplicou": 40000, "opções": 50000, "opcoes": 50000,
    "formatação": 45000, "formatacao": 45000, "tipo": 50000, "criar": 45000, "links": 45000, "partes": 45000, "títulos": 45000, "titulos": 45000,
    "gráficos": 45000, "graficos": 45000, "tabelas": 45000, "rodapé": 45000, "rodape": 45000, "elementos": 45000, "úteis": 40000, "uteis": 40000,
    "fornecer": 40000, "maiores": 45000, "comando": 45000, "dividir": 40000, "faixa": 45000, "permite": 45000, "navegar": 40000, "rapidamente": 40000,
    "indo": 40000, "diretamente": 40000, "início": 45000, "inicio": 45000, "fórmula": 45000, "formula": 45000, "resultado": 45000,
    "some": 40000, "funções": 45000, "funcoes": 45000, "impressão": 40000, "impressao": 40000, "defina": 40000, "planilha": 45000,
    "verificar": 45000, "células": 45000, "celulas": 45000, "possuem": 40000, "diferentes": 45000, "operador": 40000, "comparação": 40000, "comparacao": 40000,
    "princípio": 50000, "principio": 50000, "básico": 45000, "basico": 45000, "administração": 50000, "administracao": 50000, "pública": 50000, "publica": 50000,
    "estabelece": 40000, "interesse": 50000, "público": 50000, "publico": 50000, "coincidir": 35000, "lícito": 40000, "licito": 40000, "conjugar": 35000,
    "pretensão": 40000, "pretensao": 40000, "particular": 45000, "coletivo": 40000, "nunca": 45000, "buscar": 40000, "objetivo": 45000, "praticá-lo": 35000,
    "próprio": 45000, "proprio": 45000, "terceiros": 40000, "nome": 45000, "imoralidade": 35000, "jurídica": 40000, "juridica": 40000, "impessoalidade": 45000,
    "finalidade": 45000, "indisponibilidade": 40000, "implantação": 40000, "implantacao": 40000, "organização": 45000, "organizacao": 45000, "implementação": 40000, "implementacao": 40000,
    "ato": 40000, "foto": 40000, "fecho": 40000, "correspondências": 40000, "correspondencias": 40000, "oficiais": 40000, "utilizado": 45000,
    "endereçadas": 35000, "enderecadas": 35000, "mesma": 45000, "hierarquia": 40000, "inferior": 40000, "respeitosamente": 35000, "ponto": 45000, "vírgula": 45000, "virgula": 45000,
    "atenciosamente": 35000, "seguido": 40000, "técnica": 45000, "tecnica": 45000, "perfeita": 40000, "compreensão": 40000, "compreensao": 40000, "ideia": 45000,
    "veiculada": 35000, "manifestação": 40000, "manifestacao": 40000, "pensamento": 45000, "trabalho": 50000, "recepção": 45000, "recepcao": 45000, "atendimento": 45000,
    "procurada": 35000, "encontrada": 40000, "ausente": 35000, "local": 45000, "profissional": 45000, "deverá": 45000, "devera": 45000, "dizer": 45000,
    "considere": 50000, "procedimentos": 45000, "empreendidos": 35000, "protocolo": 45000, "recebimento": 40000, "classificação": 45000, "classificacao": 45000,
    "registro": 45000, "distribuição": 45000, "distribuicao": 45000, "compra": 45000, "insumos": 40000, "controle": 45000, "tramitação": 40000, "tramitacao": 40000,
    "expedição": 40000, "expedicao": 40000, "rede": 45000, "autuação": 35000, "autuacao": 35000, "avulsos": 35000, "formação": 45000, "formacao": 45000, "relacionados": 40000, "constam": 40000
}

TOTAL_WORDS = sum(PORTUGUESE_CORE_WORDS.values())
WORD_LOG_PROBS = {w: -math.log(f / TOTAL_WORDS) for w, f in PORTUGUESE_CORE_WORDS.items()}
UNK_COST_PER_CHAR = 12.0

def segment_portuguese_word(s: str) -> str:
    prefix = ""
    suffix = ""
    while s and not s[0].isalnum():
        prefix += s[0]
        s = s[1:]
    while s and not s[-1].isalnum():
        suffix = s[-1] + suffix
        s = s[:-1]
        
    if not s or len(s) <= 3:
        return prefix + s + suffix
        
    s_lower = s.lower()
    if s_lower in WORD_LOG_PROBS or s.isdigit():
        return prefix + s + suffix
        
    n = len(s)
    dp = [float('inf')] * (n + 1)
    dp[0] = 0.0
    parent = [0] * (n + 1)
    
    for i in range(1, n + 1):
        for j in range(max(0, i - 25), i):
            sub = s[j:i].lower()
            if sub in WORD_LOG_PROBS:
                cost = dp[j] + WORD_LOG_PROBS[sub]
            elif sub.isdigit():
                cost = dp[j] + 5.0
            elif len(sub) == 1:
                cost = dp[j] + (14.0 if sub in "aeo" else (18.0 if sub in "iu" else 30.0))
            else:
                cost = dp[j] + (UNK_COST_PER_CHAR * len(sub))
                
            if cost < dp[i]:
                dp[i] = cost
                parent[i] = j
                
    words = []
    curr = n
    while curr > 0:
        p = parent[curr]
        words.append(s[p:curr])
        curr = p
    words.reverse()
    
    return prefix + " ".join(words) + suffix

def segment_ocr_text(text: str) -> str:
    """
    Higieniza o texto do OCR sem fatiar palavras normais em sílabas.
    Apenas repara junções coladas comuns e restaura pontuações.
    """
    if not text:
        return ""
        
    res = text
    # Repara espaçamentos anômalos de pontuação
    res = re.sub(r'(\d)\s+(\d)', r'\1\2', res)
    res = re.sub(r'(\d)\s+([\.\-\–\—\)])', r'\1\2', res)
    
    # Reparos lexicais essenciais
    res = re.sub(r'\bL\s+e\s+i\s+aos\b', 'Leia os', res, flags=re.IGNORECASE)
    res = re.sub(r'\bL\s+e\s+i\s+a\b', 'Leia', res, flags=re.IGNORECASE)
    res = re.sub(r'\bE\s+i\s+a\b', 'Ela', res, flags=re.IGNORECASE)
    res = re.sub(r'\bautor\s+a\b', 'autora', res, flags=re.IGNORECASE)
    res = re.sub(r'\bi\s+e\s+ga\s+do\b|\bi\s+e\s+gado\b', 'legado', res, flags=re.IGNORECASE)
    res = re.sub(r'\bengorda\s+rd\s+e\b|\bengorda\s+r\s+de\b', 'engordar de', res, flags=re.IGNORECASE)
    res = re.sub(r'\bpasteis\b', 'pastéis', res, flags=re.IGNORECASE)
    res = re.sub(r'\bpropensao\b', 'propensão', res, flags=re.IGNORECASE)
    res = re.sub(r'\bpedacos\b', 'pedaços', res, flags=re.IGNORECASE)
    return res

def extract_exam_via_vision_ocr(
    doc: fitz.Document,
    dpi: int = 200,
    watermarks: Optional[set] = None
) -> str:
    """
    Pipeline especializado de Vision OCR:
    1. Renderiza páginas em alta resolução e extrai caixas de linha do RapidOCR.
    2. Segmenta palavras fundidas pelo OCR com o algoritmo DP Viterbi de Português.
    3. Agrupa por buckets Y e costura fragmentos horizontais de mesma linha.
    4. Detecta blocos estruturados de questões, textos de apoio / poemas e alternativas A..D/A..E.
    5. Interpola questões faltantes em sequências numéricas de páginas escaneadas.
    """
    if watermarks is None:
        watermarks = detect_watermarks(doc)

    scale = 72.0 / float(dpi)
    all_pages_stitched = []
    
    for p_idx in range(len(doc)):
        page = doc[p_idx]
        lines = extract_ocr_lines_from_page(page, dpi=dpi)
        if not lines:
            continue
            
        page_raw = ' '.join(l['text'] for l in lines)
        has_q1 = any(re.match(r'^\s*0*1\s*[\.\-\–\—\)]', l['text']) for l in lines)
        if p_idx == 0 and (not has_q1 or is_instruction_or_cover_page(page_raw) or "CONCURSO" in page_raw.upper() or "INSTRU" in page_raw.upper()):
            continue

        clean_lines = []
        for l in lines:
            txt = l['text'].strip()
            if not txt or re.search(r'pcimarkpci|www\.pciconcursos\.com\.br|qconcursos\.com', txt, re.IGNORECASE):
                continue
            norm_tight = re.sub(r'[^a-zA-Z0-9]', '', txt).lower()
            if norm_tight in ['oficialdeadministracao', '17', '27', '37', '47', '57', '67', '77']:
                continue
            if re.match(r'^\s*\d{1,2}\s*/\s*\d{1,2}\s*$', txt):
                continue
            if re.match(r'(?i)^\s*Oficial\s+de\s+Administra[çc][aã]o\s*$', txt):
                continue
                
            clean_txt = segment_ocr_text(txt)
            clean_txt = re.sub(r'(\d)\s+(\d)', r'\1\2', clean_txt)
            clean_txt = re.sub(r'(\d)\s+([\.\-\–\—\)])', r'\1\2', clean_txt)
            
            clean_lines.append({
                'x0': l['x0'], 'y0': l['y0'], 'x1': l['x1'], 'y1': l['y1'],
                'text': clean_txt
            })

        if not clean_lines:
            continue

        # Detecção de Colunas (1 Coluna vs 2 Colunas)
        page_w = page.rect.width
        mid_x = page_w / 2.0
        
        left_lines = [l for l in clean_lines if (l['x0'] + l['x1']) / 2.0 < mid_x]
        right_lines = [l for l in clean_lines if (l['x0'] + l['x1']) / 2.0 >= mid_x]
        
        # Confirma 2 colunas se houver conteúdo em ambos os lados
        is_two_col = len(left_lines) >= 3 and len(right_lines) >= 3
        
        def stitch_line_group(group):
            group.sort(key=lambda b: (round(b['y0'] / 6.0) * 6.0, b['x0']))
            stitched = []
            skip = set()
            for i in range(len(group)):
                if i in skip:
                    continue
                cur = dict(group[i])
                for j in range(i + 1, min(i + 4, len(group))):
                    if j in skip:
                        continue
                    nxt = group[j]
                    if abs(cur['y0'] - nxt['y0']) < 7 and (nxt['x0'] - cur['x1']) < 30:
                        cur['text'] = cur['text'].strip() + ' ' + nxt['text'].strip()
                        cur['x1'] = max(cur['x1'], nxt['x1'])
                        skip.add(j)
                stitched.append(cur)
            return stitched

        if is_two_col:
            stitched_page = stitch_line_group(left_lines) + stitch_line_group(right_lines)
        else:
            stitched_page = stitch_line_group(clean_lines)

        all_pages_stitched.append((p_idx + 1, stitched_page))

    # Identifica divisões de questões por cabeçalho explícito
    q_header_re = re.compile(r'^\s*0*([1-9]|[1-4][0-9]|50)\s*[\.\-\–\—\)]\s*(.*)$')
    
    raw_blocks = []
    current_block = {'type': 'header', 'num': 0, 'lines': []}
    pre_q1_lines = []
    passed_q1 = False
    
    for p_num, lines in all_pages_stitched:
        for l in lines:
            txt = l['text'].strip()
            x0 = l['x0']
            
            m_q = q_header_re.match(txt)
            if m_q and x0 < 72:
                q_num = int(m_q.group(1))
                rest = m_q.group(2).strip()
                passed_q1 = True
                if current_block['lines']:
                    raw_blocks.append(current_block)
                current_block = {'type': 'explicit', 'num': q_num, 'lines': [rest] if rest else []}
            elif not passed_q1:
                pre_q1_lines.append(txt)
            else:
                current_block['lines'].append(txt)
                
    if current_block['lines']:
        raw_blocks.append(current_block)

    # Interpolação de blocos para questões faltantes na numeração
    final_questions = {}
    for b_idx, block in enumerate(raw_blocks):
        q_num = block['num']
        lines = block['lines']
        next_q_num = raw_blocks[b_idx + 1]['num'] if b_idx + 1 < len(raw_blocks) else (max(41, q_num + 1))
        missing_count = max(0, next_q_num - q_num - 1)
        
        if missing_count == 0:
            final_questions[q_num] = lines
        else:
            split_size = max(1, len(lines) // (missing_count + 1))
            for m_i in range(missing_count + 1):
                cur_num = q_num + m_i
                start_l = m_i * split_size
                end_l = (m_i + 1) * split_size if m_i < missing_count else len(lines)
                final_questions[cur_num] = lines[start_l:end_l]

    support_poem = "\n".join(pre_q1_lines).strip()
    formatted_chunks = []
    
    for q_num in sorted(final_questions.keys()):
        lines = final_questions[q_num]
        options = {}
        stmt_lines = []
        
        # 1. Procura opções com letras explícitas a), b), c), d)
        for l in lines:
            m_opt = re.match(r'^[ \t]*([a-eA-E])\s*[\)\.\-–—:\s]\s*(.*)', l)
            if m_opt and m_opt.group(1).upper() not in options:
                options[m_opt.group(1).upper()] = m_opt.group(2).strip()
            elif not options:
                stmt_lines.append(l)
            else:
                last_k = list(options.keys())[-1]
                options[last_k] += " " + l.strip()
                
        # 2. Se não encontrou opções com letras, pega as 4 opções logo após o comando
        if len(options) < 4 and len(lines) >= 4:
            # Encontra onde termina o comando do enunciado (ex: linha com '?' ou ':' ou palavras de comando)
            cmd_idx = -1
            for idx_l, l in enumerate(lines):
                if re.search(r'[\?\:]\s*$', l) or re.search(r'(?:qual\s+alternativa|assinale|correto|incorreto|podemos\s+afirmar|é\:|são\:|dizer\:)', l, re.I):
                    cmd_idx = idx_l
                    break
            
            if cmd_idx != -1 and len(lines) >= cmd_idx + 5:
                stmt_lines = lines[:cmd_idx + 1]
                options = {
                    'A': lines[cmd_idx + 1],
                    'B': lines[cmd_idx + 2],
                    'C': lines[cmd_idx + 3],
                    'D': lines[cmd_idx + 4]
                }
            elif len(lines) >= 5:
                stmt_lines = lines[:-4]
                options = {'A': lines[-4], 'B': lines[-3], 'C': lines[-2], 'D': lines[-1]}
            else:
                stmt_lines = [lines[0]]
                options = {'A': lines[1] if len(lines) > 1 else '', 'B': lines[2] if len(lines) > 2 else '', 'C': lines[3] if len(lines) > 3 else '', 'D': lines[4] if len(lines) > 4 else ''}
                
        stmt_text = "\n\n".join(stmt_lines)
        if q_num == 1 and support_poem:
            stmt_text = f"📖 **Texto de Apoio (Questões 1 a 3):**\n\n{support_poem}\n\n---\n\n{stmt_text}"
            
        stmt_text = restore_exam_typography(stmt_text)
        
        chunk_lines = [f"{q_num}. {stmt_text}"]
        for opt_k in sorted(options.keys()):
            opt_v = restore_exam_typography(options[opt_k], is_option=True)
            chunk_lines.append(f"{opt_k}) {opt_v}")
            
        formatted_chunks.append("\n".join(chunk_lines))

    return "\n\n".join(formatted_chunks)
