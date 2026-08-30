import re
import json
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

def clean_text_artifacts(text: str) -> str:
    """Remove cabeçalhos repetidos, banners de matéria, rodapés e ruídos de scraper."""
    if not text:
        return ""
    
    # Remove ruídos de scrapers (ex: 'de 5 Q1403422 Q21 da prova', 'Questão X de Y', 'Reportar Erro')
    text = re.sub(r'(?:Quest[ãa]o\s+)?\d+\s+de\s+\d+\s+Q\d+\s+Q\d+\s+da\s+prova', '', text, flags=re.IGNORECASE)
    text = re.sub(r'de\s+\d+\s+Q\d+\s+Q\d+\s+da\s+prova', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Q\d+\s+da\s+prova', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bQ\d{6,}\b', '', text)
    text = re.sub(r'\bReportar\s+Erro\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bClique\s+na\s+alternativa\s+correta\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bRefazer\s+Simulado\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'pcimarkpci[^\n]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'www\.pciconcursos\.com\.br', '', text, flags=re.IGNORECASE)
    text = re.sub(r'qconcursos\.com', '', text, flags=re.IGNORECASE)
    
    # Remove cabeçalhos institucionais repetidos que vazam entre páginas
    institutional_pats = [
        r'(?:^|\n)\s*(?:PREFEITURA\s+MUNICIPAL|GOVERNO\s+DO\s+ESTADO|ESTADO\s+D[OE]|MINIST[ÉE]RIO\s+D[AEO]|C[ÂA]MARA\s+MUNICIPAL|SECRETARIA\s+MUNICIPAL|SECRETARIA\s+DE\s+ESTADO|TRIBUNAL\s+DE\s+JUSTI[ÇC]A|INSTITUTO\s+[A-Z\s]+)[^\n]*',
        r'(?:^|\n)\s*CONCURSO\s+P[ÚU]BLICO[^\n]*',
        r'(?:^|\n)\s*PROVA\s+(?:OBJETIVA|ESCRITA|DISCURSIVA|DE\s+CONHECIMENTOS)[^\n]*',
        r'(?:^|\n)\s*EDITAL\s+(?:N[º°\.]?\s*)?\d+[^\n]*',
        r'(?:^|\n)\s*CADERNO\s+DE\s+(?:PROVAS?|QUEST[ÕO]ES)[^\n]*',
        r'(?:^|\n)\s*\d+º?\s+SIMULADO[^\n]*',
        r'(?:^|\n)\s*\d+\s+AGENTE\s+COMERCIAL[^\n]*',
        r'(?:^|\n)\s*(?:CARGO|FUN[ÇC][ÃA]O)\s*:\s*[^\n]*',
        r'(?:^|\n)\s*N[ÍI]VEL\s+(?:SUPERIOR|M[ÉE]DIO|FUNDAMENTAL)[^\n]*',
        r'(?:^|\n)\s*CONHECIMENTOS\s+(?:ESPEC[ÍI]FICOS|B[ÁA]SICOS|GERAIS)\s*(?=\n|$)',
        r'(?:^|\n)\s*[A-ZÁ-Ú\s]{3,35}\s*[-–—]\s*\d+\s*(?=\n|$)',
        r'(?m)^\s*(?:[A-Z\s\-]+–\s*)?\d{1,2}\s*$',
    ]
    for pat in institutional_pats:
        text = re.sub(pat, '', text, flags=re.IGNORECASE)
    
    # Remove gabaritos vazados
    text = re.sub(r'\(?\s*(?:Correta|Gabarito|Resposta|Gabarito\s*Oficial)\s*[:=-]?\s*(?:[A-Ea-eXNxn\*]|CERTO|ERRADO|C|E)\s*\)?', '', text, flags=re.IGNORECASE)
    
    # Remove seções finais de rascunho
    text = re.sub(r'\n+(?:QUEST[ÃA\ufffd\?]?O\s+DA\s+PROVA\s+DISSERTATIVA|PROPOSTA\s+DE\s+REDA[ÇC\ufffd\?][ÃA\ufffd\?]?O|FOLHA\s+DE\s+RESPOSTAS?|RASCUNHO).*', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove múltiplos espaços mantendo quebras de linha limpas
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def parse_html_exam(html_content: str, source_url: str = "") -> List[Dict[str, Any]]:
    """
    Parser especializado para páginas HTML com simulados ou cadernos de questões (ex: PCI Concursos, QConcursos).
    Extrai com precisão cirúrgica os enunciados limpos, alternativas estruturadas (A, B, C, D, E) e o gabarito oficial.
    """
    if isinstance(html_content, (bytes, bytearray)):
        try:
            html_content = html_content.decode('utf-8')
        except UnicodeDecodeError:
            html_content = html_content.decode('latin-1', errors='replace')

    soup = BeautifulSoup(html_content, 'html.parser')
    questions = []
    
    # 1. Extração de Gabarito do JavaScript da página (ex: var simGabaritos = ["A", "C", "B", "D", "A"])
    gabaritos_list = []
    for script in soup.find_all('script'):
        stext = script.string or ""
        m_gab = re.search(r'var\s+simGabaritos\s*=\s*(\[[^\]]+\])', stext)
        if m_gab:
            try:
                gabaritos_list = json.loads(m_gab.group(1))
            except Exception:
                pass
            break

    # 2. Localização dos blocos de questão
    sim_questoes = soup.select('.sim-questao, .questao-item, .question-card, .q-item')
    
    if sim_questoes:
        for idx, q_elem in enumerate(sim_questoes):
            # Extrair número da questão da prova
            q_num = str(idx + 1)
            badge_prova = q_elem.select_one('.badge-secondary, .badge-info, .q-num')
            if badge_prova and ('da prova' in badge_prova.text or 'Quest' in badge_prova.text):
                m_qnum = re.search(r'Q?(\d+)', badge_prova.text)
                if m_qnum:
                    q_num = m_qnum.group(1)

            # Extrair enunciado limpo
            enunciado_elem = q_elem.select_one('.sim-enunciado, .enunciado, .question-text, .q-text')
            if enunciado_elem:
                enunciado_text = enunciado_elem.get_text(separator='\n', strip=True)
            else:
                q_clone = BeautifulSoup(str(q_elem), 'html.parser')
                for unwanted in q_clone.select('.badge, .sim-alts, .sim-report, .sim-feedback, button, script, style'):
                    unwanted.decompose()
                enunciado_text = q_clone.get_text(separator=' ', strip=True)

            enunciado_clean = clean_text_artifacts(enunciado_text)

            # Extrair alternativas
            options = {}
            alt_elems = q_elem.select('.btn-sim-alt, .opcao-item, .alternative, .q-alt')
            for alt in alt_elems:
                letra = alt.get('data-letra')
                if not letra:
                    letra_span = alt.select_one('.sim-letra, .letter, .badge')
                    if letra_span:
                        letra = letra_span.text.strip().upper()
                
                alt_clone = BeautifulSoup(str(alt), 'html.parser')
                for ls in alt_clone.select('.sim-letra, .letter, .badge'):
                    ls.decompose()
                opt_text = alt_clone.get_text(separator=' ', strip=True)
                
                if letra:
                    letra = letra.strip().upper()
                    # Remove prefixos redundantes tipo 'A) ' ou 'A - ' do texto da alternativa
                    opt_text = re.sub(rf'^{re.escape(letra)}\s*[\.\-\)]?\s*', '', opt_text, flags=re.IGNORECASE).strip()
                    opt_text = clean_text_artifacts(opt_text)
                    options[letra] = opt_text

            if not options:
                for label in q_elem.select('label'):
                    inp = label.find('input')
                    letra = inp.get('value') if inp else None
                    if letra and len(letra) == 1:
                        opt_text = label.get_text(strip=True)
                        opt_text = re.sub(rf'^{re.escape(letra)}\s*[\.\-\)]?\s*', '', opt_text, flags=re.IGNORECASE).strip()
                        options[letra.upper()] = clean_text_artifacts(opt_text)

            # Extrair gabarito oficial real
            correct_ans = 'A'
            if idx < len(gabaritos_list):
                correct_ans = str(gabaritos_list[idx]).upper()
            elif 'A' in options:
                correct_ans = 'A'
            elif 'C' in options:
                correct_ans = 'C'

            # Extrair imagens da questão se presentes
            q_images = []
            for img in q_elem.select('img'):
                src = img.get('src')
                if src and not any(x in src.lower() for x in ['logo', 'icon', 'advert', 'ads', 'google']):
                    q_images.append(src)

            questions.append({
                'numero_questao': q_num,
                'enunciado': enunciado_clean,
                'opcoes': options,
                'resposta': correct_ans,
                'disciplina': 'Conhecimentos Gerais',
                'images': q_images if q_images else None
            })

    return questions
