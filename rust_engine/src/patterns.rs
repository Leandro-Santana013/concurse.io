//! concurse.io — Padrões Regex Mestres Nativos do Pipeline em Rust
use once_cell::sync::Lazy;
use regex::Regex;

/// Regex universal de cabeçalhos de questões estrito no início de linha
pub static HEADER_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?i)(?:^|\n)[ \t]*(?:(?:QUEST[AÃ\?]?O\s+|ITEM\s+)(0*\d{1,3})[ \t]*(?:[\.\-–—:\)]|\n+|[ \t]+)|(0*\d{1,3})[ \t]*(?:[\.\-–—:\)]|\n+|\t+|[ \t]+(?:\p{Alphabetic}|["'“”‘’(\[«\*_<]))|\((0*\d{1,3})\)[ \t]+)"##
    ).unwrap()
});

/// Regex primário para identificação de alternativas de resposta (A, B, C, D, E)
pub static OPTION_PRIMARY_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?:^|\n|[.;:\)]\s*|\s{2,})(?:([A-E])\s*\(\s*\)|\(?\s*([A-E])\s*\)?\s*[\.\-–—:\)]|\(([A-E])\)|\[([A-E])\])\s*"##
    ).unwrap()
});

/// Regex de fallback para alternativas no início de linha
pub static OPTION_NEWLINE_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?:^|\n)\s*([A-E])\s*(?:\n|\s{2,})"##).unwrap()
});

/// Regex para detecção de textos de apoio e deadzones compartilhadas (padrão numérico explícito)
pub static CONTEXT_TEXT_BANNER_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?i)(?:^|\n|\.\s+|\s+)(?:<[^>]+>|\*{0,3}|_{0,3})*\s*((?:Instru[çc][ãa\?]?o\s*[:.\-]?\s*|[Oo]\s+texto\s+(?:a\s+seguir|abaixo|seguinte|1|2|I|II)?\s*(?:servir[aá\?]?\s+de\s+base\s+para\s+responder|refere-se|para\s+responder|para)?|[Pp]ara\s+(?:responder\s+(?:[àa\?]?s\s+)?|as\s+)?quest[oõa\?]?es|[Ll]eia\s+o\s+texto(?:\s+\d+)?\s*(?:para\s+responder|(?:a\s+seguir|abaixo))?|[Aa]s\s+quest[oõa\ufffd\?]?es(?:\s+de)?|[Cc]onsidere\s+(?:o\s+texto|a\s+situa[cç][aã\?]?o\s+hipot[eé\?]?tica|o\s+caso)\s*(?:(?:a\s+seguir|abaixo))?|[Cc]om\s+base\s+no\s+texto\s*(?:(?:abaixo|a\s+seguir))?\s*,\s*responda|[Tt]exto\s+(?:I|II|III|1|2|3)?\s*(?:\(?[^)]*\))?\s*[-–—:]?\s*(?:para\s+(?:as\s+)?quest[oõa\ufffd\?]?es|base\s+para\s+as\s+quest[oõa\ufffd\?]?es))[^\.:]{0,120}?quest[oõa\ufffd\?]?es?\s*(?:de\s+n[úu]meros?\s+|de\s+)?(?:\*{0,2}|_{0,2})?(0*\d{1,3})\s*(?:a|e|ao?|at[eé\ufffd\?]?|\be\b|,|\-)\s*(?:a\s+)?(?:\*{0,2}|_{0,2})?(0*\d{1,3})(?:\*{0,2}|_{0,2})?[.:–—]?)"##
    ).unwrap()
});

/// Regex para detecção de textos de apoio em inglês e frases relativas (ex: 'Use the following TEXT to answer the next two questions')
pub static RELATIVE_CONTEXT_BANNER_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?i)(?:^|\n|\.\s+|\s+)(?:<[^>]+>|\*{0,3}|_{0,3})*\s*((?:(?:Use|Read)\s+the\s+following\s+TEXT\s+to\s+answer|(?:Leia|Considere|Utilize)\s+o\s+texto\s+(?:a\s+seguir|abaixo)\s+para\s+responder\s+[àa]s)\s+(?:the\s+next\s+(\w+|\d+)\s+questions?|pr[óo]ximas\s+(\w+|\d+)\s+quest[õo]es|questions?\s+(\d+)\s*(?:and|to|a|-)\s*(\d+))[\.:–—]?)"##
    ).unwrap()
});

/// Regex para detecção de gatilhos de imagens e figuras no enunciado
pub static IMAGE_TRIGGER_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?i)\b(?:figura|gr[áa]fico|grafico|quadro|tabela|diagrama|circuito|desenho|ilustra[çc][ãa\?]?o|mapa|esquema|imagem|paqu[íi]metro|circunfer[êe]ncia|tetraedro|planta|fluxograma|fotografia|foto|tira|tirinha|charge|cartum|organograma|cronograma|histograma|exemplo|casinha|vilarejo|estrada|malha|plano\s+cartesiano|representad[ao]|mostrad[ao]|conforme\s+(?:o\s+desenho|a\s+figura|a\s+imagem|o\s+esquema|o\s+gr[áa]fico|o\s+exemplo))\b"##
    ).unwrap()
});

/// Regex para detecção de legendas estritas de figuras
pub static CAPTION_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?i)^\s*(?:figura|gr[áa]fico|grafico|tabela|quadro|diagrama|circuito|mapa|esquema|imagem|ilustra[çc][ãa\?]?o|foto|tira|charge|cartum)\b(?:\s*(?:\d+|[A-Za-z]|I|II|III|IV|V|VI|VII|VIII|IX|X))?\s*[-–—:]?"##
    ).unwrap()
});

/// Regex para detecção de banners e títulos de seções de disciplinas
pub static SUBJECT_BANNER_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(
        r##"(?im)^[ \t]*(?:<[^>]+>|\*{1,3}|_{1,3})*[ \t]*(?:(?:FGV\s+CONHECIMENTO\s+|CEBRASPE\s*[-–—:]*\s*|VUNESP\s*[-–—:]*\s*|IBAM\s*[-–—:]*\s*|FCC\s*[-–—:]*\s*|CESGRANRIO\s*[-–—:]*\s*)?(?:NO[ÇC\?][ÕO\?]?ES\s+DE\s+|CONHECIMENTOS\s+(?:B[ÁA\?]?SICOS|ESPEC[ÍI\?]?FICOS|GERAIS|REGIONAIS)\s*[-–—:]*\s*|BLOCO\s+[I|V|X\d]+\s*[-–—:]*\s*|PARTE\s+[I|V|X\d]+\s*[-–—:]*\s*|DISCIPLINA\s*:\s*)?(L[ÍI\?]?NGUA\s+PORTUGUESA|PORTUGU[ÊE\?]?S|INTERPRETA[ÇC\?][ÃA\?]?O\s+DE\s+TEXTO|GRAM[ÁA\?]?TICA|REDA[ÇC\?][ÃA\?]?O\s+OFICIAL|MATEM[ÁA\?]?TICA\s+E\s+RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO|RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO-MATEM[ÁA\?]?TICO|RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO\s+MATEM[ÁA\?]?TICO|RACIOC[ÍI\?]?NIO\s+L[ÓO\?]?GICO|MATEM[ÁA\?]?TICA\s+FINANCEIRA|MATEM[ÁA\?]?TICA|INFORM[ÁA\?]?TICA|TECNOLOGIA\s+DA\s+INFORM[AÃ\?]?O|CI[ÊE\?]?NCIA\s+DE\s+DADOS|DIREITO\s+CONSTITUCIONAL|DIREITO\s+ADMINISTRATIVO|DIREITO\s+PENAL|DIREITO\s+CIVIL|DIREITO\s+PROCESSUAL\s+CIVIL|DIREITO\s+PROCESSUAL\s+PENAL|DIREITO\s+PROCESSUAL\s+DO\s+TRABALHO|DIREITO\s+PROCESSUAL|DIREITO\s+TRIBUT[ÁA\?]?RIO|DIREITO\s+PREVIDENCI[ÁA\?]?RIO|DIREITO\s+DO\s+TRABALHO|DIREITO\s+FINANCEIRO|DIREITO\s+AMBIENTAL|DIREITO\s+ELEITORAL|DIREITO\s+EMPRESARIAL|DIREITOS\s+HUMANOS|LEGISLA[ÇC\?][ÃA\?]?O\s+(?:ACERCA\s+DE\s+[^\n\.\,]+|DE\s+SEGURAN[ÇC\?]?A\s+[^\n\.\,]+|ESPEC[ÍI\?]?FICA|APLICADA|INSTITUCIONAL|DO\s+SUS)|LEGISLA[ÇC\?][ÃA\?]?O|[ÉE\?]?TICA\s+NO\s+SERVI[ÇC\?]?O\s+P[ÚU\?]?BLICO|[ÉE\?]?TICA|REGIMENTO\s+INTERNO|ESTATUTO\s+DOS\s+SERVIDORES|ADMINISTRA[ÇC\?][ÃA\?]?O\s+FINANCEIRA\s+E\s+OR[ÇC\?]?AMENT[ÁA\?]?RIA|AFO|OR[ÇC\?]?AMENTO\s+P[ÚU\?]?BLICO|ADMINISTRA[ÇC\?][ÃA\?]?O\s+P[ÚU\?]?BLICA|ADMINISTRA[ÇC\?][ÃA\?]?O\s+GERAL|GEST[ÃA\?]?O\s+P[ÚU\?]?BLICA|GEST[ÃA\?]?O\s+DE\s+PESSOAS|RECURSOS\s+HUMANOS|POL[ÍI\?]?TICAS\s+P[ÚU\?]?BLICAS|ARQUIVOLOGIA|CONTABILIDADE\s+P[ÚU\?]?BLICA|CONTABILIDADE\s+GERAL|CONTABILIDADE|AUDITORIA|ECONOMIA|ESTAT[ÍI\?]?STICA|CONHECIMENTOS\s+B[ÁA\?]?SICOS|CONHECIMENTOS\s+ESPEC[ÍI\?]?FICOS|CONHECIMENTOS\s+GERAIS|CONHECIMENTOS\s+REGIONAIS|ATUALIDADES|HIST[ÓO\?]?RIA\s+E\s+GEOGRAFIA|GEOGRAFIA|HIST[ÓO\?]?RIA|ENFERMAGEM|MEDICINA|SA[ÚU\?]?DE\s+P[ÚU\?]?BLICA|SUS|FARM[ÁA\?]?CIA|ODONTOLOGIA|BIOLOGIA|PSICOLOGIA|SERVI[ÇC\?]?O\s+SOCIAL|NUTRI[ÇC\?][ÃA\?]?O|ENGENHARIA\s+CIVIL|ENGENHARIA\s+EL[ÉE\?]?TRICA|ENGENHARIA\s+MEC[ÂA\?]?NICA|ENGENHARIA|F[ÍI\?]?SICA|QU[ÍI\?]?MICA|PEDAGOGIA|L[ÍI\?]?NGUA\s+INGLESA|INGL[ÊE\?]?S|L[ÍI\?]?NGUA\s+ESPANHOLA|ESPANHOL|SEGURAN[ÇC\?]?A\s+P[ÚU\?]?BLICA|CRIMINOLOGIA))(?:[ \t]*(?:<[^>]+>|\*{1,3}|_{1,3})*)*(?:$|[ \t]*[-–—:][^\n]*|[ \t]+(?:Use\s+the|Instru[çc][ãa]o|Para\s+responder|Leia|Considere)[^\n]*)$"##
    ).unwrap()
});
