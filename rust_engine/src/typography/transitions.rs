//! Módulo de comandos de questão, frases de transição, artigos de lei e recomposição de sentenças pareadas
use once_cell::sync::Lazy;
use regex::Regex;

static COMMAND_PATTERNS: Lazy<Vec<Regex>> = Lazy::new(|| {
    vec![
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:Ap[óo]s\s+an[áa]lise\s*,?\s*)?(?:Assinale|Marque|Indique|Identifique)\s+(?:a\s+alternativa|a\s+op[çc][ãa]o|a\s+assertiva|a\s+proposi[çc][ãa]o|o\s+item|a\s+sequ[êe]ncia|o\s+que\s+se\s+pede|abaixo|corretamente|a\(s\)\s+afirmativa\(s\)|as\s+afirmativas|o\s+correto|o\s+incorreto)[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)(A\s+sequ[êe]ncia\s+(?:CORRETA|correta|INCORRETA|incorreta|adequada|certa)[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:Correlacione|Associe)\s+(?:corretamente|as\s+colunas|os\s+itens|a\s+coluna)[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:Match|Choose)\s+[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:Est[áa]\s*\([ãa]o\)\s+correta\s*\([s\)]\)|Est[ãa]o\s+corretas?|Est[áa]\s+correta?|Est[áa]\s+CORRETO|Est[ãa]o\s+CORRETAS?|S[ãa]o\s+corretas?|S[ãa]o\s+verdadeiras?|S[ãa]o\s+falsas?)[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:[ÉE]\s+correto|[ÉE]\s+INCORRETO|[ÉE]\s+verdadeiro|[ÉE]\s+falso|[ÉE]\s+adequado)\s+(?:afirmar|dizer|o\s+que\s+se\s+afirma|o\s+que\s+se\s+diz|apenas)[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:A\s+respeito\s+dessas?\s+afirmativas?|Quanto\s+[àa]s?\s+afirmativas?|Sobre\s+as\s+afirmativas?|Acerca\s+das\s+afirmativas?|Com\s+rela[çc][ãa]o\s+[àa]s\s+afirmativas?|Em\s+rela[çc][ãa]o\s+[àa]s\s+afirmativas?)[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:Julgue\s+os\s+itens|Analise\s+os\s+itens|Avalie\s+as\s+afirmativas|Considere\s+as\s+afirmativas)[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:Em\s+quais?|Quais?|Qual(?:\s+das?)?)\s+(?:afirmativas?|proposi[çc][õo]es|assertivas?|itens?|alternativas?|op[çc][õo]es|est[ãa]o|apresenta|cont[ée]m|delas|destas|dessas)[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
        Regex::new(r##"(?i)\b((?:De\s+acordo\s+com\s+o\s+texto|Com\s+base\s+no\s+texto|Segundo\s+o\s+texto)\s*,\s*(?:assinale|marque|indique|identifique|[ée]\s+correto|est[áa]\s+correto)[^\n]*?(?:[:\.\?]|$))"##).unwrap(),
    ]
});

static TRANSITION_PATTERNS: Lazy<Vec<Regex>> = Lazy::new(|| {
    vec![
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:Ess[ea]s?|Est[ea]s?|Ta[li]s?|Os|As|Cada|Tais)\s+(?:elementos|itens|conceitos|termos|defini[çc][õo]es|caracter[íi]sticas|situa[çc][õo]es|assertivas|proposi[çc][õo]es|fatores|aspectos|grupos|senten[çc]as|frases|palavras|express[õo]es|enunciados)\s+(?:correspondem|referem-se|dizem\s+respeito|apresentam|relacionam-se|est[ãa]o|s[ãa]o|possuem|t[êe]m|tratam)[^\n]*)"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:Associe|Relacione|Correlacione|Vincule)\s+(?:os\s+elementos|os\s+itens|as\s+colunas|os\s+termos|as\s+defini[çc][õo]es|as\s+frases|as\s+senten[çc]as|cada\s+um)[^\n]*)"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)((?:A\s+respeito|Em\s+rela[çc][ãa]o|Quanto)\s+(?:a\s+ess[ea]s|a\s+est[ea]s|aos\s+elementos|aos\s+itens|às\s+situa[çc][õo]es|às\s+defini[çc][õo]es)[^\n]*)"##).unwrap(),
    ]
});

static SLASH_CONTINUATION_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"\n+\s*(/\s+[A-Za-z\u{00C0}-\u{00DC}])"##).unwrap()
});

static LEGAL_ARTICLES_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(^|\n|[.;:]\s+|\s{2,}|\b[A-Za-z\u{00C0}-\u{00DC}]+\s+)(Art\.\s*\d+[º°\.]?|§\s*\d+[º°\.]?|Parágrafo\s+[ÚUúu]nico|Inciso\s+[I|V|X\d]+)\s*[:.\-]?\s*"##).unwrap()
});

static NARRATIVE_PREP_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(?:em\s+seu|no\s+seu|no|na|nos|nas|do|da|dos|das|pelo|pela|pelos|pelas|conforme|segundo|termos\s+do|disposto\s+no|previsto\s+no|com\s+base\s+no|sob\s+o|sobre\s+o|ao|aos|seu|sua|este|esta)\s*$"##).unwrap()
});

/// Isola comandos finais de questão
pub fn format_question_commands(text: &str) -> String {
    let mut t = text.to_string();
    for c_pat in COMMAND_PATTERNS.iter() {
        t = c_pat.replace_all(&t, "\n\n$1\n\n").into_owned();
    }
    t
}

/// Isola frases de transição e ligação entre enunciados e opções/lacunas
pub fn format_transition_phrases(text: &str) -> String {
    let mut t = text.to_string();
    for t_pat in TRANSITION_PATTERNS.iter() {
        t = t_pat.replace_all(&t, "\n\n$1\n\n").into_owned();
    }
    t
}

/// Recompõe quebras artificiais de pares de sentenças com barra (/)
pub fn repair_slash_continuations(text: &str) -> String {
    SLASH_CONTINUATION_REGEX.replace_all(text, " $1").into_owned()
}

/// Formata menções a artigos de leis com proteção de preposições narrativas
pub fn format_legal_articles(text: &str) -> String {
    LEGAL_ARTICLES_REGEX.replace_all(text, |caps: &regex::Captures| {
        let prefix = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let art = caps.get(2).map(|m| m.as_str()).unwrap_or("");
        if NARRATIVE_PREP_REGEX.is_match(prefix) {
            caps.get(0).unwrap().as_str().to_string()
        } else {
            format!("{}\n\n{} - ", prefix, art)
        }
    }).into_owned()
}
