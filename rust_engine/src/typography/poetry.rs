//! Módulo de detecção e formatação tipográfica de versos e estrofes de poemas
use once_cell::sync::Lazy;
use regex::Regex;

pub static POEM_CUES_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)\b(?:poema|poesias?|versos?|estrofes?|soneto|trovas?|cantiga|can[çc][ãa]o|l[íi]ric[ao]|ode|quadras?|tercetos?|oitavas?|d[ée]cimas?|poeta|poetisa|haicai|haikai)\b"##).unwrap()
});

pub static FAMOUS_POETS_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)\b(?:Fernando\s+Pessoa|Lu[íi]z\s+Gonzaga|Cam[õo]es|Lu[íi]s\s+de\s+Cam[õo]es|Gon[çc]alves\s+Dias|Carlos\s+Drummond|Drummond|Manuel\s+Bandeira|Vinicius\s+de\s+Moraes|Castro\s+Alves|Cec[íi]lia\s+Meireles|Machado\s+de\s+Assis|Olavo\s+Bilac|Casimiro\s+de\s+Abreu|Augusto\s+dos\s+Anjos|Ferreira\s+Gullar|Humberto\s+Teixeira|Jo[ãa]o\s+Cabral)\b"##).unwrap()
});

pub static PROSE_PROMPT_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)^(?:Nos?\s+versos?|Nas?\s+estrofes?|No\s+poema|No\s+soneto|No\s+trecho|No\s+texto|No\s+fragmento|O\s+eu\s+(?:po[ée]tico|l[íi]rico)|O\s+autor|O\s+poeta\s+(?:narra|afirma|expressa|utiliza|reitera|sugere|cria)|A\s+partir|Com\s+base|Sobre\s+(?:o|a|os|as)|Em\s+rela[çc][ãa]o|De\s+acordo|Para\s+isso|Nesse\s+sentido|Considerando\s+o|Tendo\s+em\s+vista)\b"##).unwrap()
});

static OPTION_PREFIX_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"^(?:\([a-eA-E]\)|[a-eA-E][.)])\s+"##).unwrap()
});

static COMMAND_START_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)^(?:Assinale|Marque|Indique|Identifique|A\s+respeito|Considerando|Com\s+base|De\s+acordo|Julgue|Analise|O\s+texto|Em\s+rela[çc][ãa]o)\b"##).unwrap()
});

static ROMAN_START_LONG_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"^(?:I|II|III|IV|V|VI|VII|VIII|IX|X)\.\s+"##).unwrap()
});

static POEM_UNSQUASH_ASTERISKS_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"\*\s+\*([A-Za-z\u{00C0}-\u{00DC}0-9\"'\-])"##).unwrap()
});

static POEM_UNSQUASH_I_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)</i>\s*<i>([A-Za-z\u{00C0}-\u{00DC}0-9\"'\-])"##).unwrap()
});

static POEM_UNSQUASH_U_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)</u>\s*<u>([A-Za-z\u{00C0}-\u{00DC}0-9\"'\-])"##).unwrap()
});

pub static INTRO_COMMAND_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)^(?:Leia|Considere|Observe|Veja|Analise|Texto\s+para|Fragmento\s+de|Trecho\s+de)\b"##).unwrap()
});

/// Desaglutina tags de formatação coladas entre versos poéticos
pub fn unsquash_poem_lines(text: &str) -> String {
    let mut t = text.to_string();
    t = POEM_UNSQUASH_ASTERISKS_REGEX.replace_all(&t, "*\n*$1").into_owned();
    t = POEM_UNSQUASH_I_REGEX.replace_all(&t, "</i>\n<i>$1").into_owned();
    t = POEM_UNSQUASH_U_REGEX.replace_all(&t, "</u>\n<u>$1").into_owned();
    t
}

/// Identifica se a linha é uma citação de autor/obra no final de estrofe
pub fn is_author_attribution(line: &str) -> bool {
    let clean = line.trim().trim_matches(|c| c == '(' || c == ')' || c == '.' || c == ',' || c == '*' || c == '_' || c == '`');
    if clean.is_empty() {
        return false;
    }
    if FAMOUS_POETS_REGEX.is_match(clean) {
        return true;
    }
    let words: Vec<&str> = clean.split_whitespace().collect();
    if words.len() >= 2 && words.len() <= 6 && clean.chars().count() <= 60 {
        if words.iter().all(|w| w.chars().next().map(|c| c.is_uppercase()).unwrap_or(false) || w == &"de" || w == &"da" || w == &"do" || w == &"e") {
            return true;
        }
    }
    false
}

/// Determina se uma linha possui métrica e características de verso poético
pub fn is_verse_line(line: &str) -> bool {
    let l = line.trim();
    if l.is_empty() {
        return false;
    }
    let clean = l.trim_matches(|c| c == '*' || c == '_' || c == '`' || c == '"');
    if clean.is_empty() {
        return false;
    }
    if OPTION_PREFIX_REGEX.is_match(clean) {
        return false;
    }
    if COMMAND_START_REGEX.is_match(clean) {
        return false;
    }
    if PROSE_PROMPT_REGEX.is_match(clean) {
        return false;
    }
    if ROMAN_START_LONG_REGEX.is_match(clean) && clean.chars().count() > 60 {
        return false;
    }
    if l.starts_with("---") || l.starts_with("###") || l.starts_with("📖") || l.starts_with("**") {
        return false;
    }
    true
}

/// Avalia se um conjunto de linhas forma um bloco de estrofe poética
pub fn is_poem_stanza_block(lines: &[&str], has_poetic_context: bool) -> bool {
    if !has_poetic_context {
        return false;
    }

    let valid_lines: Vec<&str> = lines.iter().map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    if valid_lines.len() < 2 {
        return false;
    }

    if !valid_lines.iter().all(|l| is_verse_line(l)) {
        return false;
    }

    let char_counts: Vec<usize> = valid_lines.iter().map(|l| l.trim().trim_matches(|c| c == '*' || c == '_' || c == '`').chars().count()).collect();
    let total_chars: usize = char_counts.iter().sum();
    let avg_len = total_chars as f64 / valid_lines.len() as f64;
    let max_len = *char_counts.iter().max().unwrap_or(&0);

    avg_len <= 75.0 && max_len <= 85
}

/// Formata as linhas de uma estrofe em bloco Markdown com citação (>)
pub fn format_poem_stanza(lines: &[&str]) -> String {
    lines.iter()
        .map(|l| l.trim())
        .filter(|l| !l.is_empty())
        .map(|l| format!("> {}", l))
        .collect::<Vec<String>>()
        .join("\n")
}
