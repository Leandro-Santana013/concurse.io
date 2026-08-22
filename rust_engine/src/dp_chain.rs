//! concurse.io — Algoritmo de Encadeamento Ótimo por Programação Dinâmica em Rust

#[derive(Debug, Clone)]
pub struct QuestionCandidate {
    pub start: usize,
    pub end: usize,
    pub number: usize,
    pub is_explicit: bool,
}

/// Encontra a cadeia contínua de questões com maior pontuação global
pub fn solve_dp_chain(candidates: &[QuestionCandidate]) -> Vec<QuestionCandidate> {
    let n = candidates.len();
    if n == 0 {
        return Vec::new();
    }

    let mut dp = vec![1i32; n];
    let mut prev = vec![None; n];

    for i in 0..n {
        let min_j = if i > 50 { i - 50 } else { 0 };
        for j in min_j..i {
            let diff = (candidates[i].number as i32) - (candidates[j].number as i32);
            let step_score = if diff == 1 {
                100 + if candidates[i].is_explicit { 5 } else { 0 }
            } else if (2..=4).contains(&diff) {
                (25 - diff * 5) + if candidates[i].is_explicit { 5 } else { 0 }
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
