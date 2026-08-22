import re
from typing import List, Dict, Any, Tuple, Optional
import fitz

from services.pdf_pipeline.layout_detector import (
    extract_ocr_lines_from_page,
    detect_watermarks
)
from services.pdf_pipeline.typography_restorer import restore_exam_typography, restore_ocr_lexical_spacing
from services.pdf_pipeline.formula_formatter import format_latex_formulas

def extract_exam_via_vision_ocr(
    doc: fitz.Document,
    dpi: int = 160,
    watermarks: Optional[set] = None
) -> List[Dict[str, Any]]:
    """
    Pipeline especializado de OCR Vision:
    Renderiza páginas como imagem, detecta caixas delimitadoras de linhas via RapidOCR,
    reconstrói colunas preservando faixas horizontais de largura total (tirinhas/poemas)
    e extrai enunciados com alternativas completas A..E.
    """
    if watermarks is None:
        watermarks = detect_watermarks(doc)

    ordered_page_blocks = []
    
    for p_idx in range(len(doc)):
        page = doc[p_idx]
        lines = extract_ocr_lines_from_page(page, dpi=dpi)
        if not lines:
            continue
            
        # Filtra marcas d'água e ruídos
        clean_lines = []
        for l in lines:
            txt = l['text'].strip()
            if not txt:
                continue
            if re.search(r'pcimarkpci|www\.pciconcursos\.com\.br|qconcursos\.com', txt, re.IGNORECASE):
                continue
            clean_lines.append(l)
            
        if not clean_lines:
            continue

        page_w = page.rect.width
        mid_x = page_w / 2.0
        
        # Identifica faixas de largura total (Full-width banners) vs Colunas duplas
        # Linhas com largura > 55% da página são consideradas horizontais completas
        full_width_lines = [l for l in clean_lines if l['width'] > (page_w * 0.55)]
        col_lines = [l for l in clean_lines if l['width'] <= (page_w * 0.55)]
        
        # Agrupa linhas por Y para reconstruir leitura lógica
        # 1. Faixas superiores de largura total (ex: poemas ou tirinhas)
        top_full = [l for l in full_width_lines if l['y0'] < (page.rect.height * 0.45)]
        bottom_full = [l for l in full_width_lines if l['y0'] >= (page.rect.height * 0.45)]
        
        left_col = [l for l in col_lines if l['mid_x'] < mid_x]
        right_col = [l for l in col_lines if l['mid_x'] >= mid_x]
        
        # Ordena cada grupo por Y
        top_full.sort(key=lambda l: l['y0'])
        bottom_full.sort(key=lambda l: l['y0'])
        left_col.sort(key=lambda l: l['y0'])
        right_col.sort(key=lambda l: l['y0'])
        
        page_text_parts = []
        if top_full:
            page_text_parts.append("\n".join(l['text'] for l in top_full))
        if left_col:
            page_text_parts.append("\n".join(l['text'] for l in left_col))
        if right_col:
            page_text_parts.append("\n".join(l['text'] for l in right_col))
        if bottom_full:
            page_text_parts.append("\n".join(l['text'] for l in bottom_full))
            
        p_combined_text = "\n\n".join(page_text_parts)
        # Aplica restaurador léxico
        p_combined_text = restore_ocr_lexical_spacing(p_combined_text)
        ordered_page_blocks.append(p_combined_text)

    full_text = "\n\n".join(ordered_page_blocks)
    return full_text
