//! concurse.io — Motor Central em Rust (concurse_core)
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

mod patterns;
mod dp_chain;
mod subject_classifier;
mod typography;
mod option_parser;

use patterns::{
    HEADER_REGEX, OPTION_PRIMARY_REGEX, OPTION_NEWLINE_REGEX,
    CONTEXT_TEXT_BANNER_REGEX, IMAGE_TRIGGER_REGEX, CAPTION_REGEX
};
use dp_chain::{QuestionCandidate, solve_dp_chain};
use subject_classifier::{
    classify_subject_canonical as rust_classify_canonical,
    scan_subject_sections as rust_scan_sections
};
use typography::{
    restore_exam_typography_native,
    restore_ocr_lexical_spacing_native,
    clean_text_artifacts_native
};
use option_parser::parse_question_body_native;

#[inline]
fn safe_prefix_slice<'a>(s: &'a str, end_byte: usize, max_lookback_bytes: usize) -> &'a str {
    let mut start = end_byte.saturating_sub(max_lookback_bytes);
    while start > 0 && !s.is_char_boundary(start) {
        start = start.saturating_sub(1);
    }
    let mut end = end_byte.min(s.len());
    while end > 0 && !s.is_char_boundary(end) {
        end = end.saturating_sub(1);
    }
    if start <= end {
        &s[start..end]
    } else {
        ""
    }
}

fn byte_to_char_index(s: &str, byte_offset: usize) -> usize {
    let mut bound = byte_offset.min(s.len());
    while bound > 0 && !s.is_char_boundary(bound) {
        bound = bound.saturating_sub(1);
    }
    s[..bound].chars().count()
}

/// Executa o pipeline de texto completo em Rust (zero ping-pong FFI)
#[pyfunction]
fn process_exam_text(py: Python, full_text: &str) -> PyResult<PyObject> {
    let text_len = full_text.len();
    if text_len == 0 {
        return Ok(PyList::empty_bound(py).into());
    }

    // 1. Escaneia seções e títulos de disciplinas
    let sections = rust_scan_sections(full_text);

    // 2. Escaneia banners de textos de apoio (Context Banners)
    let mut context_blocks = Vec::new();
    for cap in CONTEXT_TEXT_BANNER_REGEX.captures_iter(full_text) {
        if let (Some(m_all), Some(m_q1), Some(m_q2)) = (cap.get(1), cap.get(2), cap.get(3)) {
            if let (Ok(q1), Ok(q2)) = (m_q1.as_str().parse::<usize>(), m_q2.as_str().parse::<usize>()) {
                if q1 <= q2 && q2 - q1 <= 50 {
                    context_blocks.push((q1, q2, m_all.start(), m_all.end()));
                }
            }
        }
    }

    // 3. Escaneia cabeçalhos de questões e calcula DP Chain ótimo
    let mut candidates = Vec::new();
    for cap in HEADER_REGEX.captures_iter(full_text) {
        let m = cap.get(0).unwrap();
        let q_str = cap.get(1).or_else(|| cap.get(2)).or_else(|| cap.get(3)).or_else(|| cap.get(4));
        if let Some(m_str) = q_str {
            if let Ok(q_num) = m_str.as_str().parse::<usize>() {
                if (1..=200).contains(&q_num) {
                    let is_explicit = cap.get(1).is_some();
                    if !is_explicit {
                        let prefix_slice = safe_prefix_slice(full_text, m.start(), 40);
                        let last_nl = prefix_slice.rfind('\n').map(|idx| idx + 1).unwrap_or(0);
                        let same_line_prefix = &prefix_slice[last_nl..];
                        let prefix_upper = same_line_prefix.to_uppercase();
                        if prefix_upper.contains("QUADRO")
                            || prefix_upper.contains("FIGURA")
                            || prefix_upper.contains("TABELA")
                            || prefix_upper.contains("TEXTO")
                            || prefix_upper.contains("PÁGINA")
                            || prefix_upper.contains("PAGINA")
                            || prefix_upper.contains("ART.")
                            || prefix_upper.contains("ARTIGO")
                            || prefix_upper.contains("QUESTÕES DE")
                            || prefix_upper.contains("QUESTOES DE")
                        {
                            continue;
                        }
                    }
                    candidates.push(QuestionCandidate {
                        start: m.start(),
                        end: m.end(),
                        number: q_num,
                        is_explicit,
                    });
                }
            }
        }
    }

    let optimal_chain = solve_dp_chain(&candidates);
    let py_list = PyList::empty_bound(py);
    let n = optimal_chain.len();

    // 4. Mapeia e formata os textos de apoio compartilhados
    let mut resolved_contexts = Vec::new();
    for (q_min, q_max, _b_start, b_end) in &context_blocks {
        let mut ctx_end = text_len;
        for item in &optimal_chain {
            if item.number >= *q_min && item.start > *b_end {
                ctx_end = item.start;
                break;
            }
        }
        if *b_end < ctx_end {
            let ctx_raw = &full_text[*b_end..ctx_end];
            let ctx_clean = restore_exam_typography_native(ctx_raw, false);
            if !ctx_clean.trim().is_empty() {
                resolved_contexts.push((*q_min, *q_max, ctx_clean));
            }
        }
    }

    // 5. Itera sobre cada questão fatiando alternativas e aplicando tipografia nativa
    for (i, item) in optimal_chain.iter().enumerate() {
        let q_num = item.number;
        let start_byte = item.start;
        let end_byte = item.end;
        let next_start = if i + 1 < n { optimal_chain[i + 1].start } else { text_len };

        let chunk_raw = if end_byte <= next_start && next_start <= text_len {
            &full_text[end_byte..next_start]
        } else {
            ""
        };

        let parsed = parse_question_body_native(chunk_raw);

        // Mapeia a matéria ativa para a posição da questão
        let mut active_subject = "Geral";
        for sec in &sections {
            if sec.start <= start_byte {
                active_subject = sec.canonical_name;
            } else {
                break;
            }
        }

        if active_subject == "Geral" {
            let inferred = rust_classify_canonical(&parsed.enunciado);
            if inferred != "Geral" {
                active_subject = inferred;
            }
        }

        // Anexa texto de apoio se aplicável
        let mut final_enunciado = parsed.enunciado;
        for (q_min, q_max, ctx_text) in &resolved_contexts {
            if *q_min <= q_num && q_num <= *q_max {
                let check_len = ctx_text.len().min(30);
                if !final_enunciado.contains(&ctx_text[..check_len]) {
                    final_enunciado = format!("📖 **Texto de Apoio (Questões {} a {}):**\n\n{}\n\n---\n\n{}", q_min, q_max, ctx_text, final_enunciado);
                }
                break;
            }
        }

        final_enunciado = restore_exam_typography_native(&final_enunciado, false);

        let dict = PyDict::new_bound(py);
        dict.set_item("numero_questao", q_num.to_string())?;
        dict.set_item("enunciado", final_enunciado)?;

        let opts_dict = PyDict::new_bound(py);
        for (k, v) in parsed.opcoes {
            opts_dict.set_item(k, v)?;
        }
        dict.set_item("opcoes", opts_dict)?;

        let fallback_ans = if parsed.is_certo_errado { "C" } else { "A" };
        dict.set_item("resposta", parsed.embedded_answer.unwrap_or_else(|| fallback_ans.to_string()))?;
        dict.set_item("disciplina", active_subject)?;
        dict.set_item("is_certo_errado", parsed.is_certo_errado)?;
        dict.set_item("start_char", byte_to_char_index(full_text, start_byte))?;
        dict.set_item("end_char", byte_to_char_index(full_text, end_byte))?;

        py_list.append(dict)?;
    }

    Ok(py_list.into())
}

/// Restauração tipográfica exportada para o Python
#[pyfunction]
fn restore_exam_typography(_py: Python, text: &str, is_option: Option<bool>) -> PyResult<String> {
    Ok(restore_exam_typography_native(text, is_option.unwrap_or(false)))
}

/// Desacoplamento léxico de OCR exportado para o Python
#[pyfunction]
fn restore_ocr_lexical_spacing(_py: Python, text: &str) -> PyResult<String> {
    Ok(restore_ocr_lexical_spacing_native(text))
}

/// Limpeza de artefatos de texto exportada para o Python
#[pyfunction]
fn clean_text_artifacts(_py: Python, text: &str) -> PyResult<String> {
    Ok(clean_text_artifacts_native(text))
}

/// Escaneia todo o texto e extrai os cabeçalhos válidos de questões usando DP Chain
#[pyfunction]
fn scan_question_headers(py: Python, full_text: &str) -> PyResult<PyObject> {
    let mut candidates = Vec::new();

    for cap in HEADER_REGEX.captures_iter(full_text) {
        let m = cap.get(0).unwrap();
        let q_str = cap.get(1).or_else(|| cap.get(2)).or_else(|| cap.get(3)).or_else(|| cap.get(4));
        
        if let Some(m_str) = q_str {
            if let Ok(q_num) = m_str.as_str().parse::<usize>() {
                if (1..=200).contains(&q_num) {
                    let is_explicit = cap.get(1).is_some();
                    if !is_explicit {
                        let prefix_slice = safe_prefix_slice(full_text, m.start(), 40);
                        let last_nl = prefix_slice.rfind('\n').map(|idx| idx + 1).unwrap_or(0);
                        let same_line_prefix = &prefix_slice[last_nl..];
                        let prefix_upper = same_line_prefix.to_uppercase();
                        if prefix_upper.contains("QUADRO")
                            || prefix_upper.contains("FIGURA")
                            || prefix_upper.contains("TABELA")
                            || prefix_upper.contains("TEXTO")
                            || prefix_upper.contains("PÁGINA")
                            || prefix_upper.contains("PAGINA")
                            || prefix_upper.contains("ART.")
                            || prefix_upper.contains("ARTIGO")
                            || prefix_upper.contains("QUESTÕES DE")
                            || prefix_upper.contains("QUESTOES DE")
                        {
                            continue;
                        }
                    }

                    candidates.push(QuestionCandidate {
                        start: m.start(),
                        end: m.end(),
                        number: q_num,
                        is_explicit,
                    });
                }
            }
        }
    }

    let optimal_chain = solve_dp_chain(&candidates);
    let py_list = PyList::empty_bound(py);

    for item in optimal_chain {
        let char_start = byte_to_char_index(full_text, item.start);
        let char_end = byte_to_char_index(full_text, item.end);
        let dict = PyDict::new_bound(py);
        dict.set_item("number", item.number)?;
        dict.set_item("start", char_start)?;
        dict.set_item("end", char_end)?;
        dict.set_item("is_explicit", item.is_explicit)?;
        py_list.append(dict)?;
    }

    Ok(py_list.into())
}

/// Identifica blocos de textos de apoio compartilhados e banners
#[pyfunction]
fn scan_context_banners(py: Python, full_text: &str) -> PyResult<PyObject> {
    let py_list = PyList::empty_bound(py);

    for cap in CONTEXT_TEXT_BANNER_REGEX.captures_iter(full_text) {
        if let (Some(m_all), Some(m_q1), Some(m_q2)) = (cap.get(1), cap.get(2), cap.get(3)) {
            if let (Ok(q1), Ok(q2)) = (m_q1.as_str().parse::<usize>(), m_q2.as_str().parse::<usize>()) {
                if q1 <= q2 && q2 - q1 <= 50 {
                    let char_start = byte_to_char_index(full_text, m_all.start());
                    let char_end = byte_to_char_index(full_text, m_all.end());
                    let dict = PyDict::new_bound(py);
                    dict.set_item("q_min", q1)?;
                    dict.set_item("q_max", q2)?;
                    dict.set_item("banner_start", char_start)?;
                    dict.set_item("banner_end", char_end)?;
                    py_list.append(dict)?;
                }
            }
        }
    }

    Ok(py_list.into())
}

/// Parseia as alternativas de uma questão selecionando a melhor sequência (A..E)
#[pyfunction]
fn parse_options_fast(py: Python, chunk: &str) -> PyResult<PyObject> {
    let chunk_len = chunk.len();
    let mut matches = Vec::new();

    for cap in OPTION_PRIMARY_REGEX.captures_iter(chunk) {
        let m = cap.get(0).unwrap();
        let letter = cap.get(1).or_else(|| cap.get(2)).or_else(|| cap.get(3)).or_else(|| cap.get(4))
            .map(|l| l.as_str().to_uppercase()).unwrap_or_default();
        if !letter.is_empty() {
            matches.push((m.start(), m.end(), letter));
        }
    }

    if matches.is_empty() {
        for cap in OPTION_NEWLINE_REGEX.captures_iter(chunk) {
            let m = cap.get(0).unwrap();
            let letter = cap.get(1).map(|l| l.as_str().to_uppercase()).unwrap_or_default();
            if !letter.is_empty() {
                matches.push((m.start(), m.end(), letter));
            }
        }
    }

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

            if seq.len() >= 3 {
                let score = (seq.len() as f64) * 1000.0 + (seq[0].0 as f64 / chunk_len.max(1) as f64) * 100.0;
                if score > best_score {
                    best_score = score;
                    best_seq = seq;
                }
            }
        }
    }

    let result = PyDict::new_bound(py);
    if best_seq.len() >= 2 {
        let first_start = best_seq[0].0;
        let enunciado = &chunk[..first_start];
        result.set_item("enunciado", enunciado)?;

        let options_dict = PyDict::new_bound(py);
        for (idx, opt) in best_seq.iter().enumerate() {
            let s_val = opt.1;
            let e_val = if idx + 1 < best_seq.len() { best_seq[idx + 1].0 } else { chunk_len };
            let opt_text = chunk[s_val..e_val].trim();
            options_dict.set_item(&opt.2, opt_text)?;
        }
        result.set_item("options", options_dict)?;
        result.set_item("is_certo_errado", false)?;
    } else {
        result.set_item("enunciado", chunk)?;
        let options_dict = PyDict::new_bound(py);
        options_dict.set_item("C", "Certo")?;
        options_dict.set_item("E", "Errado")?;
        result.set_item("options", options_dict)?;
        result.set_item("is_certo_errado", true)?;
    }

    Ok(result.into())
}

/// Classifica deterministamente um texto ou cabeçalho de disciplina para seu nome canônico
#[pyfunction]
fn classify_subject_canonical(_py: Python, raw_text: &str) -> PyResult<String> {
    Ok(rust_classify_canonical(raw_text).to_string())
}

/// Escaneia todo o texto de uma prova em busca de banners e seções de disciplinas
#[pyfunction]
fn scan_subject_sections(py: Python, full_text: &str) -> PyResult<PyObject> {
    let sections = rust_scan_sections(full_text);
    let py_list = PyList::empty_bound(py);

    for sec in sections {
        let dict = PyDict::new_bound(py);
        dict.set_item("raw_header", sec.raw_header)?;
        dict.set_item("canonical_name", sec.canonical_name)?;
        dict.set_item("start", sec.start)?;
        dict.set_item("end", sec.end)?;
        py_list.append(dict)?;
    }

    Ok(py_list.into())
}

/// Verifica e extrai menções e gatilhos reais de imagens/diagramas em um texto/enunciado
#[pyfunction]
fn match_image_triggers(py: Python, text: &str) -> PyResult<PyObject> {
    let dict = PyDict::new_bound(py);
    let mut triggers = Vec::new();
    let mut has_trigger = false;

    for cap in IMAGE_TRIGGER_REGEX.captures_iter(text) {
        if let Some(m) = cap.get(0) {
            has_trigger = true;
            triggers.push(m.as_str().to_lowercase());
        }
    }

    let is_caption = CAPTION_REGEX.is_match(text);

    dict.set_item("has_trigger", has_trigger)?;
    dict.set_item("triggers", triggers)?;
    dict.set_item("is_caption", is_caption)?;

    Ok(dict.into())
}

/// Função de verificação de disponibilidade nativa
#[pyfunction]
fn is_native_available() -> bool {
    true
}

/// Módulo Python exportado via PyO3
#[pymodule]
fn concurse_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_exam_text, m)?)?;
    m.add_function(wrap_pyfunction!(restore_exam_typography, m)?)?;
    m.add_function(wrap_pyfunction!(restore_ocr_lexical_spacing, m)?)?;
    m.add_function(wrap_pyfunction!(clean_text_artifacts, m)?)?;
    m.add_function(wrap_pyfunction!(scan_question_headers, m)?)?;
    m.add_function(wrap_pyfunction!(scan_context_banners, m)?)?;
    m.add_function(wrap_pyfunction!(parse_options_fast, m)?)?;
    m.add_function(wrap_pyfunction!(classify_subject_canonical, m)?)?;
    m.add_function(wrap_pyfunction!(scan_subject_sections, m)?)?;
    m.add_function(wrap_pyfunction!(match_image_triggers, m)?)?;
    m.add_function(wrap_pyfunction!(is_native_available, m)?)?;
    Ok(())
}
