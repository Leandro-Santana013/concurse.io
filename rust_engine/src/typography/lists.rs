//! Módulo de desaglutinação e formatação de listas, itens numéricos, romanos, letras e lacunas
use once_cell::sync::Lazy;
use regex::Regex;

static BULLET_ITEM_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?:^|\n|[:.;]\s*|\s{2,})([—–\-•])\s+([0-9A-Za-z\u{00C0}-\u{00DC}])"##).unwrap()
});

static SUB_ITEM_LETTERS_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?:^|\n|[.;:\)]\s*|\s{2,})([A-E])\s*[.)]\s*([A-Z\u{00C0}-\u{00DC}"])"##).unwrap()
});

static ROMAN_NUMERALS_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(^|\n|[.;:\)]\s*|\s{2,}|\b[A-Za-z\u{00C0}-\u{00DC}]+\s+)(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[.\-–—)]\s*([A-Z\u{00C0}-\u{00DC}"])"##).unwrap()
});

static SECTION_WORDS_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(?:Se[çc][ãa]o|Artigo|Art|Cap[íi]tulo|T[íi]tulo|Livro|Parte|Anexo|Item|Grupo|Classe|N[íi]vel|Fase|Bloco|Quadro|Tabela|Coluna|Volume|Edi[çc][ãa]o)\s*$"##).unwrap()
});

static GAP_FILL_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?:^|\n|\s+)(\(\s*_{1,4}\s*\)|\(\s*\))\s*([A-Za-z\u{00C0}-\u{00DC}0-9"'\-])"##).unwrap()
});

static NUMERIC_PAREN_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?:^|\n|[.;:\)]\s*|\s{2,}|\b)\((\d{1,2})\)\s*([A-Za-z\u{00C0}-\u{00DC}"])"##).unwrap()
});

static NUMBERED_ITEM_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(^|\n|[.;:\)]\s*|\s{2,})([1-9]|1[0-2])\s*[\.\)]\s*([A-Z\u{00C0}-\u{00DC}"])"##).unwrap()
});

/// Desaglutina itens de lista com marcadores (- , • , –)
pub fn format_bullet_items(text: &str) -> String {
    BULLET_ITEM_REGEX.replace_all(text, |caps: &regex::Captures| {
        let full = caps.get(0).unwrap().as_str();
        let bullet = caps.get(1).unwrap().as_str();
        let first_char = caps.get(2).unwrap().as_str();
        let lead_punct = if full.starts_with(':') {
            ":"
        } else if full.starts_with('.') {
            "."
        } else if full.starts_with(';') {
            ";"
        } else {
            ""
        };
        format!("{}\n\n{} {}", lead_punct, bullet, first_char)
    }).into_owned()
}

/// Desaglutina sub-itens de letras (A., B., C.)
pub fn format_sub_item_letters(text: &str) -> String {
    SUB_ITEM_LETTERS_REGEX.replace_all(text, "\n\n$1. $2").into_owned()
}

/// Desaglutina numerais romanos (I., II.) com proteção de palavras de seção
pub fn format_roman_items(text: &str) -> String {
    ROMAN_NUMERALS_REGEX.replace_all(text, |caps: &regex::Captures| {
        let prefix = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let roman = caps.get(2).map(|m| m.as_str()).unwrap_or("");
        let letter = caps.get(3).map(|m| m.as_str()).unwrap_or("");
        if SECTION_WORDS_REGEX.is_match(prefix) {
            caps.get(0).unwrap().as_str().to_string()
        } else {
            format!("{}\n\n{}. {}", prefix, roman, letter)
        }
    }).into_owned()
}

/// Desaglutina lacunas de preenchimento (__) e ( )
pub fn format_gap_fills(text: &str) -> String {
    GAP_FILL_REGEX.replace_all(text, "\n\n$1 $2").into_owned()
}

/// Desaglutina itens numéricos entre parênteses ((1), (2))
pub fn format_numeric_parentheses(text: &str) -> String {
    NUMERIC_PAREN_REGEX.replace_all(text, "\n\n($1) $2").into_owned()
}

/// Desaglutina itens numéricos (1., 2.) preservando pontuação precedente e palavras curtas
pub fn format_numbered_items(text: &str) -> String {
    NUMBERED_ITEM_REGEX.replace_all(text, |caps: &regex::Captures| {
        let lead = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let num = caps.get(2).map(|m| m.as_str()).unwrap_or("");
        let next_char = caps.get(3).map(|m| m.as_str()).unwrap_or("");
        let lead_punct = if lead.contains(';') { ";" } else { "" };
        format!("{}\n\n{}. {}", lead_punct, num, next_char)
    }).into_owned()
}
