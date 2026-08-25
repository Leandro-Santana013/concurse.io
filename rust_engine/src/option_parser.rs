//! concurse.io — Parser Nativo de Enunciados, Alternativas e Gabaritos em Rust
use std::collections::HashMap;
use once_cell::sync::Lazy;
use regex::Regex;
use crate::patterns::{OPTION_PRIMARY_REGEX, OPTION_NEWLINE_REGEX};
use crate::typography::{restore_exam_typography_native, clean_text_artifacts_native};

static EMBEDDED_ANSWER_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)\(?\s*(?:Correta|Gabarito|Resposta|Gabarito\s*Oficial)\s*[:=-]?\s*([A-Ea-eXNxn\*]|CERTO|ERRADO|C|E)\s*\)?").unwrap()
});

static CERTO_ERRADO_REGEX: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(?:^|\n|\s{2,})(?:\(?\s*(CERTO|ERRADO|C|E)\s*\)?)\s*").unwrap()
});

#[derive(Debug, Clone)]
pub struct ParsedQuestionBody {
    pub enunciado: String,
    pub opcoes: HashMap<String, String>,
    pub embedded_answer: Option<String>,
    pub is_certo_errado: bool,
}

/// Extrai e formata o enunciado e suas alternativas em uma única passada
pub fn parse_question_body_native(raw_chunk: &str) -> ParsedQuestionBody {
    let clean_chunk = clean_text_artifacts_native(raw_chunk);

    // 1. Extração de Gabarito Embutido (ex: "(Correta: C)")
    let mut embedded_answer = None;
    if let Some(cap) = EMBEDDED_ANSWER_REGEX.captures(&clean_chunk) {
        if let Some(ans_match) = cap.get(1) {
            let mut ans_upper = ans_match.as_str().to_uppercase();
            if ans_upper == "CERTO" {
                ans_upper = "C".to_string();
            } else if ans_upper == "ERRADO" {
                ans_upper = "E".to_string();
            }
            embedded_answer = Some(ans_upper);
        }
    }

    // 2. Busca por alternativas primárias (A..E)
    let mut matches = Vec::new();
    for cap in OPTION_PRIMARY_REGEX.captures_iter(&clean_chunk) {
        let m = cap.get(0).unwrap();
        let letter = cap.get(1).or_else(|| cap.get(2)).or_else(|| cap.get(3)).or_else(|| cap.get(4))
            .map(|l| l.as_str().to_uppercase()).unwrap_or_default();
        if !letter.is_empty() {
            matches.push((m.start(), m.end(), letter));
        }
    }

    if matches.is_empty() {
        for cap in OPTION_NEWLINE_REGEX.captures_iter(&clean_chunk) {
            let m = cap.get(0).unwrap();
            let letter = cap.get(1).map(|l| l.as_str().to_uppercase()).unwrap_or_default();
            if !letter.is_empty() {
                matches.push((m.start(), m.end(), letter));
            }
        }
    }

    // 3. Encontra a melhor sequência contínua (ex: A, B, C, D, E)
    let chunk_len = clean_chunk.len();
    let mut best_seq: Vec<(usize, usize, String)> = Vec::new();
    let mut best_score = -1.0;

    for (s_idx, m_first) in matches.iter().enumerate() {
        if m_first.2 == "A" {
            let mut seq = vec![m_first.clone()];
            let mut expected = b'B';

            for next_m in &matches[s_idx + 1..] {
                if next_m.2.as_bytes()[0] == expected {
                    seq.push(next_m.clone());
                    expected += 1;
                    if expected > b'E' {
                        break;
                    }
                }
            }

            if seq.len() >= 2 {
                let score = (seq.len() as f64) * 1000.0 + (seq[0].0 as f64 / chunk_len.max(1) as f64) * 100.0;
                if score > best_score {
                    best_score = score;
                    best_seq = seq;
                }
            }
        }
    }

    // 4. Se encontrou sequência A..E válida (2 a 5 opções)
    if !best_seq.is_empty() {
        let first_start = best_seq[0].0;
        let enunciado_raw = clean_chunk[..first_start].trim().to_string();

        let mut opcoes = HashMap::new();
        for i in 0..best_seq.len() {
            let letter = best_seq[i].2.clone();
            let content_start = best_seq[i].1;
            let content_end = if i + 1 < best_seq.len() {
                best_seq[i + 1].0
            } else {
                chunk_len
            };

            let opt_content_raw = clean_chunk[content_start..content_end].trim();
            let opt_formatted = restore_exam_typography_native(opt_content_raw, true);
            opcoes.insert(letter, opt_formatted);
        }

        let enunciado_formatted = restore_exam_typography_native(&enunciado_raw, false);

        return ParsedQuestionBody {
            enunciado: enunciado_formatted,
            opcoes,
            embedded_answer,
            is_certo_errado: false,
        };
    }

    // 5. Caso não tenha A..E, testa se é modelo Certo / Errado (CESPE / Cebraspe)
    let ce_matches: Vec<_> = CERTO_ERRADO_REGEX.captures_iter(&clean_chunk).collect();
    if ce_matches.len() >= 2 {
        let mut opcoes = HashMap::new();
        opcoes.insert("C".to_string(), "Certo".to_string());
        opcoes.insert("E".to_string(), "Errado".to_string());

        let first_match_start = ce_matches[0].get(0).unwrap().start();
        let enunciado_raw = clean_chunk[..first_match_start].trim();
        let enunciado_formatted = restore_exam_typography_native(enunciado_raw, false);

        return ParsedQuestionBody {
            enunciado: enunciado_formatted,
            opcoes,
            embedded_answer,
            is_certo_errado: true,
        };
    }

    // 6. Heurística de fallback: divide as 4 ou 5 últimas linhas ou blocos se parecerem opções
    let lines: Vec<&str> = clean_chunk.split('\n').map(|l| l.trim()).filter(|l| !l.is_empty()).collect();
    for num_opts in [5, 4] {
        if lines.len() >= num_opts + 1 {
            let candidate_opts = &lines[lines.len() - num_opts..];
            let statement_lines = &lines[..lines.len() - num_opts];
            let all_valid = candidate_opts.iter().all(|l| !l.is_empty() && l.len() < 300);

            if all_valid && !statement_lines.is_empty() {
                let mut opcoes = HashMap::new();
                let letters = ["A", "B", "C", "D", "E"];
                for (idx, opt_line) in candidate_opts.iter().enumerate() {
                    let clean_opt = opt_line.trim_start_matches(|c: char| c.is_ascii_punctuation() || c.is_whitespace() || c == '•');
                    opcoes.insert(letters[idx].to_string(), restore_exam_typography_native(clean_opt, true));
                }
                let enunciado_raw = statement_lines.join("\n");
                let enunciado_formatted = restore_exam_typography_native(&enunciado_raw, false);

                return ParsedQuestionBody {
                    enunciado: enunciado_formatted,
                    opcoes,
                    embedded_answer,
                    is_certo_errado: false,
                };
            }
        }
    }

    // Fallback padrão seguro (Certo / Errado)
    let mut opcoes = HashMap::new();
    opcoes.insert("C".to_string(), "Certo".to_string());
    opcoes.insert("E".to_string(), "Errado".to_string());
    let enunciado_formatted = restore_exam_typography_native(&clean_chunk, false);

    ParsedQuestionBody {
        enunciado: enunciado_formatted,
        opcoes,
        embedded_answer,
        is_certo_errado: true,
    }
}
