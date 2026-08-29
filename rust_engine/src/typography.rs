//! concurse.io — Motor de Restauração Tipográfica e Limpeza de Textos em Rust
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

static URL_RAW_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(?:\*\([Ff]onte:\s*|\(?[Ff]onte\s*:\s*|\(?[Aa]cesso\s+em\s*:\s*)?(?:https?://|://)[a-zA-Z0-9\-_./%?&=#@:+ \u{00C0}-\u{00FC}]+(?:\([a-zA-Z0-9\-_\s./%?&=#@:+\u{00C0}-\u{00FC}]+\)[a-zA-Z0-9\-_./%?&=#@:+ \u{00C0}-\u{00FC}]*)*(?:\.pdf|\.html|\.php|[a-zA-Z0-9/])(?:\)\*|\))?"##).unwrap()
});
static URL_EXTRACT_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(?:https?://|://)[a-zA-Z0-9\-_./%?&=#@:+ \u{00C0}-\u{00FC}]+(?:\([a-zA-Z0-9\-_\s./%?&=#@:+\u{00C0}-\u{00FC}]+\)[a-zA-Z0-9\-_./%?&=#@:+ \u{00C0}-\u{00FC}]*)*(?:\.pdf|\.html|\.php|[a-zA-Z0-9/])"##).unwrap()
});

static MULTI_SPACE_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"[ \t]{2,}"##).unwrap());
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
static BULLET_ITEM_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?:^|\n|[:.;]\s*|\s{2,})([—–\-•])\s+([0-9A-Za-z\u{00C0}-\u{00DC}])"##).unwrap()
});

static SUB_ITEM_LETTERS_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n|[.;:\)]\s*|\s{2,})([A-E])\s*[.)]\s*([A-Z\u{00C0}-\u{00DC}"])"##).unwrap());
static ROMAN_NUMERALS_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(^|\n|[.;:\)]\s*|\s{2,}|\b[A-Za-z\u{00C0}-\u{00DC}]+\s+)(I|II|III|IV|V|VI|VII|VIII|IX|X)\s*[.\-–—)]\s*([A-Z\u{00C0}-\u{00DC}"])"##).unwrap());
static SECTION_WORDS_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)(?:Se[çc][ãa]o|Artigo|Art|Cap[íi]tulo|T[íi]tulo|Livro|Parte|Anexo|Item|Grupo|Classe|N[íi]vel|Fase|Bloco|Quadro|Tabela|Coluna|Volume|Edi[çc][ãa]o)\s*$"##).unwrap());
static GAP_FILL_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n|\s+)(\(\s*_{1,4}\s*\)|\(\s*\))\s*([A-Za-z\u{00C0}-\u{00DC}0-9"'\-])"##).unwrap());
static NUMERIC_PAREN_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n|[.;:\)]\s*|\s{2,}|\b)\((\d{1,2})\)\s*([A-Za-z\u{00C0}-\u{00DC}"])"##).unwrap());
static NUMERIC_INTERNAL_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n|[.;]\s+)(\d{1,2})\s*[.)]\s*([A-Z\u{00C0}-\u{00DC}"][A-Za-z\u{00C0}-\u{00DC}0-9\s]{3,})"##).unwrap());
static LEGAL_ARTICLES_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)(^|\n|[.;:]\s+|\s{2,}|\b[A-Za-z\u{00C0}-\u{00DC}]+\s+)(Art\.\s*\d+[º°\.]?|§\s*\d+[º°\.]?|Parágrafo\s+[ÚUúu]nico|Inciso\s+[I|V|X\d]+)\s*[:.\-]?\s*"##).unwrap());
static NARRATIVE_PREP_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?i)(?:em\s+seu|no\s+seu|no|na|nos|nas|do|da|dos|das|pelo|pela|pelos|pelas|conforme|segundo|termos\s+do|disposto\s+no|previsto\s+no|com\s+base\s+no|sob\s+o|sobre\s+o|ao|aos|seu|sua|este|esta)\s*$"##).unwrap());

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

static POEM_CUES_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)\b(?:poema|poesias?|versos?|estrofes?|soneto|trovas?|cantiga|can[çc][ãa]o|l[íi]ric[ao]|ode|quadras?|tercetos?|oitavas?|d[ée]cimas?|poeta|poetisa|haicai|haikai)\b"##).unwrap()
});

static FAMOUS_POETS_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)\b(?:Fernando\s+Pessoa|Lu[íi]z\s+Gonzaga|Cam[õo]es|Lu[íi]s\s+de\s+Cam[õo]es|Gon[çc]alves\s+Dias|Carlos\s+Drummond|Drummond|Manuel\s+Bandeira|Vinicius\s+de\s+Moraes|Castro\s+Alves|Cec[íi]lia\s+Meireles|Machado\s+de\s+Assis|Olavo\s+Bilac|Casimiro\s+de\s+Abreu|Augusto\s+dos\s+Anjos|Ferreira\s+Gullar|Humberto\s+Teixeira|Jo[ãa]o\s+Cabral)\b"##).unwrap()
});

static PROSE_PROMPT_REGEX: Lazy<Regex> = Lazy::new(|| {
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

static VERSE_NUMBER_PREFIX_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"^(?:\d{1,2}\s+|\[\d{1,2}\]\s*|\(\d{1,2}\)\s*)"##).unwrap()
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

static INTRO_COMMAND_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)^(?:Leia|Considere|Observe|Veja|Analise|Texto\s+para|Fragmento\s+de|Trecho\s+de)\b"##).unwrap()
});

static AUTHOR_ATTRIBUTION_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)^\s*(?:\([A-Za-z\u{00C0}-\u{00DC}\d\s\.,–—\-\:\/\"'“”‘’]+\)|(?:Fonte|Dispon[íi]vel|In|Extra[íi]do|Fragmento|Trecho|Texto)\s*[:\.]|[-–—]\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*$"##).unwrap()
});

fn unsquash_poem_lines(block: &str) -> String {
    let s1 = POEM_UNSQUASH_ASTERISKS_REGEX.replace_all(block, "*\n*$1");
    let s2 = POEM_UNSQUASH_I_REGEX.replace_all(&s1, "</i>\n<i>$1");
    let s3 = POEM_UNSQUASH_U_REGEX.replace_all(&s2, "</u>\n<u>$1");
    s3.to_string()
}

fn is_author_attribution(line: &str) -> bool {
    let l = line.trim().trim_matches(|c| c == '*' || c == '_' || c == '`');
    if l.is_empty() {
        return false;
    }
    if AUTHOR_ATTRIBUTION_REGEX.is_match(l) {
        return true;
    }
    if l.chars().count() <= 45 && FAMOUS_POETS_REGEX.is_match(l) {
        return true;
    }
    false
}

fn is_verse_line(line: &str) -> bool {
    let l = line.trim().trim_matches(|c| c == '*' || c == '_' || c == '`');
    if l.is_empty() || l.chars().count() > 85 {
        return false;
    }
    if OPTION_PREFIX_REGEX.is_match(l) || COMMAND_START_REGEX.is_match(l) || PROSE_PROMPT_REGEX.is_match(l) || is_author_attribution(l) {
        return false;
    }
    if ROMAN_START_LONG_REGEX.is_match(l) && l.chars().count() > 60 {
        return false;
    }
    if l.starts_with("---") || l.starts_with("###") || l.starts_with("📖") || l.starts_with("**") {
        return false;
    }
    true
}

fn is_poem_stanza_block(lines: &[&str], has_poetic_context: bool) -> bool {
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

fn format_poem_stanza(lines: &[&str]) -> String {
    lines.iter()
        .map(|l| l.trim())
        .filter(|l| !l.is_empty())
        .map(|l| format!("> {}", l))
        .collect::<Vec<String>>()
        .join("\n")
}


static TABLE_ROW_3COL: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"^([A-Za-z\u{00C0}-\u{00DC}\w\s\-\/\(\)\.]{2,30}?)\s{1,8}(\d+(?:[\,\.]\d+)?)\s{1,8}(\d+(?:[\,\.]\d+)?)$"##).unwrap()
});
static TABLE_ROW_4COL: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"^([A-Za-z\u{00C0}-\u{00DC}\w\s\-\/\(\)\.]{2,30}?)\s{1,8}(\d+(?:[\,\.]\d+)?)\s{1,8}(\d+(?:[\,\.]\d+)?)\s{1,8}(\d+(?:[\,\.]\d+)?)$"##).unwrap()
});
static INTERLEAVED_TABLE_3COL_3ROWS: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?i)(Pre[çc]o\s+Custo|Produto\s+Valor|Item\s+Pre[çc]o\s+Custo)\s+([A-Za-z\u{00C0}-\u{00DC}]+)\s+(\d+(?:[\,\.]\d+)?)\s+(\d+(?:[\,\.]\d+)?)\s+([A-Za-z\u{00C0}-\u{00DC}]+)\s+(\d+(?:[\,\.]\d+)?)\s+(\d+(?:[\,\.]\d+)?)\s+([A-Za-z\u{00C0}-\u{00DC}]+)\s+(\d+(?:[\,\.]\d+)?)\s+(\d+(?:[\,\.]\d+)?)"##
    ).unwrap()
});
static INTERLEAVED_TABLE_3COL_2ROWS: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?i)(Pre[çc]o\s+Custo|Produto\s+Valor|Item\s+Pre[çc]o\s+Custo)\s+([A-Za-z\u{00C0}-\u{00DC}]+)\s+(\d+(?:[\,\.]\d+)?)\s+(\d+(?:[\,\.]\d+)?)\s+([A-Za-z\u{00C0}-\u{00DC}]+)\s+(\d+(?:[\,\.]\d+)?)\s+(\d+(?:[\,\.]\d+)?)"##
    ).unwrap()
});
static COMPOUND_INTEREST_EQ: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"\((\d+[\,\.]\d+)\)\s*(\d+)\s*=\s*(\d+[\,\.]\d+)"##).unwrap()
});

/// Formata tabelas sem molduras/bordas embutidas no texto em tabelas Markdown
pub fn format_embedded_tables_native(text: &str) -> String {
    let mut t = text.to_string();

    // 0. Interleaved table formats (ex: Preço Custo Vestido 400 210 Blusa 250 90 Saia 300 100)
    if let Some(cap) = INTERLEAVED_TABLE_3COL_3ROWS.captures(&t) {
        let md_tab = format!(
            "\n\n| Item | Preço | Custo |\n| :--- | ---: | ---: |\n| {} | {} | {} |\n| {} | {} | {} |\n| {} | {} | {} |\n\n",
            cap.get(2).unwrap().as_str(), cap.get(3).unwrap().as_str(), cap.get(4).unwrap().as_str(),
            cap.get(5).unwrap().as_str(), cap.get(6).unwrap().as_str(), cap.get(7).unwrap().as_str(),
            cap.get(8).unwrap().as_str(), cap.get(9).unwrap().as_str(), cap.get(10).unwrap().as_str(),
        );
        t = INTERLEAVED_TABLE_3COL_3ROWS.replace(&t, regex::NoExpand(&md_tab)).into_owned();
    } else if let Some(cap) = INTERLEAVED_TABLE_3COL_2ROWS.captures(&t) {
        let md_tab = format!(
            "\n\n| Item | Preço | Custo |\n| :--- | ---: | ---: |\n| {} | {} | {} |\n| {} | {} | {} |\n\n",
            cap.get(2).unwrap().as_str(), cap.get(3).unwrap().as_str(), cap.get(4).unwrap().as_str(),
            cap.get(5).unwrap().as_str(), cap.get(6).unwrap().as_str(), cap.get(7).unwrap().as_str(),
        );
        t = INTERLEAVED_TABLE_3COL_2ROWS.replace(&t, regex::NoExpand(&md_tab)).into_owned();
    }

    let lines: Vec<&str> = t.lines().collect();
    let mut new_lines: Vec<String> = Vec::new();
    let mut i = 0;

    while i < lines.len() {
        let line = lines[i].trim();

        // 1. Verifica tabela de 3 colunas (Item / Num1 / Num2)
        if let Some(cap) = TABLE_ROW_3COL.captures(line) {
            let mut rows = Vec::new();
            rows.push((
                cap.get(1).unwrap().as_str().trim().to_string(),
                cap.get(2).unwrap().as_str().trim().to_string(),
                cap.get(3).unwrap().as_str().trim().to_string(),
            ));

            let mut j = i + 1;
            while j < lines.len() {
                let next_line = lines[j].trim();
                if let Some(next_cap) = TABLE_ROW_3COL.captures(next_line) {
                    rows.push((
                        next_cap.get(1).unwrap().as_str().trim().to_string(),
                        next_cap.get(2).unwrap().as_str().trim().to_string(),
                        next_cap.get(3).unwrap().as_str().trim().to_string(),
                    ));
                    j += 1;
                } else {
                    break;
                }
            }

            if rows.len() >= 2 {
                // Tenta extrair cabeçalho da linha anterior se aplicável
                let mut headers = vec!["Item".to_string(), "Preço".to_string(), "Custo".to_string()];
                if !new_lines.is_empty() {
                    let prev = new_lines.last().unwrap().trim();
                    let tokens: Vec<&str> = prev.split_whitespace().collect();
                    if tokens.len() == 2 && tokens.iter().all(|t| t.chars().next().map(|c| c.is_uppercase()).unwrap_or(false)) {
                        headers = vec!["Item".to_string(), tokens[0].to_string(), tokens[1].to_string()];
                        new_lines.pop();
                    } else if tokens.len() == 3 && tokens.iter().all(|t| t.chars().next().map(|c| c.is_uppercase()).unwrap_or(false)) {
                        headers = vec![tokens[0].to_string(), tokens[1].to_string(), tokens[2].to_string()];
                        new_lines.pop();
                    }
                }

                let mut md_tab = Vec::new();
                md_tab.push(format!("| {} |", headers.join(" | ")));
                md_tab.push("| :--- | ---: | ---: |".to_string());
                for r in &rows {
                    md_tab.push(format!("| {} | {} | {} |", r.0, r.1, r.2));
                }

                new_lines.push(format!("\n\n{}\n\n", md_tab.join("\n")));
                i = j;
                continue;
            }
        }

        // 2. Verifica tabela de 4 colunas
        if let Some(cap) = TABLE_ROW_4COL.captures(line) {
            let mut rows = Vec::new();
            rows.push((
                cap.get(1).unwrap().as_str().trim().to_string(),
                cap.get(2).unwrap().as_str().trim().to_string(),
                cap.get(3).unwrap().as_str().trim().to_string(),
                cap.get(4).unwrap().as_str().trim().to_string(),
            ));

            let mut j = i + 1;
            while j < lines.len() {
                let next_line = lines[j].trim();
                if let Some(next_cap) = TABLE_ROW_4COL.captures(next_line) {
                    rows.push((
                        next_cap.get(1).unwrap().as_str().trim().to_string(),
                        next_cap.get(2).unwrap().as_str().trim().to_string(),
                        next_cap.get(3).unwrap().as_str().trim().to_string(),
                        next_cap.get(4).unwrap().as_str().trim().to_string(),
                    ));
                    j += 1;
                } else {
                    break;
                }
            }

            if rows.len() >= 2 {
                let mut md_tab = Vec::new();
                md_tab.push("| Item | Coluna 1 | Coluna 2 | Coluna 3 |".to_string());
                md_tab.push("| :--- | ---: | ---: | ---: |".to_string());
                for r in &rows {
                    md_tab.push(format!("| {} | {} | {} | {} |", r.0, r.1, r.2, r.3));
                }

                new_lines.push(format!("\n\n{}\n\n", md_tab.join("\n")));
                i = j;
                continue;
            }
        }

        new_lines.push(lines[i].to_string());
        i += 1;
    }

    new_lines.join("\n")
}

/// Formata equações de juros/potências e expressões matemáticas para KaTeX / Markdown
pub fn format_math_formulas_native(text: &str) -> String {
    let mut t = text.to_string();

    // 1. Tabela de potências financeiras (ex: (1,035) 2 = 1,071 ... (1,035) 6 = 1,229)
    let matches: Vec<regex::Captures> = COMPOUND_INTEREST_EQ.captures_iter(&t).collect();
    if matches.len() >= 3 {
        let base_val = matches[0].get(1).unwrap().as_str();
        let mut md_tab = vec![
            format!("| $n$ | $({})^n$ |", base_val),
            "| :---: | :---: |".to_string(),
        ];
        for cap in &matches {
            let n = cap.get(2).unwrap().as_str();
            let val = cap.get(3).unwrap().as_str();
            md_tab.push(format!("| {} | {} |", n, val));
        }
        let tab_str = format!("\n\n{}\n\n", md_tab.join("\n"));

        // Substitui a sequência de equações pela tabela estruturada
        static SEQ_EQ_BLOCK: Lazy<Regex> = Lazy::new(|| {
            Regex::new(r##"(?:\(\d+[\,\.]\d+\)\s*\d+\s*=\s*\d+[\,\.]\d+\s*){3,}"##).unwrap()
        });
        if SEQ_EQ_BLOCK.is_match(&t) {
            t = SEQ_EQ_BLOCK.replace(&t, regex::NoExpand(tab_str.as_str())).into_owned();
        } else {
            t = COMPOUND_INTEREST_EQ.replace_all(&t, "$($1)^{$2} = $3$").into_owned();
        }
    } else if !matches.is_empty() {
        t = COMPOUND_INTEREST_EQ.replace_all(&t, "$($1)^{$2} = $3$").into_owned();
    }

    // 2. Unidades e potências comuns
    t = Regex::new(r##"\b(\d+)\s*m²\b"##).unwrap().replace_all(&t, "$1 $\\text{m}^2$").into_owned();
    t = Regex::new(r##"\b(\d+)\s*m³\b"##).unwrap().replace_all(&t, "$1 $\\text{m}^3$").into_owned();
    t = Regex::new(r##"\b(\d+)\s*cm²\b"##).unwrap().replace_all(&t, "$1 $\\text{cm}^2$").into_owned();
    t = Regex::new(r##"\b(\d+)\s*km²\b"##).unwrap().replace_all(&t, "$1 $\\text{km}^2$").into_owned();

    t
}

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
    t = OCR_BULLET_CORRUPT_B.replace_all(&t, "B) $1").into_owned();
    t = OCR_BULLET_CORRUPT_C.replace_all(&t, "C) $1").into_owned();
    t = OCR_BULLET_CORRUPT_D.replace_all(&t, "D) $1").into_owned();

    // 4. Múltiplas opções na mesma linha
    t = MULTI_OPT_INLINE_PAREN.replace_all(&t, "$1\n\n$2 ").into_owned();
    t = MULTI_OPT_INLINE_ENCLOSED.replace_all(&t, "$1\n\n$2 ").into_owned();
    t = MULTI_OPT_INLINE_DOT.replace_all(&t, "$1\n\n$2 $3").into_owned();

    t
}

static HEADING_WITH_PREP_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(?:(^|\s+|[:.\-]\s*|\b)(\b(?:da|do|das|dos|na|no|nas|nos|pela|pelo|pelas|pelos|em|à|a|ao|aos|com|para|de|o|os|um|uma|este|esta|esse|essa|e|ou|match|with|entre|segundo|conforme|sob|sobre)\s+)((?:(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:1[ªaºo]|2[ªaºo]|3[ªaºo]|4[ªaºo]|Primeir[ao]|Segund[ao]|Terceir[ao]|Quart[ao])(?:<\/?(?:u|b|i|strong|em)>)*\s+(?:<\/?(?:u|b|i|strong|em)>)*(?:Coluna|Column|Tabela|Quadro|Bloco)\b(?:<\/?(?:u|b|i|strong|em)>)*|(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:Coluna|Column|Quadro|Painel|Tira|Bloco|Tabela)(?:<\/?(?:u|b|i|strong|em)>)*\s+(?:<\/?(?:u|b|i|strong|em)>)*(?:0*\d+|I{1,3}|IV|V|VI|VII|VIII|IX|X|[A-E]\b)(?:<\/?(?:u|b|i|strong|em)>)*|(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:QUADRO|PAINEL|TIRA|BLOCO|TABELA)(?:<\/?(?:u|b|i|strong|em)>)*\s+\d+\b(?:<\/?(?:u|b|i|strong|em)>)*)(?:\s*[-–—:]\s*(?:<\/?(?:u|b|i|strong|em)>)*(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o|Conceito|Descri[çc][ãa]o)(?:<\/?(?:u|b|i|strong|em)>)*)?)|(^|\s+|[:.\-]\s*)()((?:(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:1[ªaºo]|2[ªaºo]|3[ªaºo]|4[ªaºo]|Primeir[ao]|Segund[ao]|Terceir[ao]|Quart[ao])(?:<\/?(?:u|b|i|strong|em)>)*\s+(?:<\/?(?:u|b|i|strong|em)>)*(?:Coluna|Column|Tabela|Quadro|Bloco)\b(?:<\/?(?:u|b|i|strong|em)>)*|(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:Coluna|Column|Quadro|Painel|Tira|Bloco|Tabela)(?:<\/?(?:u|b|i|strong|em)>)*\s+(?:<\/?(?:u|b|i|strong|em)>)*(?:0*\d+|I{1,3}|IV|V|VI|VII|VIII|IX|X|[A-E]\b)(?:<\/?(?:u|b|i|strong|em)>)*|(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:QUADRO|PAINEL|TIRA|BLOCO|TABELA)(?:<\/?(?:u|b|i|strong|em)>)*\s+\d+\b(?:<\/?(?:u|b|i|strong|em)>)*)(?:\s*[-–—:]\s*(?:<\/?(?:u|b|i|strong|em)>)*(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o|Conceito|Descri[çc][ãa]o)(?:<\/?(?:u|b|i|strong|em)>)*)?))\s*[:.\-]?"##).unwrap()
});
static NUMBERED_ITEM_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(^|\n|[.;:\)]\s*|\s{2,})([1-9]|1[0-2])\s*[\.\)]\s*([A-Z\u{00C0}-\u{00DC}"])"##).unwrap()
});

static TAG_STRIPPER_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)<\/?(?:u|b|i|strong|em)>|\*\*"##).unwrap()
});

fn format_headings_and_quadros(text: &str) -> String {
    HEADING_WITH_PREP_REGEX.replace_all(text, |caps: &regex::Captures| {
        let prefix_lead = caps.get(1).or_else(|| caps.get(4)).map(|m| m.as_str()).unwrap_or("");
        let has_prep = caps.get(2).is_some() && !caps.get(2).unwrap().as_str().is_empty();
        if has_prep {
            caps.get(0).unwrap().as_str().to_string()
        } else {
            let heading = caps.get(3).or_else(|| caps.get(6)).unwrap().as_str().trim();
            let stripped = TAG_STRIPPER_REGEX.replace_all(heading, "");
            let clean = stripped.trim_start_matches(|c: char| c == '.' || c == ';' || c == ':' || c == ')' || c.is_whitespace())
                                .trim_end_matches([':', '.', '-'])
                                .trim();
            let clean_collapsed = clean.split_whitespace().collect::<Vec<_>>().join(" ");
            let lead_punct = if prefix_lead.contains(':') { ":" } else { "" };
            format!("{}\n\n**{}:**\n\n", lead_punct, clean_collapsed)
        }
    }).into_owned()
}

/// Restaura a tipografia editorial completa de questões e textos de apoio
pub fn restore_exam_typography_native(text: &str, is_option: bool) -> String {
    if text.is_empty() {
        return String::new();
    }

    let mut t = restore_ocr_lexical_spacing_native(text);

    // 0. Recomposição de URLs e codificação percentual quebradas entre linhas
    t = PERCENT_ENCODING_BREAK_REGEX.replace_all(&t, "%$1").into_owned();
    t = PERCENT_ENCODING_SPACE_REGEX.replace_all(&t, "%$1").into_owned();
    t = URL_LINE_BREAK_REGEX.replace_all(&t, "$1$2").into_owned();
    t = URL_LINE_BREAK_REGEX.replace_all(&t, "$1$2").into_owned();

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

    // 4.1 Comandos em inglês (Match column 1 with column 2:)
    t = MATCH_COLUMN_EN.replace_all(&t, "\n\nMatch column $1 with column $2:\n\n").into_owned();

    // 4.2 Rótulos de tabela colados e desaglutinação de itens com parênteses numéricos
    t = TABLE_LABELS_REGEX.replace_all(&t, "\n\n$1 ").into_owned();
    t = NUMERIC_PAREN_ATTACHED.replace_all(&t, "$1\n\n$2").into_owned();
    t = NUMERIC_PAREN_TEXT_ATTACHED.replace_all(&t, "$1 $2").into_owned();

    // 4.3 Desaglutinação de itens com marcadores/hífen/traço
    t = BULLET_ITEM_REGEX.replace_all(&t, |caps: &regex::Captures| {
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
    }).into_owned();

    // 4. Formatação de Quadros, Painéis e Cabeçalhos de Coluna
    t = format_headings_and_quadros(&t);

    // 5. Desaglutinação de sub-itens de letras
    t = SUB_ITEM_LETTERS_REGEX.replace_all(&t, "\n\n$1. $2").into_owned();

    // 6. Comandos finais de questão
    for c_pat in COMMAND_PATTERNS.iter() {
        t = c_pat.replace_all(&t, "\n\n$1\n\n").into_owned();
    }

    // 7. Itens romanos (apenas se não precedido por palavras de seção/título)
    t = ROMAN_NUMERALS_REGEX.replace_all(&t, |caps: &regex::Captures| {
        let prefix = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let roman = caps.get(2).map(|m| m.as_str()).unwrap_or("");
        let letter = caps.get(3).map(|m| m.as_str()).unwrap_or("");
        if SECTION_WORDS_REGEX.is_match(prefix) {
            caps.get(0).unwrap().as_str().to_string()
        } else {
            format!("{}\n\n{}. {}", prefix, roman, letter)
        }
    }).into_owned();

    // 8. Lacunas de preenchimento
    t = GAP_FILL_REGEX.replace_all(&t, "\n\n$1 $2").into_owned();

    // 8.1 Recomposição de sentenças pareadas com barra em itens/lacunas
    t = SLASH_CONTINUATION_REGEX.replace_all(&t, " $1").into_owned();

    // 9. Itens numéricos entre parênteses
    t = NUMERIC_PAREN_REGEX.replace_all(&t, "\n\n($1) $2").into_owned();

    // 10. Itens numéricos internos (1. , 2. ) preservando pontuação precedente
    t = NUMBERED_ITEM_REGEX.replace_all(&t, |caps: &regex::Captures| {
        let lead = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let num = caps.get(2).map(|m| m.as_str()).unwrap_or("");
        let next_char = caps.get(3).map(|m| m.as_str()).unwrap_or("");
        let lead_punct = if lead.contains(';') { ";" } else { "" };
        format!("{}\n\n{}. {}", lead_punct, num, next_char)
    }).into_owned();

    // 10.1 Frases de transição e conexão de itens
    for t_pat in TRANSITION_PATTERNS.iter() {
        t = t_pat.replace_all(&t, "\n\n$1\n\n").into_owned();
    }

    // 11. Artigos de lei (apenas se não precedido por preposições narrativas)
    t = LEGAL_ARTICLES_REGEX.replace_all(&t, |caps: &regex::Captures| {
        let prefix = caps.get(1).map(|m| m.as_str()).unwrap_or("");
        let art = caps.get(2).map(|m| m.as_str()).unwrap_or("");
        if NARRATIVE_PREP_REGEX.is_match(prefix) {
            caps.get(0).unwrap().as_str().to_string()
        } else {
            format!("{}\n\n{} - ", prefix, art)
        }
    }).into_owned();

    // 12. Normalização de quebras de linha múltiplas
    t = Regex::new(r##"\n{3,}"##).unwrap().replace_all(&t, "\n\n").into_owned();

fn percent_decode_utf8(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut decoded_bytes = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let b1 = bytes[i + 1];
            let b2 = bytes[i + 2];
            if b1.is_ascii_hexdigit() && b2.is_ascii_hexdigit() {
                if let Ok(hex_str) = std::str::from_utf8(&bytes[i + 1..i + 3]) {
                    if let Ok(val) = u8::from_str_radix(hex_str, 16) {
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
            raw_url = raw_url.trim_matches(|c| c == '.' || c == ',' || c == ')' || c == '(' || c == ' ' || c == '\n' || c == '\r' || c == '*').to_string();
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

    // 14.1 Detecção e Formatação de Tabelas sem bordas e Fórmulas Matemáticas
    t = format_embedded_tables_native(&t);
    t = format_math_formulas_native(&t);

    // 15. Reconstrução de Parágrafos Fluidos e Preservação de Estrofes de Poemas
    let raw_blocks: Vec<&str> = t.split("\n\n").map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    let mut final_paras: Vec<String> = Vec::new();
    let has_global_poetic_context = POEM_CUES_REGEX.is_match(&t) || FAMOUS_POETS_REGEX.is_match(&t);

    for (block_idx, block) in raw_blocks.iter().enumerate() {
        if block.starts_with("---")
            || block.starts_with("📖")
            || block.starts_with("**")
            || block.starts_with("###")
            || block.starts_with("*(")
            || block.starts_with('>')
            || block.starts_with('|')
            || block.contains("\n|")
        {
            final_paras.push(block.to_string());
            continue;
        }

        let first_char = block.chars().next().unwrap_or(' ');
        if !final_paras.is_empty()
            && first_char.is_lowercase()
            && !final_paras.last().unwrap().starts_with("---")
            && !final_paras.last().unwrap().starts_with("📖")
            && !final_paras.last().unwrap().starts_with("**")
            && !final_paras.last().unwrap().starts_with("###")
            && !final_paras.last().unwrap().starts_with("*(")
            && !final_paras.last().unwrap().starts_with('>')
            && !final_paras.last().unwrap().starts_with('|')
        {
            let last_idx = final_paras.len() - 1;
            final_paras[last_idx] = format!("{} {}", final_paras[last_idx], block);
            continue;
        }

        let prev_block_text = if block_idx > 0 { raw_blocks[block_idx - 1] } else { "" };
        let has_local_poetic_context = has_global_poetic_context
            || POEM_CUES_REGEX.is_match(prev_block_text)
            || FAMOUS_POETS_REGEX.is_match(prev_block_text)
            || POEM_CUES_REGEX.is_match(block)
            || FAMOUS_POETS_REGEX.is_match(block);

        let unsquashed = unsquash_poem_lines(block);
        let lines: Vec<&str> = unsquashed.split('\n').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();

        // Se o bloco possui comando na primeira linha seguido de estrofe
        let mut lines_owned: Vec<String> = lines.into_iter().map(|s| s.to_string()).collect();
        let is_intro = !lines_owned.is_empty() && (lines_owned[0].ends_with(':') || INTRO_COMMAND_REGEX.is_match(&lines_owned[0]));
        if lines_owned.len() >= 3 && is_intro {
            final_paras.push(lines_owned[0].clone());
            lines_owned.drain(..1);
        }

        let lines_refs: Vec<&str> = lines_owned.iter().map(|s| s.as_str()).collect();

        // Se o bloco inteiro é uma estrofe
        if is_poem_stanza_block(&lines_refs, has_local_poetic_context) {
            final_paras.push(format_poem_stanza(&lines_refs));
            continue;
        }

        // Se o bloco contém uma estrofe seguida de prosa/comentário (ex: versos seguidos de "Nos versos de Luiz Gonzaga...")
        if has_local_poetic_context && lines_owned.len() >= 3 {
            for split_idx in 2..lines_owned.len() {
                let verse_refs: Vec<&str> = lines_owned[..split_idx].iter().map(|s| s.as_str()).collect();
                let first_rem = lines_owned[split_idx].trim().trim_matches(|c| c == '*' || c == '_' || c == '`');
                if PROSE_PROMPT_REGEX.is_match(first_rem) || is_author_attribution(first_rem) || !is_verse_line(&lines_owned[split_idx]) {
                    if is_poem_stanza_block(&verse_refs, true) {
                        final_paras.push(format_poem_stanza(&verse_refs));
                        lines_owned.drain(..split_idx);
                        break;
                    }
                }
            }
        }

        let mut current_sub: Vec<String> = Vec::new();

        for line in lines_owned {
            if current_sub.is_empty() {
                current_sub.push(line);
                continue;
            }

            let prev_line = current_sub.last().unwrap().clone();
            let prev_trimmed = prev_line.trim_end();
            let is_prev_incomplete = prev_trimmed.ends_with(',')
                || prev_trimmed.ends_with(';')
                || prev_trimmed.ends_with(" e")
                || prev_trimmed.ends_with(" ou")
                || prev_trimmed.ends_with(" de")
                || prev_trimmed.ends_with(" do")
                || prev_trimmed.ends_with(" da")
                || prev_trimmed.ends_with(" dos")
                || prev_trimmed.ends_with(" das")
                || prev_trimmed.ends_with(" em")
                || prev_trimmed.ends_with(" com")
                || prev_trimmed.ends_with(" para")
                || prev_trimmed.ends_with(" por")
                || prev_trimmed.ends_with(" que")
                || prev_trimmed.ends_with(" na")
                || prev_trimmed.ends_with(" no")
                || prev_trimmed.ends_with(" a");

            let is_prev_end = !is_prev_incomplete && (prev_trimmed.ends_with('.') || prev_trimmed.ends_with(':') || prev_trimmed.ends_with('?') || prev_trimmed.ends_with('!'));

            let is_prev_item = prev_line.starts_with("I.") || prev_line.starts_with("II.") || prev_line.starts_with("III.")
                || prev_line.starts_with("IV.") || prev_line.starts_with("V.") || prev_line.starts_with("VI.")
                || prev_line.starts_with("VII.") || prev_line.starts_with("VIII.") || prev_line.starts_with("IX.") || prev_line.starts_with("X.")
                || prev_line.starts_with("(__)") || prev_line.starts_with("( )") || (prev_line.starts_with('(') && prev_line.contains(')'));

            let is_current_item = line.starts_with("I.") || line.starts_with("II.") || line.starts_with("III.")
                || line.starts_with("IV.") || line.starts_with("V.") || line.starts_with("VI.")
                || line.starts_with("VII.") || line.starts_with("VIII.") || line.starts_with("IX.") || line.starts_with("X.")
                || line.starts_with("(__)") || line.starts_with("( )") || (line.starts_with('(') && line.contains(')'))
                || line.starts_with("**") || line.starts_with("Correlacione") || line.starts_with("Assinale")
                || line.starts_with("Marque") || line.starts_with("Indique") || line.starts_with("A sequência")
                || line.starts_with("Julgue") || line.starts_with("Analise");

            if !is_prev_incomplete && (is_current_item || (is_prev_item && is_prev_end) || (is_prev_end && prev_line.len() > 30 && line.len() > 10)) {
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
