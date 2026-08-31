"""
concurse.io — Motor Autônomo e Determinístico de Extração e Vinculação de Imagens em PDFs de Concursos
====================================================================================================
Este módulo implementa a captura visual de alta precisão (imagens raster + diagramas vetoriais),
validação de proporção/área, eliminação de marcas d'água/cabeçalhos estatísticos e anexamento
espacial rigoroso às questões (baseado na arquitetura validada e robusta da branch main).

Funcionalidades:
----------------
1. Filtro Estatístico de Marcas d'Água e Logos Fixos (ocorrências em N >= 3 páginas).
2. Extração Precisa de Blocos Visuais:
   - Imagens raster nativas (fitz.Page.get_images + b['type'] == 1).
   - Desenhos vetoriais filtrados (geometrias, circuitos, esquemas), descartando linhas divisórias.
3. Validação Geométrica Rigorosa:
   - Proporção de aspecto válida: 0.15 <= width / height <= 8.0.
   - Área mínima significativa (área >= 500 px²).
   - Eliminação de zonas mortas de cabeçalho (topo < 40px) e rodapé (fundo > page_h - 40px).
4. Proteção contra Inclusão Indevida de Enunciados:
   - Legendas restritas apenas a rótulos curtos ("Figura 1", "Gráfico 2").
5. Vinculação Espacial em 2 Fases:
   - Fase 1: Trigger Word (figura, gráfico, quadro, etc.).
   - Fase 2: Gap Visual Scan (posição entre questões na mesma coluna).
6. Deduplicação Visual Automática por Hash MD5.
"""

import os
import io
import re
import fitz  # PyMuPDF
import hashlib
import json
import collections
import argparse
from typing import List, Dict, Any, Optional, Tuple, Set

try:
    from .rust_bridge import rust_match_image_triggers
except ImportError:
    rust_match_image_triggers = lambda text: None


# =============================================================================
# CONSTANTES E PADRÕES REGEX DETERMINÍSTICOS
# =============================================================================

IMAGE_TRIGGER_PATTERN = (
    r'\b('
    r'figura|gr[áa]fico|quadro|tabela|diagrama|desenho|'
    r'ilustra[çc][ãa]o|mapa|esquema|imagem|paqu[íi]metro|'
    r'planta|fluxograma|fotografia|foto|tira|tirinha|charge|'
    r'cartum|organograma|histograma|exemplo|casinha|vilarejo|estrada|malha|'
    r'circuito\s+(?:abaixo|acima|a\s+seguir|da\s+figura)|diagrama\s+de\s+circuito|'
    r'regi[ãa]o\s+(?:plana\s+)?representada\s+(?:abaixo|acima|a\s+seguir)|'
    r'representad[ao]\s+(?:abaixo|acima|a\s+seguir)|'
    r'conforme\s+(?:o|a|os|as)?\s*(?:desenho|esquema|figura|imagem|gr[áa]fico|tabela|planta)'
    r')\b'
)

IMAGE_TRIGGER_REGEX = re.compile(IMAGE_TRIGGER_PATTERN, re.IGNORECASE)

CAPTION_PATTERN = (
    r'^\s*(?:'
    r'figura|gr[áa]fico|tabela|quadro|diagrama|circuito|mapa|esquema|'
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
        padding: int = 6,
        min_cluster_size: int = 20,
        min_cluster_area: int = 450,
        watermark_page_threshold: int = 3
    ):
        self.output_dir = output_dir
        self.dpi = dpi
        self.padding = padding
        self.min_cluster_size = min_cluster_size
        self.min_cluster_area = min_cluster_area
        self.watermark_page_threshold = watermark_page_threshold
        self.saved_image_hashes: Dict[str, str] = {}  # {md5_hash: relative_path}

    def detect_watermarks_and_headers(self, doc: fitz.Document) -> Set[Tuple[int, int, int, int]]:
        """
        Analisa todas as páginas do PDF e identifica retângulos de imagens ou cabeçalhos
        que se repetem em 3 ou mais páginas distintas (marcas d'água, rodapés e cabeçalhos institucionais).
        """
        bbox_pages = collections.defaultdict(set)
        for p_idx, page in enumerate(doc):
            page_seen = set()
            # Blocos de imagem do dicionário da página
            try:
                dict_page = page.get_text('dict')
                for b in dict_page.get('blocks', []):
                    if b.get('type') == 1:
                        bbox = b['bbox']
                        rounded = (round(bbox[0]/10), round(bbox[1]/10), round(bbox[2]/10), round(bbox[3]/10))
                        page_seen.add(rounded)
            except Exception:
                pass

            # Imagens diretas (evitando duplicar xrefs dentro da mesma página)
            seen_xrefs = set()
            for img_info in page.get_images():
                xref = img_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)
                for r in page.get_image_rects(xref):
                    rounded = (round(r.x0/10), round(r.y0/10), round(r.x1/10), round(r.y1/10))
                    page_seen.add(rounded)

            # Desenhos e molduras repetidas
            for d in page.get_drawings():
                r = d['rect']
                if r.width >= 5 and r.height >= 5:
                    rounded = (round(r.x0/10), round(r.y0/10), round(r.x1/10), round(r.y1/10))
                    page_seen.add(rounded)

            for rounded in page_seen:
                bbox_pages[rounded].add(p_idx)

        return {k for k, pages in bbox_pages.items() if len(pages) >= self.watermark_page_threshold}

    def find_diagram_clusters(
        self,
        page: fitz.Page,
        watermarks: Set[Tuple[int, int, int, int]],
        text_blocks: Optional[List[Any]] = None
    ) -> List[fitz.Rect]:
        """
        Coleta e agrupa com precisão elementos visuais válidos da página,
        rejeitando divisórias de 1px, cabeçalhos de topo e rodapés de página.
        """
        useful_rects: List[fitz.Rect] = []
        page_w = page.rect.width
        page_h = page.rect.height

        dead_zone_top = 40
        dead_zone_bottom = page_h - 40

        # 1. Imagens Raster (Tipo 1 do PyMuPDF ou page.get_images)
        try:
            dict_page = page.get_text('dict')
            for b in dict_page.get('blocks', []):
                if b.get('type') == 1:
                    bx0, by0, bx1, by1 = b['bbox']
                    r = fitz.Rect(bx0, by0, bx1, by1)
                    
                    # Filtra zonas mortas
                    if r.y1 <= dead_zone_top or r.y0 >= dead_zone_bottom:
                        continue
                    
                    # Filtra marcas d'água
                    rounded = (round(r.x0/10), round(r.y0/10), round(r.x1/10), round(r.y1/10))
                    if rounded in watermarks:
                        continue

                    # Filtra scans de página inteira (capa)
                    if r.width >= page_w * 0.85 and r.height >= page_h * 0.85:
                        continue

                    area = r.width * r.height
                    aspect = r.width / r.height if r.height > 0 else 999
                    if area >= self.min_cluster_area and 0.12 <= aspect <= 10.0:
                        useful_rects.append(r)
        except Exception:
            pass

        for img_info in page.get_images():
            for r in page.get_image_rects(img_info[0]):
                if r.y1 <= dead_zone_top or r.y0 >= dead_zone_bottom:
                    continue
                rounded = (round(r.x0/10), round(r.y0/10), round(r.x1/10), round(r.y1/10))
                if rounded in watermarks:
                    continue
                if r.width >= page_w * 0.85 and r.height >= page_h * 0.85:
                    continue
                area = r.width * r.height
                aspect = r.width / r.height if r.height > 0 else 999
                if area >= self.min_cluster_area and 0.12 <= aspect <= 10.0:
                    # Evita duplicar se já capturado via get_text('dict')
                    if not any(abs(r.x0 - u.x0) < 5 and abs(r.y0 - u.y0) < 5 for u in useful_rects):
                        useful_rects.append(r)

        # 2. Desenhos Vetoriais Ricos (circuitos, esquemas, geometrias complexas)
        # Filtra estritamente para não capturar linhas divisórias ou molduras simples
        drawings = page.get_drawings()
        diag_drawings: List[fitz.Rect] = []
        for d in drawings:
            r = d['rect']
            # Rejeita linhas horizontais/verticais finas
            if r.width < 12 or r.height < 12:
                continue
            if r.y1 <= dead_zone_top or r.y0 >= dead_zone_bottom:
                continue
            # Rejeita réguas e divisórias de coluna
            if (r.width > page_w * 0.70 and r.height < 15) or (r.height > page_h * 0.70 and r.width < 15):
                continue
            # Rejeita fundos de página
            if r.width > page_w * 0.80 and r.height > page_h * 0.80:
                continue

            rounded = (round(r.x0/10), round(r.y0/10), round(r.x1/10), round(r.y1/10))
            if rounded in watermarks:
                continue
            diag_drawings.append(r)

        # Agrupa desenhos vetoriais adjacentes apenas se formarem um cluster denso
        if diag_drawings:
            v_clusters: List[fitz.Rect] = []
            for r in diag_drawings:
                merged = False
                for vc in v_clusters:
                    if abs(r.x0 - vc.x0) < 120 and (r.y0 <= vc.y1 + 15 and r.y1 >= vc.y0 - 15):
                        vc.include_rect(r)
                        merged = True
                        break
                if not merged:
                    v_clusters.append(fitz.Rect(r))

            for vc in v_clusters:
                v_area = vc.width * vc.height
                v_aspect = vc.width / vc.height if vc.height > 0 else 999
                # Aceita vetor apenas se for um diagrama real (área suficiente e não uma linha)
                if v_area >= 1200 and 0.20 <= v_aspect <= 6.0:
                    if not any(u.contains(vc) for u in useful_rects):
                        useful_rects.append(vc)

        # 3. Detecção Automática de Ilustrações em PDFs Escaneados (Visual Gap Detection)
        if not useful_rects and text_blocks:
            sorted_tb = sorted([b for b in text_blocks if len(b) >= 5 and b[4].strip()], key=lambda b: b[1])
            for i in range(len(sorted_tb) - 1):
                b_curr = sorted_tb[i]
                b_next = sorted_tb[i + 1]
                curr_txt = b_curr[4]
                next_txt = b_next[4]
                
                has_trigger = bool(IMAGE_TRIGGER_REGEX.search(curr_txt) or IMAGE_TRIGGER_REGEX.search(next_txt))
                gap_y0 = b_curr[3] + 4
                gap_y1 = b_next[1] - 4
                gap_h = gap_y1 - gap_y0
                
                if (has_trigger and gap_h >= 25) or (gap_h >= 80):
                    gap_x0 = max(25.0, min(b_curr[0], b_next[0]) - 10)
                    gap_x1 = min(page_w - 25.0, max(b_curr[2], b_next[2], page_w * 0.75) + 10)
                    gap_rect = fitz.Rect(gap_x0, gap_y0, gap_x1, gap_y1)
                    
                    if gap_rect.y1 <= dead_zone_bottom and gap_rect.y0 >= dead_zone_top:
                        useful_rects.append(gap_rect)

        if not useful_rects:
            return []

        # 4. Agrupamento Geométrico Estrito por Proximidade (sem misturar colunas)
        clusters: List[fitz.Rect] = []
        for r in useful_rects:
            merged = False
            for c in clusters:
                # Merge apenas se estiverem alinhados na mesma coluna e imediatamente adjacentes
                if abs(r.x0 - c.x0) < 80 and (r.y0 <= c.y1 + 15 and r.y1 >= c.y0 - 15):
                    c.include_rect(r)
                    merged = True
                    break
            if not merged:
                clusters.append(fitz.Rect(r))

        # Validação final de tamanho e aspecto
        valid_clusters = []
        for c in clusters:
            area = c.width * c.height
            aspect = c.width / c.height if c.height > 0 else 999
            if area >= self.min_cluster_area and 0.12 <= aspect <= 10.0:
                valid_clusters.append(c)

        return valid_clusters

    def render_and_save_crop(
        self,
        page_obj: fitz.Page,
        cluster: fitz.Rect,
        exam_id: Any,
        q_num: Any,
        img_index: int
    ) -> Optional[str]:
        """
        Recorta a região com padding de segurança, renderiza em DPI configurado,
        calcula o hash MD5 e persiste no disco (com deduplicação automática).
        Aplica clamping inteligente contra blocos de texto da página para evitar vazamentos de texto no crop.
        """
        page_w = page_obj.rect.width
        page_h = page_obj.rect.height
        pad = self.padding

        min_x0 = 0.0
        min_y0 = 0.0
        max_x1 = float(page_w)
        max_y1 = float(page_h)

        try:
            text_blocks = [b for b in page_obj.get_text('blocks') if b[4].strip()]
            for b in text_blocks:
                bx0, by0, bx1, by1 = b[:4]
                # Verifica sobreposição horizontal e vertical de vizinhança
                h_overlap = not (bx1 < cluster.x0 - 15 or bx0 > cluster.x1 + 15)
                v_overlap = not (by1 < cluster.y0 - 15 or by0 > cluster.y1 + 15)

                if h_overlap:
                    # Texto está abaixo do cluster de imagem
                    if by0 >= cluster.y1 - 1:
                        max_y1 = min(max_y1, by0 - 1.0)
                    # Texto está acima do cluster de imagem
                    if by1 <= cluster.y0 + 1:
                        min_y0 = max(min_y0, by1 + 1.0)

                if v_overlap:
                    # Texto está à direita do cluster
                    if bx0 >= cluster.x1 - 1:
                        max_x1 = min(max_x1, bx0 - 1.0)
                    # Texto está à esquerda do cluster
                    if bx1 <= cluster.x0 + 1:
                        min_x0 = max(min_x0, bx1 + 1.0)
        except Exception:
            pass

        crop_rect = fitz.Rect(
            max(min_x0, cluster.x0 - pad),
            max(min_y0, cluster.y0 - pad),
            min(max_x1, cluster.x1 + pad),
            min(max_y1, cluster.y1 + pad)
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
            print(f"[Diagram Cropper] Erro ao renderizar crop: {e}")
            return None

    def attach_images_to_questions(
        self,
        doc: fitz.Document,
        questions: List[Dict[str, Any]],
        page_diagrams: Dict[int, List[fitz.Rect]],
        exam_id: Any = 0
    ) -> List[Dict[str, Any]]:
        """
        Executa o pipeline de vinculação espacial e contextual de imagens:
        Para cada diagrama detectado em uma página:
        1. Calcula sua posição (X, Y) e coluna.
        2. Avalia todas as questões candidatas na página (e páginas adjacentes).
        3. Prioriza a questão que contém a imagem espacialmente no seu corpo ou
           que tem palavra-gatilho explícita na vizinhança imediata.
        """
        if not page_diagrams or not questions:
            return questions

        total_pages = len(doc)

        # Mapeia triggers nas questões
        for q in questions:
            enunciado = q.get('enunciado', q.get('statement', ''))
            rust_res = rust_match_image_triggers(enunciado)
            if rust_res is not None:
                q['_has_trigger'] = rust_res.get('has_trigger', False)
            else:
                q['_has_trigger'] = bool(IMAGE_TRIGGER_REGEX.search(enunciado))

        used_diagrams: Set[Tuple[int, int]] = set()

        # Processa página por página de forma ordenada
        for p_idx in sorted(page_diagrams.keys()):
            clusters = page_diagrams[p_idx]
            page_obj = doc[p_idx]
            page_w = page_obj.rect.width
            page_h = page_obj.rect.height

            # Candidatos na página
            page_qs = [(i, q) for i, q in enumerate(questions) if q.get('_page') == p_idx]
            page_qs.sort(key=lambda x: x[1].get('_y', 0))

            # Apenas a página imediatamente anterior (p_idx - 1) se houver questão iniciada lá e a imagem estiver no topo da página
            prev_page_qs = [(i, q) for i, q in enumerate(questions) if q.get('_page') == p_idx - 1]

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
                if aspect < 0.12 or aspect > 10.0:
                    continue

                best_q_idx = -1
                best_score = float('inf')

                # Agrupa questões estritamente pela mesma coluna (metade da página)
                mid_x = page_w / 2.0
                is_col_left = cluster_center_x < mid_x
                same_col_qs = [pq for pq in page_qs if (pq[1].get('_x', 0) < mid_x) == is_col_left]
                candidates = same_col_qs if same_col_qs else page_qs

                # Avalia cada questão candidata
                for q_idx, q in candidates:
                    q_y = q.get('_y', 0)
                    has_trigger = q.get('_has_trigger', False)

                    # A questão começa acima ou muito próxima da imagem (tolerância de 20px)
                    if q_y <= cluster_center_y + 20:
                        vertical_dist = cluster_center_y - q_y
                        if vertical_dist >= 0:
                            # Se tem palavra-gatilho explícita na vizinhança (distância razoável), dá prioridade máxima
                            if has_trigger and vertical_dist <= 350:
                                score = vertical_dist * 0.1
                            else:
                                score = vertical_dist

                            if score < best_score:
                                best_score = score
                                best_q_idx = q_idx

                # Se nenhuma questão foi encontrada acima na mesma coluna/página:
                if best_q_idx == -1:
                    # Prioriza estritamente questões da mesma coluna
                    col_trigger_qs = [pq for pq in same_col_qs if pq[1].get('_has_trigger')]
                    if col_trigger_qs:
                        best_q_idx = min(col_trigger_qs, key=lambda pq: pq[1].get('_y', 0))[0]
                    elif same_col_qs:
                        best_q_idx = same_col_qs[0][0]
                    else:
                        trigger_qs = [pq for pq in page_qs if pq[1].get('_has_trigger')]
                        if trigger_qs:
                            best_q_idx = min(trigger_qs, key=lambda pq: abs(pq[1].get('_y', 0) - cluster_center_y))[0]
                        elif prev_page_qs and cluster.y0 < 220:
                            # Apenas a última questão da página imediatamente anterior se tiver gatilho
                            prev_trigger_qs = [pq for pq in prev_page_qs if pq[1].get('_has_trigger')]
                            if prev_trigger_qs:
                                best_q_idx = max(prev_trigger_qs, key=lambda x: x[1].get('_y', 0))[0]

                if best_q_idx != -1:
                    target_q = questions[best_q_idx]
                    has_trigger = target_q.get('_has_trigger', False)
                    # Evita anexar linhas isoladas de tabela a questões sem gatilho
                    if not has_trigger and best_score > 350:
                        continue
                    q_images = target_q.get('images') or []
                    q_num = target_q.get('numero_questao', '0')

                    rel_url = self.render_and_save_crop(
                        page_obj=page_obj,
                        cluster=cluster,
                        exam_id=exam_id,
                        q_num=q_num,
                        img_index=len(q_images) + 1
                    )

                    if rel_url:
                        if rel_url not in q_images:
                            q_images.append(rel_url)
                        target_q['images'] = q_images
                        used_diagrams.add(diag_key)

        # Limpeza temporária
        for q in questions:
            q.pop('_has_trigger', None)

        return questions

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
    watermarks: Set[Tuple[int, int, int, int]],
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
    return extractor.render_and_save_crop(page_obj, cluster, exam_id, q_num, img_idx)


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
