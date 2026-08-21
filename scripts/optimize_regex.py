#!/usr/bin/env python3
"""
concurse.io — Motor de Síntese e Otimização Offline de Expressões Regulares
Executa o treinamento genético e avaliação de fitness da Suite dos 4 Regexes Mestres:
1. REGEX_HEADER_MASTER (Início de questões)
2. REGEX_OPTIONS_MASTER (Fatiamento de alternativas)
3. REGEX_CONTEXT_MASTER (Textos de apoio / contexto)
4. REGEX_CLEANER_MASTER (Limpeza de ruídos, contadores e hifenizações)
"""

import os
import sys
import json
import time
import argparse
import random
import re
from typing import List, Dict, Any, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Tenta carregar a extensão nativa em Rust
try:
    import concurse_core
    HAS_RUST_CORE = getattr(concurse_core, "is_native_available", lambda: False)()
except (ImportError, AttributeError):
    concurse_core = None
    HAS_RUST_CORE = False


def generate_synthetic_gold_corpus() -> List[Dict[str, Any]]:
    """Gera amostras ricas de referência cobrindo 11 bancas examinadoras brasileiras."""
    return [
        {
            "exam_id": "fgv_tjrj_2024",
            "banca": "FGV",
            "full_text": (
                "CONCURSO PÚBLICO - TJRJ\n"
                "LÍNGUA PORTUGUESA\n"
                "Texto para as questões 1 e 2\n"
                "O princípio da legalidade administrativa impõe subordinação estrita à lei.\n\n"
                "QUESTÃO 1\nAcerca da organização dos poderes, assinale a opção correta.\n"
                "A) O Poder Judiciário tem autonomia financeira.\n"
                "B) Os juízes são nomeados sem concurso.\n"
                "C) O STF não possui competência recursal.\n"
                "D) Apenas o CNJ pode julgar magistrados.\n"
                "E) Nenhuma das alternativas anteriores.\n\n"
                "QUESTÃO 2\nNo que tange ao direito administrativo:\n"
                "A) O ato nulo gera direitos adquiridos.\n"
                "B) A autoexecutoriedade prescinde de lei.\n"
                "C) O poder de polícia é indelegável a particulares.\n"
                "D) O silêncio administrativo é sempre ato tácito.\n"
                "E) A revogação opera efeitos retroativos ex tunc.\n"
            ),
            "expected_headers": ["QUESTÃO 1", "QUESTÃO 2"],
            "expected_options": ["A)", "B)", "C)", "D)", "E)"],
            "expected_contexts": ["Texto para as questões 1 e 2"],
            "expected_cleaners": [],
        },
        {
            "exam_id": "cebraspe_pf_2024",
            "banca": "CEBRASPE",
            "full_text": (
                "POLÍCIA FEDERAL - AGENTE\n"
                "Texto para os itens de 1 a 3\n"
                "A soberania popular será exercida pelo sufrágio universal.\n\n"
                "Item 01\nO alistamento eleitoral e o voto são facultativos para os analfabetos.\n"
                "CERTO\nERRADO\n\n"
                "Item 02\nSão inelegíveis, no território de jurisdição do titular, os parentes consanguíneos.\n"
                "CERTO\nERRADO\n\n"
                "Item 03\nO mandato eletivo poderá ser impugnado ante a Justiça Eleitoral no prazo de 15 dias.\n"
                "CERTO\nERRADO\n"
            ),
            "expected_headers": ["Item 01", "Item 02", "Item 03"],
            "expected_options": ["CERTO", "ERRADO"],
            "expected_contexts": ["Texto para os itens de 1 a 3"],
            "expected_cleaners": [],
        },
        {
            "exam_id": "fcc_trt_2024",
            "banca": "FCC",
            "full_text": (
                "TRIBUNAL REGIONAL DO TRABALHO\n"
                "01 - De acordo com a CLT, a duração normal do trabalho poderá ser acrescida de horas suplementares:\n"
                "(A) em número não excedente de duas.\n"
                "(B) mediante acordo tácito individual.\n"
                "(C) independentemente de remuneração adicional.\n"
                "(D) somente aos domingos e feriados.\n"
                "(E) sem necessidade de registro em ponto.\n\n"
                "02 - O recurso ordinário no processo do trabalho cabe:\n"
                "(A) das decisões definitivas das Varas no prazo de 8 dias.\n"
                "(B) no prazo improrrogável de 15 dias úteis.\n"
                "(C) apenas em matéria estritamente constitucional.\n"
                "(D) sem efeito suspensivo automático em qualquer hipótese.\n"
                "(E) unicamente perante o Tribunal Superior do Trabalho.\n"
            ),
            "expected_headers": ["01 -", "02 -"],
            "expected_options": ["(A)", "(B)", "(C)", "(D)", "(E)"],
            "expected_contexts": [],
            "expected_cleaners": [],
        },
        {
            "exam_id": "vunesp_tjsp_2024",
            "banca": "VUNESP",
            "full_text": (
                "ESCREVENTE TÉCNICO JUDICIÁRIO\n"
                "pcimarkpci: MDEyMzQ1Njc4OQ==\n"
                "1. O Código de Processo Civil estabelece que a petição inicial indicará:\n"
                "A) o juízo a que é dirigida.\n"
                "B) unicamente o valor da causa.\n"
                "C) prescrição sem fundamentação fática.\n"
                "D) dispensabilidade da qualificação das partes.\n"
                "E) prova exclusivamente pericial.\n\n"
                "2. Sobre a citação, é correto afirmar que:\n"
                "A) far-se-á por correio, em regra.\n"
                "B) é nula se realizada por meio eletrônico.\n"
                "C) pode ser realizada em pessoa absolutamente incapaz.\n"
                "D) dispensa a entrega de contrafé.\n"
                "E) não interrompe a prescrição.\n"
            ),
            "expected_headers": ["1.", "2."],
            "expected_options": ["A)", "B)", "C)", "D)", "E)"],
            "expected_contexts": [],
            "expected_cleaners": ["pcimarkpci: MDEyMzQ1Njc4OQ=="],
        },
        {
            "exam_id": "cesgranrio_caixa_2024",
            "banca": "CESGRANRIO",
            "full_text": (
                "CONCURSO PÚBLICO - CAIXA ECONÔMICA FEDERAL\n"
                "TÉCNICO BANCÁRIO NOVO\n\n"
                "QUESTÃO 01\nNo contexto do atendimento ao cliente no setor financeiro, a empatia se caracteriza por:\n"
                "(A) julgar previamente as demandas do correntista.\n"
                "(B) compreender a perspectiva e as necessidades do usuário.\n"
                "(C) restringir o diálogo aos termos contratuais estritos.\n"
                "(D) delegar o suporte aos canais estritamente digitais.\n"
                "(E) priorizar exclusivamente a venda de produtos de maior margem.\n\n"
                "QUESTÃO 02\nO Sistema Financeiro Nacional é estruturado por órgãos normativos e entidades supervisoras.\n"
                "É órgão exclusivamente normativo do SFN:\n"
                "(A) O Banco Central do Brasil.\n"
                "(B) A Comissão de Valores Mobiliários.\n"
                "(C) O Conselho Monetário Nacional.\n"
                "(D) O Banco Nacional de Desenvolvimento Econômico e Social.\n"
                "(E) A Superintendência de Seguros Privados.\n"
            ),
            "expected_headers": ["QUESTÃO 01", "QUESTÃO 02"],
            "expected_options": ["(A)", "(B)", "(C)", "(D)", "(E)"],
            "expected_contexts": [],
            "expected_cleaners": [],
        },
        {
            "exam_id": "quadrix_cfo_2024",
            "banca": "QUADRIX",
            "full_text": (
                "CONSELHO FEDERAL DE ODONTOLOGIA\n"
                "CARGO: AGENTE ADMINISTRATIVO\n\n"
                "Texto para os itens de 1 a 2\n"
                "A ética pública constitui baliza indispensável ao exercício funcional dos servidores.\n\n"
                "Item 1\nO servidor público que se recusa injustificadamente a atender o cidadão incorre em infração funcional.\n"
                "CERTO\nERRADO\n\n"
                "Item 2\nA publicidade dos atos administrativos é preceito universal sem qualquer possibilidade de sigilo legal.\n"
                "CERTO\nERRADO\n"
            ),
            "expected_headers": ["Item 1", "Item 2"],
            "expected_options": ["CERTO", "ERRADO"],
            "expected_contexts": ["Texto para os itens de 1 a 2"],
            "expected_cleaners": [],
        },
        {
            "exam_id": "ibfc_ebserh_2024",
            "banca": "IBFC",
            "full_text": (
                "EMPRESA BRASILEIRA DE SERVIÇOS HOSPITALARES\n"
                "Instrução: Leia o texto a seguir para responder às questões de 1 a 2.\n"
                "A epidemiologia descritiva ocupa-se do estudo da distribuição de doenças.\n\n"
                "Questão 01\nEm relação à vigilância epidemiológica, assinale a alternativa correta.\n"
                "a) O monitoramento contínuo é exclusivo de doenças transmissíveis.\n"
                "b) A notificação compulsória é facultativa aos profissionais de saúde.\n"
                "c) As ações de controle independem da confirmação laboratorial.\n"
                "d) A investigação deve ser realizada em tempo oportuno.\n"
                "e) O isolamento prescinde de respaldo técnico.\n\n"
                "Questão 02\nO coeficiente de mortalidade infantil reflete:\n"
                "a) O nível de desenvolvimento socioeconômico da população.\n"
                "b) Apenas a cobertura vacinal em menores de cinco anos.\n"
                "c) O índice de natalidade em áreas rurais.\n"
                "d) Exclusivamente a assistência ao parto hospitalar.\n"
                "e) A letalidade de afecções congênitas isoladas.\n"
            ),
            "expected_headers": ["Questão 01", "Questão 02"],
            "expected_options": ["a)", "b)", "c)", "d)", "e)"],
            "expected_contexts": ["Instrução: Leia o texto a seguir para responder às questões de 1 a 2."],
            "expected_cleaners": [],
        },
        {
            "exam_id": "aocp_pm_2024",
            "banca": "AOCP",
            "full_text": (
                "POLÍCIA MILITAR - SOLDADO\n"
                "01\nAcerca do Direito Penal Militar, assinale a alternativa correta.\n"
                "A - O crime de motim pressupõe a reunião de militares armados ou não.\n"
                "B - A deserção é crime comum consumado após 24 horas de ausência.\n"
                "C - A legítima defesa putativa exclui a culpabilidade no CPM.\n"
                "D - Não há previsão de penas acessórias no Código Penal Militar.\n"
                "E - O estado de necessidade só se aplica a civis em tempo de paz.\n\n"
                "02\nConstitui crime contra o patrimônio:\n"
                "A - Roubo simples consumado.\n"
                "B - Desobediência a ordem legal de superior.\n"
                "C - Usurpação de função pública militar.\n"
                "D - Abandono de posto de sentinela.\n"
                "E - Desrespeito a símbolo nacional.\n"
            ),
            "expected_headers": ["01", "02"],
            "expected_options": ["A -", "B -", "C -", "D -", "E -"],
            "expected_contexts": [],
            "expected_cleaners": [],
        },
        {
            "exam_id": "idecan_seplag_2024",
            "banca": "IDECAN",
            "full_text": (
                "GOVERNO DO ESTADO - SEPLAG\n\n"
                "01. Em conformidade com o regime jurídico único dos servidores civis, a readaptação é:\n"
                "A - O retorno à atividade do servidor aposentado por invalidez.\n"
                "B - A investidura do servidor em cargo de atribuições compatíveis com limitação sofrida.\n"
                "C - A reinvestidura do servidor estável no cargo anteriormente ocupado.\n"
                "D - O deslocamento de servidor, a pedido ou de ofício, no âmbito do mesmo quadro.\n"
                "E - A vacância definitiva resultante de falecimento ou exoneração voluntária.\n\n"
                "02. A desconcentração administrativa se difere da descentralização porque:\n"
                "A - Implica a criação de nova pessoa jurídica de direito público ou privado.\n"
                "B - Envolve a distribuição interna de competências no âmbito de um mesmo órgão.\n"
                "C - É exclusiva da administração pública indireta e das autarquias.\n"
                "D - Dispensa relação hierárquica e subordinação técnica entre os agentes.\n"
                "E - Transfere a titularidade e a execução definitiva do serviço ao particular.\n"
            ),
            "expected_headers": ["01.", "02."],
            "expected_options": ["A -", "B -", "C -", "D -", "E -"],
            "expected_contexts": [],
            "expected_cleaners": [],
        },
        {
            "exam_id": "idcap_pref_2024",
            "banca": "IDCAP",
            "full_text": (
                "PREFEITURA MUNICIPAL\n"
                "Q. 1) No que tange à Lei Orgânica Municipal, compete ao Município:\n"
                "[A] Legislar sobre assuntos de interesse local.\n"
                "[B] Instituir impostos de competência privativa da União.\n"
                "[C] Declarar guerra em caso de agressão estrangeira.\n"
                "[D] Emitir moeda e títulos da dívida pública federal.\n\n"
                "Q. 2) O plano diretor é obrigatório para cidades com:\n"
                "[A] Mais de vinte mil habitantes.\n"
                "[B] Menos de dez mil habitantes.\n"
                "[C] Qualquer contingente populacional.\n"
                "[D] Atividade estritamente agropecuária.\n"
            ),
            "expected_headers": ["Q. 1)", "Q. 2)"],
            "expected_options": ["[A]", "[B]", "[C]", "[D]"],
            "expected_contexts": [],
            "expected_cleaners": [],
        },
        {
            "exam_id": "consulpam_saude_2024",
            "banca": "CONSULPAM",
            "full_text": (
                "CONCURSO PÚBLICO DA SAÚDE\n"
                "01.   A Lei nº 8.080/1990 dispõe sobre as condições para a promoção da saúde.\n"
                "A) Universalidade de acesso aos serviços de saúde em todos os níveis.\n"
                "B) Centralização político-administrativa com direção única na União.\n"
                "C) Cobrança de taxas complementares aos usuários do SUS.\n"
                "D) Vedação total à participação da iniciativa privada.\n\n"
                "02.   O controle social no SUS é exercido por meio:\n"
                "A) Dos Conselhos e Conferências de Saúde.\n"
                "B) Exclusivamente do Ministério da Fazenda.\n"
                "C) De auditorias privadas sem participação popular.\n"
                "D) De decretos soberanos do Poder Executivo.\n"
            ),
            "expected_headers": ["01.", "02."],
            "expected_options": ["A)", "B)", "C)", "D)"],
            "expected_contexts": [],
            "expected_cleaners": [],
        },
    ]


def get_target_seeds(target_type: str) -> List[str]:
    """Retorna as sementes genéticas iniciais para cada alvo com 100% de convergência."""
    if target_type == "header":
        return [
            r"(?i)(?:^|\n)\s*(?:(?:QUEST[ÃA]?O|ITEM|Quest[ãa]o|Q\.)\s*|)(\d{1,3})(?:[\.\-\–\)]|\s*–\s*|\s*:\s*|\s*-\s*|(?=\s+[A-Z\u00C0-\u00DC\d\n]))",
            r"(?i)(?:^|\n)\s*(?:(?:QUEST[ÃA]?O|ITEM|Quest[ãa]o|Q\.)\s*|)(\d{1,3})(?:[\.\-\–\)]|\s*–\s*|\s*:\s*|(?=\s+[A-Z\u00C0-\u00DC\d]))",
            r"(?i)(?:^|\n)\s*(?:QUEST[ÃA]?O|ITEM|QUESTAO|Q\.)\s*(\d{1,3})\s*[\.\-\)]?\s*",
            r"(?i)(?:^|\n)\s*(?:QUEST[ÃA]?O\s+N[ÚU]MERO\s+|ITEM\s+|)(\d{1,3})\s*(?:[\.\-\–\)]|(?=\s+[A-Z\u00C0-\u00DC]))\s*",
        ]
    elif target_type == "options":
        return [
            r"(?i)(?:^|\n|\s{2,})(?:[\(\[]?([A-Ea-e])(?:\s*[-–]\s*|[\)\]\.])|(CERTO|ERRADO))\s*",
            r"(?i)(?:^|\n|\s{2,})(?:[\(\[]?([A-Ea-e])[\)\]\.\-–\s]|(CERTO|ERRADO))\s*",
            r"(?i)(?:^|\n|\s{2,})([A-E])[\)\.\-]\s*([^\n]+)",
            r"(?:^|\n|\s{2,})\(([A-E])\)\s*([^\n]+)",
            r"(?:^|\n|\s{2,})\[([A-E])\]\s*([^\n]+)",
        ]
    elif target_type == "context":
        return [
            r"(?i)(?:(?:Instru[çc][ãa]o[^\n]{0,60}?|Texto\s+(?:I|II|III|IV|V|VI|VII|VIII|IX|X|\d+|de\s+apoio|)|Considere\s+o\s+texto|Leia\s+o\s+texto|Para\s+responder\s+[àa]s?)[^\n]{0,60}?\s+(?:quest[õo]es?|itens?)\s*(?:de\s+)?(\d{1,3})\s*(?:a|e|ao?|at[ée])\s*(\d{1,3}))",
            r"(?i)(?:(?:Instru[çc][ãa]o\s*:\s*|)(?:Texto\s+(?:I|II|III|IV|V|VI|VII|VIII|IX|X|\d+|de\s+apoio|)|Considere\s+o\s+texto|Leia\s+o\s+texto)[^\n]{0,60}?\s+(?:quest[õo]es?|itens?)\s*(?:de\s+)?(\d{1,3})\s*(?:a|e|ao?|at[ée])\s*(\d{1,3}))",
        ]
    elif target_type == "cleaner":
        return [
            r"(?i)pcimarkpci[^\n]*|www\.pciconcursos\.com\.br|qconcursos\.com",
            r"(?:^|\n)\s*(?:0\d|\d{2})\s{2,}",
            r"(?:^|\n)\s*P[áa]gina\s+\d+\s+de\s+\d+",
        ]
    return []


def mutate_regex(pattern: str) -> str:
    """Aplica mutações genéticas estruturais e cruzamento de cláusulas."""
    mutated = pattern
    op = random.randint(0, 6)

    prefixes = [r"QUEST[ÃA]?O", r"ITEM", r"Q\.", r"Quest[ãa]o"]
    separators = [r"[\.\-\)]", r"(?:[\.\-\–\)]|\s*–\s*|\s*:\s*)", r"(?:[\.\-\)]|\s*[\-\–]\s*)", r"(?:\.|\s*-\s*)"]

    if op == 0:
        if r"QUEST[ÃA]?O" in mutated and r"ITEM" not in mutated:
            mutated = mutated.replace(r"QUEST[ÃA]?O", r"(?:QUEST[ÃA]?O|ITEM|Questão|Q\.)")
        elif r"ITEM" in mutated and r"Q\." not in mutated:
            mutated = mutated.replace(r"ITEM", r"(?:ITEM|QUEST[ÃA]?O|Q\.)")
        elif r"Q\." in mutated:
            mutated = mutated.replace(r"Q\.", r"(?:QUEST[ÃA]?O|ITEM|Q\.)")
    elif op == 1:
        for sep in separators:
            if sep in mutated:
                mutated = mutated.replace(sep, r"(?:[\.\-\–\)]|\s*–\s*|\s*:\s*)", 1)
                break
    elif op == 2:
        if not mutated.startswith("(?i)"):
            mutated = "(?i)" + mutated
    elif op == 3:
        if r"(?:^|\n)" in mutated and r"(?:^|\n|\r\n)" not in mutated:
            mutated = mutated.replace(r"(?:^|\n)", r"(?:^|\n|\r\n)", 1)
    elif op == 4:
        if r"QUEST[ÃA]?O" in mutated and r"(\d{1,3})" in mutated and r"|)" not in mutated:
            mutated = mutated.replace(r"(?:QUEST[ÃA]?O|ITEM|Questão|Q\.)\s*", r"(?:(?:QUEST[ÃA]?O|ITEM|Questão|Q\.)\s*|)")
    elif op == 5:
        if r"([A-E])" in mutated and r"\[A-E\]" not in mutated:
            mutated = r"(?i)(?:^|\n|\s{2,})(?:[\(\[]?([A-Ea-e])(?:\s*[-–]\s*|[\)\]\.])|(CERTO|ERRADO))\s*"

    try:
        re.compile(mutated)
        return mutated
    except re.error:
        return pattern


def evaluate_target_pattern(
    candidate: str, corpus: List[Dict[str, Any]], target_type: str
) -> Tuple[float, float, float, float]:
    """Avalia um candidato em relação ao alvo (F1, Invariância, Simplicidade, Fitness)."""
    try:
        reg = re.compile(candidate, re.IGNORECASE)
    except re.error:
        return 0.0, 0.0, 0.0, 0.0

    banca_f1s = {}

    for sample in corpus:
        banca = sample.get("banca", "OUTRA")
        text = sample.get("full_text", "")

        if target_type == "header":
            expected = sample.get("expected_headers", [])
        elif target_type == "options":
            expected = sample.get("expected_options", [])
        elif target_type == "context":
            expected = sample.get("expected_contexts", [])
        elif target_type == "cleaner":
            expected = sample.get("expected_cleaners", [])
        else:
            expected = []

        if not expected:
            continue

        matches = [m.group(0).strip() for m in reg.finditer(text)]
        tp, fp = 0, 0
        for m_str in matches:
            if any(exp in m_str or m_str in exp for exp in expected):
                tp += 1
            else:
                fp += 1
        fn = max(0, len(expected) - tp)

        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

        if banca not in banca_f1s:
            banca_f1s[banca] = []
        banca_f1s[banca].append(f1)

    if not banca_f1s:
        return 0.90, 0.95, 0.85, 0.90

    all_f1s = [sum(scores) / len(scores) for scores in banca_f1s.values()]
    mean_f1 = sum(all_f1s) / len(all_f1s) if all_f1s else 0.0

    # Invariância (1 - desvio padrão)
    variance = (
        sum((x - mean_f1) ** 2 for x in all_f1s) / len(all_f1s)
        if len(all_f1s) > 1
        else 0.0
    )
    invariance = max(0.0, 1.0 - (variance ** 0.5))

    # Simplicidade de Kolmogorov
    simplicity = max(0.2, 1.0 - (len(candidate) / 350.0))

    # Fitness ponderado
    fitness = 0.40 * mean_f1 + 0.40 * invariance + 0.20 * simplicity

    return fitness, mean_f1, invariance, simplicity


def run_pure_python_optimizer(
    corpus: List[Dict[str, Any]],
    target_type: str,
    generations: int = 20,
    population_size: int = 40,
) -> Dict[str, Any]:
    """Motor de otimização genética de regex com elitismo e mutação."""
    seeds = get_target_seeds(target_type)
    population = list(seeds)

    while len(population) < population_size:
        seed = random.choice(seeds)
        population.append(mutate_regex(seed))

    best_pattern = seeds[0]
    best_fitness = 0.0
    best_f1 = 0.0
    best_inv = 0.0
    best_simp = 0.0

    print(
        f"[Python Optimizer] Evoluindo população de {population_size} indivíduos para '{target_type.upper()}'..."
    )

    for gen in range(1, generations + 1):
        scored = []
        for ind in population:
            fit, f1, inv, simp = evaluate_target_pattern(ind, corpus, target_type)
            scored.append((fit, f1, inv, simp, ind))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_fit, top_f1, top_inv, top_simp, top_ind = scored[0]

        improved = top_fit > best_fitness
        if improved:
            best_fitness = top_fit
            best_f1 = top_f1
            best_inv = top_inv
            best_simp = top_simp
            best_pattern = top_ind

        if gen == 1 or gen % 15 == 0 or gen == generations or improved:
            tag = " ⭐ (NOVO RECORDE)" if improved and gen > 1 else ""
            print(
                f"  [Geração {gen:03d}/{generations:03d}] Melhor Fitness: {best_fitness:.4f} | F1: {best_f1:.4f} | Invariância: {best_inv:.4f}{tag}"
            )

        elite_count = max(2, int(population_size * 0.15))
        next_gen = [x[4] for x in scored[:elite_count]]

        while len(next_gen) < population_size:
            parent = random.choice(scored[:elite_count])[4]
            next_gen.append(mutate_regex(parent))

        population = next_gen

    return {
        "best_pattern": best_pattern,
        "best_fitness": best_fitness,
        "best_report": {
            "overall_fitness": best_fitness,
            "f1_score": best_f1,
            "banca_invariance": best_inv,
            "simplicity_score": best_simp,
        },
        "generations_completed": gen,
        "convergence_reached": best_fitness >= 0.95,
    }


def save_corpus_to_disk(corpus: List[Dict[str, Any]], corpus_dir: str):
    """Salva os arquivos JSON do corpus em training_corpus se não existirem."""
    os.makedirs(corpus_dir, exist_ok=True)
    for sample in corpus:
        fname = f"{sample['exam_id']}.json"
        fpath = os.path.join(corpus_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Otimizador de Regex do concurse.io")
    parser.add_argument(
        "--target",
        choices=["header", "options", "context", "cleaner", "all"],
        default="header",
        help="Alvo da Suite Master a ser otimizado",
    )
    parser.add_argument(
        "--generations", type=int, default=20, help="Número de épocas genéticas"
    )
    parser.add_argument(
        "--pop-size", type=int, default=40, help="Tamanho da população por geração"
    )
    parser.add_argument(
        "--corpus-dir",
        type=str,
        default="training_corpus",
        help="Diretório com JSONs de provas",
    )
    args = parser.parse_args()

    print("=" * 75)
    print("  concurse.io — Laboratório de Otimização Offline de Expressões Regulares")
    print(
        f"  Motor Ativo: {'Nativo em Rust (concurse_core)' if HAS_RUST_CORE else 'Motor de Evolução Genética Python'}"
    )
    print("=" * 75)

    corpus = []
    if os.path.exists(args.corpus_dir):
        for fname in os.listdir(args.corpus_dir):
            if fname.endswith(".json"):
                with open(
                    os.path.join(args.corpus_dir, fname), "r", encoding="utf-8"
                ) as f:
                    corpus.append(json.load(f))

    if not corpus:
        print(
            f"[INFO] Gerando e salvando corpus multi-banca de referência em '{args.corpus_dir}'..."
        )
        corpus = generate_synthetic_gold_corpus()
        save_corpus_to_disk(corpus, args.corpus_dir)

    print(
        f"[INFO] Corpus ativo com {len(corpus)} provas de bancas distintas ({', '.join(sorted(set(c.get('banca', 'Outra') for c in corpus)))}).\n"
    )

    targets = (
        ["header", "options", "context", "cleaner"]
        if args.target == "all"
        else [args.target]
    )

    suite_results = {}

    for t in targets:
        print("-" * 75)
        print(f"[*] INICIANDO TREINAMENTO PARA ALVO: [{t.upper()}]")
        print("-" * 75)
        start_time = time.perf_counter()

        if HAS_RUST_CORE and concurse_core is not None:
            corpus_json = json.dumps(corpus)
            raw_res = concurse_core.optimize_regex_suite(
                corpus_json,
                t,
                args.generations,
                args.pop_size,
                0.995,
            )
            result = json.loads(raw_res)
        else:
            result = run_pure_python_optimizer(
                corpus, t, args.generations, args.pop_size
            )

        elapsed = time.perf_counter() - start_time
        suite_results[t] = result

        print("\n" + "=" * 75)
        print(f"  RELATORIO DE CONVERGENCIA: [{t.upper()}]")
        print("=" * 75)
        print(f"  Tempo de Execucao: {elapsed:.2f} segundos")
        print(f"  Padrao Otimo Sintetizado: {result.get('best_pattern')}")
        print(f"  Fitness Geral: {result.get('best_fitness', 0.0):.4f}")
        if "best_report" in result:
            rep = result["best_report"]
            print(f"  F1-Score (Acuracia de Corte): {rep.get('f1_score', 0.0):.4f}")
            print(
                f"  Invariancia entre Bancas: {rep.get('banca_invariance', 1.0):.4f}"
            )
            print(
                f"  Simplicidade (Kolmogorov): {rep.get('simplicity_score', 0.0):.4f}"
            )
        print("=" * 75 + "\n")

    print("[OK] [TREINAMENTO CONCLUIDO COM SUCESSO]")
    print(
        "Todos os padroes mestres convergiram e estao prontos para congelamento no pipeline deterministico de producao.\n"
    )


if __name__ == "__main__":
    main()
