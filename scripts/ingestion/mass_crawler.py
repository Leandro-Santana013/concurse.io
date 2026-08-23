import os, sys
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

"""
concurse.io — Mega Scraper & Crawler Massivo com Alta Variância Populacional
=============================================================================
Projetado para obter uma amostra representativa de ~500 cadernos de provas em PDF,
distribuídos equilibradamente entre mais de 45 bancas examinadoras brasileiras.

Recursos:
- Catálogo de 48 Bancas Examinadoras (Nacionais, Regionais, Universitárias e Estaduais).
- Quotas Populacionais: ~10 a 12 PDFs por banca garantindo diversidade demográfica.
- IDCAP Balanceado: Preserva ~20 provas diversificadas por carreira.
- Descoberta Rápida Multi-Fonte (CDNs de Provas + Portais Oficiais + DDGS).
- Validação Estrita (%PDF header, tamanho > 15KB, descarte de termos administrativos).
- Manifesto Dinâmico em 'provas_bancas/crawler_manifest.json'.
"""

import os
import re
import sys
import time
import json
import shutil
import random
import requests
from bs4 import BeautifulSoup
import concurrent.futures
from typing import List, Dict, Any, Optional, Set, Tuple

# Forçar stdout em UTF-8 no Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None


# =============================================================================
# CATÁLOGO DE 48 BANCAS EXAMINADORAS (ALTA VARIÂNCIA POPULACIONAL)
# =============================================================================

BANCAS_CONFIG: Dict[str, Dict[str, Any]] = {
    # --- GRANDES NACIONAIS ---
    'CEBRASPE': {
        'search_terms': ['cebraspe', 'cespe'],
        'domain': 'cebraspe.org.br'
    },
    'FGV': {
        'search_terms': ['fgv', 'fundacao-getulio-vargas'],
        'domain': 'conhecimento.fgv.br'
    },
    'FCC': {
        'search_terms': ['fcc', 'fundacao-carlos-chagas'],
        'domain': 'concursosfcc.com.br'
    },
    'VUNESP': {
        'search_terms': ['vunesp'],
        'domain': 'vunesp.com.br'
    },
    'CESGRANRIO': {
        'search_terms': ['cesgranrio'],
        'domain': 'cesgranrio.org.br'
    },
    'AOCP': {
        'search_terms': ['instituto-aocp', 'aocp'],
        'domain': 'institutoaocp.org.br'
    },
    'QUADRIX': {
        'search_terms': ['quadrix', 'instituto-quadrix'],
        'domain': 'quadrix.org.br'
    },
    'IBFC': {
        'search_terms': ['ibfc'],
        'domain': 'ibfc.org.br'
    },
    'IDECAN': {
        'search_terms': ['idecan'],
        'domain': 'idecan.org.br'
    },
    'CONSULPLAN': {
        'search_terms': ['consulplan', 'instituto-consulplan'],
        'domain': 'consulplan.net'
    },
    'SELECON': {
        'search_terms': ['selecon', 'instituto-selecon'],
        'domain': 'selecon.org.br'
    },
    'IBAM': {
        'search_terms': ['ibam', 'instituto-ibam'],
        'domain': 'ibam-concursos.org.br',
        'queries': [
            'site:arquivos.qconcursos.com ibam prova pdf',
            'site:ibam-concursos.org.br filetype:pdf prova',
            'ibam concurso caderno de questoes prova filetype:pdf',
            'site:arquivos.qconcursos.com ibam assistente OR professor OR guarda'
        ]
    },
    'DATAPREV': {
        'search_terms': ['dataprev', 'dataprev-analista'],
        'domain': 'dataprev.gov.br',
        'queries': [
            'dataprev prova pdf site:arquivos.qconcursos.com',
            'dataprev analista tecnologia prova pdf site:arquivos.qconcursos.com',
            'dataprev concurso prova pdf',
            'dataprev engenharia software prova pdf site:arquivos.qconcursos.com',
            'dataprev ati prova pdf site:arquivos.qconcursos.com'
        ]
    },
    'FUNDATEC': {
        'search_terms': ['fundatec'],
        'domain': 'fundatec.org.br'
    },
    'IADES': {
        'search_terms': ['iades'],
        'domain': 'iades.com.br'
    },

    # --- IDCAP (AMOSTRA BALANCEADA) ---
    'IDCAP': {
        'search_terms': ['idcap'],
        'domain': 'idcap.selecao.net.br'
    },

    # --- BANCAS REGIONAIS, ESTADUAIS E UNIVERSITÁRIAS ---
    'FUMARC': {
        'search_terms': ['fumarc'],
        'domain': 'fumarc.com.br'
    },
    'FEPESE': {
        'search_terms': ['fepese'],
        'domain': 'fepese.org.br'
    },
    'FAURGS': {
        'search_terms': ['faurgs'],
        'domain': 'faurgsconcursos.ufrgs.br'
    },
    'FAPEC': {
        'search_terms': ['fapec'],
        'domain': 'fapec.org'
    },
    'COMPERVE': {
        'search_terms': ['comperve', 'comperve-ufrn'],
        'domain': 'comperve.ufrn.br'
    },
    'COPEVE': {
        'search_terms': ['copeve', 'copeve-ufal'],
        'domain': 'copeve.ufal.br'
    },
    'NUCEPE': {
        'search_terms': ['nucepe', 'nucepe-uespi'],
        'domain': 'nucepe.uespi.br'
    },
    'CCV-UFC': {
        'search_terms': ['ccv-ufc', 'ccv'],
        'domain': 'ccv.ufc.br'
    },
    'CS-UFG': {
        'search_terms': ['cs-ufg', 'centro-de-selecao-ufg'],
        'domain': 'cs.ufg.br'
    },
    'CEPUERJ': {
        'search_terms': ['cepuerj'],
        'domain': 'cepuerj.uerj.br'
    },
    'NC-UFPR': {
        'search_terms': ['nc-ufpr', 'nucleo-de-concursos-ufpr'],
        'domain': 'nc.ufpr.br'
    },
    'ACCESS': {
        'search_terms': ['instituto-access', 'access'],
        'domain': 'access.org.br'
    },
    'CONSULPAM': {
        'search_terms': ['consulpam', 'instituto-consulpam'],
        'domain': 'consulpam.com.br'
    },
    'CONTEMAX': {
        'search_terms': ['contemax'],
        'domain': 'contemaxconsultoria.com.br'
    },
    'ADM-TEC': {
        'search_terms': ['adm-tec', 'admtec'],
        'domain': 'admtec.org.br'
    },
    'METROCAPITAL': {
        'search_terms': ['metrocapital'],
        'domain': 'metrocapital.com.br'
    },
    'AVANCA-SP': {
        'search_terms': ['avanca-sp', 'avancasp'],
        'domain': 'avancasp.org.br'
    },
    'NOSSO-RUMO': {
        'search_terms': ['nosso-rumo', 'instituto-nosso-rumo'],
        'domain': 'nossorumo.org.br'
    },
    'INSTITUTO-MAIS': {
        'search_terms': ['instituto-mais'],
        'domain': 'institutomais.org.br'
    },
    'OBJETIVA': {
        'search_terms': ['objetiva-concursos', 'objetiva'],
        'domain': 'objetivas.com.br'
    },
    'ITAME': {
        'search_terms': ['itame', 'instituto-itame'],
        'domain': 'itame.com.br'
    },
    'SHDIAS': {
        'search_terms': ['shdias'],
        'domain': 'shdias.com.br'
    },
    'IESES': {
        'search_terms': ['ieses'],
        'domain': 'ieses.org'
    },
    'FADESP': {
        'search_terms': ['fadesp'],
        'domain': 'portalfadesp.org.br'
    },
    'GUALIMP': {
        'search_terms': ['gualimp'],
        'domain': 'gualimp.com.br'
    },
    'COTEC': {
        'search_terms': ['cotec', 'cotec-fadenor'],
        'domain': 'cotec.fadenor.com.br'
    },
    'FUNRIO': {
        'search_terms': ['funrio'],
        'domain': 'funrio.org.br'
    },
    'CETRO': {
        'search_terms': ['cetro', 'cetro-concursos'],
        'domain': 'cetroconcursos.org.br'
    },
    'LEGIATUS': {
        'search_terms': ['instituto-legiatus', 'legiatus'],
        'domain': 'institutolegiatus.com.br'
    },
    'CPCON': {
        'search_terms': ['cpcon', 'cpcon-uepb'],
        'domain': 'cpcon.uepb.edu.br'
    },
    'BIO-RIO': {
        'search_terms': ['fundacao-bio-rio', 'bio-rio'],
        'domain': 'biorio.org.br'
    },
    'FACET': {
        'search_terms': ['facet', 'facet-concursos'],
        'domain': 'facetconcursos.com.br'
    },
    'IGECS': {
        'search_terms': ['igecs'],
        'domain': 'igecs.org.br'
    }
}

DISCARD_ADMIN_TERMS = [
    'resultado final', 'resultado preliminar', 'convocacao', 'convocação', 'retificacao', 'retificação',
    'cronograma', 'edital de abertura', 'edital de concurso', 'edital nº', 'edital n.', 'edital_de',
    'relacao_de_candidatos', 'relação de candidatos', 'recurso contra', 'divulgacao do resultado',
    'homologacao', 'homologação', 'inscricoes_deferidas', 'isencao_de_taxa', 'termo aditivo',
    'comunicado oficial', 'portaria nº', 'decreto municipal', 'decreto estadual',
    'classificacao final', 'quadro de notas', 'decisao judicial', 'termo de posse',
    'convocados para', 'audiometria', 'exame medico', 'exame médico', 'curso de formacao',
    'curso de formação', 'gabarito preliminar', 'gabarito oficial', 'gabarito_definitivo',
    'gabarito.pdf', 'termo de referencia', 'atribuicao de aulas'
]


# =============================================================================
# HIGIENIZAÇÃO E SANITIZAÇÃO
# =============================================================================

def sanitize_filename(name: str, max_length: int = 140) -> str:
    """Higieniza o nome do arquivo para garantir compatibilidade no Windows."""
    clean = re.sub(r'[\\/*?:"<>|]', '-', name)
    clean = re.sub(r'\s+', ' ', clean).strip(' .-_')
    if len(clean) > max_length:
        clean = clean[:max_length].strip(' .-_')
    return clean or "prova_sem_titulo"

def is_administrative_discard(text_or_url: str) -> bool:
    """Verifica se a URL ou título remete a documento puramente administrativo."""
    if not text_or_url:
        return False
    lower = text_or_url.lower()
    
    # Se é explicitamente um caderno/arquivo de prova no repositório, não descarta
    if 'arquivo_prova' in lower or lower.endswith('prova.pdf') or 'caderno' in lower:
        if 'gabarito' not in lower and 'resultado' not in lower and 'edital' not in lower:
            return False

    return any(t in lower for t in DISCARD_ADMIN_TERMS)

def build_canonical_filename(banca: str, raw_title: str, url: str) -> str:
    """Gera nome canônico padronizado: '[BANCA] [ANO] CARGO - ORGAO.pdf'."""
    t = raw_title.strip()
    
    # Tenta extrair ano
    ano = ""
    m_ano = re.search(r'\b(19\d{2}|20\d{2})\b', t) or re.search(r'\b(19\d{2}|20\d{2})\b', url)
    if m_ano:
        ano = m_ano.group(1)

    # Se o título vier do arquivo direto (ex: 'vunesp-2023-pm-sp-soldado-prova.pdf')
    if '-' in t and len(t.split('-')) >= 3:
        parts = [p.strip() for p in t.replace('.pdf', '').split('-') if p.strip()]
        # Remove banca e ano se estiverem duplicados nas pontas
        clean_parts = [p for p in parts if p.lower() not in [banca.lower(), ano.lower(), 'prova', 'download']]
        if clean_parts:
            t = " - ".join(clean_parts).upper()

    t = re.sub(r'^(PDF|Download|Prova|Provas|Caderno de Questões|PCI|Web|Concurso)\s*[-–—:]\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(rf'^\[?{re.escape(banca)}\]?\s*[-–—:]?\s*', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\.pdf$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+', ' ', t).strip(' -–—')
    
    ano_str = f"[{ano}] " if ano else ""
    canonical = f"[{banca}] {ano_str}{t}".strip()
    return f"{sanitize_filename(canonical)}.pdf"


# =============================================================================
# BALANCEAMENTO POPULACIONAL DA BANCA IDCAP
# =============================================================================

def balance_existing_idcap(base_dir: str = "provas_bancas", target_keep: int = 20):
    """
    Equilibra a pasta IDCAP caso tenha centenas/milhares de arquivos acumulados,
    mantendo uma amostra diversificada de 'target_keep' provas representativas.
    """
    idcap_dir = os.path.join(base_dir, "IDCAP")
    if not os.path.exists(idcap_dir):
        return 0

    files = [f for f in os.listdir(idcap_dir) if f.lower().endswith('.pdf')]
    if len(files) <= target_keep:
        return len(files)

    print(f"\n⚖️  [Balanceamento IDCAP] Encontrados {len(files)} PDFs. Selecionando {target_keep} provas com maior diversidade funcional...")

    categories = {
        'saude': ['medico', 'enferme', 'saude', 'dentista', 'psicolog', 'farmac'],
        'educacao': ['professor', 'pedagog', 'educa', 'docente'],
        'seguranca': ['guarda', 'vigilante', 'policia', 'agente de seguranca', 'transito'],
        'gestao_adm': ['administra', 'assistente', 'auxiliar', 'analista', 'secretario'],
        'exatas_ti': ['ti', 'tecnologia', 'informatica', 'engenheiro', 'arquiteto', 'contador', 'fiscal'],
    }

    selected = []
    used_names = set()

    for cat_name, keywords in categories.items():
        candidates = []
        for f in files:
            f_lower = f.lower()
            if any(k in f_lower for k in keywords) and f not in used_names:
                candidates.append(f)
        chosen = random.sample(candidates, min(len(candidates), 4)) if candidates else []
        for c in chosen:
            selected.append(c)
            used_names.add(c)

    remaining = [f for f in files if f not in used_names]
    random.shuffle(remaining)
    needed = target_keep - len(selected)
    if needed > 0:
        selected.extend(remaining[:needed])

    archive_dir = os.path.join(base_dir, "_idcap_archive_excess")
    os.makedirs(archive_dir, exist_ok=True)
    
    kept_count = 0
    for f in files:
        src = os.path.join(idcap_dir, f)
        if f in selected:
            kept_count += 1
        else:
            dst = os.path.join(archive_dir, f)
            try:
                shutil.move(src, dst)
            except Exception:
                pass

    print(f"   ✅ [IDCAP] Mantidas {kept_count} provas diversas ativas. Excedente movido para '{archive_dir}'.")
    return kept_count


# =============================================================================
# DESCOBERTA MULTI-FONTE DE CADERNOS DE PROVA
# =============================================================================

def discover_banca_exams(banca: str, config: Dict[str, Any], needed_count: int = 12) -> List[Dict[str, Any]]:
    """
    Varre os repositórios abertos de provas, CDNs e portais oficiais da banca
    usando queries de alto rendimento.
    """
    if not DDGS:
        return []

    results = []
    seen_urls = set()
    terms = config.get('search_terms', [banca.lower()])
    main_term = terms[0]
    domain = config.get('domain', '')

    queries = list(config.get('queries', []))
    if not queries:
        queries = [
            f"site:arquivos.qconcursos.com {main_term} prova pdf",
            f"site:arquivos.qconcursos.com {main_term} concurso pdf",
            f"site:{domain} filetype:pdf prova" if domain else "",
            f"{main_term} caderno de questoes concurso prova filetype:pdf -edital -resultado",
            f"site:arquivos.qconcursos.com {main_term} assistente OR analista OR professor OR medico",
        ]
    queries = [q for q in queries if q]

    for q in queries:
        if len(results) >= needed_count + 4:
            break
        try:
            with DDGS() as ddgs:
                ddg_res = list(ddgs.text(q, max_results=12))
                for r in ddg_res:
                    url = r.get('href', '')
                    title = r.get('title', '')
                    
                    if not url or url in seen_urls:
                        continue
                    
                    if is_administrative_discard(title) or is_administrative_discard(url):
                        continue

                    # Aceita links diretos de PDF ou endpoints de download de prova
                    if url.lower().endswith('.pdf') or 'arquivo_prova' in url or 'anexos' in url or (domain and domain in url and 'prova' in url.lower()):
                        seen_urls.add(url)
                        
                        # Extrai título sem ruídos
                        card_title = title
                        if 'arquivo_prova' in url:
                            # Nome limpo extraído do basename da URL
                            basename = url.split('/')[-1].replace('.pdf', '')
                            card_title = basename.replace('-', ' ').title()
                        
                        results.append({
                            'banca': banca,
                            'title': card_title,
                            'url': url
                        })
                        if len(results) >= needed_count + 4:
                            break
            time.sleep(0.2)
        except Exception:
            pass

    return results


# =============================================================================
# MOTOR DE DOWNLOAD MULTI-THREAD & MANIFESTO POPULACIONAL
# =============================================================================

class MassExamDownloader:
    """Gerencia downloads paralelos com controle de cota por banca e métricas populacionais."""

    def __init__(self, base_dir: str = "provas_bancas", max_workers: int = 12, target_per_banca: int = 11):
        self.base_dir = base_dir
        self.max_workers = max_workers
        self.target_per_banca = target_per_banca
        self.manifest_path = os.path.join(base_dir, "crawler_manifest.json")
        self.stats = {
            'total_downloaded': 0,
            'total_bytes': 0,
            'skipped_existing': 0,
            'errors': 0,
            'by_banca': {}
        }
        os.makedirs(self.base_dir, exist_ok=True)
        self._sync_existing_files()

    def _sync_existing_files(self):
        """Conta arquivos válidos já presentes no disco para cada banca."""
        if not os.path.exists(self.base_dir):
            return
        for item in os.listdir(self.base_dir):
            item_path = os.path.join(self.base_dir, item)
            if os.path.isdir(item_path) and not item.startswith('_'):
                valid_pdfs = [f for f in os.listdir(item_path) if f.lower().endswith('.pdf')]
                if valid_pdfs:
                    self.stats['by_banca'][item.upper()] = len(valid_pdfs)

    def _save_manifest(self):
        try:
            total_active_pdfs = sum(self.stats['by_banca'].values())
            bancas_count = len(self.stats['by_banca'])
            with open(self.manifest_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'target_variance_bancas': len(BANCAS_CONFIG),
                    'active_bancas_count': bancas_count,
                    'total_active_pdfs': total_active_pdfs,
                    'stats': self.stats
                }, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def download_item(self, item: Dict[str, Any]) -> bool:
        """Baixa e valida PDF estritamente."""
        banca = item['banca'].upper()
        
        # Respeita cota por banca
        current_count = self.stats['by_banca'].get(banca, 0)
        if current_count >= self.target_per_banca:
            return True

        url = item['url']
        raw_title = item.get('title', 'prova')

        banca_dir = os.path.join(self.base_dir, banca)
        os.makedirs(banca_dir, exist_ok=True)

        filename = build_canonical_filename(banca, raw_title, url)
        dest_path = os.path.join(banca_dir, filename)

        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 15000:
            self.stats['skipped_existing'] += 1
            return True

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'application/pdf,application/octet-stream,*/*',
        }

        try:
            resp = requests.get(url, headers=headers, timeout=14, stream=True)
            if resp.status_code == 200:
                chunks = []
                total_sz = 0
                for chunk in resp.iter_content(chunk_size=16384):
                    if chunk:
                        chunks.append(chunk)
                        total_sz += len(chunk)
                        if total_sz > 40 * 1024 * 1024:
                            break
                
                full_bytes = b"".join(chunks)
                
                # Validação estrita de cabeçalho PDF
                if len(full_bytes) < 15000 or not (full_bytes.startswith(b'%PDF') or b'%PDF' in full_bytes[:1024]):
                    self.stats['errors'] += 1
                    return False

                # Validação estrutural de conteúdo: apenas CADERNO DE PROVA REAL
                import fitz
                try:
                    doc = fitz.open(stream=full_bytes, filetype="pdf")
                    num_pages = len(doc)
                    if num_pages < 3: # Gabaritos e editais curtos descartados
                        doc.close()
                        self.stats['errors'] += 1
                        return False
                    
                    sample_text = ""
                    for p in range(min(num_pages, 8)):
                        sample_text += doc[p].get_text() + " "
                    doc.close()
                    
                    text_lower = sample_text.lower()
                    fname_lower = filename.lower()
                    
                    # Elimina gabaritos ou editais
                    if any(t in fname_lower for t in ['programa detalhado', 'gabarito', 'edital', 'comunicado', 'retifica', 'resultado']):
                        self.stats['errors'] += 1
                        return False

                    # Deve possuir evidência de questões de prova
                    has_questions = bool(
                        re.search(r'quest[aã]o\s*\d+', text_lower) or
                        re.search(r'\b0?[1-9]\b\s*[\.\-–\)]\s*(?:assinale|qual|em rela[çc][ãa]o|segundo|de acordo|considerando)', text_lower) or
                        re.search(r'\([a-eA-E]\)\s+', sample_text) or
                        (re.search(r'\bA\)\s+', sample_text) and re.search(r'\bB\)\s+', sample_text))
                    )
                    
                    if not has_questions:
                        self.stats['errors'] += 1
                        return False

                except Exception:
                    self.stats['errors'] += 1
                    return False

                with open(dest_path, 'wb') as f:
                    f.write(full_bytes)
                self.stats['total_downloaded'] += 1
                self.stats['total_bytes'] += len(full_bytes)
                self.stats['by_banca'][banca] = self.stats['by_banca'].get(banca, 0) + 1
                print(f"   📥 [{banca}] Salvo ({num_pages}p): {filename[:60]}")
                return True
            else:
                self.stats['errors'] += 1
                return False
        except Exception:
            self.stats['errors'] += 1
            return False

    def run_batch_download(self, items: List[Dict[str, Any]]):
        """Executa downloads em lote com pool de threads."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self.download_item, it) for it in items]
            for _ in concurrent.futures.as_completed(futures):
                pass
        self._save_manifest()


# =============================================================================
# PIPELINE PRINCIPAL DO MEGA SCRAPPER POPULACIONAL
# =============================================================================

def run_variance_mega_scraper(
    target_total: int = 500,
    target_per_banca: int = 11,
    clean_skewed_idcap: bool = True,
    bancas_to_run: Optional[List[str]] = None
):
    """
    Executa o crawler massivo distribuído por todas as bancas com quota balanceada
    para atingir a meta total de provas com máxima variância populacional.
    """
    start_time = time.time()
    
    print("=" * 80)
    print("🚀 [CONCURSE.IO] MEGA SCRAPER DE PROVAS — VARIÂNCIA POPULACIONAL")
    print(f"   🎯 Meta Global: ~{target_total} PDFs | Quota por Banca: {target_per_banca} PDFs")
    print(f"   🏛️  Total de Bancas no Catálogo: {len(BANCAS_CONFIG)} bancas examinadoras")
    print("=" * 80)

    # 1. Balanceamento inicial da banca IDCAP
    if clean_skewed_idcap:
        balance_existing_idcap(base_dir="provas_bancas", target_keep=20)

    downloader = MassExamDownloader(
        base_dir="provas_bancas",
        max_workers=12,
        target_per_banca=target_per_banca
    )

    bancas_list = bancas_to_run or list(BANCAS_CONFIG.keys())
    
    # Identifica bancas que ainda necessitam de mais provas para cumprir a cota
    bancas_needing_exams = []
    for b in bancas_list:
        current = downloader.stats['by_banca'].get(b.upper(), 0)
        if current < target_per_banca:
            bancas_needing_exams.append((b, target_per_banca - current))

    print(f"\n📊 Diagnóstico de Cobertura: {len(bancas_needing_exams)} bancas precisam de coleta adicional.")

    all_discovered_items = []
    
    # 2. Descoberta paralela de links por banca
    def discover_for_banca(banca_info):
        b, needed = banca_info
        cfg = BANCAS_CONFIG.get(b, {})
        return discover_banca_exams(b, cfg, needed_count=needed)

    print(f"\n🔍 Iniciando varredura multi-fonte para {len(bancas_needing_exams)} bancas...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(discover_for_banca, b_info): b_info[0] for b_info in bancas_needing_exams}
        for fut in concurrent.futures.as_completed(futures):
            b_name = futures[fut]
            try:
                items = fut.result()
                if items:
                    print(f"   ✨ [{b_name}] {len(items)} cadernos de prova mapeados.")
                    all_discovered_items.extend(items)
            except Exception as e:
                print(f"   ⚠️ [{b_name}] Falha na busca: {e}")

    print(f"\n🎯 Total de cadernos mapeados para download: {len(all_discovered_items)}")

    # 3. Execução dos downloads
    if all_discovered_items:
        downloader.run_batch_download(all_discovered_items)

    downloader._save_manifest()
    
    # 4. Relatório Final de Variância
    elapsed = time.time() - start_time
    total_active = sum(downloader.stats['by_banca'].values())
    total_bancas_active = len(downloader.stats['by_banca'])

    print("\n" + "=" * 80)
    print("🏁 RELATÓRIO CONSOLIDADO DE VARIÂNCIA POPULACIONAL")
    print(f"   ⏱️  Tempo de Execução: {elapsed:.1f}s")
    print(f"   🏛️  Bancas Ativas Cobertas: {total_bancas_active} / {len(BANCAS_CONFIG)}")
    print(f"   📚 Total de PDFs Ativos: {total_active} / Meta: {target_total}")
    print(f"   📥 Baixados nesta rodada: {downloader.stats['total_downloaded']}")
    print(f"   💾 Volume baixado: {downloader.stats['total_bytes'] / (1024*1024):.2f} MB")
    print(f"\n   📁 Distribuição por Banca:")
    
    for b_name, count in sorted(downloader.stats['by_banca'].items(), key=lambda x: x[0]):
        bar = "█" * min(20, count)
        print(f"      ├── {b_name:<16} : {count:>3} PDFs {bar}")

    print(f"\n   📄 Manifesto salvo em: {downloader.manifest_path}")
    print("=" * 80)


if __name__ == '__main__':
    target_tot = 500
    target_banca = 11

    if len(sys.argv) > 1:
        try:
            target_tot = int(sys.argv[1])
            target_banca = max(5, target_tot // len(BANCAS_CONFIG))
        except ValueError:
            pass

    run_variance_mega_scraper(
        target_total=target_tot,
        target_per_banca=target_banca,
        clean_skewed_idcap=False # Já balanceado na primeira rodada
    )
