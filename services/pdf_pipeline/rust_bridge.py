"""
concurse.io — Ponte Híbrida de Integração Python <-> Rust (concurse_core)
========================================================================
Fornece acesso de altíssima performance aos algoritmos de varredura Regex,
DFA linear, Encadeamento Ótimo por Programação Dinâmica (DP Chain),
classificação taxonômica de disciplinas e detecção nativa de gatilhos de diagramas.

Se o binário compilado em Rust estiver disponível, utiliza execução nativa compilada;
caso contrário, recorre transparentemente ao fallback em Python puro.
"""

import sys
from typing import List, Dict, Any, Tuple, Optional

_RUST_AVAILABLE = False
concurse_core = None

try:
    from . import concurse_core
    _RUST_AVAILABLE = True
except (ImportError, ValueError):
    try:
        import concurse_core
        _RUST_AVAILABLE = True
    except (ImportError, ValueError):
        concurse_core = None

def is_rust_available() -> bool:
    """Informa se o motor de alta performance em Rust está ativo."""
    return _RUST_AVAILABLE

def rust_scan_question_headers(full_text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Executa a varredura global de cabeçalhos e resolve o DP Chain em Rust.
    Retorna lista de dicts: [{'number': int, 'start': int, 'end': int, 'is_explicit': bool}, ...]
    """
    if not _RUST_AVAILABLE or not concurse_core:
        return None
    try:
        return concurse_core.scan_question_headers(full_text)
    except Exception:
        return None

def rust_scan_context_banners(full_text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Identifica banners de textos de apoio compartilhados em Rust.
    Retorna lista de dicts: [{'q_min': int, 'q_max': int, 'banner_start': int, 'banner_end': int}, ...]
    """
    if not _RUST_AVAILABLE or not concurse_core:
        return None
    try:
        return concurse_core.scan_context_banners(full_text)
    except Exception:
        return None

def rust_parse_options_fast(chunk: str) -> Optional[Dict[str, Any]]:
    """
    Parseia e seleciona a melhor sequência contínua de alternativas em Rust.
    Retorna: {'enunciado': str, 'options': dict, 'is_certo_errado': bool}
    """
    if not _RUST_AVAILABLE or not concurse_core:
        return None
    try:
        return concurse_core.parse_options_fast(chunk)
    except Exception:
        return None

def rust_classify_subject(raw_text: str) -> Optional[str]:
    """
    Classifica deterministamente um texto/cabeçalho de disciplina para seu nome canônico via Rust.
    """
    if not _RUST_AVAILABLE or not concurse_core:
        return None
    try:
        res = concurse_core.classify_subject_canonical(raw_text)
        return res if res and res != "Geral" else None
    except Exception:
        return None

def rust_scan_subject_sections(full_text: str) -> Optional[List[Dict[str, Any]]]:
    """
    Escaneia todo o texto da prova em busca de banners de seções de disciplinas em Rust.
    Retorna lista de dicts: [{'raw_header': str, 'canonical_name': str, 'start': int, 'end': int}, ...]
    """
    if not _RUST_AVAILABLE or not concurse_core:
        return None
    try:
        return concurse_core.scan_subject_sections(full_text)
    except Exception:
        return None

def rust_match_image_triggers(text: str) -> Optional[Dict[str, Any]]:
    """
    Avalia a ocorrência de palavras-gatilho de imagem e legendas em Rust.
    Retorna: {'has_trigger': bool, 'triggers': List[str], 'is_caption': bool}
    """
    if not _RUST_AVAILABLE or not concurse_core:
        return None
    try:
        return concurse_core.match_image_triggers(text)
    except Exception:
        return None
