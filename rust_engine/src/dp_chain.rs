//! concurse.io — Algoritmo de Encadeamento Ótimo por Programação Dinâmica em Rust

#[derive(Debug, Clone)]
pub struct QuestionCandidate {
    pub start: usize,
    pub end: usize,
    pub number: usize,
    pub is_explicit: bool,
}

/// Encontra a cadeia contínua de questões com maior pontuação global, respeitando quebras de disciplinas
pub fn solve_dp_chain(candidates: &[QuestionCandidate]) -> Vec<QuestionCandidate> {
    solve_dp_chain_with_sections(candidates, &[])
}

/// Encontra a cadeia ótima de questões, permitindo reinício em Q1 caso haja transição de seção/disciplina
pub fn solve_dp_chain_with_sections(candidates: &[QuestionCandidate], section_boundaries: &[usize]) -> Vec<QuestionCandidate> {
    let n = candidates.len();
    if n == 0 {
        return Vec::new();
    }

    let mut dp = vec![1i32; n];
    let mut prev = vec![None; n];

    for i in 0..n {
        let min_j = if i > 100 { i - 100 } else { 0 };
        for j in min_j..i {
            let diff = (candidates[i].number as i32) - (candidates[j].number as i32);
            let dist = candidates[i].start.saturating_sub(candidates[j].end);
            
            // Rejeita saltos absurdamente longos (> 20000 caracteres) se houver opções melhores
            let dist_penalty = if dist > 20000 { 30 } else if dist > 10000 { 15 } else if dist > 5000 { 5 } else { 0 };

            // Penalidade anti-subitem: afirmativas internas ("1. ...", "2. ...") aparecem
            // aglomeradas (<250 chars entre si) dentro do corpo de uma mesma questão.
            // Questões reais FGV/CESPE distanciam-se por 400+ chars (enunciado + 5 opções).
            // Sem isso, a cadeia falsa 1-4 dentro da Q13 superava a cadeia verdadeira 12->13->14.
            let subitem_penalty = if dist < 120 { 600 } else if dist < 250 { 350 } else { 0 };

            // Verifica se há transição de disciplina entre j e i
            let crosses_section = section_boundaries.iter().any(|&b| b >= candidates[j].end && b <= candidates[i].start);

            let step_score = if diff == 1 {
                1000 
                + (if candidates[i].is_explicit { 200 } else { 0 })
                + (if candidates[j].is_explicit { 200 } else { 0 })
                - dist_penalty
                - subitem_penalty
            } else if (2..=10).contains(&diff) {
                (200 - diff * 15) 
                + (if candidates[i].is_explicit { 50 } else { 0 }) 
                + (if candidates[j].is_explicit { 50 } else { 0 }) 
                - dist_penalty
                - subitem_penalty
            } else if crosses_section && candidates[i].number == 1 {
                // Reinício em Q1 após banner de matéria (provas com numeração por disciplina).
                // Score deliberadamente baixo (300 < 1000) para que a continuação direta
                // (ex: 12->13) sempre vença o reinício falso (ex: 12->1 de subitem).
                // Antes era 800, o que permitia à cadeia falsa 1-4 dentro da Q13 da
                // DATAPREV superar a cadeia verdadeira e deslocar toda a numeração.
                300
                + (if candidates[i].is_explicit { 200 } else { 0 })
                - dist_penalty
                - subitem_penalty
            } else {
                continue;
            };

            if dp[j] + step_score > dp[i] {
                dp[i] = dp[j] + step_score;
                prev[i] = Some(j);
            }
        }
    }

    let mut best_idx = 0;
    let mut max_score = dp[0];
    for (idx, &score) in dp.iter().enumerate() {
        if score > max_score {
            max_score = score;
            best_idx = idx;
        }
    }

    let mut result = Vec::new();
    let mut curr = Some(best_idx);
    while let Some(idx) = curr {
        result.push(candidates[idx].clone());
        curr = prev[idx];
    }
    result.reverse();
    result
}

/// Seleciona a melhor cadeia entre a estrita (sem reinício) e a com seções.
///
/// Critério: maior contagem de números únicos vence — a cadeia com reinício
/// falso (ex: DATAPREV 1..12,1..4,14..70 = 69 únicos, com duplicatas) perde
/// para a cadeia contínua verdadeira (1..70 = 70 únicos). Em provas com
/// reinício legítimo por disciplina (ex: 1..10,1..10), a cadeia com seções
/// é mais longa e vence no desempate por comprimento total.
pub fn select_best_chain(
    strict_chain: Vec<QuestionCandidate>,
    section_chain: Vec<QuestionCandidate>,
) -> Vec<QuestionCandidate> {
    use std::collections::HashSet;
    let strict_unique: HashSet<usize> = strict_chain.iter().map(|c| c.number).collect();
    let section_unique: HashSet<usize> = section_chain.iter().map(|c| c.number).collect();
    if section_unique.len() > strict_unique.len() {
        return section_chain;
    }
    if strict_unique.len() > section_unique.len() {
        return strict_chain;
    }
    // Empate em únicos: prefere a cadeia mais longa (cobertura), depois a estrita.
    if section_chain.len() > strict_chain.len() {
        return section_chain;
    }
    strict_chain
}
