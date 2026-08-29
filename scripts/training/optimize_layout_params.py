#!/usr/bin/env python3
import os
import sys
import glob
import json
import itertools
from typing import List, Dict, Any, Tuple

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from services.pdf_pipeline.layout.layout_detector import LayoutConfig
from services.pdf_pipeline.hybrid_extractor import parse_exam_document

def load_evaluation_corpus(max_samples: int = 15) -> List[Tuple[str, int, Dict[str, Any]]]:
    """
    Carrega pares de (caminho_pdf, total_questoes_esperadas, metadata) para avaliação.
    Utiliza PDFs existentes em pdfs/ e correspondências em training_corpus/.
    """
    corpus_files = glob.glob(os.path.join(_repo_root, "training_corpus", "*.json"))
    pdf_files = glob.glob(os.path.join(_repo_root, "pdfs", "*.pdf"))
    
    samples = []
    
    # 1. Pareamento por PDFs existentes
    for pdf_path in pdf_files:
        if "_gab_" in pdf_path:
            continue
        filename = os.path.splitext(os.path.basename(pdf_path))[0]
        matching_json = None
        for jf in corpus_files:
            if filename in os.path.basename(jf):
                matching_json = jf
                break
        
        expected_q_count = 0
        if matching_json and os.path.exists(matching_json):
            try:
                with open(matching_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    qs = data.get("questions") or data.get("questoes") or []
                    expected_q_count = len(qs)
            except Exception:
                expected_q_count = 0

        samples.append((pdf_path, expected_q_count, {"source": "pdf", "name": filename}))
        if len(samples) >= max_samples:
            break

    return samples

def evaluate_config_on_samples(
    config: LayoutConfig,
    samples: List[Tuple[str, int, Dict[str, Any]]]
) -> Dict[str, Any]:
    """Avalia uma configuração de layout calculando pontuação agregada de fidelidade."""
    total_samples = len(samples)
    if total_samples == 0:
        return {"score": 0.0, "total_extracted": 0, "valid_options_pct": 0.0}

    total_extracted = 0
    total_valid_options = 0
    exact_count_matches = 0

    for pdf_path, expected_count, _ in samples:
        try:
            questions = parse_exam_document(
                pdf_bytes_or_path=pdf_path,
                extract_images=False,
                layout_config=config
            )
            q_count = len(questions)
            total_extracted += q_count
            
            if expected_count > 0 and q_count == expected_count:
                exact_count_matches += 1
            elif expected_count == 0 and q_count >= 5:
                exact_count_matches += 1

            for q in questions:
                opts = q.get("opcoes") or {}
                if len(opts) >= 2:
                    total_valid_options += 1
        except Exception:
            continue

    valid_opts_pct = (total_valid_options / total_extracted * 100) if total_extracted > 0 else 0.0
    accuracy_score = (exact_count_matches / total_samples * 50.0) + (valid_opts_pct * 0.5)

    return {
        "score": round(accuracy_score, 2),
        "total_extracted": total_extracted,
        "valid_options_pct": round(valid_opts_pct, 1),
        "exact_matches": exact_count_matches,
        "total_samples": total_samples
    }

def run_grid_search(samples: List[Tuple[str, int, Dict[str, Any]]]):
    """Executa busca em grade dos hiperparâmetros de layout."""
    print("=" * 70, flush=True)
    print("🔍 OTIMIZAÇÃO PARAMÉTRICA DE HIPERPARÂMETROS DE LAYOUT (GRID SEARCH)", flush=True)
    print("=" * 70, flush=True)
    print(f"📊 Total de PDFs/Provas na amostra de calibração: {len(samples)}\n", flush=True)

    param_grid = {
        "full_width_threshold": [0.50, 0.55],
        "y_overlap_tolerance": [5.0, 6.0, 7.0],
        "column_gutter_margin": [25.0, 30.0, 35.0],
        "min_overlapping_pairs": [2, 3],
        "stitch_gap_max": [20.0, 25.0],
    }

    keys = list(param_grid.keys())
    combinations = list(itertools.product(*(param_grid[k] for k in keys)))
    print(f"⚙️  Testando {len(combinations)} combinações paramétricas...\n", flush=True)

    best_score = -1.0
    best_config = LayoutConfig()
    best_metrics = {}

    for idx, comb in enumerate(combinations, start=1):
        kw = dict(zip(keys, comb))
        cfg = LayoutConfig(**kw)
        metrics = evaluate_config_on_samples(cfg, samples)

        if metrics["score"] > best_score:
            best_score = metrics["score"]
            best_config = cfg
            best_metrics = metrics
            print(f"⭐ [Melhoria #{idx}/{len(combinations)}] Score: {metrics['score']}% | Questões Extraídas: {metrics['total_extracted']} | Opções Válidas: {metrics['valid_options_pct']}%", flush=True)
            print(f"   Parâmetros: {kw}\n", flush=True)

    print("=" * 70, flush=True)
    print("🏆 RESULTADO FINAL DA OTIMIZAÇÃO DE HIPERPARÂMETROS", flush=True)
    print("=" * 70, flush=True)
    print(f"Score Geral: {best_metrics.get('score', 0)}%")
    print(f"Taxa de Opções Válidas: {best_metrics.get('valid_options_pct', 0)}%")
    print(f"Provas com Contagem Exata: {best_metrics.get('exact_matches', 0)}/{best_metrics.get('total_samples', 0)}")
    print("\nHiperparâmetros Ótimos Recomendados:")
    print(f"  • full_width_threshold  = {best_config.full_width_threshold}")
    print(f"  • y_overlap_tolerance   = {best_config.y_overlap_tolerance}")
    print(f"  • column_gutter_margin  = {best_config.column_gutter_margin}")
    print(f"  • min_overlapping_pairs = {best_config.min_overlapping_pairs}")
    print(f"  • stitch_gap_max        = {best_config.stitch_gap_max}")
    print("=" * 70)

if __name__ == "__main__":
    evaluation_samples = load_evaluation_corpus(max_samples=10)
    if not evaluation_samples:
        print("ℹ️  Nenhum PDF encontrado em 'pdfs/' para benchmark direto. Testando configuração padrão...")
        default_cfg = LayoutConfig()
        print(f"Configuração default ativa: {default_cfg}")
    else:
        run_grid_search(evaluation_samples)
