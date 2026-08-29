//! Módulo de detecção e formatação de estruturas de layout (cabeçalhos, quadros, tabelas, fórmulas e divisores)
use once_cell::sync::Lazy;
use regex::Regex;

static HEADING_WITH_PREP_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)(?:(^|\s+|[:.\-]\s*|\b)(\b(?:da|do|das|dos|na|no|nas|nos|pela|pelo|pelas|pelos|em|à|a|ao|aos|com|para|de|o|os|um|uma|este|esta|esse|essa|e|ou|match|with|entre|segundo|conforme|sob|sobre)\s+)((?:(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:1[ªaºo]|2[ªaºo]|3[ªaºo]|4[ªaºo]|Primeir[ao]|Segund[ao]|Terceir[ao]|Quart[ao])(?:<\/?(?:u|b|i|strong|em)>)*\s+(?:<\/?(?:u|b|i|strong|em)>)*(?:Coluna|Column|Tabela|Quadro|Bloco)\b(?:<\/?(?:u|b|i|strong|em)>)*|(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:Coluna|Column|Quadro|Painel|Tira|Bloco|Tabela)(?:<\/?(?:u|b|i|strong|em)>)*\s+(?:<\/?(?:u|b|i|strong|em)>)*(?:0*\d+|I{1,3}|IV|V|VI|VII|VIII|IX|X|[A-E]\b)(?:<\/?(?:u|b|i|strong|em)>)*|(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:QUADRO|PAINEL|TIRA|BLOCO|TABELA)(?:<\/?(?:u|b|i|strong|em)>)*\s+\d+\b(?:<\/?(?:u|b|i|strong|em)>)*)(?:\s*[-–—:]\s*(?:<\/?(?:u|b|i|strong|em)>)*(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o|Conceito|Descri[çc][ãa]o)(?:<\/?(?:u|b|i|strong|em)>)*)?)|(^|\s+|[:.\-]\s*)()((?:(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:1[ªaºo]|2[ªaºo]|3[ªaºo]|4[ªaºo]|Primeir[ao]|Segund[ao]|Terceir[ao]|Quart[ao])(?:<\/?(?:u|b|i|strong|em)>)*\s+(?:<\/?(?:u|b|i|strong|em)>)*(?:Coluna|Column|Tabela|Quadro|Bloco)\b(?:<\/?(?:u|b|i|strong|em)>)*|(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:Coluna|Column|Quadro|Painel|Tira|Bloco|Tabela)(?:<\/?(?:u|b|i|strong|em)>)*\s+(?:<\/?(?:u|b|i|strong|em)>)*(?:0*\d+|I{1,3}|IV|V|VI|VII|VIII|IX|X|[A-E]\b)(?:<\/?(?:u|b|i|strong|em)>)*|(?:<\/?(?:u|b|i|strong|em)>)*\s*(?:QUADRO|PAINEL|TIRA|BLOCO|TABELA)(?:<\/?(?:u|b|i|strong|em)>)*\s+\d+\b(?:<\/?(?:u|b|i|strong|em)>)*)(?:\s*[-–—:]\s*(?:<\/?(?:u|b|i|strong|em)>)*(?:Word|Meaning|Palavra|Significado|Termo|Defini[çc][ãa]o|Conceito|Descri[çc][ãa]o)(?:<\/?(?:u|b|i|strong|em)>)*)?))\s*[:.\-]?"##).unwrap()
});

static TAG_STRIPPER_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r##"(?i)<\/?(?:u|b|i|strong|em)>|\*\*"##).unwrap()
});

static DIVIDER_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n)\s*---+\s*(?:$|\n)"##).unwrap());
static DIVIDER_INLINE_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n)\s*---+\s+([^\n]+)"##).unwrap());
static ASTERISKS_ONLY_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?m)^\s*\*+\s*$"##).unwrap());
static DIALOGUE_DASH_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"(?:^|\n)\s*([—–]\s+[A-Z\u{00C0}-\u{00DC}])"##).unwrap());

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

/// Formata cabeçalhos de Quadros, Painéis e Colunas em Markdown negrito com preservação de pontuação
pub fn format_headings_and_quadros(text: &str) -> String {
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

/// Normaliza linhas divisórias em Markdown (---) e travessões de diálogo
pub fn format_dividers_and_dialogue(text: &str) -> String {
    let mut t = text.to_string();
    t = DIALOGUE_DASH_REGEX.replace_all(&t, "\n\n$1").into_owned();
    t = DIVIDER_REGEX.replace_all(&t, "\n\n---\n\n").into_owned();
    t = DIVIDER_INLINE_REGEX.replace_all(&t, "\n\n---\n\n$1").into_owned();
    t = ASTERISKS_ONLY_REGEX.replace_all(&t, "\n").into_owned();
    t
}

/// Formata tabelas sem molduras/bordas embutidas no texto em tabelas Markdown
pub fn format_embedded_tables_native(text: &str) -> String {
    let mut t = text.to_string();

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
                let mut headers = vec!["Item".to_string(), "Preço".to_string(), "Custo".to_string()];
                if !new_lines.is_empty() {
                    let prev = new_lines.last().unwrap().trim();
                    let tokens: Vec<&str> = prev.split_whitespace().collect();
                    if tokens.len() == 2 && tokens.iter().all(|tok| tok.chars().next().map(|c| c.is_uppercase()).unwrap_or(false)) {
                        headers = vec!["Item".to_string(), tokens[0].to_string(), tokens[1].to_string()];
                        new_lines.pop();
                    } else if tokens.len() == 3 && tokens.iter().all(|tok| tok.chars().next().map(|c| c.is_uppercase()).unwrap_or(false)) {
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

/// Formata equações matemáticas e potências para KaTeX / Markdown
pub fn format_math_formulas_native(text: &str) -> String {
    let mut t = text.to_string();

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

    t = Regex::new(r##"\b(\d+)\s*m²\b"##).unwrap().replace_all(&t, "$1 $\\text{m}^2$").into_owned();
    t = Regex::new(r##"\b(\d+)\s*m³\b"##).unwrap().replace_all(&t, "$1 $\\text{m}^3$").into_owned();
    t = Regex::new(r##"\b(\d+)\s*cm²\b"##).unwrap().replace_all(&t, "$1 $\\text{cm}^2$").into_owned();
    t = Regex::new(r##"\b(\d+)\s*km²\b"##).unwrap().replace_all(&t, "$1 $\\text{km}^2$").into_owned();

    t
}
