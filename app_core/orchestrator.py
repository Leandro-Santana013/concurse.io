import os
import sqlite3
import time
import threading
import uuid
import json
import traceback
import requests
import functools
import openai

GEMINI_CASCADE = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

NVIDIA_CASCADE = [
    "z-ai/glm-5.2",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-8b-instruct",
]

MODEL_CASCADE = GEMINI_CASCADE + NVIDIA_CASCADE

class Task:
    def __init__(self, exam_id, task_type, payload, model_name=None):
        self.id = str(uuid.uuid4())
        self.exam_id = exam_id
        self.task_type = task_type
        self.payload = payload
        self.model_name = model_name or "gemini-3.7-flash"
        self.cascade_index = 0
        self.status = "pendente"
        self.result = None
        self.error = None
        self.created_at = time.time()

from app_core.key_manager import AdvancedKeyManager

def get_client_for_key(key_data):
    key = key_data['key_value']
    is_gemini = True
    if key_data['provider'].lower() == 'nvidia' or key.startswith('nvapi-'):
        is_gemini = False
        
    if is_gemini:
        return openai.OpenAI(api_key=key, base_url='https://generativelanguage.googleapis.com/v1beta/openai/')
    return openai.OpenAI(api_key=key, base_url='https://integrate.api.nvidia.com/v1')

def get_cascade_for_key(key_data):
    key = key_data['key_value']
    if key_data['provider'].lower() == 'nvidia' or key.startswith('nvapi-'):
        return NVIDIA_CASCADE
    return GEMINI_CASCADE


class ModelManager:
    def __init__(self):
        self.models = {}
        self._init_models()

    def _init_models(self):
        for m in MODEL_CASCADE:
            self.models[m] = m

    def get_model(self, name):
        return self.models.get(name, name)

class TaskStack:
    def __init__(self):
        self.queue = []
        self.queue_lock = threading.Lock()
        self.history = []
        self.key_manager = AdvancedKeyManager()
        self.model_manager = ModelManager()
        self.is_running = False
        self.workers = []
        
        # Handlers fornecidos pelo app.py
        self.on_task_complete = None
        self.on_exam_progress = None

    def start(self):
        if not self.is_running:
            self.is_running = True
            for i in range(15): # Escalado para 15 workers usando a Pool de Chaves
                t = threading.Thread(target=self._loop, daemon=True, name=f"Worker-{i}")
                t.start()
                self.workers.append(t)
            print(f"[Orchestrator] {len(self.workers)} worker threads iniciadas com sucesso.")

    def push_task(self, exam_id, task_type, payload, model_name=None):
        if not model_name:
            model_name = GEMINI_CASCADE[0]
        task = Task(exam_id, task_type, payload, model_name)
        with self.queue_lock:
            self.queue.append(task)
        return task.id

    def get_status(self):
        with self.queue_lock:
            q_copy = [{"id": t.id, "exam_id": t.exam_id, "type": t.task_type, "model": t.model_name, "status": t.status} for t in list(self.queue)]
            hist_len = len(self.history)
            q_len = len(self.queue)
            models = list(self.model_manager.models.keys())
        return {
            "queue_length": q_len,
            "history_length": hist_len,
            "queue": q_copy,
            "models_loaded": models
        }

    def _loop(self):
        while self.is_running:
            task = None
            with self.queue_lock:
                for t in self.queue:
                    if t.status in ["pendente"]:
                        task = t
                        task.status = "rodando"
                        break
                        
            if not task:
                time.sleep(1)
                continue
                
            # PRIORIDADE 2: Fila Local (Árvore Binária / Heap)
            try:
                key_data = self.key_manager.get_best_key()
            except Exception as e:
                print(f"[Orchestrator] Fila de Controle: {e}. Aguardando 10s...")
                time.sleep(10)
                task.status = "pendente"
                continue
                
            client = get_client_for_key(key_data)
            
            # Alinha a cascata de modelos com o provedor da chave sorteada
            cascade = get_cascade_for_key(key_data)
            if hasattr(task, 'cascade_index') and task.cascade_index == 0:
                task.model_name = cascade[0]
                
            task_success = False
            error_msg = ""
            
            try:
                if task.task_type == "extract_questions":
                    self._process_extraction(task, client)
                elif task.task_type == "extract_questions_focused":
                    self._process_extraction_focused(task, client)
                elif task.task_type == "fallback_create":
                    self._process_fallback_create(task, client)
                
                task.status = "concluida"
                task_success = True
                if self.on_task_complete:
                    self.on_task_complete(task)
                    
            except Exception as e:
                error_msg = str(e)
                print(f"[Orchestrator] Erro na tarefa {task.id} (Exame {task.exam_id}): {error_msg}")
                
                # Handling limits and invalid keys
                if "429" in error_msg or "Quota" in error_msg or "exhausted" in error_msg.lower():
                    self.key_manager.report_error(key_data, "429")
                    task.status = "pendente"
                    continue # Retenta imediatamente com a próxima chave da árvore!
                    
                elif "401" in error_msg or "PermissionDenied" in error_msg:
                    self.key_manager.report_error(key_data, "401")
                    task.status = "pendente"
                    continue
                
                # Se não for erro de rede/cota, tentamos descer na cascata de modelos
                next_idx = task.cascade_index + 1
                if next_idx < len(cascade):
                    task.cascade_index = next_idx
                    task.model_name = cascade[next_idx]
                    print(f"[Orchestrator] Descendo na cascata: usando {task.model_name} agora.")
                    task.status = "pendente"
                    self.key_manager.release_key(key_data, success=False)
                    continue
                    
                # 3. Todos os modelos falharam. Erro final.
                task.status = "erro"
                task.error = error_msg
                if self.on_task_complete:
                    self.on_task_complete(task)
            
            # Liberar chave de volta para a árvore se não tomou ban
            if task_success or task.status == "erro":
                self.key_manager.release_key(key_data, success=task_success)

            # Ao terminar a tarefa (sucesso ou erro final), remove da fila
            if task.status in ["concluida", "erro"]:
                with self.queue_lock:
                    if task in self.queue:
                        self.queue.remove(task)
                    self.history.append(task)
                    if len(self.history) > 100:
                        self.history.pop(0)

    def _process_extraction(self, task, client):
        text = task.payload.get("text", "")
        file_path = task.payload.get("file_path", None)
        chunk_info = task.payload.get("chunk_info", "")
        
        if self.on_exam_progress:
            self.on_exam_progress(task.exam_id, f"Extraindo bloco {chunk_info} com {task.model_name}...", 50)
            
        model_name = self.model_manager.get_model(task.model_name)
        
        # Método Híbrido: extrai texto do PDF com PyMuPDF (fitz) primeiro (grátis, sem quota de upload)
        # Só usa Vision se o texto for insuficiente (PDF escaneado) ou se possuir imagens
        use_vision = False
        if file_path and not text:
            try:
                import fitz
                doc = fitz.open(file_path)
                pages_text = []
                for page in doc:
                    t = page.get_text() or ""
                    import re
                    t = re.sub(r' {2,}', ' ', t)
                    pages_text.append(t)
                    # Checa se a página possui imagens para forçar a API de Visão
                    if page.get_images(full=True):
                        use_vision = True
                            
                text = "\n".join(pages_text)
                doc.close()
                
                chars_per_page = len(text) / max(len(pages_text), 1)
                if chars_per_page < 80:
                    print(f"Texto insuficiente ({chars_per_page:.0f} chars/pag) -> forçando Vision OCR")
                    use_vision = True
                elif use_vision:
                    print("Imagens detectadas no PDF -> forçando Vision OCR")
                else:
                    print(f"Apenas texto puro detectado ({len(text)} chars). Economizando quota de Vision.")
            except Exception as e:
                print(f"PyMuPDF falhou ({e}), usando Vision OCR como fallback")
                use_vision = True
        
        prompt = """Você é um especialista em extração de dados estruturados de concursos públicos brasileiros. Analise o texto do bloco fornecido e extraia TODAS as questões que encontrar.

Retorne APENAS um array JSON válido, sem NENHUM texto Markdown adicional (sem crases).

Formato:
[
  {
    "numero_questao": "Número original da questão (ex: '1', '02', '34')",
    "enunciado": "Texto completo da questão, incluindo Textos de Referência caso a questão dependa deles.",
    "opcoes": {"A": "texto", "B": "texto", "C": "texto", "D": "texto", "E": "texto"},
    "resposta": "Letra correta caso haja gabarito, senão null",
    "disciplina": "Matéria presumida"
  }
]

REGRAS CRÍTICAS DE EXTRAÇÃO:
1. NÃO PULE AS PRIMEIRAS QUESTÕES! Extraia rigorosamente as perguntas 1, 2, 3, etc.
2. Extraia TODAS as questões de forma contígua.
3. Ignore estritamente CAPA e GABARITOS finais em formato de tabela. 
4. Textos base (ex: "Texto I", "O texto seguinte servirá de base...") devem ser incluídos como prefixo no "enunciado" da PRIMEIRA questão que depende dele, ou de todas. NUNCA crie uma questão isolada SÓ com o texto base!
5. Se uma questão for MÚLTIPLA ESCOLHA (tiver A, B, C, D), VOCÊ É OBRIGADO a preencher o objeto "opcoes". NUNCA use "opcoes": null para questões que possuem alternativas na imagem/texto!
6. Se uma questão for estritamente Certo/Errado (sem alternativas), defina "opcoes": null e "resposta": "Certo" ou "Errado".
7. Ignore as marcações "(Correta: X)" ou "(Gabarito: Y)" e não as coloque no enunciado.
8. Não crie questões que não existam. Apenas transcreva fielmente.
9. EXTRAIA RIGOROSAMENTE O NÚMERO ORIGINAL DA QUESTÃO NO CAMPO 'numero_questao' (ex: "25", "03").
10. O chunk de texto pode conter questões complexas. Não resuma nem abrevie, extraia rigorosamente TUDO, incluindo todas as alternativas.
"""
        
        content_text = prompt
        if text:
            content_text += f"\n\nTexto de Referência:\n{text}\n"
            
        try:
            if not client:
                raise Exception("API Key não configurada. Por favor, adicione uma chave GLM_API_KEY válida nas configurações.")
                
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": content_text}],
                max_tokens=8192,
                temperature=0.1
            )
        except Exception as e:
            raise e
        
        raw = response.choices[0].message.content.strip()
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0].strip()
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0].strip()
        
        # Remove escapes inválidos que o Gemini às vezes gera (ex: \N, \e, \i)
        import re as _re
        raw = _re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
        
        import json
        try:
            task.result = json.loads(raw)
        except json.JSONDecodeError as je:
            try:
                import json_repair
                task.result = json_repair.loads(raw)
                print(f"[REPAIR] JSON corrompido do chunk {chunk_info} resgatado com sucesso via json-repair!")
            except ImportError:
                print(f"JSON inválido (json-repair não instalado). (chunk {chunk_info}): {je}")
                raise Exception("Falha na geração do JSON pelo modelo.")
            except Exception as repair_e:
                print(f"JSON inválido irrecuperável do Gemini (chunk {chunk_info}): {je} | Erro Repair: {repair_e}")
                raise Exception("JSON irrecuperável gerado pelo modelo. Tentativa abortada para não perder questões.")

        # (O processamento de imagens agora é chamado em exam_service.py de uma só vez)

    def _process_extraction_focused(self, task, client):
        file_path = task.payload.get("file_path", None)
        gaps = task.payload.get("gaps", [])
        
        if self.on_exam_progress:
            self.on_exam_progress(task.exam_id, f"Resgatando questões {gaps} com {task.model_name}...", 80)
            
        model_name = self.model_manager.get_model(task.model_name)
        text = ""
        
        if file_path:
            try:
                import fitz
                import re
                doc = fitz.open(file_path)
                pages_text = []
                for page in doc:
                    t = page.get_text() or ""
                    t = re.sub(r' {2,}', ' ', t)
                    pages_text.append(t)
                text = "\n".join(pages_text)
                doc.close()
            except Exception as e:
                print(f"PyMuPDF falhou no auto-healing: {e}")
                
        prompt = f"""Você é um auditor de extração de dados. Ocorreu uma FALHA CRÍTICA anteriormente e as seguintes questões não foram extraídas deste documento: {gaps}.
Sua ÚNICA missão é vasculhar o texto fornecido, encontrar EXATAMENTE as questões numeradas como {gaps} e extraí-las.

Retorne APENAS um array JSON válido, sem NENHUM texto Markdown adicional (sem crases).

Formato:
[
  {{
    "numero_questao": "Número da questão encontrada",
    "enunciado": "Texto da questão.",
    "opcoes": {{"A": "texto"}},
    "resposta": null,
    "disciplina": "Matéria presumida"
  }}
]

REGRAS CRÍTICAS:
1. Encontre e extraia SOMENTE as questões que pertencem à lista: {gaps}.
2. Não extraia nenhuma outra questão. Se achar a questão 1 e ela não está na lista, ignore-a.
3. EXTRAIA RIGOROSAMENTE O NÚMERO ORIGINAL DA QUESTÃO NO CAMPO 'numero_questao' COMO UMA STRING.
"""
        
        content_text = prompt
        if text:
            content_text += f"\n\nTexto Integral do Documento:\n{text}\n"
            
        try:
            if not client:
                raise Exception("API Key não configurada.")
                
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": content_text}],
                max_tokens=4096,
                temperature=0.1,
                response_format={"type": "json_object"} if "openai" in str(type(client)).lower() else None
            )
            raw = response.choices[0].message.content
        except Exception as e:
            raise Exception(f"Falha de API: {e}")
            
        import json
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
        
        try:
            task.result = json.loads(raw)
        except json.JSONDecodeError as je:
            try:
                import json_repair
                task.result = json_repair.loads(raw)
            except Exception as repair_e:
                raise Exception("JSON irrecuperável no Auto-Healing.")

    def _post_process_images(self, file_path, questions, exam_id):
        import fitz
        import os
        doc = None
        try:
            doc = fitz.open(file_path)
            
            # Garante que a pasta static/pdfs/images exista
            img_dir = os.path.join("static", "pdfs", "images")
            os.makedirs(img_dir, exist_ok=True)
            
            # --- PRE-PASS: Detecção de Marca d'água / Logos de Cabeçalho ---
            import collections
            bbox_freq = collections.defaultdict(int)
            for page_num in range(len(doc)):
                blocks = doc[page_num].get_text('dict')['blocks']
                for b in blocks:
                    if b.get('type') == 1:
                        bbox = b['bbox']
                        rounded = (round(bbox[0]/10), round(bbox[1]/10), round(bbox[2]/10), round(bbox[3]/10))
                        bbox_freq[rounded] += 1
            
            watermark_bboxes = {k for k, v in bbox_freq.items() if v > 2}
            print(f"[Orchestrator] Watermarks ignorados: {watermark_bboxes}")
            # -----------------------------------------------------------------
            
            # Pre-calcular a posição Y (aproximada) de cada questão no PDF usando interseção de palavras
            import re
            
            # Cache dos blocos de texto por página para não reprocessar
            page_blocks = []
            for page_num in range(len(doc)):
                blocks = doc[page_num].get_text('dict')['blocks']
                processed_blocks = []
                for b in blocks:
                    if 'lines' not in b: continue
                    b_text = ''.join([s['text'] + ' ' for l in b['lines'] for s in l['spans']]).lower()
                    b_words = set(re.findall(r'\w+', b_text))
                    processed_blocks.append({"bbox": b["bbox"], "words": b_words})
                page_blocks.append(processed_blocks)

            question_positions = []
            for i, q in enumerate(questions):
                # Extrair palavras chaves significativas
                enunciado = q.get("enunciado", q.get("statement", "")).lower()
                q_words = set(re.findall(r'\w+', enunciado))
                
                if not q_words:
                    question_positions.append({"index": i, "page": -1, "y": -1})
                    continue
                
                best_page = -1
                best_y = -1
                best_x = -1
                best_block_idx = -1
                best_overlap = 0
                
                stopwords = {"o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas", "para", "por", "com", "sem", "que", "e", "ou", "mas", "se", "como", "é", "são", "foi", "nao", "não"}
                q_words_clean = {w for w in q_words if len(w) > 2 and w not in stopwords}
                if not q_words_clean:
                    q_words_clean = q_words # fallback
                    
                for page_num, blocks in enumerate(page_blocks):
                    for idx, b in enumerate(blocks):
                        b_words_clean = {w for w in b["words"] if len(w) > 2 and w not in stopwords}
                        if not b_words_clean:
                            continue
                            
                        overlap = len(q_words_clean.intersection(b_words_clean))
                        if overlap > best_overlap:
                            # Filtro mínimo de decência para evitar falsos positivos de blocos com 1 palavra
                            if overlap >= 4 or (overlap >= 2 and overlap / len(b_words_clean) > 0.6):
                                best_overlap = overlap
                                best_page = page_num
                                best_y = b["bbox"][1] # y0
                                best_x = b["bbox"][0] # x0
                                best_block_idx = idx
                                
                question_positions.append({"index": i, "page": best_page, "y": best_y, "x": best_x, "block_idx": best_block_idx})
            
            # Estratégia de Captura Visual (Renderização de Lacunas)
            # PDFs frequentemente fatiam imagens grandes ou usam layouts complexos.
            # Em vez de extrair XObjects crus, vamos renderizar o espaço visual entre as questões
            # SE houver algum bloco de imagem detectado nesse espaço.
            for page_num in range(len(doc)):
                page = doc[page_num]
                blocks = page.get_text('dict')['blocks']
                
                # Blocos que contêm imagens
                page_height = page.rect.height
                dead_zone_top = page_height * 0.10
                dead_zone_bottom = page_height * 0.90
                
                img_blocks = []
                for b in blocks:
                    if b.get('type') == 1:
                        bbox = b['bbox']
                        rounded = (round(bbox[0]/10), round(bbox[1]/10), round(bbox[2]/10), round(bbox[3]/10))
                        
                        with open('c:/Users/Santana/Documents/GitHub/concurse.io/orchestrator_debug.log', 'a') as df:
                            df.write(f"Checking {rounded} against {watermark_bboxes}\n")
                            
                        if rounded in watermark_bboxes:
                            continue
                            
                        center_y = (bbox[1] + bbox[3]) / 2.0
                        if center_y < dead_zone_top or center_y > dead_zone_bottom:
                            continue
                        img_blocks.append(bbox)
                        
                if not img_blocks: continue
                
                extracted_img_blocks = set()
                
                # Pega as questões desta página, ordenadas pelo Y (de cima para baixo)
                page_qs = [q for q in question_positions if q["page"] == page_num]
                page_qs.sort(key=lambda x: (x["y"], x["x"]))
                
                prev_y = dead_zone_top # Começar após o cabeçalho
                
                for idx_in_page, q in enumerate(page_qs):
                    q_y = q["y"]
                    if q_y <= prev_y + 20: 
                        # Estão quase na mesma linha, não há espaço para imagem
                        prev_y = max(prev_y, q_y + 20)
                        continue
                        
                    # Verifica se há alguma imagem visual nesse gap
                    img_blocks_in_between = []
                    for bbox in img_blocks:
                        bbox_tuple = tuple(bbox)
                        if bbox_tuple in extracted_img_blocks:
                            continue
                        if bbox[1] < q_y - 10 and bbox[3] > prev_y + 10:
                            img_blocks_in_between.append(bbox)
                            extracted_img_blocks.add(bbox_tuple)
                            
                    if img_blocks_in_between:
                        img_x0 = min(b[0] for b in img_blocks_in_between)
                        img_y0 = min(b[1] for b in img_blocks_in_between)
                        img_x1 = max(b[2] for b in img_blocks_in_between)
                        img_y1 = max(b[3] for b in img_blocks_in_between)
                        
                        rect = fitz.Rect(img_x0, img_y0, img_x1, img_y1)
                        
                        area = rect.width * rect.height
                        aspect_ratio = rect.width / rect.height if rect.height > 0 else 999
                        
                        # Filtro Geométrico: Área >= 400 e Proporção razoável
                        if area >= 400 and 0.1 <= aspect_ratio <= 10:
                            pad = 5
                            padded_rect = fitz.Rect(max(0, rect.x0 - pad), max(0, rect.y0 - pad),
                                                    min(page.rect.width, rect.x1 + pad), min(page.rect.height, rect.y1 + pad))
                            pix = page.get_pixmap(clip=padded_rect, dpi=150)
                            image_bytes = pix.tobytes("png")
                            
                            gap_y = (rect.y0 + rect.y1) / 2
                            gap_x = rect.x0
                            
                            if page_qs:
                                # Filtra apenas as questoes que estao na mesma coluna (distancia X < 200)
                                same_col_qs = [pq for pq in page_qs if abs(pq["x"] - gap_x) < 200]
                                candidate_qs = same_col_qs if same_col_qs else page_qs
                                
                                # Pegar as questoes que estao ACIMA da imagem na pagina
                                qs_above = [pq for pq in candidate_qs if pq["y"] < gap_y]
                                
                                if qs_above:
                                    # A questao imediatamente acima da imagem
                                    best_q = max(qs_above, key=lambda p: p["y"])
                                    assigned_q_idx = best_q["index"]
                                else:
                                    # Se nao tem questao acima na mesma coluna, a imagem esta no topo.
                                    # Vamos tentar pegar a ultima questao da coluna anterior (X menor)
                                    prev_col_qs = [pq for pq in page_qs if pq["x"] < gap_x - 100]
                                    if prev_col_qs:
                                        best_q = max(prev_col_qs, key=lambda p: p["y"])
                                        assigned_q_idx = best_q["index"]
                                    else:
                                        # Apelar para a pagina anterior
                                        prev_qs = [pqq for pqq in question_positions if pqq["page"] < page_num]
                                        if prev_qs:
                                            # Aqui pegamos pelo index mais alto já que estão ordenadas temporalmente
                                            assigned_q_idx = prev_qs[-1]["index"]
                                        else:
                                            # Nenhuma questao anterior, pega a primeira disponivel
                                            best_q = min(candidate_qs, key=lambda p: p["y"])
                                            assigned_q_idx = best_q["index"]
                            else:
                                assigned_q_idx = questions[0]["index"] if questions else 0
                                
                            img_filename = f"exam_{exam_id}_q_{assigned_q_idx}_img_render_p{page_num}_{int(prev_y)}.png"
                            img_path = os.path.join(img_dir, img_filename)
                            
                            with open(img_path, "wb") as f:
                                f.write(image_bytes)
                                
                            q_obj = questions[assigned_q_idx]
                            if "images" not in q_obj:
                                q_obj["images"] = []
                            
                            img_url = f"/static/pdfs/images/{img_filename}"
                            if img_url not in q_obj["images"]:
                                q_obj["images"].append(img_url)
                            
                            print(f"[Orchestrator] Imagem extraída (render restrito) e atrelada à questão index {assigned_q_idx}")
                            
                            with open('c:/Users/Santana/Documents/GitHub/concurse.io/orchestrator_debug.log', 'a') as df:
                                df.write(f"RENDERED {img_filename} for page {page_num} idx {idx_in_page} prev_y {prev_y} q_y {q_y}\n")
                        else:
                            with open('c:/Users/Santana/Documents/GitHub/concurse.io/orchestrator_debug.log', 'a') as df:
                                df.write(f"FILTERED page {page_num} gap {prev_y} to {q_y} area {area} ratio {aspect_ratio}\n")
                    else:
                        with open('c:/Users/Santana/Documents/GitHub/concurse.io/orchestrator_debug.log', 'a') as df:
                            df.write(f"NO IMAGES page {page_num} gap {prev_y} to {q_y}\n")

                    
                    prev_y = q_y + 20
                
                # Checar se tem imagem após a última questão da página
                
                # Se a página não tem nenhuma questão E não há questões nas páginas anteriores, é capa/instrução! Ignorar imagens.
                prev_qs_exist = any(pq["page"] < page_num for pq in question_positions)
                if not page_qs and not prev_qs_exist:
                    continue
                    
                q_y = dead_zone_bottom # antes do rodapé
                img_blocks_in_between = []
                for bbox in img_blocks:
                    bbox_tuple = tuple(bbox)
                    if bbox_tuple in extracted_img_blocks:
                        continue
                    if bbox[1] < q_y - 10 and bbox[3] > prev_y + 10:
                        img_blocks_in_between.append(bbox)
                        extracted_img_blocks.add(bbox_tuple)
                        
                if img_blocks_in_between:
                    img_x0 = min(b[0] for b in img_blocks_in_between)
                    img_y0 = min(b[1] for b in img_blocks_in_between)
                    img_x1 = max(b[2] for b in img_blocks_in_between)
                    img_y1 = max(b[3] for b in img_blocks_in_between)
                    
                    rect = fitz.Rect(img_x0, img_y0, img_x1, img_y1)
                    
                    area = rect.width * rect.height
                    aspect_ratio = rect.width / rect.height if rect.height > 0 else 999
                    
                    if area >= 400 and 0.1 <= aspect_ratio <= 10:
                        pad = 5
                        padded_rect = fitz.Rect(max(0, rect.x0 - pad), max(0, rect.y0 - pad),
                                                min(page.rect.width, rect.x1 + pad), min(page.rect.height, rect.y1 + pad))
                        pix = page.get_pixmap(clip=padded_rect, dpi=150)
                        
                        gap_x = rect.x0
                        if page_qs:
                            same_col_qs = [pq for pq in page_qs if abs(pq["x"] - gap_x) < 200]
                            candidate_qs = same_col_qs if same_col_qs else page_qs
                            assigned_q_idx = candidate_qs[-1]["index"]
                        else:
                            prev_qs = [pq for pq in question_positions if pq["page"] < page_num]
                            if prev_qs:
                                assigned_q_idx = prev_qs[-1]["index"]
                            else:
                                assigned_q_idx = question_positions[0]["index"] if question_positions else 0
                        
                        image_bytes = pix.tobytes("png")
                        img_filename = f"exam_{exam_id}_q_{assigned_q_idx}_img_render_end_p{page_num}_{int(q_y)}.png"
                        img_path = os.path.join(img_dir, img_filename)
                        
                        with open(img_path, "wb") as f:
                            f.write(image_bytes)
                            
                        q_obj = questions[assigned_q_idx]
                        if "images" not in q_obj:
                            q_obj["images"] = []
                        
                        img_url = f"/static/pdfs/images/{img_filename}"
                        if img_url not in q_obj["images"]:
                            q_obj["images"].append(img_url)
                        
                        print(f"[Orchestrator] Imagem extraída (render final restrito) e atrelada à questão index {assigned_q_idx}")
        except Exception as e:
            print(f"[Orchestrator] Erro no pós-processamento de imagens: {e}")
            import traceback
            with open('c:/Users/Santana/Documents/GitHub/concurse.io/orchestrator_debug.log', 'a') as df:
                df.write(f"ERROR: {e}\n{traceback.format_exc()}\n")
        finally:
            if doc:
                try:
                    doc.close()
                except Exception:
                    pass
        
    def _process_fallback_create(self, task, client):
        title = task.payload.get("title", "")
        if self.on_exam_progress:
            self.on_exam_progress(task.exam_id, f"Gerando prova simulada via {task.model_name}...", 50)
            
        model_name = self.model_manager.get_model(task.model_name)
        prompt = f"""Você é um especialista em concursos públicos brasileiros. O download do PDF original falhou, mas precisamos entregar a prova para o usuário.
Crie 10 questões realistas e de alta qualidade no exato estilo e nível da seguinte prova: "{title}".

Retorne APENAS um JSON válido — uma lista de objetos — sem nenhum texto adicional.

Formato obrigatório:
[
  {{
    "enunciado": "Texto completo da questão realista, incluindo o contexto e o que está sendo perguntado.",
    "opcoes": {{"A": "texto", "B": "texto", "C": "texto", "D": "texto", "E": "texto"}},
    "resposta": "A letra da resposta correta",
    "disciplina": "A matéria da questão (ex: Português, Matemática)"
  }}
]

As questões DEVEM ser desafiadoras e no estilo típico da banca (se estiver no título).
"""
        if not client:
            raise Exception("API Key não configurada. Por favor, adicione uma chave GLM_API_KEY válida nas configurações.")
            
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.choices[0].message.content.strip()
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0].strip()
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0].strip()
            
        import re as _re
        raw = _re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
        try:
            task.result = json.loads(raw)
        except Exception:
            try:
                import json_repair
                task.result = json_repair.loads(raw)
            except Exception:
                task.result = []

# Instância Global
orchestrator = TaskStack()
