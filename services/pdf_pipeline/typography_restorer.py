#!/usr/bin/env python3
"""
concurse.io — Restaurador Tipográfico e Reconstrutor de Parágrafos
Elimina a "massa aglutinada" típica de extrações de PDF, restaurando a diagramação
editorial perfeita: parágrafos fluidos, numerais romanos isolados, artigos de lei,
hifenizações recompostas e desaglutinação de itens.
"""

from __future__ import annotations
import re


import urllib.parse


def restore_exam_typography(text: str, is_option: bool = False) -> str:
    """
    Restaura a tipografia, parágrafos e pontuação de enunciados e textos de prova.
    Transforma texto cru ou quebrado em formatação editorial limpa e legível.
    """
    if not text:
        return ""

    t = text

    # 1. Elimina o bug de espaçamento excessivo por justificação de PDF ("As         formigas         estão")
    t = re.sub(r"[ \t]{2,}", " ", t)

    # 2. Recomposição de hifenização de quebra de linha (ex: "admi-\nnistrativo" -> "administrativo")
    t = re.sub(r"([A-Za-z\u00C0-\u00DC]+)-\s*\n\s*([a-z\u00E0-\u00FC]+)", r"\1\2", t)

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

    # 5. Formatação e Desaglutinação de Quadros, Colunas e Painéis
    def format_heading(m):
        prefix = re.sub(r"\s+", " ", m.group(1).strip())
        return f"\n\n**{prefix}:**\n\n"

    t = re.sub(
        r"(?<!\*\*)(?:^|\n|(?<=\.|\))\s+)(QUADRO\s+\d+|PAINEL\s+\d+|TIRA\s+\d+|Coluna\s+(?:0*\d+|I{1,3}|IV|V|[A-E]))\s*[:.\-]?\s*",
        format_heading,
        t,
        flags=re.IGNORECASE
    )
    t = re.sub(
        r"(?<!\*\*)(?:\b)(QUADRO\s+\d+|PAINEL\s+\d+|TIRA\s+\d+|Coluna\s+(?:0*\d+|I{1,3}|IV|V|[A-E]))\s*[:\-]\s*",
        format_heading,
        t,
        flags=re.IGNORECASE
    )

    # 7. Desaglutinação de sub-itens de letras em colunas pareadas (ex: "A. Depende de... B. Integra...")
    t = re.sub(
        r"(?:^|\n|\s+)([A-E])\s*[\.\)]\s*([A-Z\u00C0-\u00DC\"][A-Za-z\u00C0-\u00DC0-9\s]{2,})",
        r"\n\n\1. \2",
        t
    )
    t = re.sub(
        r"(?<=[a-z\u00E0-\u00FC0-9\.\)])\s+([A-E]\.\s+[A-Z\u00C0-\u00DC])",
        r"\n\n\1",
        t
    )

    # 8. Desaglutinação de Comandos Finais de Questão (executado antes para isolar o comando antes de qualquer item)
    COMMAND_PATTERNS = [
        r"A\s+sequ[êe]ncia\s+CORRETA[^\n\.\:\?]*[:\.]?",
        r"A\s+sequ[êe]ncia\s+correta[^\n\.\:\?]*[:\.]?",
        r"Correlacione\s+corretamente[^\n\.\:\?]*[:\.]?",
        r"Associe\s+corretamente[^\n\.\:\?]*[:\.]?",
        r"Assinale\s+a\s+alternativa[^\n\.\:\?]*[:\.]?",
        r"Assinale\s+a\s+op[çc][ãa]o[^\n\.\:\?]*[:\.]?",
        r"Marque\s+a\s+alternativa[^\n\.\:\?]*[:\.]?",
        r"Marque\s+a\s+op[çc][ãa]o[^\n\.\:\?]*[:\.]?",
        r"Est[áa]\s*\([ãa]o\)\s+correta\s*\([s\)]\)[^\n\.\:\?]*[:\.]?",
        r"Est[ãa]o\s+corretas?[^\n\.\:\?]*[:\.]?",
        r"Est[áa]\s+correta?[^\n\.\:\?]*[:\.]?",
        r"Est[áa]\s+CORRETO[^\n\.\:\?]*[:\.]?",
        r"Quais\s+est[ãa]o\s+corretas?[^\n\.\:\?]*[:\.]?",
        r"[ÉE]\s+correto\s+o\s+que\s+se\s+afirma\s+em[^\n\.\:\?]*[:\.]?",
        r"Julgue\s+os\s+itens[^\n\.\:\?]*[:\.]?",
    ]
    for c_pat in COMMAND_PATTERNS:
        t = re.sub(rf"(?<!\n\n)(?:^|\n|\s+)({c_pat})", r"\n\n\1\n\n", t, flags=re.IGNORECASE)

    # 9. Desaglutinação de Itens Romanos colados (ex: "I.O texto... II.A norma..." -> "\n\nI. O texto...\n\nII. A norma...")
    t = re.sub(
        r"(?:^|\n|(?<=\.|\;)\s+)(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[\.\-\–\—\)]\s*([A-Z\u00C0-\u00DC\"][A-Za-z\u00C0-\u00DC0-9\s]{2,})",
        r"\n\n\1. \2",
        t
    )

    # 10. Desaglutinação de lacunas de preenchimento (ex: "(__)O vocábulo..." -> "\n\n(__) O vocábulo...")
    t = re.sub(
        r"(?:^|\n|\s+)(\(\s*_{1,4}\s*\)|\(\s*\))\s*([A-Z\u00C0-\u00DC0-9\"])",
        r"\n\n\1 \2",
        t
    )

    # 11. Desaglutinação de itens numéricos internos (ex: "1.Os cristais... 2.Os mortais..." -> "\n\n1. Os cristais...\n\n2. Os mortais...")
    # Exige início de linha ou pontuação forte anterior e pelo menos 3 caracteres de texto subsequente
    t = re.sub(
        r"(?:^|\n|(?<=\.|\;)\s+)(\d{1,2})\s*[\.\)]\s*([A-Z\u00C0-\u00DC\"][A-Za-z\u00C0-\u00DC0-9\s]{3,})",
        r"\n\n\1. \2",
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
        raw_url = m.group(0).strip()
        sanitized_url = re.sub(r"\s+", "", raw_url)
        try:
            sanitized_url = urllib.parse.unquote(sanitized_url)
        except Exception:
            pass
        return f"\n\n*(Fonte: {sanitized_url})*\n\n"

    t = re.sub(r"(?<!\(Fonte: )https?://[^\s\)\"]+(?:\s+%[0-9A-Fa-f]{2}[^\s\)\"]*)*", clean_url_match, t)

    # 14. Desaglutinação de falas com travessão em início de linha (em-dash / en-dash)
    t = re.sub(r"(?:^|\n)\s*([—–]\s+[A-Z\u00C0-\u00DC])", r"\n\n\1", t)

    # 15. Proteção e Isolamento do Divisor Markdown Horizontal
    t = re.sub(r"(?:^|\n)\s*---+\s*(?:$|\n)", r"\n\n---\n\n", t)
    t = re.sub(r"(?:^|\n)\s*---+\s+([^\n]+)", r"\n\n---\n\n\1", t)

    # 16. Reconstrução de Parágrafos Naturais e Junção de Continuações entre Páginas:
    raw_blocks = [b.strip() for b in t.split("\n\n") if b.strip()]
    final_paras = []

    for block in raw_blocks:
        if block.startswith("---") or block.startswith("📖") or block.startswith("**QUADRO") or block.startswith("**Coluna") or block.startswith("###") or block.startswith("*("):
            final_paras.append(block)
            continue

        # Se o bloco começa com letra minúscula e o parágrafo anterior existe e não fecha com ponto final forte, junta!
        if final_paras and block and block[0].islower() and not final_paras[-1].startswith(("---", "📖", "**QUADRO", "**Coluna", "###", "*(")):
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
            is_prev_incomplete = bool(re.search(r'(?:,|;\s*$|\b(?:e|ou|de|do|da|dos|das|em|com|para|por|que|apenas|somente|todas|todos|nenhum|nenhuma|como|onde|ao|aos|na|nas|no|nos|pelo|pela|pelos|pelas|opção|opções)\s*$)', prev_line, re.IGNORECASE))
            
            # Um item estruturado real DEVE ter conteúdo substancial após o marcador (ex: "I. O princípio...", não apenas "V." isolado)
            is_current_item = (
                not is_prev_incomplete 
                and bool(re.match(r"^(?:I|II|III|IV|V|VI|VII|VIII|IX|X|\d{1,2})\.\s+[A-Za-z\u00C0-\u00DC0-9\"\(]{2,}|\(\s*_{1,4}\s*\)\s+[A-Za-z]|Art\.\s*\d+|§\s*\d+|\*\*QUADRO|\*\*Coluna|###", line))
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

    return result.strip()
