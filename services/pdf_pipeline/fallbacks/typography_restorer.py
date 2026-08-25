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

    # 4.2 Remove rótulos de tabela redundantes colados antes de itens (ex: "Word (1) Deck.", "Meaning (__) The floor...")
    t = re.sub(r"(?:^|\n|\s+)(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o)\s*[:.\-]?\s*(?=\(\d+\)|\(\s*_{1,4}\s*\))", "\n\n", t, flags=re.IGNORECASE)

    # 5. Formatação e Desaglutinação de Quadros, Colunas e Painéis (Português e Inglês)
    HEADING_ORDINAL = r"(?:1[ªaºo]|2[ªaºo]|3[ªaºo]|4[ªaºo]|Primeir[ao]|Segund[ao]|Terceir[ao]|Quart[ao])\s+(?:Coluna|Column|Tabela|Quadro|Bloco)\b"
    HEADING_COL = r"(?:Coluna|Column|Quadro|Painel|Tira|Bloco|Tabela)\s+(?:0*\d+|I{1,3}|IV|V|VI|VII|VIII|IX|X|[A-E]\b)(?:\s*[-–—:]\s*(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o|Conceito|Descri[çc][ãa]o))?"
    HEADING_PREFIXES = r"(?:QUADRO|PAINEL|TIRA|BLOCO|TABELA)\s+\d+\b"
    HEAD_PAT = rf"(?:{HEADING_ORDINAL}|{HEADING_COL}|{HEADING_PREFIXES})"
    PREPS = r"da|do|das|dos|na|no|nas|nos|pela|pelo|pelas|pelos|em|à|a|ao|aos|com|para|de|o|os|um|uma|este|esta|esse|essa|e|ou|match|with"

    def format_heading_match(m):
        prep = m.group(1)
        heading = m.group(2)
        if prep:
            # Precedido por preposição/conjunção narrativa -> mantém inalterado
            return m.group(0)
        prefix = re.sub(r"\s+", " ", heading.strip())
        clean_prefix = prefix.replace("**", "").strip()
        return f"\n\n**{clean_prefix}:**\n\n"

    t = re.sub(
        rf"(\b(?:{PREPS})\s+)?\b({HEAD_PAT})\s*[:.\-]?\s*",
        format_heading_match,
        t,
        flags=re.IGNORECASE
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

    # 9. Desaglutinação Universal de Itens Romanos (ex: "I.O texto... II. A norma..." -> "\n\nI. O texto...\n\nII. A norma...")
    t = re.sub(
        r"(?:^|\n|(?<=\.|\;|\:|\))\s*|\s{2,}|\b)(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[\.\-\–\—\)]\s*(?=[A-Z\u00C0-\u00DC\"])",
        r"\n\n\1. ",
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

    # 11. Desaglutinação de itens numéricos internos (ex: "1.Os cristais... 2.Os mortais..." -> "\n\n1. Os cristais...\n\n2. Os mortais...")
    t = re.sub(
        r"(?:^|\n|(?<=\.|\;)\s+)(\d{1,2})\s*[\.\)]\s*(?=[A-Z\u00C0-\u00DC\"][A-Za-z\u00C0-\u00DC0-9\s]{3,})",
        r"\n\n\1. ",
        t
    )

    # 12. Formatação de Artigos de Lei e Parágrafos Legais (Art. 5º, § 1º, Inciso II)
    t = re.sub(
        r"(?:^|\n|\s+)(Art\.\s*\d+[º°\.]?|§\s*\d+[º°\.]?|Parágrafo\s+[ÚUúu]nico|Inciso\s+[I|V|X\d]+)\s*[:.\-]?\s*",
        r"\n\n\1 - ",
        t,
        flags=re.IGNORECASE
    )

    # 13. Limpeza e Isolamento de Links e Fontes Bibliográficas (ex: "https://... %C3%ADvel...")
    def clean_url_match(m):
        full_match = m.group(0).strip()
        url_match = re.search(r"https?://[^\s\)\"]+(?:\s*(?:\n|\r\n)?\s*(?:%[0-9A-Fa-f]{2}|[a-zA-Z0-9\-\_\.\/\?\&\=\#])[^\s\)\"]*)*", full_match)
        if not url_match:
            return full_match
        raw_url = url_match.group(0).strip()
        sanitized_url = re.sub(r"[\.\,\s\(\)]+$", "", raw_url)
        sanitized_url = re.sub(r"\s+", "", sanitized_url)
        try:
            sanitized_url = urllib.parse.unquote(sanitized_url)
        except Exception:
            pass
        return f"\n\n*(Fonte: {sanitized_url})*\n\n"

    t = re.sub(
        r"(?:\(?[Ff]onte\s*:\s*)?https?://[^\s\)\"]+(?:\s*(?:\n|\r\n)?\s*(?:%[0-9A-Fa-f]{2}|[a-zA-Z0-9\-\_\.\/\?\&\=\#])[^\s\)\"]*)*\)?",
        clean_url_match,
        t
    )

    # 13.1 Eliminação de pontuação órfã em linhas isoladas (ex: "\n\n.\n\n")
    t = re.sub(r"(?:^|\n)\s*[\.\,\;\:]\s*(?=\n|$)", "", t)

    # 14. Desaglutinação de falas com travessão em início de linha (em-dash / en-dash)
    t = re.sub(r"(?:^|\n)\s*([—–]\s+[A-Z\u00C0-\u00DC])", r"\n\n\1", t)

    # 15. Proteção e Isolamento do Divisor Markdown Horizontal
    t = re.sub(r"(?:^|\n)\s*---+\s*(?:$|\n)", r"\n\n---\n\n", t)
    t = re.sub(r"(?:^|\n)\s*---+\s+([^\n]+)", r"\n\n---\n\n\1", t)

    # 15.1 Limpeza de marcações markdown corrompidas (apenas linhas contendo somente asteriscos)
    t = re.sub(r"(?m)^\s*\*+\s*$", "", t)

    # 16. Reconstrução de Parágrafos Naturais e Junção de Continuações entre Páginas:
    raw_blocks = [b.strip() for b in t.split("\n\n") if b.strip()]
    final_paras = []

    for block in raw_blocks:
        if block.startswith("---") or block.startswith("📖") or block.startswith("**QUADRO") or block.startswith("**Coluna") or block.startswith("**Column") or block.startswith("###") or block.startswith("*("):
            final_paras.append(block)
            continue

        # Se o bloco começa com letra minúscula e o parágrafo anterior existe e não fecha com ponto final forte, junta!
        if final_paras and block and block[0].islower() and not final_paras[-1].startswith(("---", "📖", "**QUADRO", "**Coluna", "**Column", "###", "*(")):
            final_paras[-1] = final_paras[-1] + " " + block
            continue

        lines = [l.strip() for l in block.split("\n") if l.strip()]
        current_sub = []
        for line in lines:
            if not current_sub:
                current_sub.append(line)
                continue
            prev_line = current_sub[-1]
            
            # Se a linha anterior termina com conjunção, preposição ou pontuação incompleta, NUNCA quebra parágrafo
            is_prev_incomplete = bool(re.search(r'(?:,|;\s*$|\b(?:e|ou|de|do|da|dos|das|em|com|para|por|que|apenas|somente|todas|todos|nenhum|nenhuma|como|onde|ao|aos|na|nas|no|nos|pelo|pela|pelos|pelas|opção|opções|with|match)\s*$)', prev_line, re.IGNORECASE))
            
            # Um item estruturado real DEVE ter conteúdo substancial após o marcador (ex: "I. O princípio...", "(1) Deck.", "(__) The floor...")
            is_current_item = (
                not is_prev_incomplete 
                and bool(re.match(r"^(?:I|II|III|IV|V|VI|VII|VIII|IX|X|\d{1,2})\.\s+[A-Za-z\u00C0-\u00DC0-9\"\(]{2,}|\(\d{1,2}\)\s+[A-Za-z0-9\"\'\-]|\(\s*_{1,4}\s*\)\s+[A-Za-z0-9\"\'\-]|Art\.\s*\d+|§\s*\d+|\*\*QUADRO|\*\*Coluna|\*\*Column|###", line))
            )
            
            is_prev_end = not is_prev_incomplete and bool(re.search(r"[\.\!\?\:\;]\s*$", prev_line)) and len(prev_line) > 30

            if is_current_item or (is_prev_end and len(line) > 10):
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
