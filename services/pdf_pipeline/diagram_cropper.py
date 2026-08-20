"""
concurse.io — Motor Autônomo e Determinístico de Extração e Vinculação de Imagens em PDFs de Concursos
====================================================================================================
Este módulo é 100% autônomo, exportável e reutilizável. Ele implementa toda a lógica avançada
de captura visual (desenhos vetoriais + imagens raster), agrupamento geométrico espacial,
inclusão de legendas, filtro de marcas d'água estatísticas e anexamento em 2 fases às questões.

Funcionalidades:
----------------
1. Filtro Estatístico de Marcas d'Água e Logos Repetidos (ocorrências em N >= 3 páginas).
2. Clusterização Geométrica Híbrida:
   - Captura de Desenhos Vetoriais (fitz.Page.get_drawings: circuitos, geometrias, polígonos).
   - Captura de Imagens Raster (fitz.Page.get_images: fotos, gráficos rasterizados).
3. Inclusão Inteligente de Legendas Textuais Adjacentes ("Figura 1 - Circuito...", "Gráfico 2...").
4. Deduplicação Visual por Hash MD5 de Conteúdo de Imagem.
5. Anexamento Espacial em 2 Fases:
   - Fase 1 (Trigger Word): Alta precisão quando o enunciado menciona figuras/tabelas/gráficos.
   - Fase 2 (Gap Visual Scan): Alta cobertura para diagramas órfãos sem termos disparadores.
6. Exportação Flexível: Arquivos PNG em disco, manifesto JSON estruturado e modo CLI standalone.
"""

import os
import io
import re
import fitz  # PyMuPDF
import hashlib
import json
import argparse
from typing import List, Dict, Any, Optional, Tuple, Set


# =============================================================================
# CONSTANTES E PADRÕES REGEX DETERMINÍSTICOS
# =============================================================================

IMAGE_TRIGGER_PATTERN = (
    r'\b('
    r'figura|gr[áa]fico|quadro|tabela|diagrama|circuito|desenho|'
    r'ilustra[çc][ãa]o|mapa|esquema|imagem|paqu[íi]metro|circunfer[êe]ncia|'
    r'tetraedro|planta|fluxograma|fotografia|foto|tira|tirinha|charge|'
    r'cartum|organograma|cronograma|histograma'
    r')\b'
)

IMAGE_TRIGGER_REGEX = re.compile(IMAGE_TRIGGER_PATTERN, re.IGNORECASE)

CAPTION_PATTERN = (
    r'^\s*(?:'
    r'figura|gr[áa]fico|quadro|tabela|diagrama|circuito|mapa|esquema|'
    r'imagem|ilustra[çc][ãa]o|foto|tira|charge|cartum'
    r')\b(?:\s*(?:\d+|[A-Za-z]|I|II|III|IV|V|VI|VII|VIII|IX|X))?\s*[-–—:]?'
)

CAPTION_REGEX = re.compile(CAPTION_PATTERN, re.IGNORECASE)

MULTI_FIGURE_REGEX = re.compile(
    r'(?:figura|quadro|gr[áa]fico|tabela|imagem)\s*(?:2|II|III|IV|3|4)',
    re.IGNORECASE
)


# =============================================================================
# CLASSE PRINCIPAL: EXAM IMAGE EXTRACTOR
# =============================================================================

class ExamImageExtractor:
    """
    Motor de extração e associação espacial de imagens para cadernos de provas e questões.
    """

    def __init__(
        self,
        output_dir: str = "static/images/questions",
        dpi: int = 160,
        padding: int = 8,
        min_cluster_size: int = 25,
        min_cluster_area: int = 400,
        watermark_page_threshold: int = 3
    ):
        self.output_dir = output_dir
        self.dpi = dpi
        self.padding = padding
        self.min_cluster_size = min_cluster_size
        self.min_cluster_area = min_cluster_area
        self.watermark_page_threshold = watermark_page_threshold
        self.saved_image_hashes: Dict[str, str] = {}  # {md5_hash: relative_path}

    def detect_watermarks_and_headers(self, doc: fitz.Document) -> Set[Tuple[float, float, float, float]]:
        """
        Analisa todas as páginas do PDF e identifica retângulos de vetores ou imagens
        que se repetem em N ou mais páginas (marcas d'água, rodapés e cabeçalhos fixos).
        """
        rect_counts: Dict[Tuple[float, float, float, float], int] = {}
        for page in doc:
            for d in page.get_drawings():
                r = d['rect']
                if r.width < 5 or r.height < 5:
                    continue
                key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
                rect_counts[key] = rect_counts.get(key, 0) + 1

            for img_info in page.get_images():
                for r in page.get_image_rects(img_info[0]):
                    key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
                    rect_counts[key] = rect_counts.get(key, 0) + 1

        return {k for k, v in rect_counts.items() if v >= self.watermark_page_threshold}

    def find_diagram_clusters(
        self,
        page: fitz.Page,
        watermarks: Set[Tuple[float, float, float, float]],
        text_blocks: Optional[List[Any]] = None
    ) -> List[fitz.Rect]:
        """
        Agrupa elementos visuais (desenhos vetoriais + imagens raster) adjacentes
        em clusters geométricos coerentes e engloba legendas textuais explicativas.
        """
        useful_rects: List[fitz.Rect] = []
        page_w, page_h = page.rect.width, page.rect.height

        # 1. Desenhos vetoriais (geometrias, esquemas, circuitos)
        for d in page.get_drawings():
            r = d['rect']
            if r.width < 10 or r.height < 10:
                continue
            if r.y0 < 30 or r.y1 > page_h - 30:
                continue
            if r.height > page_h * 0.75:
                continue
            key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
            if key in watermarks:
                continue
            useful_rects.append(r)

        # 2. Imagens raster embutidas
        for img_info in page.get_images():
            for r in page.get_image_rects(img_info[0]):
                if r.width < 10 or r.height < 10:
                    continue
                if r.y0 < 30 or r.y1 > page_h - 30:
                    continue
                # Descarta scan de página inteira
                if r.height > page_h * 0.75 and r.width > page_w * 0.75:
                    continue
                key = (round(r.x0, -1), round(r.y0, -1), round(r.x1, -1), round(r.y1, -1))
                if key in watermarks:
                    continue
                useful_rects.append(r)

        if not useful_rects:
            return []

        # 3. Agrupamento espacial por proximidade (mesma coluna / bloco visual)
        clusters: List[fitz.Rect] = []
        for r in useful_rects:
            merged = False
            for c in clusters:
                if abs(r.x0 - c.x0) < page_w * 0.45 and (r.y0 <= c.y1 + 25 and r.y1 >= c.y0 - 25):
                    c.include_rect(r)
                    merged = True
                    break
            if not merged:
                clusters.append(fitz.Rect(r))

        # 4. Captura e Inclusão de Legendas Adjacentes (ex: 'Figura 1 - Mapa Político')
        if text_blocks:
            for c in clusters:
                for b in text_blocks:
                    x0, y0, x1, y1, text = b[:5]
                    text_clean = text.strip()
                    if CAPTION_REGEX.search(text_clean):
                        is_below = (0 <= y0 - c.y1 <= 25) and (abs(x0 - c.x0) < page_w * 0.4)
                        is_above = (0 <= c.y0 - y1 <= 25) and (abs(x0 - c.x0) < page_w * 0.4)
                        if is_below or is_above:
                            c.include_rect(fitz.Rect(x0, y0, x1, y1))

        return [c for c in clusters if c.width > self.min_cluster_size and c.height > self.min_cluster_size]

    def render_and_save_crop(
        self,
        page_obj: fitz.Page,
        cluster: fitz.Rect,
        exam_id: Any,
        q_num: Any,
        img_index: int
    ) -> Optional[str]:
        """
        Recorta a região delimitada com padding de segurança, renderiza em DPI configurado,
        calcula o hash MD5 e persiste a imagem no disco (com deduplicação automática).
        """
        page_w = page_obj.rect.width
        page_h = page_obj.rect.height
        pad = self.padding

        crop_rect = fitz.Rect(
            max(0, cluster.x0 - pad),
            max(0, cluster.y0 - pad),
            min(page_w, cluster.x1 + pad),
            min(page_h, cluster.y1 + pad)
        )

        try:
            pix = page_obj.get_pixmap(clip=crop_rect, dpi=self.dpi)
            pix_bytes = pix.tobytes("png")
            img_hash = hashlib.md5(pix_bytes).hexdigest()

            if img_hash in self.saved_image_hashes:
                return self.saved_image_hashes[img_hash]

            os.makedirs(self.output_dir, exist_ok=True)
            img_filename = f"qimg_exam{exam_id or 0}_q{q_num}_{img_index}.png"
            img_path = os.path.join(self.output_dir, img_filename)

            with open(img_path, "wb") as f:
                f.write(pix_bytes)

            rel_url = f"/{self.output_dir.replace(os.sep, '/')}/{img_filename}"
            self.saved_image_hashes[img_hash] = rel_url
            return rel_url
        except Exception as e:
            print(f"[Image Extractor] Erro ao renderizar cluster na página {page_obj.number}: {e}")
            return None

    def attach_images_to_questions(
        self,
        doc: fitz.Document,
        questions: List[Dict[str, Any]],
        page_diagrams: Dict[int, List[fitz.Rect]],
        exam_id: Any = 0
    ) -> List[Dict[str, Any]]:
        """
        Executa o pipeline de vinculação de imagens em 2 Fases:
        - Fase 1: Vinculação por Palavra-Gatilho (Trigger Word) + Proximidade Espacial
        - Fase 2: Varredura de Lacunas Visuais (Gap Visual Scan) para capturar imagens órfãs
        """
        used_diagrams: Set[Tuple[int, int]] = set()  # {(page_num, cluster_index)}
        total_pages = len(doc)

        # -------------------------------------------------------------------------
        # FASE 1: TRIGGER WORD (Alta Precisão)
        # -------------------------------------------------------------------------
        for q in questions:
            enunciado = q.get('enunciado', '')
            has_trigger = bool(IMAGE_TRIGGER_REGEX.search(enunciado))
            if not has_trigger:
                continue

            q_page = q.get('_page', 0)
            q_num = q.get('numero_questao', '0')
            q_images = q.get('images') or []

            pages_to_check = [q_page]
            if q_page + 1 < total_pages:
                pages_to_check.append(q_page + 1)

            for p_target in pages_to_check:
                if p_target not in page_diagrams:
                    continue

                for c_idx, cluster in enumerate(page_diagrams[p_target]):
                    diag_key = (p_target, c_idx)
                    if diag_key in used_diagrams:
                        continue

                    page_obj = doc[p_target]
                    rel_url = self.render_and_save_crop(
                        page_obj=page_obj,
                        cluster=cluster,
                        exam_id=exam_id,
                        q_num=q_num,
                        img_index=len(q_images) + 1
                    )

                    if rel_url:
                        q_images.append(rel_url)
                        used_diagrams.add(diag_key)

                    # Limite de imagens por questão (permite múltiplas se explícito no texto)
                    multi_fig = bool(MULTI_FIGURE_REGEX.search(enunciado))
                    max_imgs = 3 if multi_fig else 1
                    if len(q_images) >= max_imgs:
                        break

                if q_images:
                    break

            q['images'] = q_images if q_images else None

        # -------------------------------------------------------------------------
        # FASE 2: GAP VISUAL SCAN (Alta Cobertura)
        # -------------------------------------------------------------------------
        for p_idx in sorted(page_diagrams.keys()):
            clusters = page_diagrams[p_idx]
            page_obj = doc[p_idx]
            page_h = page_obj.rect.height
            page_w = page_obj.rect.width

            page_qs = [(i, q) for i, q in enumerate(questions) if q.get('_page') == p_idx]
            page_qs.sort(key=lambda x: x[1].get('_y', 0))

            for c_idx, cluster in enumerate(clusters):
                diag_key = (p_idx, c_idx)
                if diag_key in used_diagrams:
                    continue

                cluster_center_y = (cluster.y0 + cluster.y1) / 2.0
                cluster_center_x = (cluster.x0 + cluster.x1) / 2.0

                area = cluster.width * cluster.height
                if area < self.min_cluster_area:
                    continue

                aspect = cluster.width / cluster.height if cluster.height > 0 else 999
                if aspect < 0.08 or aspect > 15:
                    continue

                best_q_idx = -1
                best_distance = float('inf')

                # Prioriza questões na mesma coluna
                same_col_qs = [pq for pq in page_qs if abs(pq[1].get('_x', 0) - cluster_center_x) < page_w * 0.45]
                candidate_qs = same_col_qs if same_col_qs else page_qs

                for q_idx, q in candidate_qs:
                    q_y = q.get('_y', 0)
                    if q_y <= cluster_center_y + 30:
                        dist = cluster_center_y - q_y
                        if dist < best_distance:
                            best_distance = dist
                            best_q_idx = q_idx

                if best_q_idx == -1:
                    prev_qs = [(i, q) for i, q in enumerate(questions) if q.get('_page', -1) < p_idx]
                    if prev_qs:
                        best_q_idx = max(prev_qs, key=lambda x: (x[1].get('_page', 0), x[1].get('_y', 0)))[0]

                if best_q_idx == -1 and candidate_qs:
                    best_q_idx = candidate_qs[0][0]

                if best_q_idx == -1:
                    continue

                target_q = questions[best_q_idx]
                target_q_num = target_q.get('numero_questao', '0')
                existing_imgs = target_q.get('images') or []

                rel_url = self.render_and_save_crop(
                    page_obj=page_obj,
                    cluster=cluster,
                    exam_id=exam_id,
                    q_num=target_q_num,
                    img_index=len(existing_imgs) + 1
                )

                if rel_url:
                    if target_q.get('images') is None:
                        target_q['images'] = []
                    if rel_url not in target_q['images']:
                        target_q['images'].append(rel_url)
                    used_diagrams.add(diag_key)

        return questions


# =============================================================================
# FUNÇÃO CONVENIENTE DE ALTO NÍVEL
# =============================================================================

def extract_images_from_pdf(
    pdf_path_or_bytes: Any,
    output_dir: str = "static/images/questions",
    dpi: int = 160
) -> Dict[str, Any]:
    """
    Função de conveniência autônoma para extrair todos os diagramas e imagens de um PDF,
    retornando o mapa de arquivos gerados e metadados estruturados.
    """
    if isinstance(pdf_path_or_bytes, (bytes, bytearray)):
        doc = fitz.open(stream=pdf_path_or_bytes, filetype='pdf')
    else:
        doc = fitz.open(pdf_path_or_bytes)

    extractor = ExamImageExtractor(output_dir=output_dir, dpi=dpi)
    watermarks = extractor.detect_watermarks_and_headers(doc)

    extracted_items = []
    for p_idx, page in enumerate(doc):
        raw_blocks = page.get_text('blocks')
        clusters = extractor.find_diagram_clusters(page, watermarks, text_blocks=raw_blocks)
        for c_idx, cluster in enumerate(clusters):
            rel_url = extractor.render_and_save_crop(page, cluster, exam_id=0, q_num=f"p{p_idx+1}", img_index=c_idx+1)
            if rel_url:
                extracted_items.append({
                    'page': p_idx + 1,
                    'bbox': [cluster.x0, cluster.y0, cluster.x1, cluster.y1],
                    'width': cluster.width,
                    'height': cluster.height,
                    'file_url': rel_url
                })

    doc.close()
    return {
        'total_images': len(extracted_items),
        'unique_images': len(extractor.saved_image_hashes),
        'items': extracted_items
    }


# =============================================================================
# FUNÇÕES WRAPPER DE RETROCOMPATIBILIDADE
# =============================================================================

def find_diagram_clusters(
    page: fitz.Page,
    watermarks: Set[Tuple[float, float, float, float]],
    text_blocks: Optional[List[Any]] = None
) -> List[fitz.Rect]:
    """Wrapper retrocompatível para encontrar clusters de diagramas na página."""
    extractor = ExamImageExtractor()
    return extractor.find_diagram_clusters(page, watermarks, text_blocks)


def extract_and_crop_diagrams(
    doc: fitz.Document,
    page_num: int,
    cluster: fitz.Rect,
    exam_id: Optional[int],
    q_num: Any,
    img_idx: int,
    saved_hashes: Dict[str, str],
    img_dir: str = "static/images/questions"
) -> Optional[str]:
    """Wrapper retrocompatível para recorte e persistência com deduplicação."""
    extractor = ExamImageExtractor(output_dir=img_dir)
    extractor.saved_image_hashes = saved_hashes
    page_obj = doc[page_num]
    res = extractor.render_and_save_crop(page_obj, cluster, exam_id, q_num, img_idx)
    return res


# =============================================================================
# MOTOR DE OCR (FALLBACK PARA PÁGINAS ESCANEADAS)
# =============================================================================

_RAPID_OCR_ENGINE = None

def get_rapidocr_engine():
    """Inicializa preguiçosamente o motor RapidOCR ONNX."""
    global _RAPID_OCR_ENGINE
    if _RAPID_OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID_OCR_ENGINE = RapidOCR()
        except Exception as e:
            print(f"[PDF Parser] RapidOCR indisponível: {e}")
            _RAPID_OCR_ENGINE = False
    return _RAPID_OCR_ENGINE if _RAPID_OCR_ENGINE is not False else None

_get_rapidocr_engine = get_rapidocr_engine

def ocr_page_fallback(page: fitz.Page) -> List[Tuple[float, float, float, float, str, int, int]]:
    """
    Executa OCR em uma página de PDF escaneada/rasterizada,
    retornando blocos no formato idêntico ao page.get_text('blocks').
    """
    engine = get_rapidocr_engine()
    if not engine:
        return []

    try:
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        
        results, _ = engine(img_bytes)
        if not results:
            return []

        scale_x = page.rect.width / pix.width
        scale_y = page.rect.height / pix.height
        
        ocr_blocks = []
        for i, item in enumerate(results):
            box, text, score = item
            if score < 0.30 or not text.strip():
                continue
            
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            
            x0 = min(xs) * scale_x
            y0 = min(ys) * scale_y
            x1 = max(xs) * scale_x
            y1 = max(ys) * scale_y
            
            ocr_blocks.append((x0, y0, x1, y1, text, i, 0))
            
        return ocr_blocks
    except Exception as e:
        print(f"[OCR Error] Falha ao processar fallback OCR na página: {e}")
        return []

_ocr_page_fallback = ocr_page_fallback


# =============================================================================
# INTERFACE DE LINHA DE COMANDO (CLI STANDALONE)
# =============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Extrai e agrupa imagens e diagramas de PDFs de Concursos Públicos.")
    parser.add_argument("pdf_path", help="Caminho do arquivo PDF para extração")
    parser.add_argument("--output-dir", default="extracted_images", help="Diretório de destino das imagens PNG")
    parser.add_argument("--dpi", type=int, default=160, help="Resolução de renderização (DPI)")
    parser.add_argument("--json", action="store_true", help="Imprime o manifesto JSON no console")

    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"Erro: Arquivo '{args.pdf_path}' não encontrado.")
        exit(1)

    result = extract_images_from_pdf(args.pdf_path, output_dir=args.output_dir, dpi=args.dpi)
    print(f"[Sucesso] {result['total_images']} imagem(ns)/diagrama(s) processados com sucesso em '{args.output_dir}'.")
    print(f"[Deduplicação] {result['unique_images']} imagem(ns) únicas salvas no disco.")

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
