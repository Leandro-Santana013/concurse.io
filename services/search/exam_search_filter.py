"""
concurse.io — Filtro Exportável de Cards de Busca (Ano, Banca, Cargo, Órgão & Match Score)
==========================================================================================
Módulo 100% determinístico e autônomo para:
1. Extração de Entidades por Regex (Ano, Banca, Órgão, Cargo, Escolaridade, Local/UF).
2. Cálculo do Match Score (0 a 100%) para ranqueamento dos cards.
3. Padronização e Higienização de Títulos de Provas ([ANO] ÓRGÃO - CARGO).
4. Filtragem e Ordenação de Resultados de Busca.
"""

import re
from typing import List, Dict, Tuple, Optional, Any


DEFAULT_SEARCH_RESULT_LIMIT = 15


# =============================================================================
# 1. CATÁLOGO DE REGEX DETERMINÍSTICO (BANCAS, ÓRGÃOS, CARGOS, UFS, CIDADES)
# =============================================================================

BANCAS_MAP = [
    ("CEBRASPE", r"\b(?:cebraspe|cespe(?:\s*/\s*unb)?|unb)\b"),
    ("FGV", r"\b(?:fgv|funda[çc][ãa]o\s+get[úu]lio\s+vargas)\b"),
    ("FCC", r"\b(?:fcc|funda[çc][ãa]o\s+carlos\s+chagas)\b"),
    ("VUNESP", r"\b(?:vunesp|funda[çc][ãa]o\s+vunesp)\b"),
    ("CESGRANRIO", r"\b(?:cesgranrio|funda[çc][ãa]o\s+cesgranrio)\b"),
    ("IBAM", r"\b(?:ibam|instituto\s+brasileiro\s+de\s+administra[çc][ãa]o\s+municipal)\b"),
    ("IDCAP", r"\b(?:idcap|idecap|id\s*cap)\b"),
    ("IDECAN", r"\b(?:idecan|instituto\s+idecan)\b"),
    ("AOCP", r"\b(?:instituto\s+aocp|aocp|assessoria\s+aocp)\b"),
    ("QUADRIX", r"\b(?:quadrix|instituto\s+quadrix)\b"),
    ("IBFC", r"\b(?:ibfc|instituto\s+brasileiro\s+de\s+forma[çc][ãa]o)\b"),
    ("SELECON", r"\b(?:selecon|instituto\s+selecon)\b"),
    ("CONSULPLAN", r"\b(?:instituto\s+consulplan|consulplan)\b"),
    ("CONSULPAM", r"\b(?:consulpam|instituto\s+consulpam)\b"),
    ("FUNDATEC", r"\b(?:fundatec|funda[çc][ãa]o\s+fundatec)\b"),
    ("FEPESE", r"\b(?:faepesul|fepese)\b"),
    ("FUNDEP", r"\b(?:fundep|funda[çc][ãa]o\s+fundep)\b"),
    ("INSTITUTO MAIS", r"\b(?:instituto\s+mais)\b"),
    ("AVALIA", r"\b(?:instituto\s+avalia|avalia)\b"),
    ("COPEVE", r"\b(?:copeve(?:\s*/\s*ufal)?|ufal)\b"),
    ("FUMARC", r"\b(?:fumarc)\b"),
    ("IBADE", r"\b(?:ibade)\b"),
    ("IADES", r"\b(?:iades)\b"),
    ("LEGALLE", r"\b(?:legalle(?:\s+concursos)?)\b"),
    ("FAURGS", r"\b(?:faurgs)\b"),
    ("CPCON", r"\b(?:cpcon(?:\s*/\s*uepb)?)\b"),
    ("CS-UFG", r"\b(?:cs[- ]ufg|centro\s+de\s+sele[çc][ãa]o\s+ufg)\b"),
    ("COMPERVE", r"\b(?:comperve(?:\s*/\s*ufrn)?)\b"),
    ("NUCEPE", r"\b(?:nucepe(?:\s*/\s*uespi)?)\b"),
    ("FUNRIO", r"\b(?:funrio)\b"),
    ("FAPEC", r"\b(?:fapec(?:\s*/\s*ufms)?)\b"),
    ("MS CONCURSOS", r"\b(?:ms\s+concursos)\b")
]

ORGAOS_MAP = [
    ("PETROBRAS", r"\b(?:petrobras|petrobr[áa]s)\b"),
    ("TRANSPETRO", r"\b(?:transpetro)\b"),
    ("CAIXA", r"\b(?:caixa\s+econ[ôo]mica(?:\s+federal)?|cef|caixa)\b"),
    ("BANCO DO BRASIL", r"\b(?:banco\s+do\s+brasil|bb)\b"),
    ("CORREIOS", r"\b(?:correios|ect)\b"),
    ("BNDES", r"\b(?:bndes)\b"),
    ("DATAPREV", r"\b(?:dataprev)\b"),
    ("SERPRO", r"\b(?:serpro)\b"),
    ("EMBRAPA", r"\b(?:embrapa)\b"),
    ("OGMO", r"\b(?:ogmo(?:\s*/\s*santos)?)\b"),
    ("RECEITA FEDERAL", r"\b(?:receita\s+federal|rfb)\b"),
    ("INSS", r"\b(?:inss|instituto\s+nacional\s+do\s+seguro\s+social)\b"),
    ("IBGE", r"\b(?:ibge)\b"),
    ("POLÍCIA FEDERAL", r"\b(?:pol[íi]cia\s+federal|pf|dpf)\b"),
    ("POLÍCIA RODOVIÁRIA FEDERAL", r"\b(?:pol[íi]cia\s+rodovi[áa]ria(?:\s+federal)?|prf|dprf)\b"),
    ("POLÍCIA CIVIL", r"\b(?:pol[íi]cia\s+civil|pc[- ]?[a-z]{2})\b"),
    ("POLÍCIA MILITAR", r"\b(?:pol[íi]cia\s+militar|pm[- ]?[a-z]{2})\b"),
    ("POLÍCIA PENAL", r"\b(?:pol[íi]cia\s+penal|depen)\b"),
    ("CORPO DE BOMBEIROS", r"\b(?:corpo\s+de\s+bombeiros?|bombeiros?|cbm[- ]?[a-z]{2})\b"),
    ("GUARDA MUNICIPAL", r"\b(?:guarda(?:\s+municipal|\s+civil|\s+metropolitana)?|gcm)\b"),
    ("STF", r"\b(?:stf|supremo\s+tribunal\s+federal)\b"),
    ("STJ", r"\b(?:stj|superior\s+tribunal\s+de\s+justi[çc]a)\b"),
    ("TST", r"\b(?:tst|tribunal\s+superior\s+do\s+trabalho)\b"),
    ("TSE", r"\b(?:tse|tribunal\s+superior\s+eleitoral)\b"),
    ("TCU", r"\b(?:tcu|tribunal\s+de\s+contas\s+da\s+uni[ãa]o)\b"),
    ("CGU", r"\b(?:cgu|controladoria[- ]geral\s+da\s+uni[ãa]o)\b"),
    ("TJ", r"\b(?:tj[- ]?[a-z]{2}|tribunal\s+de\s+justi[çc]a)\b"),
    ("TRT", r"\b(?:trt[- ]?\d{1,2}|tribunal\s+regional\s+do\s+trabalho)\b"),
    ("TRE", r"\b(?:tre[- ]?[a-z]{2}|tribunal\s+regional\s+eleitoral)\b"),
    ("TRF", r"\b(?:trf[- ]?\d{1,2}|tribunal\s+regional\s+federal)\b"),
    ("MPU", r"\b(?:mpu|minist[ée]rio\s+p[úu]blico\s+da\s+uni[ãa]o)\b"),
    ("MPE", r"\b(?:mp[- ]?[a-z]{2}|minist[ée]rio\s+p[úu]blico\s+estadual)\b"),
    ("DPU", r"\b(?:dpu|defensoria\s+p[úu]blica\s+da\s+uni[ãa]o)\b"),
    ("DPE", r"\b(?:dpe[- ]?[a-z]{2}|defensoria\s+p[úu]blica)\b"),
    ("ANVISA", r"\b(?:anvisa)\b"),
    ("ANATEL", r"\b(?:anatel)\b"),
    ("ANEEL", r"\b(?:aneel)\b"),
    ("ANP", r"\b(?:anp)\b"),
    ("BACEN", r"\b(?:banco\s+central(?:\s+do\s+brasil)?|bacen|bcb)\b"),
    ("CVM", r"\b(?:cvm)\b"),
    ("SPPREV", r"\b(?:spprev)\b"),
    ("SAAE", r"\b(?:saae(?:\s+aracruz)?)\b"),
    ("MARINHA", r"\b(?:marinha(?:\s+do\s+brasil)?)\b"),
    ("EXÉRCITO", r"\b(?:ex[ée]rcito(?:\s+brasileiro)?)\b"),
    ("AERONÁUTICA", r"\b(?:aeron[áa]utica|fab)\b"),
    ("SENADO", r"\b(?:senado(?:\s+federal)?)\b"),
    ("CÂMARA DOS DEPUTADOS", r"\b(?:c[âa]mara\s+dos\s+deputados)\b"),
    ("ASSEMBLEIA LEGISLATIVA", r"\b(?:assembleia\s+legislativa|alesp|almg|alerj)\b"),
    ("PREFEITURA", r"\b(?:prefeitura(?:\s+municipal)?(?:\s+de\s+[a-z\u00C0-\u00DC\s]+)?)\b"),
    ("CÂMARA MUNICIPAL", r"\b(?:c[âa]mara\s+municipal(?:\s+de\s+[a-z\u00C0-\u00DC\s]+)?)\b"),
    ("GOVERNO DO ESTADO", r"\b(?:governo\s+do\s+estado(?:\s+d[eo]\s+[a-z\u00C0-\u00DC\s]+)?)\b")
]

CARGOS_MAP = [
    ("AUDITOR", r"\b(?:auditor(?:\s+fiscal|\s+de\s+controle|\s+federal|\s+tribut[áa]rio)?)\b"),
    ("ANALISTA", r"\b(?:analista(?:\s+judici[áa]rio|\s+administrativo|\s+de\s+ti|\s+em\s+tecnologia|\s+ambiental|\s+de\s+gest[ãa]o)?)\b"),
    ("TÉCNICO", r"\b(?:t[ée]cnico(?:\s+judici[áa]rio|\s+administrativo|\s+banc[áa]rio|\s+de\s+enfermagem|\s+em\s+ti|\s+de\s+opera[çc][õo]es)?)\b"),
    ("DELEGADO", r"\b(?:delegado(?:\s+de\s+pol[íi]cia)?)\b"),
    ("ESCRIVÃO", r"\b(?:escriv[ãa]o(?:\s+de\s+pol[íi]cia)?)\b"),
    ("INVESTIGADOR", r"\b(?:investigador(?:\s+de\s+pol[íi]cia)?|agente\s+de\s+pol[íi]cia)\b"),
    ("PERITO", r"\b(?:perito(?:\s+criminal|\s+m[ée]dico|\s+federal)?)\b"),
    ("PAPILOSCOPISTA", r"\b(?:papiloscopista)\b"),
    ("ADVOGADO", r"\b(?:advogado|procurador(?:\s+do\s+estado|\s+do\s+munic[íi]pio|\s+da\s+fazenda|\s+federal)?)\b"),
    ("JUIZ", r"\b(?:juiz(?:\s+do\s+trabalho|\s+federal|\s+de\s+direito)?|magistratura)\b"),
    ("PROMOTOR", r"\b(?:promotor(?:\s+de\s+justi[çc]a)?)\b"),
    ("MÉDICO", r"\b(?:m[ée]dico(?:\s+cl[íi]nico|\s+do\s+trabalho|\s+perito|\s+pediatra)?)\b"),
    ("ENFERMEIRO", r"\b(?:enfermeiro|enfermagem)\b"),
    ("PSICÓLOGO", r"\b(?:psic[óo]logo)\b"),
    ("FARMACÊUTICO", r"\b(?:farmac[êe]utico)\b"),
    ("ASSISTENTE SOCIAL", r"\b(?:assistente\s+social)\b"),
    ("DENTISTA", r"\b(?:dentista|odont[óo]logo)\b"),
    ("PROFESSOR", r"\b(?:professor(?:\s+de\s+[a-z\u00C0-\u00DC\s]+)?|docente)\b"),
    ("PEDAGOGO", r"\b(?:pedagogo|pedagogia)\b"),
    ("ENGENHEIRO", r"\b(?:engenheiro(?:\s+civil|\s+mec[âa]nico|\s+el[ée]trico|\s+de\s+petr[óo]leo|\s+de\s+software|\s+qu[íi]mico)?)\b"),
    ("ARQUITETO", r"\b(?:arquiteto)\b"),
    ("CAPATAZIA", r"\b(?:trabalhador\s+portu[áa]rio(?:\s+avulso)?|capatazia|estivador|arrumador|sintraport)\b"),
    ("AGENTE ADMINISTRATIVO", r"\b(?:agente\s+administrativo|assistente\s+administrativo|auxiliar\s+administrativo)\b"),
    ("MOTORISTA", r"\b(?:motorista(?:\s+de\s+ve[íi]culos\s+pesados)?)\b"),
    ("GUARDA", r"\b(?:guarda(?:\s+portu[áa]rio|\s+patrimonial|\s+civil)?)\b")
]

ESTADOS_UFS = [
    ("AC", r"\b(?:ac|acre)\b"), ("AL", r"\b(?:al|alagoas)\b"), ("AP", r"\b(?:ap|amap[áa])\b"),
    ("AM", r"\b(?:am|amazonas)\b"), ("BA", r"\b(?:ba|bahia)\b"), ("CE", r"\b(?:ce|cear[áa])\b"),
    ("DF", r"\b(?:df|distrito\s+federal|bras[íi]lia)\b"), ("ES", r"\b(?:es|esp[íi]rito\s+santo)\b"),
    ("GO", r"\b(?:go|goi[áa]s)\b"), ("MA", r"\b(?:ma|maranh[ãa]o)\b"), ("MT", r"\b(?:mt|mato\s+grosso)\b"),
    ("MS", r"\b(?:ms|mato\s+grosso\s+do\s+sul)\b"), ("MG", r"\b(?:mg|minas\s+gerais)\b"),
    ("PA", r"\b(?:pa|par[áa])\b"), ("PB", r"\b(?:pb|para[íi]ba)\b"), ("PR", r"\b(?:pr|paran[áa])\b"),
    ("PE", r"\b(?:pe|pernambuco)\b"), ("PI", r"\b(?:pi|piau[íi])\b"), ("RJ", r"\b(?:rj|rio\s+de\s+janeiro)\b"),
    ("RN", r"\b(?:rn|rio\s+grande\s+do\s+norte)\b"), ("RS", r"\b(?:rs|rio\s+grande\s+do\s+sul)\b"),
    ("RO", r"\b(?:ro|rond[ôo]nia)\b"), ("RR", r"\b(?:rr|roraima)\b"), ("SC", r"\b(?:sc|santa\s+catarina)\b"),
    ("SP", r"\b(?:sp|s[ãa]o\s+paulo)\b"), ("SE", r"\b(?:se|sergipe)\b"), ("TO", r"\b(?:to|tocantins)\b")
]

CIDADES_MAP = [
    ("SANTOS", r"\b(?:santos)\b"),
    ("LINHARES", r"\b(?:linhares)\b"),
    ("ARACRUZ", r"\b(?:aracruz)\b"),
    ("CAMPINAS", r"\b(?:campinas)\b"),
    ("NITERÓI", r"\b(?:niter[óo]i)\b"),
    ("GUARULHOS", r"\b(?:guarulhos)\b"),
    ("OSASCO", r"\b(?:osasco)\b"),
    ("LONDRINA", r"\b(?:londrina)\b"),
    ("MARINGÁ", r"\b(?:maring[áa])\b"),
    ("UBERLÂNDIA", r"\b(?:uberl[âa]ndia)\b")
]


# =============================================================================
# 2. MOTOR DETERMINÍSTICO DE NLP PARA QUERIES DE BUSCA
# =============================================================================

def interpret_search_query_deterministic(query: str) -> Dict[str, str]:
    """
    Desmembra a busca digitada pelo usuário em campos estruturados via Regex:
    - Ano (ex: 2024)
    - Banca (ex: CEBRASPE, FGV, FCC)
    - Órgão (ex: POLÍCIA FEDERAL, PETROBRAS, INSS)
    - Cargo (ex: AUDITOR, ANALISTA, DELEGADO)
    - Escolaridade (Superior, Médio, Fundamental)
    - Local / UF (ex: SP, RJ, DF)
    - Query Otimizada para Scrapers
    """
    query_clean = query.strip() if query else ""
    # Normalização de erros de digitação comuns em concursos (ex: potuario -> portuario)
    typos = [
        (r'\bpotuari[oa]s?\b', 'portuario'),
        (r'\bpotuaria\b', 'portuaria'),
        (r'\benfermegem\b', 'enfermagem'),
        (r'\bengenhara\b', 'engenharia'),
        (r'\badminstrativ[oa]\b', 'administrativo'),
        (r'\bpolcia\b', 'policia'),
        (r'\bagene\b', 'agente'),
        (r'\bconcurs\b', 'concurso'),
    ]
    query_corrected = query_clean
    for pat, repl in typos:
        query_corrected = re.sub(pat, repl, query_corrected, flags=re.IGNORECASE)

    query_lower = query_corrected.lower()
    
    data = {
        "orgao": "",
        "banca": "",
        "ano": "",
        "cargo": "",
        "escolaridade": "",
        "local": "",
        "query_otimizada": query_corrected
    }
    
    # 1. Identificar Ano (1990 - 2035)
    m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', query_clean)
    if m_ano:
        data["ano"] = m_ano.group(1)

    # 2. Identificar Banca
    for banca_name, pattern in BANCAS_MAP:
        if re.search(pattern, query_lower):
            data["banca"] = banca_name
            break

    # 3. Identificar Órgão / Instituição
    for orgao_name, pattern in ORGAOS_MAP:
        if re.search(pattern, query_lower):
            data["orgao"] = orgao_name
            break

    # 4. Identificar Cargo
    for cargo_name, pattern in CARGOS_MAP:
        if re.search(pattern, query_lower):
            data["cargo"] = cargo_name
            break

    # 5. Identificar Escolaridade / Nível
    if re.search(r'\b(?:n[íi]vel\s+superior|superior|gradua[çc][ãa]o)\b', query_lower):
        data["escolaridade"] = "Superior"
    elif re.search(r'\b(?:n[íi]vel\s+m[ée]dio|m[ée]dio|ensino\s+m[ée]dio)\b', query_lower):
        data["escolaridade"] = "Médio"
    elif re.search(r'\b(?:n[íi]vel\s+fundamental|fundamental)\b', query_lower):
        data["escolaridade"] = "Fundamental"

    # 6. Identificar Local / UF / Cidade
    detected_local = []
    for cidade_name, pattern in CIDADES_MAP:
        if re.search(pattern, query_lower):
            detected_local.append(cidade_name)
            break

    for uf_sigla, pattern in ESTADOS_UFS:
        if re.search(pattern, query_lower):
            if uf_sigla not in detected_local:
                detected_local.append(uf_sigla)
            break
            
    if detected_local:
        data["local"] = " / ".join(detected_local)

    # 7. Geração da Query Otimizada para Scrapers
    stop_words = {
        'prova', 'provas', 'concurso', 'concursos', 'gabarito', 'pdf', 'download',
        'de', 'do', 'da', 'dos', 'das', 'para', 'em', 'no', 'na', 'nos', 'nas',
        'com', 'e', 'a', 'o', 'as', 'os', 'edital', 'processo', 'seletivo', 'privado'
    }
    tokens = [t for t in re.findall(r'\b[\w\-/]+\b', query_clean) if t.lower() not in stop_words and len(t) > 1]
    
    query_parts = []
    if data["orgao"]:
        query_parts.append(data["orgao"])
    if data["cargo"] and data["cargo"] not in query_parts:
        query_parts.append(data["cargo"])
    if data["banca"] and data["banca"] not in query_parts:
        query_parts.append(data["banca"])
    if data["ano"] and data["ano"] not in query_parts:
        query_parts.append(data["ano"])
        
    for tok in tokens:
        if tok.upper() not in [p.upper() for p in query_parts]:
            query_parts.append(tok)
            
    data["query_otimizada"] = " ".join(query_parts) + " prova concurso pdf"
    return data


# =============================================================================
# 3. CÁLCULO DE MATCH SCORE DOS CARDS
# =============================================================================

def calculate_card_match_score(
    card_title: str,
    card_url: str,
    nlp_data: Dict[str, str],
    raw_query: str
) -> int:
    """
    Calcula o Score de Relevância (0 a 100%) de um card de prova comparando
    o título/URL com os metadados identificados (Ano, Banca, Órgão, Cargo).
    """
    text_to_check = f"{card_title} {card_url}".lower()
    score = 40  # Base inicial para qualquer documento retornado
    
    # 1. Pontuação por Cargo (+30 pontos)
    cargo = nlp_data.get('cargo', '').lower()
    if cargo and cargo != 'n/a':
        if cargo in text_to_check:
            score += 30

    # 2. Pontuação por Órgão (+25 pontos)
    orgao = nlp_data.get('orgao', '').lower()
    if orgao and orgao != 'n/a':
        if orgao in text_to_check:
            score += 25

    # 3. Pontuação por Banca (+20 pontos)
    banca = nlp_data.get('banca', '').lower()
    if banca and banca != 'n/a':
        if banca in text_to_check:
            score += 20

    # 4. Pontuação por Ano (+15 pontos)
    ano = nlp_data.get('ano', '')
    if ano and ano in text_to_check:
        score += 15

    # 5. Penalização/Match de palavras-chave individuais da query
    stop_words = {'prova', 'provas', 'concurso', 'concursos', 'de', 'da', 'do', 'para', 'em', 'pdf'}
    query_terms = [w for w in raw_query.lower().split() if len(w) > 2 and w not in stop_words]
    if query_terms:
        matches = sum(1 for w in query_terms if w in text_to_check)
        term_ratio = matches / len(query_terms)
        score = int((score * 0.7) + (term_ratio * 30))

    return min(100, max(10, score))


# =============================================================================
# 4. PADRONIZAÇÃO DE TÍTULO DO CARD ([ANO] ÓRGÃO - CARGO)
# =============================================================================

def standardize_card_title(
    raw_title: str,
    nlp_data: Optional[Dict[str, str]] = None,
    url: str = ''
) -> str:
    """
    Higieniza e formata o título do card para o padrão canônico:
    Ex: '[2024] OGMO PARANAGUÁ - ESTIVADOR'
    """
    if not raw_title:
        return 'Geral / Conhecimentos Básicos'

    t = raw_title.strip()

    # 1. Extração de Ano
    ano = ''
    m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', t)
    if not m_ano and url:
        m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', url)
    if m_ano:
        ano = m_ano.group(1)
    elif nlp_data and nlp_data.get('ano') and str(nlp_data['ano']).lower() not in ['n/a', '', 'null']:
        ano = str(nlp_data['ano']).strip()

    # 2. Limpeza de ruídos de portais e bancas
    t = re.sub(r'^(?:\[\d{4}\]\s*)+', '', t)
    t = re.sub(r'[—–]', '-', t)
    t = re.sub(r'^(?:provas?\s+para\s+download|provas?)\s*-\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^(?:IDCAP|IDECAN|PCI|QConcursos|Web)\s*-\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'Processo\s+Seletivo(?:\s+Privado)?\s*[-–]?\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'Concurso\s+P[úu]blico\s*[-–]?\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\d{3}/\d{4}\s*[-–]?\s*', '', t)
    t = re.sub(r'Edital\s*(?:n[º°o]?)?\s*(?:\d+/\d+|\d+)?\s*[-–]?\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\bEdital\s*(?:n[º°o]?)?\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\b(caderno de quest[oõ]es|prova objetiva|prova matriz|gabarito definitivo|gabarito preliminar)\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\.pdf$', '', t, flags=re.IGNORECASE)

    # 3. Divide por hífens e limpa cada segmento
    parts = [re.sub(r'\s+', ' ', p).strip() for p in t.split('-') if p.strip()]

    # 4. Deduplica termos repetidos adjacentes mantendo a riqueza do cargo
    dedup_parts = []
    for p in parts:
        p_clean = re.sub(r'[^\w]', '', p).lower()
        if not p_clean:
            continue
        if not dedup_parts:
            dedup_parts.append(p)
        else:
            last_clean = re.sub(r'[^\w]', '', dedup_parts[-1]).lower()
            if p_clean != last_clean:
                dedup_parts.append(p)

    title_body = ' - '.join(dedup_parts).upper() if dedup_parts else 'PROVA DE CONCURSO'
    prefix = f'[{ano}] ' if ano else ''

    return f"{prefix}{title_body}"


# =============================================================================
# 5. FILTRO E ORDENAÇÃO DE CARDS
# =============================================================================

def filter_and_rank_exam_cards(
    raw_cards: List[Dict[str, Any]],
    user_query: str,
    min_score: int = 20,
    limit: int = DEFAULT_SEARCH_RESULT_LIMIT
) -> List[Dict[str, Any]]:
    """
    Processa uma lista de cards brutos:
    1. Interpreta a query do usuário com NLP.
    2. Calcula o Match Score para cada card.
    3. Padroniza o título.
    4. Filtra por score mínimo e ordena do maior para o menor.
    """
    nlp_data = interpret_search_query_deterministic(user_query)
    processed_cards = []
    seen_urls = set()

    for card in raw_cards:
        url = card.get('url', '')
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        raw_title = card.get('title', '')
        score = card.get('match_score') or calculate_card_match_score(raw_title, url, nlp_data, user_query)
        clean_title = standardize_card_title(raw_title, nlp_data, url)

        if score >= min_score:
            processed_cards.append({
                'title': clean_title,
                'url': url,
                'gabarito_url': card.get('gabarito_url'),
                'source': card.get('source', 'web'),
                'match_score': score,
                'nlp_data': nlp_data
            })

    # Ordena por maior relevância (Match Score)
    processed_cards.sort(key=lambda x: x['match_score'], reverse=True)
    return processed_cards[:limit]


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'DEFAULT_SEARCH_RESULT_LIMIT',
    'BANCAS_MAP',
    'ORGAOS_MAP',
    'CARGOS_MAP',
    'ESTADOS_UFS',
    'CIDADES_MAP',
    'interpret_search_query_deterministic',
    'calculate_card_match_score',
    'standardize_card_title',
    'filter_and_rank_exam_cards'
]
