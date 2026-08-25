//! concurse.io — Motor de Restauração Tipográfica e Limpeza de Textos em Rust
use once_cell::sync::Lazy;
use regex::Regex;

static CAMEL_CASE_OCR_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?i)\b(o|a|os|as|do|da|dos|das|no|na|nos|nas|ao|aos|em|de|que|se|com|para|por|e|ou|um|uma|uns|umas|seu|sua|seus|suas|este|esta|estes|estas|esse|essa|esses|essas|aquele|aquela|aqueles|aquelas|cada|pelo|pela|pelos|pelas|sobre|entre|sem|sob|como|onde|quando|mais|menos|muito|muitos|muita|muitas|bem|mal|já|ainda|assim|qual|quais|qualquer|quaisquer|todo|toda|todos|todas|outro|outra|outros|outras)([A-Z\u{00C0}-\u{00DC}][a-z\u{00E0}-\u{00FC}0-9]+)\b"##
    ).unwrap()
});

static MERGE_REPLACEMENTS: Lazy<Vec<(Regex, &'static str)>> = Lazy::new(|| {
    vec![
        (Regex::new(r##"(?i)\bAoutilizar\b"##).unwrap(), "Ao utilizar"),
        (Regex::new(r##"(?i)\bAareainsular\b"##).unwrap(), "A área insular"),
        (Regex::new(r##"(?i)\bAareatotal\b"##).unwrap(), "A área total"),
        (Regex::new(r##"(?i)\bdacidadede\b"##).unwrap(), "da cidade de"),
        (Regex::new(r##"(?i)\bdacidade\b"##).unwrap(), "da cidade"),
        (Regex::new(r##"(?i)\bdocaderno\b"##).unwrap(), "do caderno"),
        (Regex::new(r##"(?i)\bdodocumento\b"##).unwrap(), "do documento"),
        (Regex::new(r##"(?i)\bdeSantos\b"##).unwrap(), "de Santos"),
        (Regex::new(r##"(?i)\bdeSaoPaulo\b"##).unwrap(), "de São Paulo"),
        (Regex::new(r##"(?i)\bdoRiodeJaneiro\b"##).unwrap(), "do Rio de Janeiro"),
        (Regex::new(r##"(?i)\bnomunicipio\b"##).unwrap(), "no município"),
        (Regex::new(r##"(?i)\bdomunicipio\b"##).unwrap(), "do município"),
        (Regex::new(r##"(?i)\bdeacordo\b"##).unwrap(), "de acordo"),
        (Regex::new(r##"(?i)\bdeacordocom\b"##).unwrap(), "de acordo com"),
        (Regex::new(r##"(?i)\bdemaneira\b"##).unwrap(), "de maneira"),
        (Regex::new(r##"(?i)\bdeforma\b"##).unwrap(), "de forma"),
        (Regex::new(r##"(?i)\bapartir\b"##).unwrap(), "a partir"),
        (Regex::new(r##"(?i)\bapartirde\b"##).unwrap(), "a partir de"),
        (Regex::new(r##"(?i)\bpormeio\b"##).unwrap(), "por meio"),
        (Regex::new(r##"(?i)\bpormeiode\b"##).unwrap(), "por meio de"),
        (Regex::new(r##"(?i)\bcombase\b"##).unwrap(), "com base"),
        (Regex::new(r##"(?i)\bcombaseno\b"##).unwrap(), "com base no"),
        (Regex::new(r##"(?i)\bcombasena\b"##).unwrap(), "com base na"),
        (Regex::new(r##"(?i)\bcomrelação\b|\bcomrelacao\b"##).unwrap(), "com relação"),
        (Regex::new(r##"(?i)\bemrelação\b|\bemrelacao\b"##).unwrap(), "em relação"),
        (Regex::new(r##"(?i)\bnoentanto\b"##).unwrap(), "no entanto"),
        (Regex::new(r##"(?i)\bporisso\b"##).unwrap(), "por isso"),
        (Regex::new(r##"(?i)\bportanto\b"##).unwrap(), "portanto"),
        (Regex::new(r##"(?i)\balémdisso\b|\balemdisso\b"##).unwrap(), "além disso"),
        (Regex::new(r##"(?i)\batravésde\b|\batravesde\b"##).unwrap(), "através de"),
        (Regex::new(r##"(?i)\bécorreto\b|\becorreto\b"##).unwrap(), "é correto"),
        (Regex::new(r##"(?i)\béincorreto\b|\beincorreto\b"##).unwrap(), "é incorreto"),
        (Regex::new(r##"(?i)\bépossivel\b|\bépossível\b"##).unwrap(), "é possível"),
        (Regex::new(r##"(?i)\bénecessario\b|\bénecessário\b"##).unwrap(), "é necessário"),
        (Regex::new(r##"(?i)\bnãopode\b|\bnaopode\b"##).unwrap(), "não pode"),
        (Regex::new(r##"(?i)\bnãodeve\b|\bnaodeve\b"##).unwrap(), "não deve"),
        (Regex::new(r##"(?i)\bpodeser\b"##).unwrap(), "pode ser"),
        (Regex::new(r##"(?i)\bdeveser\b"##).unwrap(), "deve ser"),
        (Regex::new(r##"(?i)\bseráfeita\b|\bserafeita\b"##).unwrap(), "será feita"),
        (Regex::new(r##"(?i)\bseráfeito\b|\bserafeito\b"##).unwrap(), "será feito"),
        (Regex::new(r##"(?i)\btemcomo\b"##).unwrap(), "tem como"),
        (Regex::new(r##"(?i)\bassinaleaalternativa\b"##).unwrap(), "assinale a alternativa"),
        (Regex::new(r##"(?i)\bassinaleaalternativacorreta\b"##).unwrap(), "assinale a alternativa correta"),
        (Regex::new(r##"(?i)\bqualalternativa\b"##).unwrap(), "qual alternativa"),
        (Regex::new(r##"(?i)\bemqualalternativa\b"##).unwrap(), "em qual alternativa"),
        (Regex::new(r##"(?i)\bcomodados\b"##).unwrap(), "como dados"),
        (Regex::new(r##"(?i)\bcomoum\b"##).unwrap(), "como um"),
        (Regex::new(r##"(?i)\bcomouma\b"##).unwrap(), "como uma"),
        (Regex::new(r##"(?i)\bcomoe\b"##).unwrap(), "como e"),
        (Regex::new(r##"(?i)\bparaque\b"##).unwrap(), "para que"),
        (Regex::new(r##"(?i)\bparaum\b"##).unwrap(), "para um"),
        (Regex::new(r##"(?i)\bparauma\b"##).unwrap(), "para uma"),
    ]
});

static OCR_BULLET_CORRUPT_B: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?m)^[ \t]*(?:\!P|\(p|\[p)\s+(?=[A-Za-z\u{00C0}-\u{00DC}0-9"])"##).unwrap());
static OCR_BULLET_CORRUPT_C: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?m)^[ \t]*(?:lO|LO|\(o|\[o|\(g)\s+(?=[A-Za-z\u{00C0}-\u{00DC}0-9"])"##).unwrap());
static OCR_BULLET_CORRUPT_D: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?m)^[ \t]*(?:/\-d|\(d)\s+(?=[A-Za-z\u{00C0}-\u{00DC}0-9"])"##).unwrap());

static MULTI_OPT_INLINE_PAREN: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(\S)[ \t]+([b-eB-E]\))\s+"##).unwrap());
static MULTI_OPT_INLINE_ENCLOSED: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(\S)[ \t]+(\([b-eB-E]\))\s+"##).unwrap());
static MULTI_OPT_INLINE_DOT: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(\S)[ \t]+([b-eB-E]\.)\s+([A-Za-z\u{00C0}-\u{00DC}0-9"])"##).unwrap());

static URL_RAW_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(?:\(?[Ff]onte\s*:\s*)?https?://[^\s\)"]+(?:\s*(?:\n|\r\n)?\s*(?:%[0-9A-Fa-f]{2}|[a-zA-Z0-9\-_./?&=#])[^\s\)"]*)*\)?"##).unwrap()
});
static URL_EXTRACT_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)https?://[^\s\)"]+(?:\s*(?:\n|\r\n)?\s*(?:%[0-9A-Fa-f]{2}|[a-zA-Z0-9\-_./?&=#])[^\s\)"]*)*"##).unwrap()
});

static MULTI_SPACE_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"[ \t]{2,}"##).unwrap());
static HYPHEN_BREAK_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"([A-Za-z\u{00C0}-\u{00DC}]+)-\s*\n\s*([a-z\u{00E0}-\u{00FC}]+)"##).unwrap());
static LAW_REF_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)\b(Norma\s+Regulamentadora|Norma|Lei|Decreto|Portaria|NR|Resolu[çc][ãa]o)\s*(?:n[º°o]?\.?)?\s*\n*\s*(\d+)\s*(:?)"##).unwrap());
static SEQ_DOS_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)\bsequ[êe]nciaos\b"##).unwrap());
static QUESTION_MARKS_GLITCH: Lazy<Regex> = Lazy::new(|| Regex::new(r##"\s*\?\?\s*"##).unwrap());
static MATCH_COLUMN_EN: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)\bMatch\s+column\s+(\d+|[I|V|X]+)\s*:?\s+(?:with|to|and)\s+column\s+(\d+|[I|V|X]+)\s*:?"##).unwrap());
static TABLE_LABELS_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)(?:^|\n|\s+)(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o)\s*[:.\-]?\s*(?:\(\d+\)|\(\s*_{1,4}\s*\))"##).unwrap());

static SUB_ITEM_LETTERS_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n|[.;:\)]\s*|\s{2,})([A-E])\s*[.)]\s*([A-Z\u{00C0}-\u{00DC}"])"##).unwrap());
static ROMAN_NUMERALS_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n|[.;:\)]\s*|\s{2,}|\b)(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[.\-–—)]\s*([A-Z\u{00C0}-\u{00DC}"])"##).unwrap());
static GAP_FILL_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n|\s+)(\(\s*_{1,4}\s*\)|\(\s*\))\s*([A-Za-z\u{00C0}-\u{00DC}0-9"'\-])"##).unwrap());
static NUMERIC_PAREN_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n|[.;:\)]\s*|\s{2,}|\b)\((\d{1,2})\)\s*([A-Za-z\u{00C0}-\u{00DC}"])"##).unwrap());
static NUMERIC_INTERNAL_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n|[.;]\s+)(\d{1,2})\s*[.)]\s*([A-Z\u{00C0}-\u{00DC}"][A-Za-z\u{00C0}-\u{00DC}0-9\s]{3,})"##).unwrap());
static LEGAL_ARTICLES_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)(?:^|\n|\s+)(Art\.\s*\d+[º°\.]?|§\s*\d+[º°\.]?|Parágrafo\s+[ÚUúu]nico|Inciso\s+[I|V|X\d]+)\s*[:.\-]?\s*"##).unwrap());

static ORPHAN_PUNCT_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?m)^\s*[.,;:]\s*$"##).unwrap());
static DIALOGUE_DASH_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n)\s*([—–]\s+[A-Z\u{00C0}-\u{00DC}])"##).unwrap());
static DIVIDER_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n)\s*---+\s*(?:$|\n)"##).unwrap());
static DIVIDER_INLINE_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n)\s*---+\s+([^\n]+)"##).unwrap());
static ASTERISKS_ONLY_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?m)^\s*\*+\s*$"##).unwrap());
static MULTI_NEWLINES_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"\n{3,}"##).unwrap());

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

static CLEANER_ARTIFACTS: Lazy<Vec<Regex>> = Lazy::new(|| {
    vec![
        Regex::new(r##"(?i)pcimarkpci[^\n]*"##).unwrap(),
        Regex::new(r##"(?i)www\.pciconcursos\.com\.br|qconcursos\.com"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n)\s*P[áa]gina\s+\d+\s+de\s+\d+"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n)\s*Oficial\s+de\s+Administra[çc][ãa]o\s*"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n)\s*IBAM\s*-\s*Concursos\s*"##).unwrap(),
    ]
});

/// Limpa artefatos institucionais, marcas d'água de sites e ruídos de rodapé
pub fn clean_text_artifacts_native(text: &str) -> String {
    let mut res = text.to_string();
    for reg in CLEANER_ARTIFACTS.iter() {
        res = reg.replace_all(&res, "\n").into_owned();
    }
    res
}

/// Desacopla palavras aglutinadas por baixa resolução de scanner ou OCR
pub fn restore_ocr_lexical_spacing_native(text: &str) -> String {
    if text.is_empty() {
        return String::new();
    }

    let mut t = text.to_string();

    // 1. CamelCase OCR
    t = CAMEL_CASE_OCR_REGEX.replace_all(&t, "$1 $2").into_owned();

    // 2. Dicionário de aglutinações
    for (pat, repl) in MERGE_REPLACEMENTS.iter() {
        t = pat.replace_all(&t, *repl).into_owned();
    }

    // 3. Bullets corrompidos estritamente em início de linha
    t = OCR_BULLET_CORRUPT_B.replace_all(&t, "B) ").into_owned();
    t = OCR_BULLET_CORRUPT_C.replace_all(&t, "C) ").into_owned();
    t = OCR_BULLET_CORRUPT_D.replace_all(&t, "D) ").into_owned();

    // 4. Múltiplas opções na mesma linha
    t = MULTI_OPT_INLINE_PAREN.replace_all(&t, "$1\n\n$2 ").into_owned();
    t = MULTI_OPT_INLINE_ENCLOSED.replace_all(&t, "$1\n\n$2 ").into_owned();
    t = MULTI_OPT_INLINE_DOT.replace_all(&t, "$1\n\n$2 $3").into_owned();

    t
}

/// Restaura a tipografia editorial completa de questões e textos de apoio
pub fn restore_exam_typography_native(text: &str, is_option: bool) -> String {
    if text.is_empty() {
        return String::new();
    }

    let mut t = restore_ocr_lexical_spacing_native(text);

    // 1. Espaços excessivos
    t = MULTI_SPACE_REGEX.replace_all(&t, " ").into_owned();

    // 2. Recomposição de hifenização de quebra de linha
    t = HYPHEN_BREAK_REGEX.replace_all(&t, "$1$2").into_owned();

    // 2.1 Leis e normas
    t = LAW_REF_REGEX.replace_all(&t, "$1 $2$3").into_owned();

    // 2.2 Aglutinação específica
    t = SEQ_DOS_REGEX.replace_all(&t, "sequência dos").into_owned();

    // 3. Glitches de interrogação
    t = QUESTION_MARKS_GLITCH.replace_all(&t, " — ").into_owned();

    // Se for opção de resposta, consolida em linha única contínua
    if is_option {
        t = Regex::new(r##"\s*\n+\s*"##).unwrap().replace_all(&t, " ").into_owned();
        t = MULTI_SPACE_REGEX.replace_all(&t, " ").into_owned();
        return t.trim().to_string();
    }

    // 4. Comandos em inglês
    t = MATCH_COLUMN_EN.replace_all(&t, "\n\nMatch column $1 with column $2:\n\n").into_owned();

    // 4.1 Rótulos de tabela colados
    t = TABLE_LABELS_REGEX.replace_all(&t, "\n\n").into_owned();

    // 5. Desaglutinação de sub-itens de letras
    t = SUB_ITEM_LETTERS_REGEX.replace_all(&t, "\n\n$1. $2").into_owned();

    // 6. Comandos finais de questão
    for c_pat in COMMAND_PATTERNS.iter() {
        t = c_pat.replace_all(&t, "\n\n$1\n\n").into_owned();
    }

    // 7. Itens romanos
    t = ROMAN_NUMERALS_REGEX.replace_all(&t, "\n\n$1. $2").into_owned();

    // 8. Lacunas de preenchimento
    t = GAP_FILL_REGEX.replace_all(&t, "\n\n$1 $2").into_owned();

    // 9. Itens numéricos entre parênteses
    t = NUMERIC_PAREN_REGEX.replace_all(&t, "\n\n($1) $2").into_owned();

    // 10. Itens numéricos internos
    t = NUMERIC_INTERNAL_REGEX.replace_all(&t, "\n\n$1. $2").into_owned();

    // 11. Artigos de lei
    t = LEGAL_ARTICLES_REGEX.replace_all(&t, "\n\n$1 - ").into_owned();

fn percent_decode_utf8(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut decoded_bytes = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(h1), Some(h2)) = (s[i + 1..i + 3].chars().next(), s[i + 1..i + 3].chars().nth(1)) {
                if h1.is_ascii_hexdigit() && h2.is_ascii_hexdigit() {
                    if let Ok(val) = u8::from_str_radix(&s[i + 1..i + 3], 16) {
                        decoded_bytes.push(val);
                        i += 3;
                        continue;
                    }
                }
            }
        }
        decoded_bytes.push(bytes[i]);
        i += 1;
    }
    String::from_utf8(decoded_bytes).unwrap_or_else(|_| s.to_string())
}

    // 12.1 Limpeza e Isolamento de Links e Fontes Bibliográficas
    t = URL_RAW_REGEX.replace_all(&t, |caps: &regex::Captures| {
        let full = caps.get(0).unwrap().as_str();
        if let Some(m_url) = URL_EXTRACT_REGEX.find(full) {
            let mut raw_url = m_url.as_str().to_string();
            raw_url = raw_url.trim_matches(|c| c == '.' || c == ',' || c == ')' || c == '(' || c == ' ' || c == '\n' || c == '\r').to_string();
            raw_url = raw_url.split_whitespace().collect::<Vec<_>>().join("");
            if raw_url.contains('%') {
                raw_url = percent_decode_utf8(&raw_url);
            }
            format!("\n\n*(Fonte: {})*\n\n", raw_url)
        } else {
            full.to_string()
        }
    }).into_owned();

    // 13. Travessões de diálogo
    t = DIALOGUE_DASH_REGEX.replace_all(&t, "\n\n$1").into_owned();

    // 14. Divisores markdown
    t = DIVIDER_REGEX.replace_all(&t, "\n\n---\n\n").into_owned();
    t = DIVIDER_INLINE_REGEX.replace_all(&t, "\n\n---\n\n$1").into_owned();
    t = ASTERISKS_ONLY_REGEX.replace_all(&t, "\n").into_owned();

    // 15. Reconstrução de Parágrafos Fluidos
    let raw_blocks: Vec<&str> = t.split("\n\n").map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    let mut final_paras: Vec<String> = Vec::new();

    for block in raw_blocks {
        if block.starts_with("---")
            || block.starts_with("📖")
            || block.starts_with("**QUADRO")
            || block.starts_with("**Coluna")
            || block.starts_with("**Column")
            || block.starts_with("###")
            || block.starts_with("*(")
        {
            final_paras.push(block.to_string());
            continue;
        }

        let first_char = block.chars().next().unwrap_or(' ');
        if !final_paras.is_empty()
            && first_char.is_lowercase()
            && !final_paras.last().unwrap().starts_with("---")
            && !final_paras.last().unwrap().starts_with("📖")
        {
            let last_idx = final_paras.len() - 1;
            final_paras[last_idx] = format!("{} {}", final_paras[last_idx], block);
            continue;
        }

        let lines: Vec<&str> = block.split('\n').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
        let mut current_sub: Vec<String> = Vec::new();

        for line in lines {
            if current_sub.is_empty() {
                current_sub.push(line.to_string());
                continue;
            }

            let prev_line = current_sub.last().unwrap().clone();
            let is_prev_end = prev_line.ends_with('.') || prev_line.ends_with(':') || prev_line.ends_with('?') || prev_line.ends_with('!');
            let is_current_item = line.starts_with("I.") || line.starts_with("II.") || line.starts_with("III.") || line.starts_with("IV.") || line.starts_with("V.") || line.starts_with("(__)") || line.starts_with("(1)");

            if is_current_item || (is_prev_end && prev_line.len() > 30 && line.len() > 10) {
                final_paras.push(current_sub.join(" "));
                current_sub = vec![line.to_string()];
            } else {
                current_sub.push(line.to_string());
            }
        }
        if !current_sub.is_empty() {
            final_paras.push(current_sub.join(" "));
        }
    }

    let mut result = final_paras.join("\n\n");
    result = MULTI_SPACE_REGEX.replace_all(&result, " ").into_owned();
    result = MULTI_NEWLINES_REGEX.replace_all(&result, "\n\n").into_owned();

    result.trim().to_string()
}
