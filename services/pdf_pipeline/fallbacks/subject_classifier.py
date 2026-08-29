import re
from typing import Optional

try:
    from ..native.rust_bridge import rust_classify_subject
except (ImportError, ValueError):
    try:
        from services.pdf_pipeline.native.rust_bridge import rust_classify_subject
    except ImportError:
        rust_classify_subject = lambda text: None

# Dicionário de matérias conhecidas em concursos públicos brasileiros (tolerante a encoding e variações)
SUBJECT_PATTERNS = [
    r'L[ÍI\ufffd\?]NGUA\s+PORTUGUESA', r'PORTUGU[ÊE\ufffd\?]S', r'PORTUGUES',
    r'INTERPRETA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+DE\s+TEXTO', r'GRAM[ÁA\ufffd\?]TICA', r'REDA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+OFICIAL',
    r'MATEM[ÁA\ufffd\?]TICA\s+E\s+RACIOC[ÍI\ufffd\?]NIO\s+L[ÓO\ufffd\?]GICO', r'MATEMATICA\s+E\s+RACIOCINIO\s+LOGICO',
    r'MATEM[ÁA\ufffd\?]TICA', r'MATEMATICA', r'MATEM[ÁA\ufffd\?]TICA\s+FINANCEIRA',
    r'RACIOC[ÍI\ufffd\?]NIO\s+L[ÓO\ufffd\?]GICO', r'RACIOCINIO\s+LOGICO',
    r'RACIOC[ÍI\ufffd\?]NIO\s+L[ÓO\ufffd\?]GICO-MATEM[ÁA\ufffd\?]TICO', r'RACIOCINIO\s+LOGICO-MATEMATICO',
    r'CONHECIMENTOS\s+B[ÁA\ufffd\?]SICOS', r'CONHECIMENTOS\s+BASICOS',
    r'CONHECIMENTOS\s+GERAIS', r'CONHECIMENTOS\s+ESPEC[ÍI\ufffd\?]FICOS', r'CONHECIMENTOS\s+ESPECIFICOS',
    r'CONHECIMENTOS\s+REGIONAIS',
    r'INFORM[ÁA\ufffd\?]TICA', r'INFORMATICA',
    r'NO[ÇC\ufffd\?][ÕO\ufffd\?]ES\s+DE\s+INFORM[ÁA\ufffd\?]TICA', r'NOCOES\s+DE\s+INFORMATICA',
    r'TECNOLOGIA\s+DA\s+INFORM[ÁA\ufffd\?]O', r'SEGURAN[ÇC\ufffd\?]A\s+DA\s+INFORM[ÁA\ufffd\?]O',
    r'BANCO\s+DE\s+DADOS', r'REDES\s+DE\s+COMPUTADORES', r'ENGENHARIA\s+DE\s+SOFTWARE',
    r'DIREITO\s+CONSTITUCIONAL', r'DIREITO\s+ADMINISTRATIVO', r'DIREITO\s+PENAL', r'DIREITO\s+CIVIL',
    r'DIREITO\s+PROCESSUAL', r'DIREITO\s+PROCESSUAL\s+CIVIL', r'DIREITO\s+PROCESSUAL\s+PENAL',
    r'DIREITO\s+TRIBUT[ÁA\ufffd\?]RIO', r'DIREITO\s+TRIBUTARIO',
    r'DIREITO\s+PREVIDENCI[ÁA\ufffd\?]RIO', r'DIREITO\s+PREVIDENCIARIO',
    r'DIREITO\s+DO\s+TRABALHO', r'DIREITO\s+PROCESSUAL\s+DO\s+TRABALHO',
    r'DIREITO\s+FINANCEIRO', r'DIREITO\s+AMBIENTAL', r'DIREITOS\s+HUMANOS',
    r'DIREITO\s+ELEITORAL', r'DIREITO\s+EMPRESARIAL',
    r'LEGISLA[ÇC\ufffd\?][ÃA\ufffd\?]O', r'LEGISLACAO', r'LEGISLA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+ESPEC[ÍI\ufffd\?]FICA', r'LEGISLACAO\s+ESPECIFICA',
    r'LEGISLA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+APLICADA', r'LEGISLA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+INSTITUCIONAL',
    r'[ÉE]TICA\s+NO\s+SERVI[ÇC]O\s+P[ÚU]BLICO', r'REGIMENTO\s+INTERNO', r'ESTATUTO\s+DOS\s+SERVIDORES',
    r'BLOCO\s+[I|V|X\d]+', r'M[ÓO]DULO\s+[I|V|X\d]+', r'PARTE\s+[I|V|X\d]+', r'ATUALIDADES',
    r'HIST[ÓO]RIA\s+E\s+GEOGRAFIA', r'GEOGRAFIA', r'HIST[ÓO]RIA',
    r'ADMINISTRA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+P[ÚU\ufffd\?]BLICA', r'ADMINISTRACAO\s+PUBLICA',
    r'ADMINISTRA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+GERAL', r'ADMINISTRACAO\s+GERAL',
    r'GEST[ÃA\ufffd\?]O\s+P[ÚU\ufffd\?]BLICA', r'GESTAO\s+PUBLICA',
    r'ADMINISTRA[ÇC\ufffd\?][ÃA\ufffd\?]O\s+FINANCEIRA\s+E\s+OR[ÇC]AMENT[ÁA]RIA', r'AFO',
    r'OR[ÇC]AMENTO\s+P[ÚU]BLICO', r'POL[ÍI]TICAS\s+P[ÚU]BLICAS',
    r'CONTABILIDADE', r'CONTABILIDADE\s+GERAL',
    r'CONTABILIDADE\s+P[ÚU\ufffd\?]BLICA', r'CONTABILIDADE\s+PUBLICA',
    r'AUDITORIA', r'ESTAT[ÍI\ufffd\?]STICA', r'ESTATISTICA', r'ECONOMIA', r'FINAN[ÇC]AS\s+P[ÚU]BLICAS',
    r'ENGENHARIA\s+CIVIL', r'ENGENHARIA\s+MEC[ÂA]NICA', r'ENGENHARIA\s+EL[ÉE]TRICA', r'ENGENHARIA',
    r'F[ÍI\ufffd\?]SICA', r'FISICA', r'QU[ÍI\ufffd\?]MICA', r'QUIMICA', r'BIOLOGIA',
    r'L[ÍI\ufffd\?]NGUA\s+INGLESA', r'INGL[ÊE\ufffd\?]S', r'INGLES',
    r'L[ÍI\ufffd\?]NGUA\s+ESPANHOLA', r'ESPANHOL',
    r'SEGURAN[ÇC\ufffd\?]A\s+P[ÚU\ufffd\?]BLICA', r'SEGURANCA\s+PUBLICA',
    r'CRIMINOLOGIA', r'MEDICINA\s+LEGAL',
    r'ARQUIVOLOGIA', r'RECURSOS\s+HUMANOS', r'GEST[ÃA]O\s+DE\s+PESSOAS',
    r'PEDAGOGIA', r'ENFERMAGEM', r'MEDICINA', r'SERVI[ÇC]O\s+SOCIAL', r'PSICOLOGIA'
]

SUBJECT_REGEX = re.compile(r'^\s*(?:<[^>]+>|\*{1,3}|_{1,3})*\s*(?:' + '|'.join(SUBJECT_PATTERNS) + r')(?:[ \t]*(?:<[^>]+>|\*{1,3}|_{1,3})*)*(?:\s*[-–—:]\s*.*)?\s*$', re.IGNORECASE)

def format_subject_title(raw_text: str) -> str:
    """Normaliza o nome da matéria para seu título canônico em português."""
    if not raw_text:
        return 'Geral'
    
    # 1. Consulta prioritária de altíssima velocidade em Rust
    rust_res = rust_classify_subject(raw_text)
    if rust_res and rust_res != 'Geral':
        return rust_res

    normalized = raw_text.strip()
    normalized_clean = re.sub(r'<[^>]+>|\*{1,3}|_{1,3}', ' ', normalized)
    normalized_clean = re.sub(r'[\ufffd\?]', '', normalized_clean)
    
    canonicos = [
        (r'L[ÍI]?NGUA\s+PORTUGUESA|PORTUGU[ÊE]?S|INTERPRETA[ÇC]?[ÃA]?O\s+DE\s+TEXTO|GRAM[ÁA]?TICA', 'Língua Portuguesa'),
        (r'MATEM[ÁA]?TICA\s+E\s+RACIOC[ÍI]?NIO\s+L[ÓO]?GICO', 'Matemática e Raciocínio Lógico'),
        (r'RACIOC[ÍI]?NIO\s+L[ÓO]?GICO-MATEM[ÁA]?TICO', 'Raciocínio Lógico-Matemático'),
        (r'RACIOC[ÍI]?NIO\s+L[ÓO]?GICO', 'Raciocínio Lógico'),
        (r'MATEM[ÁA]?TICA\s+FINANCEIRA', 'Matemática Financeira'),
        (r'MATEM[ÁA]?TICA', 'Matemática'),
        (r'CONHECIMENTOS\s+B[ÁA]?SICOS', 'Conhecimentos Básicos'),
        (r'CONHECIMENTOS\s+GERAIS', 'Conhecimentos Gerais'),
        (r'CONHECIMENTOS\s+ESPEC[ÍI]?FICOS', 'Conhecimentos Específicos'),
        (r'CONHECIMENTOS\s+REGIONAIS', 'Conhecimentos Regionais'),
        (r'NO[ÇC]?[ÕO]?ES\s+DE\s+INFORM[ÁA]?TICA', 'Noções de Informática'),
        (r'INFORM[ÁA]?TICA|TECNOLOGIA\s+DA\s+INFORM|CI[ÊE]NCIA\s+DE\s+DADOS', 'Informática'),
        (r'DIREITO\s+CONSTITUCIONAL', 'Direito Constitucional'),
        (r'DIREITO\s+ADMINISTRATIVO', 'Direito Administrativo'),
        (r'DIREITO\s+PENAL', 'Direito Penal'),
        (r'DIREITO\s+CIVIL', 'Direito Civil'),
        (r'DIREITO\s+PROCESSUAL\s+CIVIL', 'Direito Processual Civil'),
        (r'DIREITO\s+PROCESSUAL\s+PENAL', 'Direito Processual Penal'),
        (r'DIREITO\s+PROCESSUAL', 'Direito Processual'),
        (r'DIREITO\s+TRIBUT[ÁA]?RIO', 'Direito Tributário'),
        (r'DIREITO\s+PREVIDENCI[ÁA]?RIO', 'Direito Previdenciário'),
        (r'DIREITO\s+DO\s+TRABALHO', 'Direito do Trabalho'),
        (r'DIREITO\s+PROCESSUAL\s+DO\s+TRABALHO', 'Direito Processual do Trabalho'),
        (r'DIREITO\s+FINANCEIRO', 'Direito Financeiro'),
        (r'DIREITO\s+AMBIENTAL', 'Direito Ambiental'),
        (r'DIREITO\s+ELEITORAL', 'Direito Eleitoral'),
        (r'DIREITO\s+EMPRESARIAL', 'Direito Empresarial'),
        (r'DIREITOS\s+HUMANOS', 'Direitos Humanos'),
        (r'LEGISLA[ÇC]?[ÃA]?O\s+ESPEC[ÍI]?FICA', 'Legislação Específica'),
        (r'LEGISLA[ÇC]?[ÃA]?O\s+APLICADA', 'Legislação Aplicada'),
        (r'LEGISLA[ÇC]?[ÃA]?O\s+INSTITUCIONAL', 'Legislação Institucional'),
        (r'LEGISLA[ÇC]?[ÃA]?O', 'Legislação'),
        (r'[ÉE]TICA\s+NO\s+SERVI[ÇC]O\s+P[ÚU]BLICO|[ÉE]TICA', 'Ética no Serviço Público'),
        (r'REGIMENTO\s+INTERNO|ESTATUTO\s+DOS\s+SERVIDORES', 'Regimento Interno e Estatuto'),
        (r'ADMINISTRA[ÇC]?[ÃA]?O\s+P[ÚU]?BLICA', 'Administração Pública'),
        (r'ADMINISTRA[ÇC]?[ÃA]?O\s+GERAL', 'Administração Geral'),
        (r'GEST[ÃA]?O\s+P[ÚU]?BLICA', 'Gestão Pública'),
        (r'ADMINISTRA[ÇC]?[ÃA]?O\s+FINANCEIRA\s+E\s+OR[ÇC]AMENT[ÁA]RIA|AFO', 'AFO e Orçamento Público'),
        (r'OR[ÇC]AMENTO\s+P[ÚU]BLICO', 'Orçamento Público'),
        (r'CONTABILIDADE\s+P[ÚU]?BLICA', 'Contabilidade Pública'),
        (r'CONTABILIDADE\s+GERAL', 'Contabilidade Geral'),
        (r'CONTABILIDADE', 'Contabilidade'),
        (r'AUDITORIA', 'Auditoria'),
        (r'ESTAT[ÍI]?STICA', 'Estatística'),
        (r'ECONOMIA|FINAN[ÇC]AS\s+P[ÚU]BLICAS', 'Economia'),
        (r'ENGENHARIA\s+CIVIL', 'Engenharia Civil'),
        (r'ENGENHARIA\s+MEC[ÂA]NICA', 'Engenharia Mecânica'),
        (r'ENGENHARIA\s+EL[ÉE]TRICA', 'Engenharia Elétrica'),
        (r'ENGENHARIA', 'Engenharia'),
        (r'F[ÍI]?SICA', 'Física'),
        (r'QU[ÍI]?MICA', 'Química'),
        (r'BIOLOGIA', 'Biologia'),
        (r'L[ÍI]?NGUA\s+INGLESA|INGL[ÊE]?S', 'Língua Inglesa'),
        (r'L[ÍI]?NGUA\s+ESPANHOLA|ESPANHOL', 'Língua Espanhola'),
        (r'SEGURAN[ÇC]?A\s+P[ÚU]?BLICA', 'Segurança Pública'),
        (r'CRIMINOLOGIA', 'Criminologia'),
        (r'MEDICINA\s+LEGAL', 'Medicina Legal'),
        (r'ARQUIVOLOGIA', 'Arquivologia'),
        (r'RECURSOS\s+HUMANOS|GEST[ÃA]O\s+DE\s+PESSOAS', 'Recursos Humanos'),
        (r'PEDAGOGIA', 'Pedagogia'),
        (r'ENFERMAGEM', 'Enfermagem'),
        (r'MEDICINA', 'Medicina'),
        (r'SERVI[ÇC]O\s+SOCIAL', 'Serviço Social'),
        (r'PSICOLOGIA', 'Psicologia'),
        (r'ATUALIDADES', 'Atualidades'),
        (r'HIST[ÓO]RIA\s+E\s+GEOGRAFIA|HIST[ÓO]RIA|GEOGRAFIA', 'História e Geografia'),
        (r'BLOCO\s+([I|V|X\d]+)', r'Bloco \1'),
        (r'M[ÓO]DULO\s+([I|V|X\d]+)', r'Módulo \1'),
        (r'PARTE\s+([I|V|X\d]+)', r'Parte \1')
    ]
    for pat, canonical_name in canonicos:
        if re.search(pat, normalized_clean, re.IGNORECASE):
            if '\\1' in canonical_name:
                return re.sub(pat, canonical_name, normalized_clean, flags=re.IGNORECASE).strip()
            return canonical_name
    
    return normalized_clean.title() if normalized_clean else 'Geral'

# Alias para compatibilidade
_format_subject_title = format_subject_title
