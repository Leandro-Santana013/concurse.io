from flask import Flask, request, jsonify, render_template
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import os
import requests
from bs4 import BeautifulSoup
import json
from dotenv import load_dotenv
from local_pdf_parser import parse_exam_text_local
from orchestrator import orchestrator

exam_progress = {}

# Callbacks para o Orchestrator atualizar o progresso
def _on_orchestrator_progress(exam_id, status_msg, pct):
    global exam_progress
    exam_progress[exam_id] = {"status": status_msg, "progress": pct}

orchestrator.onexam_progress = _on_orchestrator_progress
orchestrator.start()

load_dotenv()
# O Orchestrator já gerencia e configura a API Key inicial usando o ApiKeyManager.

app = Flask(__name__)

# Database Setup
Base = declarative_base()
engine = create_engine('sqlite:///concurse.db', echo=False)
Session = sessionmaker(bind=engine)

class Folder(Base):
    __tablename__ = 'folders'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    exams = relationship("Exam", back_populates="folder", cascade="all, delete-orphan")

class Exam(Base):
    __tablename__ = 'exams'
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    status = Column(String(20), default='Pendente') # Pendente, Aprovada
    folder_id = Column(Integer, ForeignKey('folders.id'), nullable=True)
    source_url = Column(String(500), nullable=True)
    match_score = Column(Integer, default=0)
    
    folder = relationship("Folder", back_populates="exams")
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")

class Question(Base):
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey('exams.id'))
    statement = Column(Text, nullable=False)
    options = Column(Text, nullable=True) # JSON string with options like {"A": "...", "B": "..."}
    correct_answer = Column(String(10), nullable=False) # 'A', 'B', 'Certo', 'Errado'
    subject = Column(String(100), nullable=True, default='Geral')
    images = Column(Text, nullable=True) # JSON string with image URLs
    
    exam = relationship("Exam", back_populates="questions")

class AppConfig(Base):
    __tablename__ = 'app_config'
    key = Column(String(50), primary_key=True)
    value = Column(String(500))

class ExamAttempt(Base):
    __tablename__ = 'exam_attempts'
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey('exams.id'))
    score = Column(Integer, default=0)
    total = Column(Integer, default=0)
    percentage = Column(Float, default=0.0)
    elapsed_seconds = Column(Integer, default=0)
    answers_json = Column(Text, nullable=True)
    created_at = Column(String(30), nullable=True)

# Create tables if not exist
Base.metadata.create_all(engine)

# Migration simples caso a tabela já exista e não tenha match_score
try:
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE exams ADD COLUMN match_score INTEGER DEFAULT 0"))
        conn.commit()
except Exception as e:
    pass

# Migration para coluna images em questions
try:
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE questions ADD COLUMN images TEXT"))
        conn.commit()
except Exception as e:
    pass

def get_gemini_key():
    session = Session()
    config = session.query(AppConfig).filter_by(key='GEMINI_API_KEY').first()
    db_key = config.value if config else None
    session.close()
    return db_key or os.environ.get("GEMINI_API_KEY")

# Tenta injetar no orchestrator logo no boot, se já tiver no banco
_boot_keys = get_gemini_key()
if _boot_keys:
    from orchestrator import orchestrator
    _keys_list = [k.strip() for k in _boot_keys.split(",") if k.strip()]
    if _keys_list:
        orchestrator.api_key_manager.keys = _keys_list
        print(f"[App] Orchestrator configurado no boot com {len(_keys_list)} chaves do banco.")

# Global state for progress tracking (moved to top)

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config/gemini_key', methods=['GET', 'POST'])
def manage_gemini_key():
    session = Session()
    if request.method == 'POST':
        data = request.json
        api_key = data.get('api_key', '').strip()
        if not api_key:
            session.close()
            return jsonify({"success": False, "error": "Chave não pode ser vazia."})
            
        action = data.get('action', 'replace')
        
        config = session.query(AppConfig).filter_by(key='GEMINI_API_KEY').first()
        if not config:
            config = AppConfig(key='GEMINI_API_KEY', value=api_key)
            session.add(config)
        else:
            if action == 'append':
                existing_keys = [k.strip() for k in config.value.split(',') if k.strip()]
                new_keys = [k.strip() for k in api_key.split(',') if k.strip()]
                combined = existing_keys + [k for k in new_keys if k not in existing_keys]
                config.value = ','.join(combined)
            else:
                config.value = api_key
        session.commit()
        
        # Injeta dinamicamente as novas chaves no orchestrator em tempo real
        from orchestrator import orchestrator
        final_keys_list = [k.strip() for k in config.value.split(",") if k.strip()]
        if final_keys_list:
            orchestrator.api_key_manager.keys = final_keys_list
            orchestrator.api_key_manager.current_index = 0
            print(f"[ApiKeyManager] Atualizado com {len(final_keys_list)} chaves via UI.")

        session.close()
        return jsonify({"success": True})
    else:
        config = session.query(AppConfig).filter_by(key='GEMINI_API_KEY').first()
        session.close()
        # Forçando o uso do banco de dados (ignorando a variável de ambiente temporariamente)
        has_key = bool(config and config.value)
        return jsonify({"has_key": has_key})

@app.route('/api/exams/<int:exam_id>/progress', methods=['GET'])
def getexam_progress(exam_id):
    prog = exam_progress.get(exam_id, {"status": "Processando...", "progress": 0})
    return jsonify(prog)

@app.route('/api/downloads', methods=['GET'])
def get_active_downloads():
    session = Session()
    results = []
    for exam_id, prog in exam_progress.items():
        exam = session.query(Exam).filter_by(id=exam_id).first()
        title = exam.title if exam else f"Prova {exam_id}"
        results.append({
            "id": exam_id,
            "title": title,
            "url": exam.source_url if exam else "",
            "status": prog.get('status', ''),
            "progress": prog.get('progress', 0),
            "error_type": prog.get('error_type', None),
            "total_chunks": prog.get('total_chunks', 0),
            "done_chunks": prog.get('done_chunks', 0)
        })
    session.close()
    # Ordenar: ativos primeiro (0-99), erros (-1), concluídos (100)
    results.sort(key=lambda x: (0 if 0 <= x['progress'] < 100 else 1 if x['progress'] == -1 else 2))
    return jsonify(results)

# Banco de provas públicas conhecidas — URLs validados manualmente
KNOWN_EXAMS_DB = [
    # CESGRANRIO — permite acesso direto
    {"keywords": ["banco do brasil", "escriturario", "bb"], "title": "CESGRANRIO - Banco do Brasil - Escriturário (2023)", "url": "https://www.cesgranrio.org.br/pdf/bb0123/BB0123_PROVA_TIPO_001.pdf"},
    {"keywords": ["caixa economica", "tec bancario", "caixa", "cef"], "title": "CESGRANRIO - Caixa Econômica Federal (2021)", "url": "https://www.cesgranrio.org.br/pdf/cef0121/CEF0121_PROVA_TIPO_001.pdf"},
    {"keywords": ["petrobras", "tecnico", "petroleo"], "title": "CESGRANRIO - Petrobras - Técnico (2022)", "url": "https://www.cesgranrio.org.br/pdf/pet0822/PET0822_PROVA_TIPO_001.pdf"},
    {"keywords": ["bndes", "banco nacional", "desenvolvimento"], "title": "CESGRANRIO - BNDES - Profissional (2023)", "url": "https://www.cesgranrio.org.br/pdf/bndes0323/BNDES0323_PROVA_TIPO_001.pdf"},
    # IDCAP — provas brasileiras acessíveis
    {"keywords": ["fesa", "faculdade", "docente"], "title": "IDCAP - FESA - Docente", "url": "https://www.idcap.org.br/concursos/gabaritos/fesa_docente_gabarito.pdf"},
    # FCC — provas públicas
    {"keywords": ["fcc", "metro", "metro sp", "metroviario"], "title": "FCC - Companhia do Metropolitano de São Paulo (2016)", "url": "https://www.concursosfcc.com.br/concursos/cmpausp316/cmpausp316_prova_300.pdf"},
    {"keywords": ["trt", "tribunal regional", "tecnico judiciario", "analista judiciario"], "title": "FCC - TRT 2ª Região - Técnico Judiciário (2018)", "url": "https://www.concursosfcc.com.br/concursos/trt2r18/trt2r18_prova_101.pdf"},

    # INEP ENEM — tenta baixar, pode falhar por SSL
    {"keywords": ["enem", "ensino medio", "vestibular", "inep"], "title": "ENEM 2022 - 1º Dia - Caderno Azul", "url": "https://download.inep.gov.br/areas_de_atuacao/provas_e_gabaritos/enem/2022/caderno_de_questoes_1_dia_CN.pdf"},
    # VUNESP — provas acessíveis
    {"keywords": ["vunesp", "sao paulo", "sp", "prefeitura"], "title": "VUNESP - Prefeitura de São Paulo - Agente Escolar (2023)", "url": "https://www.vunesp.com.br/PMSP1901/arquivos/PMSP1901_AGENTE_ESC_PROVA.pdf"},
    {"keywords": ["detran", "vistoriador", "agente transito"], "title": "VUNESP - DETRAN - Agente de Trânsito", "url": "https://www.vunesp.com.br/DTRN1401/arquivos/DTRN1401_AGENTE_TRANS_PROVA.pdf"},
    # CESPE/CEBRASPE
    {"keywords": ["policia federal", "agente pf"], "title": "CESPE - Polícia Federal - Agente (2014)", "url": "https://cdn.cebraspe.org.br/concursos/PF_14/arquivos/PF_001_01.PDF"},
    {"keywords": ["tcu", "tribunal de contas", "auditor"], "title": "CESPE - TCU - Auditor Federal (2015)", "url": "https://cdn.cebraspe.org.br/concursos/TCU_15/arquivos/TCU_001_01.PDF"},
    {"keywords": ["inss", "tecnico seguro social", "previdencia"], "title": "CESPE - INSS - Técnico do Seguro Social (2016)", "url": "https://cdn.cebraspe.org.br/concursos/INSS_16/arquivos/INSS_001_01.PDF"},
]


def _search_known_exams(query):
    """Busca no banco interno de provas conhecidas."""
    query_lower = query.lower()
    results = []
    for exam in KNOWN_EXAMS_DB:
        keywords = exam["keywords"]
        # Score = número de keywords que aparecem na query
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            results.append((score, exam))
    
    # Ordenar por relevância
    results.sort(key=lambda x: x[0], reverse=True)
    return [{"title": r["title"], "url": r["url"]} for _, r in results[:5]]



def _search_qc_provas(query):
    results = []
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            q = f"site:qconcursos.com/questoes-de-concursos/provas {query}"
            for r in ddgs.text(q, max_results=3):
                if "qconcursos.com" in r['href']:
                    results.append({
                        "title": "[QC] " + r['title'][:60],
                        "url": r['href'],
                        "source": "qconcursos"
                    })
    except Exception as e:
        print("Erro busca QC:", e)
    return results

def _scrape_pci_pdfs(query, nlp_data=None):
    results = []
    try:
        from ddgs import DDGS
        
        search_query = f'{query} site:pciconcursos.com.br/provas/download/'
        ddgs_results = list(DDGS().text(search_query, max_results=15))
        
        if not ddgs_results:
            return results
            
        target_words = set(query.lower().split())
        if nlp_data:
            orgao = str(nlp_data.get('orgao', '')).lower()
            cargo = str(nlp_data.get('cargo', '')).lower()
            if orgao and orgao != 'n/a': target_words.update(orgao.split())
            if cargo and cargo != 'n/a': target_words.update(cargo.split())
            
        stop_words = {'prova', 'de', 'para', 'em', 'da', 'do', 'concurso', 'pdf', 'a', 'o', 'e'}
        target_words = {w for w in target_words if len(w) > 2 and w not in stop_words}
            
        for r in ddgs_results:
            href = r.get('href', '')
            title = r.get('title', 'Prova PCI')
            
            if '/download/' in href:
                title_lower = title.lower()
                
                score = 0
                if target_words:
                    matches = sum(1 for w in target_words if w in title_lower)
                    score = int((matches / len(target_words)) * 100)
                    
                if nlp_data and nlp_data.get('cargo') and str(nlp_data['cargo']).lower() != 'n/a':
                    if str(nlp_data['cargo']).lower() in title_lower:
                        score = min(100, score + 30)
                else:
                    if not target_words: score = 50
                
                if score == 0 and target_words:
                    score = 10
                    
                results.append({
                    "title": f"PCI - {title[:100]}",
                    "url": href,
                    "match_score": score
                })
                
        results.sort(key=lambda x: x.get('match_score', 0), reverse=True)
        results = results[:6]
        
    except Exception as e:
        print(f"Erro Busca PCI: {e}")
    return results






def _scrape_idcap_pdfs(query):
    results = []
    query_lower = query.lower()
    ignore_words = {'prova', 'provas', 'concurso', 'concursos', 'filetype:pdf', 'pdf'}
    query_words = [w for w in query_lower.split() if len(w) > 3 and w not in ignore_words]

    PROVA_KEYWORDS = ['prova', 'gabarito', 'caderno', 'questões']
    SKIP_KEYWORDS = ['resultado', 'convoca', 'retifica', 'cronograma', 'edital', 'rela', 'resposta', 'recurso', 'divulga', 'homologa', 'inscri', 'isen', 'anexo', 'aditivo', 'comunicado', 'aviso', 'lista', 'decreto', 'lei', 'portaria', 'informa', 'classifica', 'quantitativo', 'local', 'data', 'nota', 'judicial', 'decis', 'cumprimento', 'gabarito', 'preliminar', 'definitiv', 'parecer']

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            concurso_links = []
            if query.startswith('http') and 'idcap' in query:
                concurso_links.append((999, query, "Link Direto"))
            else:
                for status_page in ['/index/1/', '/index/3/', '/index/4/', '/index/5/']:
                    try:
                        page.goto(f'https://idcap.org.br{status_page}', timeout=30000, wait_until='domcontentloaded')
                        
                        links = page.query_selector_all("a[href*='/informacoes/']")
                        for a in links:
                            href = a.get_attribute("href")
                            text = a.evaluate("el => el.innerText.toLowerCase()")
                            if not href: continue
                            
                            if query_words:
                                score = sum(1 for w in query_words if w in text)
                                if score > 0:
                                    concurso_links.append((score, href, text))
                            else:
                                concurso_links.append((1, href, text))
                    except Exception as e:
                        print(f"Playwright IDCAP {status_page} erro: {e}")
                        
            concurso_links.sort(key=lambda x: x[0], reverse=True)
            for score, href, concurso_title in concurso_links[:10]:
                try:
                    url = f"https://idcap.org.br{href}" if href.startswith('/') else href
                    page.goto(url, timeout=30000, wait_until='domcontentloaded')
                    
                    pdf_links = page.query_selector_all("a[href*='.pdf'], a[href*='/download/']")
                    for a in pdf_links:
                        pdf_href = a.get_attribute("href")
                        if not pdf_href: continue
                        
                        text = a.evaluate("el => el.innerText.trim()")
                        text_lower = text.lower()
                        
                        should_skip = any(kw in text_lower for kw in SKIP_KEYWORDS)
                        is_prova = any(kw in text_lower for kw in PROVA_KEYWORDS)
                        
                        # Aceitar se tiver palavra de prova OU se não tiver nenhuma palavra a ser ignorada (SKIP)
                        # Assim capturamos "Estivador", "Arrumador" porque eles não estão na lista de SKIP
                        if not should_skip:
                            clean_title = concurso_title.replace('\n', ' ').strip()
                            results.append({
                                "title": f"IDCAP - {clean_title[:100]} - {text[:80]}",
                                "url": pdf_href
                            })
                            if len(results) >= 25:
                                break
                except Exception as e:
                    print(f"Playwright IDCAP concurso {href} erro: {e}")
            
            browser.close()
    except Exception as e:
        print(f"Erro Playwright IDCAP: {e}")
    return results


def _gemini_find_pdf_urls(query, api_key_val):
    """Usa o Gemini para sugerir URLs de PDFs de provas reais."""
    if not api_key_val:
        return []
    try:
        import orchestrator as orch_module
        from orchestrator import orchestrator
        import json
        from google import genai
        
        max_attempts = len(orchestrator.api_key_manager.keys) if orchestrator.api_key_manager.keys else 1
        for attempt in range(max_attempts):
            try:
                if orchestrator.api_key_manager.keys:
                    client = orchestrator.api_key_manager.get_current_client()
                else:
                    client = genai.Client(api_key=api_key_val)
                    
                model_name = orch_module.MODEL_CASCADE[-2] # Usa modelo Lite para economizar cota
                prompt = f"""
Você é um especialista em concursos públicos brasileiros. O usuário quer encontrar provas em PDF de: "{query}"
Forneça URLs REAIS de arquivos PDF de provas de concurso. Use fontes como CEBRASPE (cdn.cebraspe.org.br), CESGRANRIO, FCC, gov.br.
Retorne APENAS JSON válido: [{{"title": "...", "url": "https://...pdf"}}]
Se não souber, retorne: []
"""
                response = client.models.generate_content(model=model_name, contents=prompt)
                raw = response.text.strip()
                if '```' in raw:
                    raw = raw.split('```')[1].split('```')[0].replace('json','').strip()
                data = json.loads(raw)
                if isinstance(data, list):
                    return data
                break
            except Exception as e:
                print(f"Erro Gemini PDF search (Tentativa {attempt+1}/{max_attempts}): {e}")
                if ('429' in str(e) or 'quota' in str(e).lower()) and orchestrator.api_key_manager.keys:
                    orchestrator.api_key_manager.rotate_key()
                else:
                    break
    except Exception as e:
        print(f"Erro no módulo Gemini PDF search: {e}")
    return []


def _search_pdfs_web(query, api_key_val=None):
    """Busca PDFs de provas: IDCAP + IDECAN + banco interno + Gemini + DDG."""

    results = []
    seen_urls = set()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'pt-BR,pt;q=0.9',
    }

    def _add_results(new_results):
        for r in new_results:
            url = r.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                results.append(r)

    # Estratégia 1: Banco interno de provas conhecidas (sempre funciona, sem quota)
    known = _search_known_exams(query)
    print(f"Banco interno: {len(known)} provas")
    _add_results(known)

    # Estratégia 2: Gemini sugere URLs adicionais (se quota disponível)
    if api_key_val and len(results) < 8:
        try:
            gemini_results = _gemini_find_pdf_urls(query, api_key_val)
            print(f"Gemini sugeriu {len(gemini_results)} URLs")
            for r in gemini_results:
                url = r.get('url', '')
                title = r.get('title', '')
                if url and '.pdf' in url.lower():
                    _add_results([{"title": title, "url": url}])
        except Exception as e:
            print(f"Gemini busca erro: {e}")

    # Estratégia 3: DuckDuckGo via DDGS (Busca Genérica Reforçada)
    if len(results) < 10:
        try:
            from ddgs import DDGS
            
            ddg_query = f'{query} prova concurso filetype:pdf'
            with DDGS() as ddgs:
                ddg_results = ddgs.text(ddg_query, max_results=8)
                for r in ddg_results:
                    url = r.get('href', '')
                    title = r.get('title', '')
                    if url and '.pdf' in url.lower():
                        _add_results([{"title": f"Web - {title[:60]}", "url": url}])
                        
                        
        except ImportError:
            print("Biblioteca 'ddgs' não instalada. Execute: pip install ddgs")
        except Exception as e:
            print(f"Erro DDGS: {e}")

    return results




@app.route('/api/search', methods=['GET'])
def search_exams():
    query = request.args.get('q', '')
    sources_param = request.args.get('sources', '')
    interpreted_query = query
    api_key_val = get_gemini_key()
    
    # Bypass para aceitar links diretos do QConcursos
    if "qconcursos.com" in query:
        return jsonify([{
            "title": "Extração Direta QConcursos",
            "url": query,
            "source": "QConcursos Direct"
        }])
        
    active_sources = [s.strip().lower() for s in sources_param.split(',')] if sources_param else ['web', 'idcap', 'pci', 'qconcursos']
    
    if api_key_val and query:
        try:
            import orchestrator as orch_module
            from orchestrator import orchestrator
                        
            max_attempts = len(orchestrator.api_key_manager.keys) if orchestrator.api_key_manager.keys else 1
            for attempt in range(max_attempts):
                try:
                    # Pega a chave que está ativa no rodízio do orchestrator
                    if orchestrator.api_key_manager.keys:
                        current_key = orchestrator.api_key_manager.keys[orchestrator.api_key_manager.current_index]
                        genai.configure(api_key=current_key)
                    else:
                        valid_api_key = api_key_val.split(',')[0].strip()
                        genai.configure(api_key=valid_api_key)
                        
                    # Usa o modelo lite para economizar o limite minúsculo (5 RPM) do modelo principal
                    model_name = "gemini-3.1-flash-lite"
                    model = orchestrator.model_manager.get_model(model_name)
                    fontes_ativas = ", ".join(active_sources) if active_sources else "Nenhuma restrição"
                    prompt = f"""
                    O usuário digitou a seguinte busca para encontrar provas de concurso: "{query}".
                    O usuário selecionou os seguintes filtros de fontes/bancas no sistema: {fontes_ativas}.
                    Interprete essa busca e extraia as informações estruturadas. 
                    DICA: Se os filtros indicarem uma banca específica (ex: idcap, idecan), assuma ela como a "banca" caso não haja outra contraditória na string.
                    Retorne APENAS um JSON válido no seguinte formato e nada mais:
                    {{
                      "orgao": "Nome do órgão (ou vazio se não souber)",
                      "banca": "Nome da banca (ou vazio)",
                      "ano": "Ano (ou vazio)",
                      "cargo": "Cargo (ou vazio)",
                      "local": "Local/Cidade/Estado (ou vazio)",
                      "query_otimizada": "Uma string de busca limpa e otimizada para encontrar a prova em PDF"
                    }}
                    """
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    clean_json = response.text.replace('```json', '').replace('```', '').strip()
                    data = json.loads(clean_json)
                    break # Sucesso, sai do loop de tentativas
                except Exception as e:
                    print(f"Erro ao usar Gemini (Tentativa {attempt+1}/{max_attempts}):", e, flush=True)
                    if ('429' in str(e) or 'quota' in str(e).lower()) and orchestrator.api_key_manager.keys:
                        print("Limite da chave atingido na busca NLP. Rotacionando chave...", flush=True)
                        orchestrator.api_key_manager.rotate_key()
                    else:
                        data = {}
                        break
            
            if not data:
                data = {}
            
            interpreted_query = data.get('query_otimizada', query)
            print("\n" + "="*30, flush=True)
            print("LOG DE BUSCA (GEMINI NLP)", flush=True)
            print(f"Órgão: {data.get('orgao', 'N/A')}", flush=True)
            print(f"Banca: {data.get('banca', 'N/A')}", flush=True)
            print(f"Ano: {data.get('ano', 'N/A')}", flush=True)
            print(f"Query Melhorada: {interpreted_query}", flush=True)
            print("="*30 + "\n", flush=True)
            
            # Otimização de fontes: se a banca foi identificada, remover scrapers de outras bancas
            banca_identificada = data.get('banca', '').strip().lower()
            
            # PCI é genérico, então não removemos ele baseado apenas no nome da banca
            scrapers_bancas_especificas = ['idcap']
            
            # 1. Verifica se o usuário digitou explicitamente o nome de um scraper na query
            query_lower = query.lower()
            scraper_explicito = None
            
            mapa_scrapers = {
                'idcap': ['idcap', 'id cap'],
                'pci': ['pci', 'pciconcurso', 'pciconcursos', 'pci concursos', 'pci concurso']
            }
            
            for scraper_key, terms in mapa_scrapers.items():
                if any(term in query_lower for term in terms):
                    scraper_explicito = scraper_key
                    break
            
            if scraper_explicito:
                # Se o usuário digitou "pci" (ou pciconcursos), remove os outros (idcap, idecan)
                for sb in ['idcap', 'pci']:
                    if sb != scraper_explicito and sb in active_sources:
                        active_sources.remove(sb)
                        print(f"Otimização: scraper '{sb}' ignorado pois o usuário digitou '{scraper_explicito}' explicitamente.", flush=True)
            elif banca_identificada and banca_identificada != "n/a":
                # 2. Se não digitou um site, mas a IA identificou a banca, removemos as bancas específicas que não batem
                for sb in scrapers_bancas_especificas:
                    if sb not in banca_identificada and sb in active_sources:
                        active_sources.remove(sb)
                        print(f"Otimização: scraper '{sb}' ignorado pois a banca buscada é '{banca_identificada}'.", flush=True)
                        
        except Exception as e:
            print("Erro ao usar Gemini:", e, flush=True)

    import concurrent.futures
    all_results = []
    
    def run_scraper(func, *args):
        try:
            return func(*args)
        except Exception as e:
            print(f"Erro no scraper {func.__name__}: {e}")
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        if 'web' in active_sources:
            futures.append(executor.submit(run_scraper, _search_pdfs_web, interpreted_query, api_key_val))

        if 'idcap' in active_sources:
            futures.append(executor.submit(run_scraper, _scrape_idcap_pdfs, query))
        if 'pci' in active_sources:
            futures.append(executor.submit(run_scraper, _scrape_pci_pdfs, query, data))
            
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                print(f"Futuro resolvido com {len(res)} resultados. Exemplo: {res[0] if res else 'None'}", flush=True)
                all_results.extend(res)
                
    # Deduplicar por URL
    def standardize_title(t, nlp_data, url=''):
        import re
        
        # 1. Tentar pescar o ano original direto do titulo antes das mutilações de texto
        ano_original = ''
        m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', t)
        if not m_ano and url:
            m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', url)
            
        if m_ano:
            ano_original = m_ano.group(1)
            
        # Limpeza agressiva do lixo textual que os sites de banca enviam
        # Normalizar travessões longos
        t = re.sub(r'[—–]', '-', t)
        
        t = re.sub(r'^(provas para download|prova para download|provas?)\s*-\s*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'^(IDCAP|IDECAN|PCI|QConcursos)\s*-\s*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'(processo seletivo(\s*privado|\s*priv|\s*pri)*)+', '', t, flags=re.IGNORECASE)
        t = re.sub(r'(concurso\s*p[uú]blico.*?)(para|-|\s|$)', '', t, flags=re.IGNORECASE)
        t = re.sub(r'psp\s*\d+/\d+\s*-\s*ogmo/s\s*-\s*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'\d{3}/\d{4}\s*-\s*', '', t)
        
        # Regex blindado para IDECAN: Pega 'EDITAL Nº X, DE 16 DE MARÇO DE 2026', 'EDT. 001/2026' ou '(EDITAL 02)'
        t = re.sub(r'(?i)\(?(edital|edt\.?)\s*(cbmmg)?\s*(nº)?\s*\d+([./]\d+)?(.*?de\s*\d+\s*de\s*[a-zç]+\s*de\s*\d+)?\)?', '', t)
        
        # Extermina parênteses que ficaram vazios após os cortes acima
        t = re.sub(r'\(\s*-\s*\)|\(\s*\)', '', t)
        
        t = re.sub(r'1ª Nota Pública.*', '', t, flags=re.IGNORECASE)
        t = re.sub(r'Cumprimento de decis.*', '', t, flags=re.IGNORECASE)
        
        t = t.strip(' -')
        t = re.sub(r'\s*-\s*-\s*', ' - ', t)
        
        # Deduplicar partes iguais divididas por hífen (Ex: Trabalhador Portuário - Trabalhador Portuário)
        parts = [p.strip() for p in t.split('-')]
        seen = set()
        clean_parts = []
        for p in parts:
            p_lower = p.lower()
            if p_lower not in seen and p_lower:
                seen.add(p_lower)
                clean_parts.append(p)
        t = ' - '.join(clean_parts)
        
        # Cruzamento de dados com a NLP
        ano = nlp_data.get('ano', '') if nlp_data else ''
        orgao = nlp_data.get('orgao', '') if nlp_data else ''
        local = nlp_data.get('local', '') if nlp_data else ''
        
        # O Gemini as vezes confunde "Processo Seletivo Privado" e acha que "Privado" é o órgão
        if orgao:
            import re
            orgao = re.sub(r'^(pri|priv|privado|processo\s*seletivo.*)$', '', orgao, flags=re.IGNORECASE).strip()
            
        if not orgao or str(orgao).lower() in ['n/a', '', 'null']:
            orgao = ""
            
        if not local or str(local).lower() in ['n/a', '', 'null']:
            local_str = ""
        else:
            # Não duplica o local se ele já for parte do nome do órgão (ex: OGMO/SANTOS e SANTOS)
            if local.lower() in orgao.lower():
                local_str = ""
            else:
                local_str = f" - {local}"
            
        cargo = t.strip()
        
        # O IDCAP e IDECAN enviam o órgão no começo do título. Evitar duplicar cruzado com a NLP:
        if orgao and cargo:
            cargo_parts = [p.strip() for p in cargo.split('-')]
            if len(cargo_parts) > 1:
                import re
                first_part = re.sub(r'[^\w\s]', ' ', cargo_parts[0]).strip().lower()
                orgao_clean = re.sub(r'[^\w\s]', ' ', orgao).strip().lower()
                first_part = re.sub(r'\s+', ' ', first_part)
                orgao_clean = re.sub(r'\s+', ' ', orgao_clean)
                
                # Remove apenas se as strings são altamente semelhantes para não comer cargos que calham de ter nome parecido
                if first_part and orgao_clean and (first_part in orgao_clean or orgao_clean in first_part):
                    cargo = ' - '.join(cargo_parts[1:]).strip()

        if not cargo:
            cargo = "Geral / Conhecimentos Básicos"
            
        # Prioridade para o ano real do card (ano_original). Fallback para a IA (nlp_data)
        if ano_original:
            ano = ano_original
        elif not ano or str(ano).lower() in ['n/a', '', 'null']:
            ano = ""
            
        # Montagem do Lego Final
        prefix = f"[{ano}] " if ano and str(ano).lower() not in ['n/a', '', 'null'] else ""
        orgao_final = f"{orgao}{local_str} - " if orgao else (f"{local} - " if local_str else "")
        
        final_string = f"{orgao_final}{cargo}".upper()
        
        # Filtro Absoluto de Redundância: Varre a string da esquerda pra direita destruindo peças coladas repetidas
        final_parts = [p.strip() for p in final_string.split('-') if p.strip()]
        dedup_parts = []
        for p in final_parts:
            if not dedup_parts:
                dedup_parts.append(p)
            else:
                p_clean = re.sub(r'[^\w]', '', p).lower()
                last_clean = re.sub(r'[^\w]', '', dedup_parts[-1]).lower()
                # Se a peça for 100% redundante a anterior, é ignorada e sumariamente pulverizada.
                if p_clean and last_clean and (p_clean == last_clean or p_clean in last_clean or last_clean in p_clean):
                    pass
                else:
                    dedup_parts.append(p)
                    
        return f"{prefix}{' - '.join(dedup_parts)}"
        
    seen_urls = set()
    pdf_results = []
    print(f"Total all_results coletados para deduplicar: {len(all_results)}", flush=True)
    for r in all_results:
        url = r.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            # Como a variavel 'data' existe no escopo de search_exams contendo o JSON do Gemini
            r['title'] = standardize_title(r.get('title', ''), data, url)
            pdf_results.append(r)
            
    print(f"PDFs encontrados pelos scrapers: {len(pdf_results)}")
    
    # Se nenhum PDF foi encontrado, retornar mensagem clara
    if not pdf_results:
        print("Nenhum PDF encontrado para esta busca.")

            
    # Registrar no banco — limpar pendentes antigos primeiro para evitar acúmulo
    session = Session()
    
    # Deletar exames Pendente que não estão na lista atual da busca
    current_urls = {r['url'] for r in pdf_results}
    old_pending = session.query(Exam).filter_by(status='Pendente').all()
    for old in old_pending:
        if old.source_url not in current_urls:
            session.delete(old)
    session.commit()
    
    # Adicionar novos que ainda não existem
    for res in pdf_results:
        m_score = res.get('match_score', 0)
        existing = session.query(Exam).filter_by(source_url=res['url']).first()
        if not existing:
            new_exam = Exam(title=res['title'], source_url=res['url'], status='Pendente', match_score=m_score)
            session.add(new_exam)
        elif existing.status != 'Pendente':
            new_exam = Exam(title=res['title'] + ' (novo)', source_url=res['url'] + f'?v={existing.id}', status='Pendente', match_score=m_score)
            session.add(new_exam)
        else:
            # Update score if existing is still pending
            existing.match_score = m_score
    session.commit()
    
    pending_exams = session.query(Exam).filter_by(status='Pendente').all()
    # Retorna o match_score junto
    results = [{"id": e.id, "title": e.title, "url": e.source_url.split('?v=')[0], "match_score": e.match_score or 0} for e in pending_exams]
    session.close()
    
    return jsonify(results)

@app.route('/api/exams/<int:exam_id>/manual_pdf', methods=['POST'])
def manual_pdf(exam_id):
    data = request.json
    pdf_url = data.get('pdf_url')
    if not pdf_url:
        return jsonify({"error": "URL não fornecida."}), 400
        
    from datetime import datetime
    
    session = Session()
    exam = session.query(Exam).filter_by(id=exam_id).first()
    
    if not exam:
        session.close()
        return jsonify({"error": "Prova não encontrada."}), 404
        
    try:
        # Avoid SSL warnings and pretend to be Chrome
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        r = requests.get(pdf_url, headers=headers, verify=False, allow_redirects=True, timeout=30)
        if r.status_code != 200:
            return jsonify({"error": f"Falha ao baixar PDF (Status: {r.status_code}). Certifique-se de que o link é o link direto do arquivo."}), 400
            
        # Check if it's actually a PDF
        content_type = r.headers.get('Content-Type', '').lower()
        if 'pdf' not in content_type and not pdf_url.endswith('.pdf'):
            # Just a warning, we still save it just in case
            pass
            
        os.makedirs('pdfs', exist_ok=True)
        filename = f"{exam_id}_{int(datetime.now().timestamp())}.pdf"
        filepath = os.path.join('pdfs', filename)
        
        with open(filepath, 'wb') as f:
            f.write(r.content)
            
        # Configurar pasta e chamar processamento
        exam.pdf_path = filepath
        exam.status = 'Aprovada'
        
        clean_title = exam.title.replace('Prova - ', '').split('.')[0][:40]
        folder_name = clean_title if clean_title else f"Pasta Prova {exam.id}"
        
        folder = session.query(Folder).filter_by(name=folder_name).first()
        if not folder:
            folder = Folder(name=folder_name)
            session.add(folder)
            session.flush()
            
        exam.folder_id = folder.id
        
        exam_progress[exam.id] = {"status": "Iniciando processamento (manual)...", "progress": 5}
        try:
            success, error_msg = _real_scrape_exam(session, exam)
        except Exception as e:
            success, error_msg = False, f"Erro interno: {str(e)}"
            
        if not success:
            exam.status = 'Pendente'
            session.commit()
            session.close()
            return jsonify({"error": error_msg}), 400
            
        session.commit()
        session.close()
        
        return jsonify({"message": "Download manual concluído e processamento iniciado."})
        
    except Exception as e:
        return jsonify({"error": f"Erro interno ao processar o link: {str(e)}"}), 500



@app.route('/api/exams/<int:exam_id>/status', methods=['POST'])
def update_exam_status(exam_id):
    data = request.json
    new_status = data.get('status')
    
    session = Session()
    exam = session.query(Exam).filter_by(id=exam_id).first()
    if not exam:
        session.close()
        return jsonify({"success": False, "error": "Exam not found"})
        
    if new_status == 'Negada':
        session.delete(exam)
        session.commit()
        session.close()
        return jsonify({"success": True, "status": "Negada"})
        
    if new_status == 'Aprovada':
        exam.status = new_status
        
        clean_title = exam.title.replace('Prova - ', '').split('.')[0][:40]
        folder_name = clean_title if clean_title else f"Pasta Prova {exam.id}"
        
        folder = session.query(Folder).filter_by(name=folder_name).first()
        if not folder:
            folder = Folder(name=folder_name)
            session.add(folder)
            session.flush()
            
        exam.folder_id = folder.id
        
        exam_progress[exam_id] = {"status": "Iniciando processamento...", "progress": 5}
        try:
            success, error_msg = _real_scrape_exam(session, exam)
        except Exception as e:
            success, error_msg = False, f"Erro interno: {str(e)}"
            
        if not success:
            exam.status = 'Pendente'
            session.commit()
            session.close()
            return jsonify({"success": False, "error": error_msg})
            
        session.commit()
        result = {"success": True, "status": exam.status}
    else:
        exam.status = new_status
        session.commit()
        result = {"success": True, "status": exam.status}
        
    session.close()
    return jsonify(result)

def _real_scrape_exam(session, exam):
    """Baixa o PDF e usa o Gemini para extrair as questões."""
    if session.query(Question).filter_by(exam_id=exam.id).count() > 0:
        return True, ""
        
    exam.status = 'Aprovada'
    session.commit()
    exam_progress[exam.id] = {"status": "Iniciando...", "progress": 0}

    if "qconcursos.com" in exam.source_url:
        import threading
        def qc_bg_task(e_id, source_url):
            import app as _app
            from app import Session
            bg_session = Session()
            exam_progress = _app.exam_progress
            exam_progress[e_id] = {"status": "Extraindo questões via QConcursos (Login)...", "progress": 10}
            import subprocess, sys
            result = subprocess.run([sys.executable, 'qc_scraper.py', str(e_id), source_url], capture_output=True, text=True)
            bg_exam = bg_session.query(Exam).filter_by(id=e_id).first()
            if result.returncode == 0:
                exam_progress[e_id] = {"status": "Processamento concluído!", "progress": 100}
            else:
                err_msg = (result.stdout + result.stderr)[:100]
                exam_progress[e_id] = {"status": f"Erro QC: {err_msg}", "progress": -1}
                if bg_exam:
                    bg_exam.status = 'Erro'
            bg_session.commit()
            bg_session.close()
            
        t = threading.Thread(target=qc_bg_task, args=(exam.id, exam.source_url))
        t.start()
        session.close()
        return True, "Scraper do QConcursos iniciado usando a sessão salva. Acompanhe o progresso."

    api_key_val = get_gemini_key()
    if not api_key_val:
        session.close()
        print("GEMINI_API_KEY não configurada!")
        return False, "Chave GEMINI_API_KEY não configurada."
    
    if not exam.source_url:
        session.close()
        print("URL da prova não definida!")
        return False, "URL da prova vazia."
        
    try:
        # 1. Download PDF
        exam_progress[exam.id] = {"status": "Baixando prova original...", "progress": 15}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/pdf,*/*',
        }
        
        text = ""
        pdf_downloaded = False
        pdf_bytes = None
        
        # Check if PDF was already downloaded manually
        if hasattr(exam, 'pdf_path') and exam.pdf_path and os.path.exists(exam.pdf_path):
            print(f"Bypassing download, using existing PDF: {exam.pdf_path}")
            with open(exam.pdf_path, 'rb') as f:
                pdf_bytes = f.read()
        
        # Estratégia 1: requests simples com verify=False
        try:
            if not pdf_bytes:
                import warnings
                from urllib3.exceptions import InsecureRequestWarning
                warnings.filterwarnings('ignore', category=InsecureRequestWarning)
                
                req_session = requests.Session()
                req_session.headers.update(headers)
                url_to_download = exam.source_url
                
                if "pciconcursos.com.br/provas/download/" in url_to_download:
                    print(f"Buscando token atualizado do PCI para: {url_to_download}")
                    from bs4 import BeautifulSoup
                    res_pci = req_session.get(url_to_download, timeout=20, verify=False)
                    soup_pci = BeautifulSoup(res_pci.text, 'html.parser')
                    for link in soup_pci.select('a'):
                        arq = link.get('data-arquivo')
                        tok = link.get('data-code')
                        acao = link.get('data-acao')
                        if arq and tok and acao == 'baixar' and 'gabarito' not in arq.lower():
                            url_to_download = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
                            req_session.headers.update({'Referer': exam.source_url})
                            print(f"Token fresco obtido, baixando PDF...")
                            break
                
                r = req_session.get(url_to_download, timeout=30, allow_redirects=True, verify=False)
                r.raise_for_status()
                if r.headers.get('Content-Type', '').startswith('application/pdf') or r.content[:4] == b'%PDF':
                    pdf_bytes = r.content
                    print(f"PDF baixado via requests: {len(pdf_bytes)} bytes")
                else:
                    print(f"requests retornou {r.headers.get('Content-Type','?')} - nao e PDF")
        except Exception as e:
            print(f"requests falhou ({type(e).__name__}), tentando Playwright...")
        
        # Estratégia 2: Playwright com navegação real (bypass anti-bot completo)
        if not pdf_bytes:
            try:
                from playwright.sync_api import sync_playwright
                import tempfile as _tempfile
                dl_dir = _tempfile.mkdtemp(prefix="pw_dl_")
                
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=headers['User-Agent'],
                        accept_downloads=True,
                        ignore_https_errors=True
                    )
                    page = context.new_page()
                    
                    # Interceptar resposta da requisição PDF
                    captured = []
                    def handle_response(response):
                        ct = response.headers.get('content-type', '')
                        if 'pdf' in ct or response.url.lower().endswith('.pdf'):
                            try:
                                captured.append(response.body())
                            except Exception:
                                pass
                    
                    page.on('response', handle_response)
                    
                    try:
                        if "pciconcursos.com.br/provas/download/" in exam.source_url:
                            page.goto(exam.source_url, timeout=20000)
                            
                            # Esperar renderização dos links
                            try:
                                page.wait_for_selector("a.prova-pdf-link[data-acao='baixar']", timeout=15000)
                            except Exception:
                                pass # Tenta pegar mesmo assim
                                
                            # Pega os atributos direto do DOM para montar a URL
                            loc = page.locator("a.prova-pdf-link[data-acao='baixar']")
                            pdf_url = None
                            
                            links_to_try = []
                            for i in range(loc.count()):
                                arq = loc.nth(i).get_attribute("data-arquivo")
                                tok = loc.nth(i).get_attribute("data-code")
                                if arq and tok and "gabarito" not in arq.lower():
                                    links_to_try.append(f"https://www.pciconcursos.com.br/download/{arq}?token={tok}")
                            
                            print(f"Encontrados {len(links_to_try)} links de prova no PCI para testar.")
                            
                            for i, test_url in enumerate(links_to_try):
                                print(f"Tentando link {i+1}/{len(links_to_try)}: {test_url}")
                                
                                try:
                                    with page.expect_download(timeout=10000) as dl_info:
                                        page.goto(test_url)
                                    
                                    dl = dl_info.value
                                    import tempfile
                                    temp_path = os.path.join(tempfile.gettempdir(), f"pci_temp_{exam.id}_{i}.pdf")
                                    dl.save_as(temp_path)
                                    
                                    with open(temp_path, "rb") as f:
                                        body = f.read()
                                        
                                    if body[:4] == b'%PDF':
                                        print(f"PDF capturado com sucesso via download: {len(body)} bytes")
                                        pdf_url = test_url
                                        pdf_bytes = body
                                        break
                                    else:
                                        print("Download concluído mas não é um PDF válido.")
                                except Exception as e:
                                    print(f"Link falhou (provável 404 no PCI ou timeout): {type(e).__name__}")
                            
                            if not pdf_url:
                                raise Exception("Nenhum link PDF válido foi encontrado (todos deram erro ou 404).")
                        else:
                            # Caso não seja pci, podemos tentar o mesmo pra outros
                            r = context.request.get(exam.source_url, headers={'Referer': exam.source_url})
                            if r.status == 200:
                                pdf_bytes = r.body()
                                if pdf_bytes[:4] == b'%PDF':
                                    print(f"PDF capturado via context.request.get genérico: {len(pdf_bytes)} bytes")
                                else:
                                    raise Exception("Conteúdo genérico baixado não é um PDF válido.")
                            else:
                                raise Exception(f"Falha genérica no download: HTTP {r.status}")
                                    
                    except Exception as e:
                        last_error = str(e)
                        print(f"Erro Playwright get: {e}")
                    
                    browser.close()
            except Exception as e:
                last_error = str(e)
                print(f"Playwright falhou: {type(e).__name__}: {str(e)[:120]}")
        
        if pdf_bytes and pdf_bytes[:4] == b'%PDF':
            exam_progress[exam.id] = {"status": "Extraindo texto do PDF...", "progress": 30}
            try:
                import PyPDF2
                import io
                import tempfile
                pdf_file = io.BytesIO(pdf_bytes)
                reader = PyPDF2.PdfReader(pdf_file)
                total_pages = len(reader.pages)
                
                pdf_chunks = []
                pages_per_chunk = 5
                step_size = 4  # Sobreposição de 1 página (0-4, 4-8, 8-12...)
                temp_dir = tempfile.mkdtemp(prefix=f"exam_{exam.id}_")
                
                for i in range(0, total_pages, step_size):
                    writer = PyPDF2.PdfWriter()
                    for j in range(i, min(i + pages_per_chunk, total_pages)):
                        writer.add_page(reader.pages[j])
                    chunk_path = os.path.join(temp_dir, f"chunk_{i}.pdf")
                    with open(chunk_path, "wb") as f_out:
                        writer.write(f_out)
                    pdf_chunks.append(chunk_path)
                
                if pdf_chunks:
                    pdf_downloaded = True
                    print(f"PDF dividido em {len(pdf_chunks)} chunks para OCR.")
            except Exception as e:
                print(f"Erro ao processar PDF com PyPDF2: {e}")
                pdf_downloaded = False
        else:
            print(f"Nenhuma estrategia conseguiu baixar o PDF de: {exam.source_url}")
            pdf_downloaded = False
            
        # Em vez de processar sincronicamente, envia para a fila do Orchestrator
        task_ids = []
        if pdf_downloaded:
            exam_progress[exam.id] = {"status": f"Enviando {len(pdf_chunks)} blocos para IA...", "progress": 35, "total_chunks": len(pdf_chunks), "done_chunks": 0}
            for idx, chunk_path in enumerate(pdf_chunks):
                t_id = orchestrator.push_task(exam.id, "extract_questions", {"file_path": chunk_path, "attempts": 0, "chunk_info": f"{idx+1}/{len(pdf_chunks)}"})
                task_ids.append(t_id)
        else:
            exam_progress[exam.id] = {"status": "Site bloqueou o robô ou PDF saiu do ar.", "progress": -1, "error_type": "download_blocked"}
            return False, "O site oficial bloqueou nosso robô ou o PDF saiu do ar. Por favor, clique em 'Ignorar' neste e tente BAIXAR OUTRO LINK da lista!"
            
        # Processamento Assíncrono para não travar a UI
        import threading
        
        def background_processing(t_ids, e_id, source_url):
            bg_session = Session()
            bg_exam = bg_session.query(Exam).filter_by(id=e_id).first()
            if not bg_exam:
                bg_session.close()
                return
                
            if "qconcursos.com" in bg_exam.source_url:
                exam_progress[bg_exam.id] = {"status": "Extraindo questões via QConcursos (Login)...", "progress": 10}
                import subprocess, sys
                result = subprocess.run([sys.executable, 'qc_scraper.py', str(bg_exam.id), bg_exam.source_url], capture_output=True, text=True)
                if result.returncode == 0:
                    exam_progress[bg_exam.id] = {"status": "Processamento concluído!", "progress": 100}
                else:
                    err_msg = (result.stdout + result.stderr)[:100]
                    exam_progress[bg_exam.id] = {"status": f"Erro QC: {err_msg}", "progress": -1}
                    bg_exam.status = 'Erro'
                bg_session.commit()
                bg_session.close()
                return

            import time
            finished_tasks = {}
            start_wait = time.time()
            MAX_WAIT = 1800  # 30 minutos máximo para provas gigantes como ENEM
            total_chunks = len(t_ids)
            while len(finished_tasks) < len(t_ids):
                # Timeout de segurança
                elapsed = time.time() - start_wait
                if elapsed > MAX_WAIT:
                    exam_progress[e_id] = {"status": "Tempo limite excedido. Tente novamente.", "progress": -1, "error_type": "timeout"}
                    bg_session.close()
                    return
                
                for t in list(orchestrator.history):
                    if t.id in t_ids and t.id not in finished_tasks:
                        finished_tasks[t.id] = t
                
                # Progresso granular baseado em chunks reais (35% a 90%)
                done = len(finished_tasks)
                chunk_pct = 35 + int((done / total_chunks) * 55) if total_chunks > 0 else 55
                exam_progress[e_id] = {
                    "status": f"Extraindo questões ({done}/{total_chunks} blocos)...",
                    "progress": min(chunk_pct, 90),
                    "total_chunks": total_chunks,
                    "done_chunks": done
                }
                time.sleep(1)
                
            questoes = []
            has_error = False
            error_str = ""
            for t_id in t_ids:
                t = finished_tasks[t_id]
                if t.status == "erro":
                    has_error = True
                    error_str = t.error or "Erro desconhecido"
                    break
                if isinstance(t.result, list):
                    questoes.extend(t.result)
            
            if has_error:
                if "429" in error_str or "Quota" in error_str or "exhausted" in error_str.lower():
                    db_q = Question(
                        exam_id=bg_exam.id,
                        statement=f"⚠️ Limite gratuito da Inteligência Artificial excedido.\n\nAs questões não puderam ser extraídas automaticamente.\n\nLink original: {source_url}",
                        options=None,
                        correct_answer="Certo"
                    )
                    bg_session.add(db_q)
                    exam_progress[bg_exam.id] = {"status": "Limite da IA atingido. Aguarde 1 min ou adicione mais chaves.", "progress": -1, "error_type": "quota_exceeded"}
                elif "404" in error_str or "not found" in error_str.lower():
                    exam_progress[bg_exam.id] = {"status": "Modelo de IA indisponível. Verifique no Manager.", "progress": -1, "error_type": "model_not_found"}
                    bg_exam.status = 'Erro'
                else:
                    exam_progress[bg_exam.id] = {"status": f"Erro: {error_str[:60]}", "progress": -1, "error_type": "unknown"}
                    bg_exam.status = 'Erro'
            else:
                if not questoes:
                    exam_progress[bg_exam.id] = {"status": "A IA não conseguiu ler questões neste PDF.", "progress": -1, "error_type": "no_questions"}
                    bg_exam.status = 'Erro'
                else:
                    exam_progress[bg_exam.id] = {"status": "Salvando questões...", "progress": 90}
                    import re
                    import difflib
                    saved_count = 0
                    seen_questions = []
                    
                    for q in questoes:
                        enunciado = q.get('enunciado', '').strip()
                        if not enunciado: continue
                        
                        # Filtro Anti-Repetição Cirúrgico: 
                        # Usa apenas o FINAL do enunciado (últimos 150 caracteres).
                        # Isso ignora textos de apoio longos (que seriam iguais para várias questões)
                        # e foca na "pergunta" real. Ignoramos as opções para evitar falso-negativos caso a IA embaralhe a ordem.
                        normalized = re.sub(r'\W+', '', enunciado[-150:].lower())
                        
                        is_duplicate = False
                        for seen in seen_questions:
                            if difflib.SequenceMatcher(None, normalized, seen).ratio() > 0.85:
                                is_duplicate = True
                                break
                                
                        if is_duplicate:
                            continue
                            
                        seen_questions.append(normalized)
                        
                        enunciado = re.sub(r'\(?\s*(?:Correta|Gabarito|Resposta)\s*:\s*[A-E]\s*\)?', '', enunciado, flags=re.IGNORECASE).strip()
                        db_q = Question(
                            exam_id=bg_exam.id,
                            statement=enunciado,
                            options=json.dumps(q.get('opcoes'), ensure_ascii=False) if q.get('opcoes') else None,
                            correct_answer=str(q.get('resposta', 'A')).strip()[:10],
                            subject=str(q.get('disciplina', 'Geral')).strip()[:100],
                            images=json.dumps(q.get('images'), ensure_ascii=False) if q.get('images') else None
                        )
                        bg_session.add(db_q)
                        saved_count += 1
                        
                    if saved_count == 0:
                        exam_progress[bg_exam.id] = {"status": "Nenhuma questão legível encontrada no PDF.", "progress": -1, "error_type": "no_questions"}
                        bg_exam.status = 'Erro'
                    else:
                        exam_progress[bg_exam.id] = {"status": f"Concluído! {saved_count} questões extraídas.", "progress": 100}
                        bg_exam.status = 'Aprovada'
                    
            bg_session.commit()
            bg_session.close()

        threading.Thread(target=background_processing, args=(task_ids, exam.id, exam.source_url), daemon=True).start()
        
        return True, ""
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, f"Erro inesperado: {str(e)[:50]}"

@app.route('/api/notebook/stats', methods=['GET'])
def get_notebook_stats():
    session = Session()
    attempts = session.query(ExamAttempt).all()
    wrong_q_counts = {}
    
    for a in attempts:
        if not a.answers_json: continue
        try:
            answers = json.loads(a.answers_json)
            exam_q_list = session.query(Question).filter_by(exam_id=a.exam_id).order_by(Question.id).all()
            for idx_str, given_ans in answers.items():
                idx = int(idx_str)
                if idx < len(exam_q_list):
                    q = exam_q_list[idx]
                    if given_ans.strip().upper() != q.correct_answer.strip().upper():
                        subject = q.subject or 'Geral'
                        wrong_q_counts[subject] = wrong_q_counts.get(subject, 0) + 1
        except:
            pass
            
    session.close()
    
    # Sort subjects by error count descending
    stats = [{"subject": k, "count": v} for k, v in sorted(wrong_q_counts.items(), key=lambda x: x[1], reverse=True)]
    return jsonify(stats)

@app.route('/api/notebook', methods=['GET'])
def get_error_notebook():
    """Retorna uma 'prova' contendo apenas as questões que o usuário errou historicamente."""
    subject_filter = request.args.get('subject')
    session = Session()
    attempts = session.query(ExamAttempt).all()
    
    wrong_q_counts = {}
    
    for a in attempts:
        if not a.answers_json: continue
        try:
            answers = json.loads(a.answers_json)
            exam_q_list = session.query(Question).filter_by(exam_id=a.exam_id).order_by(Question.id).all()
            for idx_str, given_ans in answers.items():
                idx = int(idx_str)
                if idx < len(exam_q_list):
                    q = exam_q_list[idx]
                    if given_ans.strip().upper() != q.correct_answer.strip().upper():
                        wrong_q_counts[q.id] = wrong_q_counts.get(q.id, 0) + 1
        except:
            pass
            
    query = session.query(Question).filter(Question.id.in_(wrong_q_counts.keys()))
    if subject_filter:
        query = query.filter(Question.subject == subject_filter)
        
    questions = query.limit(100).all()
    
    q_data = [{
        "id": q.id, 
        "statement": q.statement, 
        "options": json.loads(q.options) if q.options else None,
        "correct_answer": q.correct_answer,
        "subject": q.subject or 'Geral',
        "error_count": wrong_q_counts.get(q.id, 1)
    } for q in questions]
    
    session.close()
    title_suffix = f" - {subject_filter}" if subject_filter else " (Todas as matérias)"
    return jsonify({
        "id": "notebook",
        "title": f"Caderno de Erros{title_suffix}",
        "questions": q_data
    })

@app.route('/api/generate_exam', methods=['POST'])
def generate_custom_exam():
    """Gera um simulado aleatório com base na quantidade pedida."""
    data = request.json or {}
    count = min(int(data.get('count', 20)), 100) # Max 100 questions
    
    session = Session()
    from sqlalchemy.sql.expression import func
    questions = session.query(Question).order_by(func.random()).limit(count).all()
    
    q_data = [{
        "id": q.id, 
        "statement": q.statement, 
        "options": json.loads(q.options) if q.options else None,
        "correct_answer": q.correct_answer,
        "subject": q.subject or 'Geral'
    } for q in questions]
    
    session.close()
    return jsonify({
        "id": "custom",
        "title": f"Simulado Personalizado ({len(questions)} questões)",
        "questions": q_data
    })


@app.route('/api/stats', methods=['GET'])
def get_global_stats():
    session = Session()
    attempts = session.query(ExamAttempt).all()
    
    total_exams = len(set(a.exam_id for a in attempts))
    total_questions = sum(a.total for a in attempts)
    total_correct = sum(a.score for a in attempts)
    global_accuracy = (total_correct / total_questions * 100) if total_questions > 0 else 0
    
    # Calculate streak based on created_at
    from datetime import datetime
    dates = set(a.created_at[:10] for a in attempts if a.created_at)
    dates_sorted = sorted(list(dates), reverse=True)
    streak = 0
    today = datetime.now().strftime('%Y-%m-%d')
    if dates_sorted and (dates_sorted[0] == today or (len(dates_sorted) > 0 and (datetime.now() - datetime.strptime(dates_sorted[0], '%Y-%m-%d')).days == 1)):
        for i in range(len(dates_sorted)):
            if i == 0:
                streak = 1
                continue
            prev_date = datetime.strptime(dates_sorted[i-1], '%Y-%m-%d')
            curr_date = datetime.strptime(dates_sorted[i], '%Y-%m-%d')
            if (prev_date - curr_date).days == 1:
                streak += 1
            else:
                break
    
    session.close()
    return jsonify({
        "total_exams": total_exams,
        "total_questions": total_questions,
        "total_correct": total_correct,
        "global_accuracy": round(global_accuracy, 1),
        "streak": streak
    })

@app.route('/api/orchestrator/status', methods=['GET'])
def get_orchestrator_status():
    return jsonify(orchestrator.get_status())

@app.route('/api/folders', methods=['GET'])
def get_folders():
    session = Session()
    folders = session.query(Folder).all()
    result = []
    for f in folders:
        exams_data = []
        for e in f.exams:
            if e.status != 'Aprovada':
                continue
            # Buscar stats de tentativas
            attempts = session.query(ExamAttempt).filter_by(exam_id=e.id).order_by(ExamAttempt.id.desc()).all()
            best_pct = max((a.percentage for a in attempts), default=None)
            last_pct = attempts[0].percentage if attempts else None
            attempt_count = len(attempts)
            exams_data.append({
                "id": e.id, "title": e.title,
                "best_score": round(best_pct, 1) if best_pct is not None else None,
                "last_score": round(last_pct, 1) if last_pct is not None else None,
                "attempt_count": attempt_count
            })
        if exams_data:
            result.append({"id": f.id, "name": f.name, "exams": exams_data})
            
    # Include orphaned exams as "Provas Avulsas"
    orphan_exams = session.query(Exam).filter_by(folder_id=None).all()
    orphan_data = []
    for e in orphan_exams:
        if e.status != 'Aprovada':
            continue
        attempts = session.query(ExamAttempt).filter_by(exam_id=e.id).order_by(ExamAttempt.id.desc()).all()
        best_pct = max((a.percentage for a in attempts), default=None)
        last_pct = attempts[0].percentage if attempts else None
        attempt_count = len(attempts)
        orphan_data.append({
            "id": e.id, "title": e.title,
            "best_score": round(best_pct, 1) if best_pct is not None else None,
            "last_score": round(last_pct, 1) if last_pct is not None else None,
            "attempt_count": attempt_count
        })
    if orphan_data:
        result.append({"id": "avulsas", "name": "Provas Avulsas", "exams": orphan_data})

    session.close()
    return jsonify(result)

@app.route('/api/qc/login', methods=['POST'])
def qc_login():
    import subprocess, sys
    try:
        subprocess.Popen([sys.executable, 'qc_auth.py'])
        return jsonify({"status": "Janela aberta! Faça o login no QConcursos na janela que apareceu."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/exams/<int:exam_id>', methods=['GET'])
def get_exam(exam_id):
    session = Session()
    exam = session.query(Exam).filter_by(id=exam_id).first()
    if not exam:
        session.close()
        return jsonify({"error": "Exam not found"}), 404
        
    questions = []
    for q in exam.questions:
        options_dict = json.loads(q.options) if q.options else None
        images_list = json.loads(q.images) if q.images else []
        questions.append({
            "id": q.id, 
            "statement": q.statement, 
            "options": options_dict,
            "correct_answer": q.correct_answer,
            "subject": getattr(q, 'subject', 'Geral') or 'Geral',
            "images": images_list
        })
        
    result = {
        "id": exam.id,
        "title": exam.title,
        "questions": questions
    }
    session.close()
    return jsonify(result)

@app.route('/api/exams/<int:exam_id>', methods=['DELETE'])
def delete_exam(exam_id):
    session = Session()
    exam = session.query(Exam).filter_by(id=exam_id).first()
    if not exam:
        session.close()
        return jsonify({"success": False}), 404
        
    folder_id = exam.folder_id
    session.delete(exam)  # cascade deletes questions
    
    # Se pasta ficar vazia, deletá-la também
    if folder_id:
        session.flush()
        remaining = session.query(Exam).filter_by(folder_id=folder_id).count()
        if remaining == 0:
            folder = session.query(Folder).filter_by(id=folder_id).first()
            if folder:
                session.delete(folder)
                
    session.commit()
    session.close()
    return jsonify({"success": True})

@app.route('/api/exams/<int:exam_id>/submit', methods=['POST'])
def submit_exam_score(exam_id):
    """Salva o resultado de uma tentativa da prova."""
    data = request.json
    session = Session()
    exam = session.query(Exam).filter_by(id=exam_id).first()
    if not exam:
        session.close()
        return jsonify({"error": "Prova não encontrada."}), 404
    
    from datetime import datetime
    attempt = ExamAttempt(
        exam_id=exam_id,
        score=data.get('score', 0),
        total=data.get('total', 0),
        percentage=data.get('percentage', 0.0),
        elapsed_seconds=data.get('elapsed_seconds', 0),
        answers_json=json.dumps(data.get('answers', {}), ensure_ascii=False),
        created_at=datetime.now().isoformat()
    )
    session.add(attempt)
    session.commit()
    attempt_id = attempt.id
    session.close()
    return jsonify({"success": True, "attempt_id": attempt_id})

@app.route('/api/exams/<int:exam_id>/history', methods=['GET'])
def get_exam_history(exam_id):
    """Retorna o histórico de tentativas de uma prova."""
    session = Session()
    attempts = session.query(ExamAttempt).filter_by(exam_id=exam_id).order_by(ExamAttempt.id.desc()).all()
    result = [{
        "id": a.id,
        "score": a.score,
        "total": a.total,
        "percentage": round(a.percentage, 1),
        "elapsed_seconds": a.elapsed_seconds,
        "created_at": a.created_at
    } for a in attempts]
    session.close()
    return jsonify(result)

@app.route('/api/config/keys_status', methods=['GET'])
def get_keys_status():
    """Testa cada chave da API e retorna o status."""
    session = Session()
    config = session.query(AppConfig).filter_by(key='GEMINI_API_KEY').first()
    session.close()
    
    if not config or not config.value:
        return jsonify({"keys": [], "message": "Nenhuma chave configurada."})
    
    keys = [k.strip() for k in config.value.split(',') if k.strip()]
    results = []
    
    for i, key in enumerate(keys):
        key_suffix = '...' + key[-4:] if len(key) > 4 else key
        try:
            from google import genai
            import orchestrator as orch_module
            client = genai.Client(api_key=key)
            model_name = orch_module.MODEL_CASCADE[-2]
            client.models.generate_content(model=model_name, contents='Olá')
            results.append({"index": i + 1, "suffix": key_suffix, "status": "active", "label": "Ativa"})
        except Exception as e:
            print(f"DEBUG EXCEPTION: {repr(e)}")
            err = str(e).lower()
            if '429' in str(e) or 'quota' in err or 'exhausted' in err or 'rate' in err:
                results.append({"index": i + 1, "suffix": key_suffix, "status": "exhausted", "label": "Esgotada"})
            else:
                results.append({"index": i + 1, "suffix": key_suffix, "status": "invalid", "label": "Inválida"})
    
    # Restaurar a chave ativa original do orchestrator
    if orchestrator.api_key_manager.keys:
        active_key = orchestrator.api_key_manager.keys[orchestrator.api_key_manager.current_index]
        genai.configure(api_key=active_key)
    
    return jsonify({"keys": results})

@app.route('/api/explain/<int:question_id>', methods=['POST'])
def explain_question(question_id):
    """Usa o Gemini para explicar o gabarito da questão."""
    session = Session()
    q = session.query(Question).filter_by(id=question_id).first()
    if not q:
        session.close()
        return jsonify({"error": "Questão não encontrada"}), 404
        
    data = request.json or {}
    user_answer = data.get('user_answer', 'Nenhuma')
    
    prompt = f"""
    Atue como um professor de cursinho focado em concursos públicos.
    Foi apresentada a seguinte questão de concurso:
    
    Enunciado: {q.statement}
    
    Alternativas disponíveis (se houver):
    {q.options}
    
    O gabarito oficial é: {q.correct_answer}
    O aluno marcou: {user_answer}
    
    Por favor, explique de forma didática e direta (em até 3 parágrafos curtos):
    1. Por que a alternativa {q.correct_answer} está correta (qual a base legal/teórica)?
    2. Por que a alternativa que o aluno marcou ({user_answer}) está errada (se ele tiver marcado uma diferente da correta).
    """
    
    session.close()
    
    # Obter a chave ativa e fazer a chamada
    try:
        from google import genai
        import orchestrator as orch_module
        from orchestrator import orchestrator
        client = orchestrator.api_key_manager.get_current_client()
        model_name = orch_module.MODEL_CASCADE[-2]
        response = client.models.generate_content(model=model_name, contents=prompt)
        explanation = response.text
        return jsonify({"explanation": explanation})
    except Exception as e:
        return jsonify({"error": f"Erro ao gerar explicação: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
