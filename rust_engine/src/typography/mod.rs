//! concurse.io — Motor de Restauração Tipográfica e Limpeza de Textos em Rust
//!
//! Arquitetura modular dividida por domínios:
//! - `cleaners`: Limpeza de ruídos de scrapers, normalização UTF-8 e espaçamentos OCR.
//! - `structure`: Cabeçalhos de quadros, painéis, tabelas embutidas e fórmulas matemáticas.
//! - `lists`: Marcadores, numeração (1-12), numerais romanos (I-X), letras e lacunas (__).
//! - `transitions`: Comandos de questão, enunciados de ligação intermediários e artigos de lei.
//! - `urls`: Decodificação percentual e formatação de fontes/links.
//! - `poetry`: Detecção de métrica poética e preservação de estrofes de versos.
//! - `tests`: Suíte de testes unitários automatizados.

pub mod cleaners;
pub mod structure;
pub mod lists;
pub mod transitions;
pub mod urls;
pub mod poetry;

#[cfg(test)]
mod tests;

#[allow(unused_imports)]
pub use cleaners::{clean_text_artifacts_native, restore_ocr_lexical_spacing_native};
#[allow(unused_imports)]
pub use structure::{format_embedded_tables_native, format_math_formulas_native};
#[allow(unused_imports)]
pub use urls::percent_decode_utf8;

use once_cell::sync::Lazy;
use regex::Regex;

static MULTI_SPACE_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"[ \t]{2,}"##).unwrap());
static MULTI_NEWLINES_REGEX: Lazy<Regex> = Lazy::new(|| Regex::new(r##"\n{3,}"##).unwrap());

/// Restaura a tipografia editorial completa de questões e textos de apoio
pub fn restore_exam_typography_native(raw_text: &str, is_option: bool) -> String {
    if raw_text.is_empty() {
        return String::new();
    }

    let mut t = raw_text.to_string();

    // 1. Correção lexical e artefatos de quebra de OCR
    t = cleaners::preprocess_lexical_flow(&t);

    // Se for uma alternativa individual curta, normaliza e finaliza
    if is_option {
        t = MULTI_SPACE_REGEX.replace_all(&t, " ").into_owned();
        t = MULTI_NEWLINES_REGEX.replace_all(&t, "\n\n").into_owned();
        return t.trim().to_string();
    }

    // 2. Desaglutinação de itens com marcadores/hífen/traço (- , • , –)
    t = lists::format_bullet_items(&t);

    // 3. Formatação de Quadros, Painéis e Cabeçalhos de Coluna
    t = structure::format_headings_and_quadros(&t);

    // 4. Desaglutinação de sub-itens de letras (A., B., C.)
    t = lists::format_sub_item_letters(&t);

    // 5. Comandos finais de questão ("Assinale a alternativa...", "Match column...")
    t = transitions::format_question_commands(&t);

    // 6. Itens romanos (I., II.) com proteção de palavras de seção
    t = lists::format_roman_items(&t);

    // 7. Lacunas de preenchimento (__) e ( )
    t = lists::format_gap_fills(&t);

    // 8. Recomposição de sentenças pareadas com barra em itens/lacunas (A / B)
    t = transitions::repair_slash_continuations(&t);

    // 9. Itens numéricos entre parênteses ((1), (2))
    t = lists::format_numeric_parentheses(&t);

    // 10. Itens numéricos sem parênteses (1., 2.) com preservação de pontuação
    t = lists::format_numbered_items(&t);

    // 11. Frases de transição e conexão de itens ("Esses elementos correspondem a...")
    t = transitions::format_transition_phrases(&t);

    // 12. Artigos de lei com proteção de preposições narrativas
    t = transitions::format_legal_articles(&t);

    // 13. Limpeza e Isolamento de Links e Fontes Bibliográficas (*(Fonte: ...)*)
    t = urls::format_urls_and_sources(&t);

    // 14. Divisores markdown (---) e travessões de diálogo
    t = structure::format_dividers_and_dialogue(&t);

    // 15. Detecção e Formatação de Tabelas sem bordas e Fórmulas Matemáticas
    t = structure::format_embedded_tables_native(&t);
    t = structure::format_math_formulas_native(&t);

    // 16. Reconstrução de Parágrafos Fluidos e Preservação de Estrofes de Poemas
    t = reconstruct_paragraph_flow(&t);

    t
}

/// Reconstrói parágrafos fluidos preservando blocos especiais (poemas, tabelas, cabeçalhos, divisores)
fn reconstruct_paragraph_flow(text: &str) -> String {
    let raw_blocks: Vec<&str> = text.split("\n\n").map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    let mut final_paras: Vec<String> = Vec::new();
    let has_global_poetic_context = poetry::POEM_CUES_REGEX.is_match(text) || poetry::FAMOUS_POETS_REGEX.is_match(text);

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
            || poetry::POEM_CUES_REGEX.is_match(prev_block_text)
            || poetry::FAMOUS_POETS_REGEX.is_match(prev_block_text)
            || poetry::POEM_CUES_REGEX.is_match(block)
            || poetry::FAMOUS_POETS_REGEX.is_match(block);

        let unsquashed = poetry::unsquash_poem_lines(block);
        let lines: Vec<&str> = unsquashed.split('\n').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();

        let mut lines_owned: Vec<String> = lines.into_iter().map(|s| s.to_string()).collect();
        let is_intro = !lines_owned.is_empty() && (lines_owned[0].ends_with(':') || poetry::INTRO_COMMAND_REGEX.is_match(&lines_owned[0]));
        if lines_owned.len() >= 3 && is_intro {
            final_paras.push(lines_owned[0].clone());
            lines_owned.drain(..1);
        }

        let lines_refs: Vec<&str> = lines_owned.iter().map(|s| s.as_str()).collect();

        // Se o bloco inteiro é uma estrofe
        if poetry::is_poem_stanza_block(&lines_refs, has_local_poetic_context) {
            final_paras.push(poetry::format_poem_stanza(&lines_refs));
            continue;
        }

        // Se o bloco contém uma estrofe seguida de prosa/comentário
        if has_local_poetic_context && lines_owned.len() >= 3 {
            for split_idx in 2..lines_owned.len() {
                let verse_refs: Vec<&str> = lines_owned[..split_idx].iter().map(|s| s.as_str()).collect();
                let first_rem = lines_owned[split_idx].trim().trim_matches(|c| c == '*' || c == '_' || c == '`');
                if poetry::PROSE_PROMPT_REGEX.is_match(first_rem) || poetry::is_author_attribution(first_rem) || !poetry::is_verse_line(&lines_owned[split_idx]) {
                    if poetry::is_poem_stanza_block(&verse_refs, true) {
                        final_paras.push(poetry::format_poem_stanza(&verse_refs));
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
