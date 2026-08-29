#!/usr/bin/env python3
"""
concurse.io — Restaurador Tipográfico e Reconstrutor de Parágrafos (Fallback Python)
Elimina a "massa aglutinada" típica de extrações de PDF, restaurando a diagramação
editorial perfeita: parágrafos fluidos, numerais romanos isolados, artigos de lei,
hifenizações recompostas e desaglutinação de itens.
"""

from __future__ import annotations
import os
import json
import re
import urllib.parse

# Carregamento dinâmico de checkpoints treinados pelo otimizador genético
_CHECKPOINT_PATTERNS: dict[str, str] = {}
_CHECKPOINT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "checkpoints",
    "best_patterns.json"
)
if os.path.exists(_CHECKPOINT_FILE):
    try:
        with open(_CHECKPOINT_FILE, "r", encoding="utf-8") as _cf:
            _ck_data = json.load(_cf)
            for _k, _v in _ck_data.items():
                if isinstance(_v, dict) and "pattern" in _v and _v["pattern"]:
                    _CHECKPOINT_PATTERNS[_k] = _v["pattern"]
    except Exception:
        pass

try:
    from ..native.rust_bridge import rust_restore_typography, rust_restore_ocr_lexical_spacing
except (ImportError, ValueError):
    try:
        from services.pdf_pipeline.native.rust_bridge import rust_restore_typography, rust_restore_ocr_lexical_spacing
    except ImportError:
        rust_restore_typography = None
        rust_restore_ocr_lexical_spacing = None

POEM_CUES_REGEX = re.compile(
    r'(?i)\b(?:poema|poesias?|versos?|estrofes?|soneto|trovas?|cantiga|can[çc][ãa]o|l[íi]ric[ao]|ode|quadras?|tercetos?|oitavas?|d[ée]cimas?|poeta|poetisa|haicai|haikai)\b'
)

FAMOUS_POETS_REGEX = re.compile(
    r'(?i)\b(?:Fernando\s+Pessoa|Drummond|Manuel\s+Bandeira|Vinicius\s+de\s+Moraes|Cec[íi]lia\s+Meireles|Castro\s+Alves|Gon[çc]alves\s+Dias|Olavo\s+Bilac|Machado\s+de\s+Assis|Greg[óo]rio\s+de\s+Matos|Florbela\s+Espanca|Lu[íi]s\s+de\s+Cam[õo]es|Cam[õo]es|Cruz\s+e\s+Sousa|Augusto\s+dos\s+Anjos|M[áa]rio\s+de\s+Andrade|Oswald\s+de\s+Andrade|Cora\s+Coralina|Ad[ée]lia\s+Prado|Ferreira\s+Gullar|Jo[ãa]o\s+Cabral|Luiz\s+Gonzaga)\b'
)

PROSE_PROMPT_REGEX = re.compile(
    r'(?i)^(?:Nos?\s+versos?|Nas?\s+estrofes?|No\s+poema|No\s+soneto|No\s+trecho|No\s+texto|No\s+fragmento|O\s+eu\s+(?:po[ée]tico|l[íi]rico)|O\s+autor|O\s+poeta\s+(?:narra|afirma|expressa|utiliza|reitera|sugere|cria)|A\s+partir|Com\s+base|Sobre\s+(?:o|a|os|as)|Em\s+rela[çc][ãa]o|De\s+acordo|Para\s+isso|Nesse\s+sentido|Considerando\s+o|Tendo\s+em\s+vista)\b'
)

def unsquash_poem_lines(block: str) -> str:
    """
    Desmembra versos que foram aglutinados na mesma linha por OCR ou formatação de estilos (*verso 1* *verso 2*).
    """
    b = block
    b = re.sub(r'\*\s+\*(?=[A-Za-z\u00C0-\u00DC0-9\"\'\-])', '*\n*', b)
    b = re.sub(r'</i>\s*<i>(?=[A-Za-z\u00C0-\u00DC0-9\"\'\-])', '</i>\n<i>', b, flags=re.IGNORECASE)
    b = re.sub(r'</u>\s*<u>(?=[A-Za-z\u00C0-\u00DC0-9\"\'\-])', '</u>\n<u>', b, flags=re.IGNORECASE)
    return b

def is_verse_line(line: str) -> bool:
    """Verifica se uma linha individual tem formato e limites característicos de verso."""
    l = line.strip().strip('*_`')
    if not l or len(l) > 85:
        return False
    # Não pode ser opção de múltipla escolha
    if re.match(r'^(?:\([a-eA-E]\)|[a-eA-E][\.\)])\s+', l):
        return False
    # Não pode ser comando de questão ou comentário discursivo
    if re.match(r'(?i)^(?:Assinale|Marque|Indique|Identifique|A\s+respeito|Considerando|Com\s+base|De\s+acordo|Julgue|Analise|O\s+texto|Em\s+rela[çc][ãa]o)\b', l):
        return False
    if PROSE_PROMPT_REGEX.match(l):
        return False

    # Não pode ser item de lista (romano, numérico, marcador, lacuna)
    if re.match(r'^(?:(?:[IVXLCDM]+|\d{1,3})\.|\([IVXLCDM\d]+\)|[-•*]|\(__\))\s*', l):
        return False
    # Não pode ser cabeçalho ou divisor
    if l.startswith(('---', '###', '📖', '**')):
        return False
    return True

def is_poem_stanza_block(lines: list[str], has_poetic_context: bool = False) -> bool:
    """
    Determina se uma sequência de linhas constitui uma estrofe de poema.
    Exige contexto poético explícito para evitar falsos positivos em parágrafos de prosa em 2 colunas.
    """
    if not has_poetic_context:
        return False

    valid_lines = [l.strip() for l in lines if l.strip()]
    if len(valid_lines) < 2:
        return False

    if not all(is_verse_line(l) for l in valid_lines):
        return False

    char_counts = [len(l.strip().strip('*_`')) for l in valid_lines]
    avg_len = sum(char_counts) / len(valid_lines)
    max_len = max(char_counts)

    return avg_len <= 75 and max_len <= 85


def format_poem_stanza(lines: list[str]) -> str:
    """Formata uma estrofe de poema como bloco de citação Markdown (>) preservando os versos."""
    return "\n".join(f"> {l.strip()}" for l in lines if l.strip())




def restore_ocr_lexical_spacing(text: str) -> str:
    """
    Desacopla palavras aglutinadas geradas por motores de OCR devido a kerning apertado
    ou baixa resolução de scanner (ex: "oMicrosoftWord" -> "o Microsoft Word", "dacidade" -> "da cidade").
    """
    if not text:
        return ""
    
    if rust_restore_ocr_lexical_spacing:
        res = rust_restore_ocr_lexical_spacing(text)
        if res is not None:
            return res
    
    t = text

    # 1. Aglutinações de preposições e palavras comuns com maiúsculas (CamelCase OCR)
    t = re.sub(
        r"\b(o|a|os|as|do|da|dos|das|no|na|nos|nas|ao|aos|em|de|que|se|com|para|por|e|ou|um|uma|uns|umas|seu|sua|seus|suas|este|esta|estes|estas|esse|essa|esses|essas|aquele|aquela|aqueles|aquelas|cada|pelo|pela|pelos|pelas|sobre|entre|sem|sob|como|onde|quando|mais|menos|muito|muitos|muita|muitas|bem|mal|já|ainda|assim|qual|quais|qualquer|quaisquer|todo|toda|todos|todas|outro|outra|outros|outras)([A-Z\u00C0-\u00DC][a-z\u00E0-\u00FC0-9]+)\b",
        r"\1 \2",
        t
    )

    # 2. Aglutinações específicas frequentes em editais e provas
    merges = [
        (r"\bAoutilizar\b", "Ao utilizar"),
        (r"\baoutilizar\b", "ao utilizar"),
        (r"\bAareainsular\b", "A área insular"),
        (r"\baareainsular\b", "a área insular"),
        (r"\bAareatotal\b", "A área total"),
        (r"\baareatotal\b", "a área total"),
        (r"\bdacidadede\b", "da cidade de"),
        (r"\bdacidade\b", "da cidade"),
        (r"\bdocaderno\b", "do caderno"),
        (r"\bdodocumento\b", "do documento"),
        (r"\bdeSantos\b", "de Santos"),
        (r"\bdeSaoPaulo\b", "de São Paulo"),
        (r"\bdoRiodeJaneiro\b", "do Rio de Janeiro"),
        (r"\bnomunicipio\b", "no município"),
        (r"\bdomunicipio\b", "do município"),
        (r"\bdeacordo\b", "de acordo"),
        (r"\bdeacordocom\b", "de acordo com"),
        (r"\bdemaneira\b", "de maneira"),
        (r"\bdeforma\b", "de forma"),
        (r"\bapartir\b", "a partir"),
        (r"\bapartirde\b", "a partir de"),
        (r"\bpormeio\b", "por meio"),
        (r"\bpormeiode\b", "por meio de"),
        (r"\bcombase\b", "com base"),
        (r"\bcombaseno\b", "com base no"),
        (r"\bcombasena\b", "com base na"),
        (r"\bcomrelação\b", "com relação"),
        (r"\bcomrelacao\b", "com relação"),
        (r"\bemrelação\b", "em relação"),
        (r"\bemrelacao\b", "em relação"),
        (r"\bnoentanto\b", "no entanto"),
        (r"\bporisso\b", "por isso"),
        (r"\bportanto\b", "portanto"),
        (r"\balémdisso\b", "além disso"),
        (r"\balemdisso\b", "além disso"),
        (r"\batravésde\b", "através de"),
        (r"\batravesde\b", "através de"),
        (r"\bécorreto\b", "é correto"),
        (r"\béincorreto\b", "é incorreto"),
        (r"\bépossivel\b", "é possível"),
        (r"\bépossível\b", "é possível"),
        (r"\bénecessario\b", "é necessário"),
        (r"\bénecessário\b", "é necessário"),
        (r"\bnãopode\b", "não pode"),
        (r"\bnaopode\b", "não pode"),
        (r"\bnãodeve\b", "não deve"),
        (r"\bnaodeve\b", "não deve"),
        (r"\bpodeser\b", "pode ser"),
        (r"\bdeveser\b", "deve ser"),
        (r"\bseráfeita\b", "será feita"),
        (r"\bseráfeito\b", "será feito"),
        (r"\bserafeita\b", "será feita"),
        (r"\bserafeito\b", "será feito"),
        (r"\btemcomo\b", "tem como"),
        (r"\bassinaleaalternativa\b", "assinale a alternativa"),
        (r"\bassinaleaalternativacorreta\b", "assinale a alternativa correta"),
        (r"\bqualalternativa\b", "qual alternativa"),
        (r"\bemqualalternativa\b", "em qual alternativa"),
        (r"\bcomodados\b", "como dados"),
        (r"\bcomoum\b", "como um"),
        (r"\bcomouma\b", "como uma"),
        (r"\bcomoe\b", "como e"),
        (r"\bparaque\b", "para que"),
        (r"\bparaum\b", "para um"),
        (r"\bparauma\b", "para uma"),
    ]
    for pattern, repl in merges:
        t = re.sub(pattern, repl, t, flags=re.IGNORECASE)

    # 3. Limpeza de bullets OCR corrompidos em alternativas (!P, lO, /-d, @, etc.) estritamente em início de linha
    t = re.sub(r"(?m)^[ \t]*(?:\!P|\(p|\[p)\s+(?=[A-Za-z\u00C0-\u00DC0-9\"])", r"B) ", t)
    t = re.sub(r"(?m)^[ \t]*(?:lO|LO|\(o|\[o|\(g)\s+(?=[A-Za-z\u00C0-\u00DC0-9\"])", r"C) ", t)
    t = re.sub(r"(?m)^[ \t]*(?:\/\-d|\(d)\s+(?=[A-Za-z\u00C0-\u00DC0-9\"])", r"D) ", t)

    # 4. Desacoplamento de múltiplas alternativas impressas/lidas na mesma linha (ex: "c) opc1 d) opc2")
    t = re.sub(r"(?<=\S)[ \t]+([b-eB-E]\))\s+", r"\n\n\1 ", t)
    t = re.sub(r"(?<=\S)[ \t]+(\([b-eB-E]\))\s+", r"\n\n\1 ", t)
    t = re.sub(r"(?<=\S)[ \t]+([b-eB-E]\.)\s+(?=[A-Za-z\u00C0-\u00DC0-9\"])", r"\n\n\1 ", t)

    return t


def restore_exam_typography(text: str, is_option: bool = False) -> str:
    """
    Restaura a tipografia, parágrafos e pontuação de enunciados e textos de prova.
    Transforma texto cru ou quebrado em formatação editorial limpa e legível.
    """
    if not text:
        return ""

    if rust_restore_typography:
        res = rust_restore_typography(text, is_option)
        if res is not None:
            return res

    t = restore_ocr_lexical_spacing(text)

    # 1. Elimina o bug de espaçamento excessivo por justificação de PDF ("As         formigas         estão")
    t = re.sub(r"[ \t]{2,}", " ", t)

    # 2. Recomposição de hifenização de quebra de linha (ex: "admi-\nnistrativo" -> "administrativo")
    t = re.sub(r"([A-Za-z\u00C0-\u00DC]+)-\s*\n\s*([a-z\u00E0-\u00FC]+)", r"\1\2", t)

    # 0. Recomposição de URLs e codificação percentual quebradas entre linhas
    t = re.sub(r'%\s*\n\s*([0-9A-Fa-f]{2})', r'%\1', t)
    t = re.sub(r'%\s+([0-9A-Fa-f]{2})', r'%\1', t)
    t = re.sub(r'((?:https?://|://)[^\s\n\)]+)[ \t]+(%[0-9A-Fa-f]{2}[a-zA-Z0-9\-_./%?&=#@:+~]*)', r'\1\2', t)
    t = re.sub(r'((?:https?://|://)[^\s\n\)]+[-_/])[ \t]+([a-zA-Z0-9\-_./?&=#@:+~]{2,}(?:\.[a-zA-Z0-9]+)?)(?=\s|$|\n)', r'\1\2', t)

    def _stitch_url(m):
        u1 = m.group(1).rstrip()
        u2 = m.group(2).strip()
        if len(u2) < 2 and not u2.startswith(('%', '-', '_', '/', '.')):
            return m.group(0)
        if re.match(r'(?i)^(?:Quest[ãa]o|\d+[\.\-\)]|\([a-eA-E]\)|[a-eA-E][\.\)]|Leia|Considere|Observe|Veja|Analise|Dispon[íi]vel|Acesso|Adaptado)\b', u2):
            return m.group(0)
        if u1.endswith('/'):
            if not (u2.startswith('%') or '/' in u2 or u2.endswith(('.pdf', '.htm', '.html', '.php', '.aspx')) or '-' in u2 or '_' in u2 or '%' in u2):
                return m.group(0)
        elif not u1.endswith(('-', '_', '&', '=', '?', '%', '.')):
            if not (u2.startswith(('%', '-', '/', '.')) or '%' in u2 or '/' in u2 or '-' in u2 or u2.endswith(('.pdf', '.htm', '.html', '.php'))):
                return m.group(0)
        return f"{u1}{u2}"

    for _ in range(3):
        t = re.sub(r'((?:https?://|://)[^\s\n\)]+)\s*\n\s*([a-zA-Z0-9\-_./%?&=#@:+~]+(?:\([^\)]+\)[a-zA-Z0-9\-_./%?&=#@:+~]*)*\)?)(?=\s|$|\n)', _stitch_url, t)

    # 2.1 Costura de referências de Leis e Normas quebradas (ex: "Norma Regulamentadora\n29:" -> "Norma Regulamentadora 29:")
    t = re.sub(
        r"\b(Norma\s+Regulamentadora|Norma|Lei|Decreto|Portaria|NR|Resolu[çc][ãa]o)\s*(?:n[º°o]?\.?)?\s*\n*\s*(\d+)\s*(:?)",
        r"\1 \2\3",
        t,
        flags=re.IGNORECASE
    )

    # 2.2 Correção de aglutinações de palavras comuns do OCR
    t = re.sub(r"\bsequ[êe]nciaos\b", "sequência dos", t, flags=re.IGNORECASE)

    # 3. Limpeza de glitches de caracteres UTF-8 perdidos (ex: "??" -> "—")
    t = re.sub(r"\s*\?\?\s*", " — ", t)

    # Tratamento específico para Alternativas de Resposta:
    # Alternativas devem ser blocos de linha única contínua (ex: "II, IV e\nV." -> "II, IV e V.")
    if is_option:
        t = re.sub(r"\s*\n+\s*", " ", t)
        t = re.sub(r"[ \t]{2,}", " ", t)
        return t.strip()

    # 4. Formatação de Título de Artigo/Texto de Apoio (ex: "Por Que o YouTube...? Em 2025...")
    def format_title(m):
        banner = m.group(1) or ""
        title = m.group(2).strip()
        body_start = m.group(3)
        if title.startswith("#"):
            return f"{banner}\n\n{title}\n\n{body_start}"
        return f"{banner}\n\n### {title}\n\n{body_start}"

    if "### " not in t:
        t = re.sub(
            r"(📖\s+\*\*Texto\s+de\s+Apoio[^\*]*\*\*:?\s*\n*)?([A-Z\u00C0-\u00DC][^\n\.\!\?]{15,120}\?)\s*([A-Z\u00C0-\u00DC])",
            format_title,
            t
        )

    # 4.1 Normalização de comandos pareados em inglês (ex: "Match column 1 with column 2:")
    t = re.sub(
        r"\bMatch\s+column\s+(\d+|[I|V|X]+)\s*:?\s+(?:with|to|and)\s+column\s+(\d+|[I|V|X]+)\s*:?",
        r"\n\nMatch column \1 with column \2:\n\n",
        t,
        flags=re.IGNORECASE
    )

    # 4.2 Preserva numeração de itens após rótulos de tabela (ex: "Word (1) Deck." -> "\n\n(1) Deck.")
    t = re.sub(r"(?:^|\n|\s+)(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o)\s*[:.\-]?\s*(\(\d+\)|\(\s*_{1,4}\s*\))", r"\n\n\1 ", t, flags=re.IGNORECASE)
    t = re.sub(r"(\b\d+|[A-Za-z\u00C0-\u00DC])\s*(\(\d+\))", r"\1\n\n\2", t)
    t = re.sub(r"(\(\d+\))\s*([A-Za-z\u00C0-\u00DC])", r"\1 \2", t)

    # 4.3 Desaglutinação de itens com marcadores/hífen/traço (ex: "resultados: - 6 pessoas...", "Caribe. - 24 pessoas...")
    t = re.sub(r"(?:^|\n|(?<=[:.;])\s*|\s{2,}|\.\s+)([—–\-•])\s+([0-9A-Za-z\u00C0-\u00DC])", r"\n\n\1 \2", t)

    # 5. Formatação e Desaglutinação de Quadros, Colunas e Painéis (Português e Inglês)
    TAGS_OPT = r"(?:<\/?(?:u|b|i|strong|em)>)*"
    HEADING_ORDINAL = rf"{TAGS_OPT}\s*(?:1[ªaºo]|2[ªaºo]|3[ªaºo]|4[ªaºo]|Primeir[ao]|Segund[ao]|Terceir[ao]|Quart[ao]){TAGS_OPT}\s+{TAGS_OPT}(?:Coluna|Column|Tabela|Quadro|Bloco)\b{TAGS_OPT}"
    HEADING_COL = rf"{TAGS_OPT}\s*(?:Coluna|Column|Quadro|Painel|Tira|Bloco|Tabela){TAGS_OPT}\s+{TAGS_OPT}(?:0*\d+|I{{1,3}}|IV|V|VI|VII|VIII|IX|X|[A-E]\b){TAGS_OPT}(?:\s*[-–—:]\s*{TAGS_OPT}(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o|Conceito|Descri[çc][ãa]o){TAGS_OPT})?"
    HEADING_PREFIXES = rf"{TAGS_OPT}\s*(?:QUADRO|PAINEL|TIRA|BLOCO|TABELA){TAGS_OPT}\s+\d+\b{TAGS_OPT}"
    HEAD_PAT = rf"(?:{HEADING_ORDINAL}|{HEADING_COL}|{HEADING_PREFIXES})"
    PREPS = r"da|do|das|dos|na|no|nas|nos|pela|pelo|pelas|pelos|em|à|a|ao|aos|com|para|de|o|os|um|uma|este|esta|esse|essa|e|ou|match|with|entre|segundo|conforme|sob|sobre"

    def format_heading_match(m):
        prefix_lead = m.group(1) or m.group(4) or ""
        prep = m.group(2) or m.group(5)
        heading = m.group(3) or m.group(6)
        if prep:
            # Precedido por preposição/conjunção narrativa ("a Coluna 01", "na Coluna 02") -> mantém inalterado
            return m.group(0)
        clean_prefix = re.sub(r"<\/?(?:u|b|i|strong|em)>|\*\*", "", heading).strip()
        clean_prefix = re.sub(r"\s+", " ", clean_prefix).strip()
        lead_punct = ":" if ":" in prefix_lead else ""
        return f"{lead_punct}\n\n**{clean_prefix}:**\n\n"

    t = re.sub(
        rf"(?i)(?:(^|\s+|[:.\-]\s*)(\b(?:{PREPS})\s+)({HEAD_PAT})|(^|\s+|[:.\-]\s*)()({HEAD_PAT}))\s*[:.\-]?(?=\s|$)",
        format_heading_match,
        t
    )

    # 7. Desaglutinação de sub-itens de letras em colunas pareadas (ex: "A. Depende de... B. Integra...")
    t = re.sub(
        r"(?:^|\n|(?<=\.|\;|\:|\))\s*|\s{2,})([A-E])\s*[\.\)]\s*(?=[A-Z\u00C0-\u00DC\"])",
        r"\n\n\1. ",
        t
    )

    # 8. Desaglutinação de Comandos Finais de Questão (executado antes para isolar o comando antes de qualquer item)
    COMMAND_PATTERNS = [
        r"(?:Ap[óo]s\s+an[áa]lise\s*,?\s*)?(?:Assinale|Marque|Indique|Identifique)\s+(?:a\s+alternativa|a\s+op[çc][ãa]o|a\s+assertiva|a\s+proposi[çc][ãa]o|o\s+item|a\s+sequ[êe]ncia|o\s+que\s+se\s+pede|abaixo|corretamente|a\(s\)\s+afirmativa\(s\)|as\s+afirmativas|o\s+correto|o\s+incorreto)[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"A\s+sequ[êe]ncia\s+(?:CORRETA|correta|INCORRETA|incorreta|adequada|certa)[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"(?:Correlacione|Associe)\s+(?:corretamente|as\s+colunas|os\s+itens|a\s+coluna)[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"(?:Match|Choose)\s+[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"(?:Est[áa]\s*\([ãa]o\)\s+correta\s*\([s\)]\)|Est[ãa]o\s+corretas?|Est[áa]\s+correta?|Est[áa]\s+CORRETO|Est[ãa]o\s+CORRETAS?|S[ãa]o\s+corretas?|S[ãa]o\s+verdadeiras?|S[ãa]o\s+falsas?)[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"(?:[ÉE]\s+correto|[ÉE]\s+INCORRETO|[ÉE]\s+verdadeiro|[ÉE]\s+falso|[ÉE]\s+adequado)\s+(?:afirmar|dizer|o\s+que\s+se\s+afirma|o\s+que\s+se\s+diz|apenas)[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"(?:A\s+respeito\s+dessas?\s+afirmativas?|Quanto\s+[àa]s?\s+afirmativas?|Sobre\s+as\s+afirmativas?|Acerca\s+das\s+afirmativas?|Com\s+rela[çc][ãa]o\s+[àa]s\s+afirmativas?|Em\s+rela[çc][ãa]o\s+[àa]s\s+afirmativas?)[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"(?:Julgue\s+os\s+itens|Analise\s+os\s+itens|Avalie\s+as\s+afirmativas|Considere\s+as\s+afirmativas)[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"(?:Em\s+quais?|Quais?|Qual(?:\s+das?)?)\s+(?:afirmativas?|proposi[çc][õo]es|assertivas?|itens?|alternativas?|op[çc][õo]es|est[ãa]o|apresenta|cont[ée]m|delas|destas|dessas)[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"(?:Em\s+quais?|Quais?|Qual(?:\s+das?)?)\s+[A-Za-z\u00C0-\u00DC\s]{3,50}\s+(?:corret[ao]s?|incorret[ao]s?|verdadeir[ao]s?|fals[ao]s?|introduzidas?|atendidas?|v[áa]lidas?)[^\n]*?(?:[:\.\?]|$|(?=\n))",
        r"\b(?:De\s+acordo\s+com\s+o\s+texto|Com\s+base\s+no\s+texto|Segundo\s+o\s+texto)\s*,\s*(?:assinale|marque|indique|identifique|[ée]\s+correto|est[áa]\s+correto)[^\n]*?(?:[:\.\?]|$|(?=\n))",
    ]
    for c_pat in COMMAND_PATTERNS:
        t = re.sub(rf"(?<!\n\n)(?:^|\n|\s+)({c_pat})", r"\n\n\1\n\n", t, flags=re.IGNORECASE)

    # 9. Desaglutinação Universal de Itens Romanos (apenas se não precedido por palavras de seção/título)
    def format_roman_item(m):
        prefix = m.group(1) or ""
        roman = m.group(2)
        if re.search(r'(?:Se[çc][ãa]o|Artigo|Art|Cap[íi]tulo|T[íi]tulo|Livro|Parte|Anexo|Item|Grupo|Classe|N[íi]vel|Fase|Bloco|Quadro|Tabela|Coluna|Volume|Edi[çc][ãa]o)\s*$', prefix, re.IGNORECASE):
            return m.group(0)
        return f"{prefix}\n\n{roman}. "

    t = re.sub(
        r"(^|\n|(?<=\.|\;|\:|\))\s*|\s{2,}|\b[A-Za-z\u00C0-\u00DC]+\s+)(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[\.\-\–\—\)]\s*(?=[A-Z\u00C0-\u00DC\"])",
        format_roman_item,
        t
    )

    # 10. Desaglutinação de lacunas de preenchimento (ex: "(__) 3,5 m... (__)0,08 m..." -> "\n\n(__) 3,5 m...\n\n(__) 0,08 m...")
    t = re.sub(
        r"(?:^|\n|\s+)(\(\s*_{1,4}\s*\)|\(\s*\))\s*(?=[A-Za-z\u00C0-\u00DC0-9\"\'\-])",
        r"\n\n\1 ",
        t
    )

    # 10.1 Desaglutinação de itens numéricos entre parênteses (ex: "(1) Deck. (2) Hull." ou "(1)Instalação...")
    t = re.sub(
        r"(?:^|\n|(?<=\.|\;|\:|\))\s*|\s{2,}|\b)\((\d{1,2})\)\s*(?=[A-Za-z\u00C0-\u00DC\"])",
        r"\n\n(\1) ",
        t
    )

    # 10.2 Recomposição de sentenças pareadas com barra em itens/lacunas (ex: "(__) ACENDER a luz.\n/ ASCENDER socialmente" -> "(__) ACENDER a luz. / ASCENDER socialmente")
    t = re.sub(r"\n+\s*(/\s+[A-Za-z\u00C0-\u00DC])", r" \1", t)

    # 11. Itens numéricos sem parênteses (1. , 2. ) isolados e desaglutinados (inclusive palavras curtas como 'Pé')
    def format_numbered_item(m):
        lead = m.group(1) or ""
        num = m.group(2)
        lead_punct = ";" if ";" in lead else ""
        return f"{lead_punct}\n\n{num}. "

    t = re.sub(
        r"(^|\n|[.;:\)]\s*|\s{2,})([1-9]|1[0-2])\s*[\.\)]\s*(?=[A-Z\u00C0-\u00DC\"])",
        format_numbered_item,
        t
    )

    # 11.1 Desaglutinação de Frases de Transição e Conexão de Itens (ex: "5. Passagem. Esses elementos correspondem a..." -> "5. Passagem.\n\nEsses elementos correspondem a...")
    TRANSITION_PATTERNS = [
        r"(?:Ess[ea]s?|Est[ea]s?|Ta[li]s?|Os|As|Cada|Tais)\s+(?:elementos|itens|conceitos|termos|defini[çc][õo]es|caracter[íi]sticas|situa[çc][õo]es|assertivas|proposi[çc][õo]es|fatores|aspectos|grupos|senten[çc]as|frases|palavras|express[õo]es|enunciados)\s+(?:correspondem|referem-se|dizem\s+respeito|apresentam|relacionam-se|est[ãa]o|s[ãa]o|possuem|t[êe]m|tratam)[^\n]*",
        r"(?:Associe|Relacione|Correlacione|Vincule)\s+(?:os\s+elementos|os\s+itens|as\s+colunas|os\s+termos|as\s+defini[çc][õo]es|as\s+frases|as\s+senten[çc]as|cada\s+um)[^\n]*",
        r"(?:A\s+respeito|Em\s+rela[çc][ãa]o|Quanto)\s+(?:a\s+ess[ea]s|a\s+est[ea]s|aos\s+elementos|aos\s+itens|às\s+situa[çc][õo]es|às\s+defini[çc][õo]es)[^\n]*",
    ]
    for tr_pat in TRANSITION_PATTERNS:
        t = re.sub(rf"(?<!\n\n)(?:^|\n|\s+)({tr_pat})", r"\n\n\1\n\n", t, flags=re.IGNORECASE)

    # 12. Artigos e parágrafos de legislação
    def format_legal_article(m):
        prefix = m.group(1) or ""
        art = m.group(2)
        if re.search(r'(?:em\s+seu|no\s+seu|no|na|nos|nas|do|da|dos|das|pelo|pela|pelos|pelas|conforme|segundo|termos\s+do|disposto\s+no|previsto\s+no|com\s+base\s+no|sob\s+o|sobre\s+o|ao|aos|seu|sua|este|esta)\s*$', prefix, re.IGNORECASE):
            return m.group(0)
        return f"{prefix}\n\n{art} - "

    t = re.sub(
        r"(^|\n|[.;:]\s+|\s{2,}|\b[A-Za-z\u00C0-\u00DC]+\s+)(Art\.\s*\d+[º°\.]?|§\s*\d+[º°\.]?|Parágrafo\s+[ÚUúu]nico|Inciso\s+[I|V|X\d]+)\s*[:.\-]?\s*",
        format_legal_article,
        t,
        flags=re.IGNORECASE
    )

    # 13. Links e referências web: isola a URL e preserva metadados
    def clean_url_match(m):
        full_match = m.group(0)
        url_match = re.search(r"(?:https?://|://)[a-zA-Z0-9\-_./%?&=#@:+~\u00C0-\u00FC]+(?:\([a-zA-Z0-9\-_\s./%?&=#@:+~\u00C0-\u00FC]+\)[a-zA-Z0-9\-_./%?&=#@:+~\u00C0-\u00FC]*)*(?:\.pdf|\.html|\.php|[a-zA-Z0-9/\u00C0-\u00FC])", full_match, re.IGNORECASE)
        if not url_match:
            return full_match
        raw_url = url_match.group(0).strip()
        raw_url = raw_url.strip("()*. ")
        try:
            sanitized_url = urllib.parse.unquote(raw_url)
        except Exception:
            sanitized_url = raw_url
        return f"\n\n*(Fonte: {sanitized_url})*\n\n"

    t = re.sub(
        r"(?i)(?:\*\([Ff]onte:\s*|\(?[Ff]onte\s*:\s*|\(?[Aa]cesso\s+em\s*:\s*)?(?:https?://|://)[a-zA-Z0-9\-_./%?&=#@:+~\u00C0-\u00FC]+(?:\([a-zA-Z0-9\-_\s./%?&=#@:+~\u00C0-\u00FC]+\)[a-zA-Z0-9\-_./%?&=#@:+~\u00C0-\u00FC]*)*(?:\.pdf|\.html|\.php|[a-zA-Z0-9/\u00C0-\u00FC])(?:\)\*|\))?",
        clean_url_match,
        t
    )

    t = re.sub(r"(?i)\*\)\s*\n+\s*[\.,;:]\s*(?=Acesso\s+em\b)", "*)\n\n", t)
    t = re.sub(r"(?m)^\s*[\.,;:]\s*", "", t)

    # 13.1 Eliminação de pontuação órfã em linhas isoladas (ex: "\n\n.\n\n")
    t = re.sub(r"(?:^|\n)\s*[\.\,\;\:]\s*(?=\n|$)", "", t)

    # 14. Desaglutinação de falas com travessão em início de linha (em-dash / en-dash)
    t = re.sub(r"(?:^|\n)\s*([—–]\s+[A-Z\u00C0-\u00DC])", r"\n\n\1", t)

    # 15. Proteção e Isolamento do Divisor Markdown Horizontal
    t = re.sub(r"(?:^|\n)\s*---+\s*(?:$|\n)", r"\n\n---\n\n", t)
    t = re.sub(r"(?:^|\n)\s*---+\s+([^\n]+)", r"\n\n---\n\n\1", t)

    # 15.1 Limpeza de marcações markdown corrompidas (apenas linhas contendo somente asteriscos)
    t = re.sub(r"(?m)^\s*\*+\s*$", "", t)

    # 16. Reconstrução de Parágrafos Naturais e Preservação de Estrofes e Poemas:
    raw_blocks = [b.strip() for b in t.split("\n\n") if b.strip()]
    final_paras = []
    
    # Rastreia se o contexto geral do texto é poético
    has_global_poetic_context = bool(POEM_CUES_REGEX.search(t) or FAMOUS_POETS_REGEX.search(t))

    for block_idx, block in enumerate(raw_blocks):
        if block.startswith("---") or block.startswith("📖") or block.startswith("**") or block.startswith("###") or block.startswith("*(") or block.startswith(">") or block.startswith("|") or "\n|" in block:
            final_paras.append(block)
            continue

        # Se o bloco começa com letra minúscula e o parágrafo anterior existe e não fecha com ponto final forte, junta!
        if final_paras and block and block[0].islower() and not final_paras[-1].startswith(("---", "📖", "**", "###", "*(", ">", "|")):
            final_paras[-1] = final_paras[-1] + " " + block
            continue

        # Contexto local do bloco anterior/atual
        prev_block_text = raw_blocks[block_idx - 1] if block_idx > 0 else ""
        has_local_poetic_context = (
            has_global_poetic_context 
            or bool(POEM_CUES_REGEX.search(prev_block_text) or FAMOUS_POETS_REGEX.search(prev_block_text))
            or bool(POEM_CUES_REGEX.search(block) or FAMOUS_POETS_REGEX.search(block))
        )

        # Desmembra versos aglutinados no bloco
        block = unsquash_poem_lines(block)
        lines = [l.strip() for l in block.split("\n") if l.strip()]

        # Se o bloco tem comando/intro na primeira linha (ex: "Leia o fragmento a seguir, de Fernando Pessoa:")
        is_intro = lines[0].endswith(':') or bool(re.match(r'(?i)^(?:Leia|Considere|Observe|Veja|Analise|Texto\s+para|Fragmento\s+de|Trecho\s+de)\b', lines[0]))
        if len(lines) >= 3 and is_intro:
            final_paras.append(lines[0])
            lines = lines[1:]


        # Se o bloco inteiro é uma estrofe de poema
        if is_poem_stanza_block(lines, has_poetic_context=has_local_poetic_context):
            final_paras.append(format_poem_stanza(lines))
            continue

        # Se o bloco contém uma estrofe seguida de prosa/comentário (ex: versos seguidos de "Nos versos de Luiz Gonzaga...")
        if has_local_poetic_context and len(lines) >= 3:
            for split_idx in range(2, len(lines)):
                verse_candidate = lines[:split_idx]
                remaining_lines = lines[split_idx:]
                first_rem = remaining_lines[0].strip().strip('*_`')
                if PROSE_PROMPT_REGEX.match(first_rem) or not is_verse_line(remaining_lines[0]):
                    if is_poem_stanza_block(verse_candidate, has_poetic_context=True):
                        final_paras.append(format_poem_stanza(verse_candidate))
                        lines = remaining_lines
                        break


        current_sub = []
        for line in lines:
            if not current_sub:
                current_sub.append(line)
                continue
            prev_line = current_sub[-1]
            
            # Se a linha anterior termina com conjunção, preposição ou pontuação incompleta, NUNCA quebra parágrafo
            is_prev_incomplete = bool(re.search(r'(?:,|;\s*$|\b(?:e|ou|de|do|da|dos|das|em|com|para|por|que|apenas|somente|todas|todos|nenhum|nenhuma|como|onde|ao|aos|na|nas|no|nos|pelo|pela|pelos|pelas|opção|opções|with|match)\s*$)', prev_line, re.IGNORECASE))
            
            # Um item estruturado real DEVE ter conteúdo substancial após o marcador (ex: "I. O princípio...", "(1) Deck.", "(__) The floor...")
            is_prev_item = bool(re.match(r"^(?:I|II|III|IV|V|VI|VII|VIII|IX|X|\d{1,2})\.\s+[A-Za-z\u00C0-\u00DC0-9\"\(]{2,}|\(\d{1,2}\)\s+[A-Za-z0-9\"\'\-]|\(\s*_{1,4}\s*\)\s+[A-Za-z0-9\"\'\-]", prev_line))
            is_current_item = (
                not is_prev_incomplete 
                and bool(re.match(r"^(?:I|II|III|IV|V|VI|VII|VIII|IX|X|\d{1,2})\.\s+[A-Za-z\u00C0-\u00DC0-9\"\(]{2,}|\(\d{1,2}\)\s+[A-Za-z0-9\"\'\-]|\(\s*_{1,4}\s*\)\s+[A-Za-z0-9\"\'\-]|Art\.\s*\d+|§\s*\d+|\*\*|###|(?:Correlacione|Assinale|Marque|Indique|Identifique|A\s+sequ[êe]ncia|Est[áa]\(?[ãa]o\)?|S[ãa]o|[ÉE]\s+correto|[ÉE]\s+INCORRETO|Julgue|Analise)", line))
            )
            
            is_prev_end = not is_prev_incomplete and bool(re.search(r"[\.\!\?\:\;]\s*$", prev_line))

            if not is_prev_incomplete and (is_current_item or (is_prev_item and is_prev_end) or (is_prev_end and len(prev_line) > 30 and len(line) > 10)):
                final_paras.append(" ".join(current_sub))
                current_sub = [line]
            else:
                current_sub.append(line)
        if current_sub:
            final_paras.append(" ".join(current_sub))

    result = "\n\n".join(final_paras)

    # 17. Limpeza final de espaçamentos residuais
    result = re.sub(r"[ \t]+", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()

