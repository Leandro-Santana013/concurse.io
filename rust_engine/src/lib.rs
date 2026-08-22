//! concurse.io — Motor Central em Rust (concurse_core)
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

mod patterns;
mod dp_chain;
mod subject_classifier;

use patterns::{
    HEADER_REGEX, OPTION_PRIMARY_REGEX, OPTION_NEWLINE_REGEX,
    CONTEXT_TEXT_BANNER_REGEX, IMAGE_TRIGGER_REGEX, CAPTION_REGEX
};
use dp_chain::{QuestionCandidate, solve_dp_chain};
use subject_classifier::{
    classify_subject_canonical as rust_classify_canonical,
    scan_subject_sections as rust_scan_sections
};

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
        let dict = PyDict::new_bound(py);
        dict.set_item("number", item.number)?;
        dict.set_item("start", item.start)?;
        dict.set_item("end", item.end)?;
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
                    let dict = PyDict::new_bound(py);
                    dict.set_item("q_min", q1)?;
                    dict.set_item("q_max", q2)?;
                    dict.set_item("banner_start", m_all.start())?;
                    dict.set_item("banner_end", m_all.end())?;
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

    // Busca a melhor sequência contínua (ex: A, B, C, D, E)
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
    m.add_function(wrap_pyfunction!(scan_question_headers, m)?)?;
    m.add_function(wrap_pyfunction!(scan_context_banners, m)?)?;
    m.add_function(wrap_pyfunction!(parse_options_fast, m)?)?;
    m.add_function(wrap_pyfunction!(classify_subject_canonical, m)?)?;
    m.add_function(wrap_pyfunction!(scan_subject_sections, m)?)?;
    m.add_function(wrap_pyfunction!(match_image_triggers, m)?)?;
    m.add_function(wrap_pyfunction!(is_native_available, m)?)?;
    Ok(())
}
