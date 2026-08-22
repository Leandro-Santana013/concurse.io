//! concurse.io — Classificador Taxonômico e Detector de Seções de Disciplinas em Rust
use once_cell::sync::Lazy;
use regex::Regex;


pub static SUBJECT_RULES: Lazy<Vec<(Regex, &'static str)>> = Lazy::new(|| {
    vec![
        // Língua Portuguesa & Comunicação
        (Regex::new(r"(?i)\b(?:L[ÍI\?]?NGUA\s+PORTUGUESA|PORTUGU[ÊE\?]?S|INTERPRETA[ÇC\?][ÃA\?]?O\s+DE\s+TEXTO|GRAM[ÁA\?]?TICA|REDA[ÇC\?][ÃA\?]?O\s+OFICIAL)\b").unwrap(), "Língua Portuguesa"),
        
        // Raciocínio Lógico & Matemática
        (Regex::new(r"(?i)\b(?:RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO-MATEM[ÁA\?]?TICO|RACIOCINIO\s+LOGICO-MATEMATICO)\b").unwrap(), "Raciocínio Lógico-Matemático"),
        (Regex::new(r"(?i)\b(?:MATEM[ÁA\?]?TICA\s+E\s+RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO|MATEMATICA\s+E\s+RACIOCINIO\s+LOGICO)\b").unwrap(), "Matemática e Raciocínio Lógico"),
        (Regex::new(r"(?i)\b(?:RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO|RACIOCINIO\s+LOGICO)\b").unwrap(), "Raciocínio Lógico"),
        (Regex::new(r"(?i)\b(?:MATEM[ÁA\?]?TICA\s+FINANCEIRA|MATEMATICA\s+FINANCEIRA)\b").unwrap(), "Matemática Financeira"),
        (Regex::new(r"(?i)\b(?:MATEM[ÁA\?]?TICA|MATEMATICA)\b").unwrap(), "Matemática"),
        
        // Informática e Tecnologia
        (Regex::new(r"(?i)\b(?:NO[ÇC\?][ÕO\?]?ES\s+DE\s+INFORM[ÁA\?]?TICA|NOCOES\s+DE\s+INFORMATICA)\b").unwrap(), "Noções de Informática"),
        (Regex::new(r"(?i)\b(?:INFORM[ÁA\?]?TICA|INFORMATICA|TECNOLOGIA\s+DA\s+INFORM[AÃ\?]?O|CI[ÊE\?]?NCIA\s+DE\s+DADOS|SEGURAN[ÇC\?]?A\s+DA\s+INFORM[AÃ\?]?O|BANCO\s+DE\s+DADOS|REDES\s+DE\s+COMPUTADORES|ENGENHARIA\s+DE\s+SOFTWARE)\b").unwrap(), "Informática"),
        
        // Direito
        (Regex::new(r"(?i)\b(?:DIREITO\s+CONSTITUCIONAL)\b").unwrap(), "Direito Constitucional"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+ADMINISTRATIVO)\b").unwrap(), "Direito Administrativo"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+PROCESSUAL\s+CIVIL)\b").unwrap(), "Direito Processual Civil"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+PROCESSUAL\s+PENAL)\b").unwrap(), "Direito Processual Penal"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+PROCESSUAL\s+DO\s+TRABALHO)\b").unwrap(), "Direito Processual do Trabalho"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+PROCESSUAL)\b").unwrap(), "Direito Processual"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+PENAL\s+MILITAR)\b").unwrap(), "Direito Penal Militar"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+PENAL)\b").unwrap(), "Direito Penal"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+CIVIL)\b").unwrap(), "Direito Civil"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+TRIBUT[ÁA\?]?RIO|DIREITO\s+TRIBUTARIO)\b").unwrap(), "Direito Tributário"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+PREVIDENCI[ÁA\?]?RIO|DIREITO\s+PREVIDENCIARIO)\b").unwrap(), "Direito Previdenciário"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+DO\s+TRABALHO)\b").unwrap(), "Direito do Trabalho"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+FINANCEIRO)\b").unwrap(), "Direito Financeiro"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+AMBIENTAL)\b").unwrap(), "Direito Ambiental"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+ELEITORAL)\b").unwrap(), "Direito Eleitoral"),
        (Regex::new(r"(?i)\b(?:DIREITO\s+EMPRESARIAL|DIREITO\s+COMERCIAL)\b").unwrap(), "Direito Empresarial"),
        (Regex::new(r"(?i)\b(?:DIREITOS\s+HUMANOS)\b").unwrap(), "Direitos Humanos"),
        
        // Legislação e Normas
        (Regex::new(r"(?i)\b(?:LEGISLA[ÇC\?][ÃA\?]?O\s+ESPEC[ÍI\?]?FICA|LEGISLACAO\s+ESPECIFICA)\b").unwrap(), "Legislação Específica"),
        (Regex::new(r"(?i)\b(?:LEGISLA[ÇC\?][ÃA\?]?O\s+APLICADA|LEGISLACAO\s+APLICADA)\b").unwrap(), "Legislação Aplicada"),
        (Regex::new(r"(?i)\b(?:LEGISLA[ÇC\?][ÃA\?]?O\s+INSTITUCIONAL|LEGISLACAO\s+INSTITUCIONAL)\b").unwrap(), "Legislação Institucional"),
        (Regex::new(r"(?i)\b(?:LEGISLA[ÇC\?][ÃA\?]?O|LEGISLACAO)\b").unwrap(), "Legislação"),
        (Regex::new(r"(?i)\b(?:[ÉE\?]?TICA\s+NO\s+SERVI[ÇC\?]?O\s+P[ÚU\?]?BLICO|[ÉE\?]?TICA)\b").unwrap(), "Ética no Serviço Público"),
        (Regex::new(r"(?i)\b(?:REGIMENTO\s+INTERNO|ESTATUTO\s+DOS\s+SERVIDORES|ESTATUTO)\b").unwrap(), "Regimento Interno e Estatuto"),
        
        // Administração & Gestão
        (Regex::new(r"(?i)\b(?:ADMINISTRA[ÇC\?][ÃA\?]?O\s+FINANCEIRA\s+E\s+OR[ÇC\?]?AMENT[ÁA\?]?RIA|AFO)\b").unwrap(), "AFO e Orçamento Público"),
        (Regex::new(r"(?i)\b(?:OR[ÇC\?]?AMENTO\s+P[ÚU\?]?BLICO)\b").unwrap(), "Orçamento Público"),
        (Regex::new(r"(?i)\b(?:ADMINISTRA[ÇC\?][ÃA\?]?O\s+P[ÚU\?]?BLICA|ADMINISTRACAO\s+PUBLICA)\b").unwrap(), "Administração Pública"),
        (Regex::new(r"(?i)\b(?:ADMINISTRA[ÇC\?][ÃA\?]?O\s+GERAL|ADMINISTRACAO\s+GERAL)\b").unwrap(), "Administração Geral"),
        (Regex::new(r"(?i)\b(?:GEST[ÃA\?]?O\s+P[ÚU\?]?BLICA|GESTAO\s+PUBLICA)\b").unwrap(), "Gestão Pública"),
        (Regex::new(r"(?i)\b(?:GEST[ÃA\?]?O\s+DE\s+PESSOAS|RECURSOS\s+HUMANOS)\b").unwrap(), "Gestão de Pessoas"),
        (Regex::new(r"(?i)\b(?:POL[ÍI\?]?TICAS\s+P[ÚU\?]?BLICAS)\b").unwrap(), "Políticas Públicas"),
        (Regex::new(r"(?i)\b(?:ARQUIVOLOGIA)\b").unwrap(), "Arquivologia"),
        
        // Contabilidade & Finanças
        (Regex::new(r"(?i)\b(?:CONTABILIDADE\s+P[ÚU\?]?BLICA|CONTABILIDADE\s+PUBLICA)\b").unwrap(), "Contabilidade Pública"),
        (Regex::new(r"(?i)\b(?:CONTABILIDADE\s+GERAL)\b").unwrap(), "Contabilidade Geral"),
        (Regex::new(r"(?i)\b(?:CONTABILIDADE)\b").unwrap(), "Contabilidade"),
        (Regex::new(r"(?i)\b(?:AUDITORIA)\b").unwrap(), "Auditoria"),
        (Regex::new(r"(?i)\b(?:ECONOMIA|FINAN[ÇC\?]?AS\s+P[ÚU\?]?BLICAS)\b").unwrap(), "Economia"),
        (Regex::new(r"(?i)\b(?:ESTAT[ÍI\?]?STICA|ESTATISTICA)\b").unwrap(), "Estatística"),
        
        // Conhecimentos Gerais / Básicos / Específicos
        (Regex::new(r"(?i)\b(?:CONHECIMENTOS\s+B[ÁA\?]?SICOS|CONHECIMENTOS\s+BASICOS)\b").unwrap(), "Conhecimentos Básicos"),
        (Regex::new(r"(?i)\b(?:CONHECIMENTOS\s+ESPEC[ÍI\?]?FICOS|CONHECIMENTOS\s+ESPECIFICOS)\b").unwrap(), "Conhecimentos Específicos"),
        (Regex::new(r"(?i)\b(?:CONHECIMENTOS\s+REGIONAIS|HIST[ÓO\?]?RIA\s+E\s+GEOGRAFIA|GEOGRAFIA|HIST[ÓO\?]?RIA)\b").unwrap(), "Conhecimentos Gerais e Regionais"),
        (Regex::new(r"(?i)\b(?:CONHECIMENTOS\s+GERAIS|ATUALIDADES)\b").unwrap(), "Conhecimentos Gerais"),
        
        // Saúde & Biológicas
        (Regex::new(r"(?i)\b(?:ENFERMAGEM)\b").unwrap(), "Enfermagem"),
        (Regex::new(r"(?i)\b(?:MEDICINA\s+DO\s+TRABALHO|MEDICINA\s+LEGAL|MEDICINA)\b").unwrap(), "Medicina"),
        (Regex::new(r"(?i)\b(?:SA[ÚU\?]?DE\s+P[ÚU\?]?BLICA|SUS)\b").unwrap(), "Saúde Pública"),
        (Regex::new(r"(?i)\b(?:FARM[ÁA\?]?CIA|FARMACIA)\b").unwrap(), "Farmácia"),
        (Regex::new(r"(?i)\b(?:ODONTOLOGIA)\b").unwrap(), "Odontologia"),
        (Regex::new(r"(?i)\b(?:BIOLOGIA)\b").unwrap(), "Biologia"),
        (Regex::new(r"(?i)\b(?:PSICOLOGIA)\b").unwrap(), "Psicologia"),
        (Regex::new(r"(?i)\b(?:SERVI[ÇC\?]?O\s+SOCIAL)\b").unwrap(), "Serviço Social"),
        (Regex::new(r"(?i)\b(?:NUTRI[ÇC\?][ÃA\?]?O)\b").unwrap(), "Nutrição"),
        
        // Engenharias & Exatas
        (Regex::new(r"(?i)\b(?:ENGENHARIA\s+CIVIL)\b").unwrap(), "Engenharia Civil"),
        (Regex::new(r"(?i)\b(?:ENGENHARIA\s+EL[ÉE\?]?TRICA)\b").unwrap(), "Engenharia Elétrica"),
        (Regex::new(r"(?i)\b(?:ENGENHARIA\s+MEC[ÂA\?]?NICA)\b").unwrap(), "Engenharia Mecânica"),
        (Regex::new(r"(?i)\b(?:ENGENHARIA\s+AGRON[ÔO\?]?MICA|AGRONOMIA)\b").unwrap(), "Agronomia"),
        (Regex::new(r"(?i)\b(?:ENGENHARIA\s+AMBIENTAL)\b").unwrap(), "Engenharia Ambiental"),
        (Regex::new(r"(?i)\b(?:ENGENHARIA)\b").unwrap(), "Engenharia"),
        (Regex::new(r"(?i)\b(?:F[ÍI\?]?SICA|FISICA)\b").unwrap(), "Física"),
        (Regex::new(r"(?i)\b(?:QU[ÍI\?]?MICA|QUIMICA)\b").unwrap(), "Química"),
        
        // Educação & Humanas
        (Regex::new(r"(?i)\b(?:PEDAGOGIA|DID[ÁA\?]?TICA|LEGISLA[ÇC\?][ÃA\?]?O\s+EDUCACIONAL)\b").unwrap(), "Pedagogia e Educação"),
        
        // Línguas Estrangeiras
        (Regex::new(r"(?i)\b(?:L[ÍI\?]?NGUA\s+INGLESA|INGL[ÊE\?]?S|INGLES)\b").unwrap(), "Língua Inglesa"),
        (Regex::new(r"(?i)\b(?:L[ÍI\?]?NGUA\s+ESPANHOLA|ESPANHOL)\b").unwrap(), "Língua Espanhola"),
        
        // Segurança Pública
        (Regex::new(r"(?i)\b(?:SEGURAN[ÇC\?]?A\s+P[ÚU\?]?BLICA|CRIMINOLOGIA)\b").unwrap(), "Segurança Pública"),
    ]
});

/// Classifica deterministamente uma string crua para seu nome canônico
pub fn classify_subject_canonical(raw_text: &str) -> &'static str {
    let text = raw_text.trim();
    if text.is_empty() {
        return "Geral";
    }

    for (regex, canonical) in SUBJECT_RULES.iter() {
        if regex.is_match(text) {
            return canonical;
        }
    }

    "Geral"
}

/// Estrutura para representar seções de matérias identificadas no texto
#[derive(Debug, Clone)]
pub struct SubjectSection {
    pub raw_header: String,
    pub canonical_name: &'static str,
    pub start: usize,
    pub end: usize,
}

/// Escaneia todo o texto de uma prova em busca de banners de mudança de disciplina
pub fn scan_subject_sections(full_text: &str) -> Vec<SubjectSection> {
    use crate::patterns::SUBJECT_BANNER_REGEX;

    let mut sections = Vec::new();

    for cap in SUBJECT_BANNER_REGEX.captures_iter(full_text) {
        if let Some(m) = cap.get(0) {
            let raw = m.as_str().trim();
            let canonical = classify_subject_canonical(raw);
            if canonical != "Geral" {
                sections.push(SubjectSection {
                    raw_header: raw.to_string(),
                    canonical_name: canonical,
                    start: m.start(),
                    end: m.end(),
                });
            }
        }
    }

    sections
}
