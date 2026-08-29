//! Módulo de limpeza de artefatos de OCR, ruídos de scraper e restauração lexical
use once_cell::sync::Lazy;
use regex::Regex;

static CAMEL_CASE_OCR_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"\b(o|a|os|as|do|da|dos|das|no|na|nos|nas|ao|aos|em|de|que|se|com|para|por|e|ou|um|uma|uns|umas|seu|sua|seus|suas|este|esta|estes|estas|esse|essa|esses|essas|aquele|aquela|aqueles|aquelas|cada|pelo|pela|pelos|pelas|sobre|entre|sem|sob|como|onde|quando|mais|menos|muito|muitos|muita|muitas|bem|mal|já|ainda|assim|qual|quais|qualquer|quaisquer|todo|toda|todos|todas|outro|outra|outros|outras)([A-Z\u{00C0}-\u{00DC}][a-z\u{00E0}-\u{00FC}0-9]+)\b"##
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

static OCR_BULLET_CORRUPT_B: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?m)^[ \t]*(?:\!P|\(p|\[p)\s+([A-Za-z\u{00C0}-\u{00DC}0-9"])"##).unwrap());
static OCR_BULLET_CORRUPT_C: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?m)^[ \t]*(?:lO|LO|\(o|\[o|\(g)\s+([A-Za-z\u{00C0}-\u{00DC}0-9"])"##).unwrap());
static OCR_BULLET_CORRUPT_D: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?m)^[ \t]*(?:/\-d|\(d)\s+([A-Za-z\u{00C0}-\u{00DC}0-9"])"##).unwrap());

static MULTI_OPT_INLINE_PAREN: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(\S)[ \t]+([b-eB-E]\))\s+"##).unwrap());
static MULTI_OPT_INLINE_ENCLOSED: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(\S)[ \t]+(\([b-eB-E]\))\s+"##).unwrap());
static MULTI_OPT_INLINE_DOT: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(\S)[ \t]+([b-eB-E]\.)\s+([A-Za-z\u{00C0}-\u{00DC}0-9"])"##).unwrap());

static HYPHEN_BREAK_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"([A-Za-z\u{00C0}-\u{00DC}]+)-\s*\n\s*([a-z\u{00E0}-\u{00FC}]+)"##).unwrap());
static PERCENT_ENCODING_BREAK_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"%\s*\n\s*([0-9A-Fa-f]{2})"##).unwrap());
static PERCENT_ENCODING_SPACE_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"%\s+([0-9A-Fa-f]{2})"##).unwrap());
static URL_LINE_BREAK_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(https?://[^\s\n\)]+)\s*\n\s*(%[0-9A-Fa-f]{2}|[a-zA-Z0-9\-_./?&=#@:+]+|\([^\)]+\))"##).unwrap());
static LAW_REF_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)\b(Norma\s+Regulamentadora|Norma|Lei|Decreto|Portaria|NR|Resolu[çc][ãa]o)\s*(?:n[º°o]?\.?)?\s*\n*\s*(\d+)\s*(:?)"##).unwrap());
static SEQ_DOS_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)\bsequ[êe]nciaos\b"##).unwrap());
static QUESTION_MARKS_GLITCH: Lazy<Regex> = Lazy::new(|| Regex::new(r##"\s*\?\?\s*"##).unwrap());
static MATCH_COLUMN_EN: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)\bMatch\s+column\s+(\d+|[I|V|X]+)\s*:?\s+(?:with|to|and)\s+column\s+(\d+|[I|V|X]+)\s*:?"##).unwrap());
static TABLE_LABELS_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)(?:^|\n|\s+)(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o)\s*[:.\-]?\s*(\(\d+\)|\(\s*_{1,4}\s*\))"##).unwrap());
static NUMERIC_PAREN_ATTACHED: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(\b\d+|[A-Za-z\u{00C0}-\u{00DC}])\s*(\(\d+\))"##).unwrap());
static NUMERIC_PAREN_TEXT_ATTACHED: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(\(\d+\))\s*([A-Za-z\u{00C0}-\u{00DC}])"##).unwrap());

static CLEANER_ARTIFACTS: Lazy<Vec<Regex>> = Lazy::new(|| {
    vec![
        Regex::new(r##"(?i)pcimarkpci[^\n]*"##).unwrap(),
        Regex::new(r##"(?i)www\.pciconcursos\.com\.br|qconcursos\.com"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n)\s*P[áa]gina\s+\d+\s+de\s+\d+"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n)\s*Oficial\s+de\s+Administra[çc][ãa]o\s*"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n)\s*IBAM\s*-\s*Concursos\s*"##).unwrap(),
        Regex::new(r##"(?i)[\u{E000}-\u{F8FF}]+"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n)\s*FGV\s+CONHECIMENTO\s*(?:\n|$)"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)TIPO\s+\d+\s*[-–—:]*\s*[A-ZÁ-Ú\s]+\s*[-–—:]*\s*P[ÁA]GINA\s+\d+\s*"##).unwrap(),
        Regex::new(r##"(?i)(?:^|\n|\s+)TIPO\s+[A-ZÁ-Ú\s]+\s*[-–—:]*\s*P[ÁA]GINA\s+\d+\s*"##).unwrap(),
        Regex::new(r##"(?i)(?:[-–—:]*\s*\b(?:TARDE|MANH[ÃA]|NOITE)\b|(?:\bATI\b|\bAnalista\b|\bOficial\b|\bT[ée]cnico\b)\s*[-–—:]*\s*[A-Za-z\u{00C0}-\u{00DC} \t,\-]{2,50}|\bRealiza[cç][aã]o\s+[A-Za-z]+|VFGVCONHECIMENTO|FGVCONHECIMENTO|EMPRESA\s+DE\s+TECNOLOGIA\s+E\s+INFORMA[ÇC][ÕO]ES\s+DA\s+PREVID[ÊE]NCIA\s*[-–—:]*\s*DATAPREV)"##).unwrap(),
    ]
});

/// Limpa ruídos recorrentes de scrapers, cabeçalhos repetidos e banners de matéria
pub fn clean_text_artifacts_native(text: &str) -> String {
    let mut res = text.to_string();
    for reg in CLEANER_ARTIFACTS.iter() {
        res = reg.replace_all(&res, "\n").into_owned();
    }
    res
}

/// Corrige palavras aglutinadas por erros de OCR e normaliza marcadores corrompidos
pub fn restore_ocr_lexical_spacing_native(text: &str) -> String {
    let mut t = text.to_string();

    t = CAMEL_CASE_OCR_REGEX.replace_all(&t, "$1 $2").into_owned();

    for (reg, repl) in MERGE_REPLACEMENTS.iter() {
        t = reg.replace_all(&t, *repl).into_owned();
    }

    t = OCR_BULLET_CORRUPT_B.replace_all(&t, "(B) $1").into_owned();
    t = OCR_BULLET_CORRUPT_C.replace_all(&t, "(C) $1").into_owned();
    t = OCR_BULLET_CORRUPT_D.replace_all(&t, "(D) $1").into_owned();

    t = MULTI_OPT_INLINE_PAREN.replace_all(&t, "$1\n\n$2 ").into_owned();
    t = MULTI_OPT_INLINE_ENCLOSED.replace_all(&t, "$1\n\n$2 ").into_owned();
    t = MULTI_OPT_INLINE_DOT.replace_all(&t, "$1\n\n$2 $3").into_owned();

    t
}

/// Executa a primeira etapa de normalização lexical e desaglutinação de elementos estruturais
pub fn preprocess_lexical_flow(text: &str) -> String {
    let mut t = text.to_string();

    t = HYPHEN_BREAK_REGEX.replace_all(&t, "$1$2").into_owned();
    t = PERCENT_ENCODING_BREAK_REGEX.replace_all(&t, "%$1").into_owned();
    t = PERCENT_ENCODING_SPACE_REGEX.replace_all(&t, "%$1").into_owned();
    t = URL_LINE_BREAK_REGEX.replace_all(&t, "$1$2").into_owned();

    t = LAW_REF_REGEX.replace_all(&t, "$1 $2$3").into_owned();
    t = SEQ_DOS_REGEX.replace_all(&t, "sequência dos").into_owned();
    t = QUESTION_MARKS_GLITCH.replace_all(&t, " ").into_owned();
    t = MATCH_COLUMN_EN.replace_all(&t, "Match column $1 with column $2:").into_owned();
    t = TABLE_LABELS_REGEX.replace_all(&t, "\n\n$1 ").into_owned();
    t = NUMERIC_PAREN_ATTACHED.replace_all(&t, "$1\n\n$2").into_owned();
    t = NUMERIC_PAREN_TEXT_ATTACHED.replace_all(&t, "$1 $2").into_owned();

    t
}
