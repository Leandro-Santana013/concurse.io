import time
import threading
import uuid
import json
import traceback
import requests
import functools
import google.generativeai as genai
MODEL_CASCADE = [
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.0-flash",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]

class Task:
    def __init__(self, exam_id, task_type, payload, model_name=None):
        self.id = str(uuid.uuid4())
        self.exam_id = exam_id
        self.task_type = task_type
        self.payload = payload
        self.model_name = model_name or MODEL_CASCADE[0]
        self.cascade_index = 0
        self.status = "pendente"
        self.result = None
        self.error = None
        self.created_at = time.time()

class RateLimitManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.key_limits = {}

    def update_limits(self, api_key, limit, remaining, reset_secs):
        with self.lock:
            if api_key not in self.key_limits:
                self.key_limits[api_key] = {"limit": 0, "remaining": 0, "reset_time": 0, "blocked_until": 0}
            self.key_limits[api_key]["limit"] = limit
            self.key_limits[api_key]["remaining"] = remaining
            self.key_limits[api_key]["reset_time"] = time.time() + reset_secs
            print(f"[RateLimit] Chave {api_key[:6]}... - Limite: {limit}, Restantes: {remaining}, Reset em: {reset_secs}s")

    def block_key(self, api_key, cooldown_secs=60):
        with self.lock:
            if api_key not in self.key_limits:
                self.key_limits[api_key] = {"limit": 0, "remaining": 0, "reset_time": 0, "blocked_until": 0}
            
            reset_time = self.key_limits[api_key].get("reset_time", 0)
            now = time.time()
            if reset_time > now:
                cooldown = max(cooldown_secs, reset_time - now)
            else:
                cooldown = cooldown_secs
                
            self.key_limits[api_key]["blocked_until"] = now + cooldown
            print(f"[RateLimit] Chave {api_key[:6]}... BLOQUEADA por {cooldown}s (Erro 429).")
            
    def is_key_available(self, api_key):
        with self.lock:
            if api_key not in self.key_limits:
                return True
                
            info = self.key_limits[api_key]
            
            # Se a chave foi bloqueada hard por um 429
            if time.time() < info["blocked_until"]:
                return False
                
            # Se o reset time local (baseado no ultimo header) já passou
            if time.time() > info["reset_time"] and info["reset_time"] > 0:
                info["remaining"] = max(info["limit"], 1) # Restaura a capacidade
                info["reset_time"] = 0 # Zera o timer pra não ficar triggando
                return True
                
            # Se a chave não tem reset_time e está sem saldo (nunca teve headers ou esgotou e travou), liberamos 1 requisição para ela poder buscar os headers frescos
            if info["reset_time"] == 0 and info["remaining"] <= 0:
                info["remaining"] = 1
                return True
                
            # Se ainda tem requisições restantes, está disponível
            if info["remaining"] > 0:
                return True
                
            return False
            
    def get_wait_time(self, api_key):
        with self.lock:
            if api_key not in self.key_limits:
                return 0
            info = self.key_limits[api_key]
            now = time.time()
            if info["blocked_until"] > now:
                return info["blocked_until"] - now
            if info["remaining"] <= 0 and info["reset_time"] > now:
                return info["reset_time"] - now
            return 0

rate_limit_manager = RateLimitManager()

# Monkey-patch no requests.Session.send para interceptar headers do Gemini
_original_send = requests.Session.send

@functools.wraps(_original_send)
def _hooked_send(self, request, **kwargs):
    response = _original_send(self, request, **kwargs)
    if "googleapis.com" in request.url:
        limit_str = response.headers.get("x-ratelimit-limit-requests")
        remaining_str = response.headers.get("x-ratelimit-remaining-requests")
        reset_str = response.headers.get("x-ratelimit-reset-requests")
        if limit_str and remaining_str and reset_str:
            try:
                api_key = request.headers.get("x-goog-api-key")
                if api_key:
                    rate_limit_manager.update_limits(
                        api_key, int(limit_str), int(remaining_str), int(reset_str)
                    )
            except ValueError:
                pass
    return response

requests.Session.send = _hooked_send

class ApiKeyManager:
    def __init__(self):
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        self.lock = threading.Lock()
        keys_str = os.environ.get("GEMINI_API_KEY", "")
        self.keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        self.current_index = 0
        
        if self.keys:
            genai.configure(api_key=self.keys[0], transport='rest')
            print(f"[ApiKeyManager] Inicializado com {len(self.keys)} chave(s). Usando Chave 1.")
            
    def rotate_key(self, model_manager=None):
        with self.lock:
            if len(self.keys) <= 1:
                return False # Não há chaves suficientes para rodízio
                
            original_index = self.current_index
            for _ in range(len(self.keys)):
                self.current_index = (self.current_index + 1) % len(self.keys)
                new_key = self.keys[self.current_index]
                if rate_limit_manager.is_key_available(new_key):
                    genai.configure(api_key=new_key, transport='rest')
                    if model_manager:
                        model_manager._init_models()
                    print(f"[ApiKeyManager] ROTATIVO ATIVADO: Alternando para a Chave {self.current_index + 1}/{len(self.keys)}")
                    return True
            
            # Se todas bloqueadas, gira de qualquer forma para não travar num índice só, mas vai exigir wait no loop
            self.current_index = (original_index + 1) % len(self.keys)
            genai.configure(api_key=self.keys[self.current_index], transport='rest')
            if model_manager:
                model_manager._init_models()
            print(f"[ApiKeyManager] Aviso: Todas as chaves esgotadas/bloqueadas. Retornando falso (aguardar cota).")
            return False

    def get_current_key(self):
        with self.lock:
            if not self.keys:
                return None
            return self.keys[self.current_index]

class ModelManager:
    def __init__(self):
        self.models = {}
        self._init_models()

    def _init_models(self):
        try:
            self.models["gemini-3.5-flash"] = genai.GenerativeModel('gemini-3.5-flash')
            self.models["gemini-2.5-flash"] = genai.GenerativeModel('gemini-2.5-flash')
            self.models["gemini-3.1-flash-lite"] = genai.GenerativeModel('gemini-3.1-flash-lite')
            self.models["gemini-2.5-flash-lite"] = genai.GenerativeModel('gemini-2.5-flash-lite')
        except Exception as e:
            print("Aviso: Falha ao carregar alguns modelos no manager. Detalhes:", e)

    def get_model(self, name):
        if name in self.models:
            return self.models[name]
        return self.models.get("gemini-3.5-flash")

class TaskStack:
    def __init__(self):
        self.queue = []
        self.queue_lock = threading.Lock()
        self.history = []
        self.api_key_manager = ApiKeyManager()
        self.model_manager = ModelManager()
        self.is_running = False
        self.workers = []
        
        # Handlers fornecidos pelo app.py
        self.on_task_complete = None
        self.on_exam_progress = None

    def start(self):
        if not self.is_running:
            self.is_running = True
            for i in range(4): # 4 workers para paralelismo
                t = threading.Thread(target=self._loop, daemon=True, name=f"Worker-{i}")
                t.start()
                self.workers.append(t)
            print(f"[Orchestrator] {len(self.workers)} worker threads iniciadas com sucesso.")

    def push_task(self, exam_id, task_type, payload, model_name=None):
        task = Task(exam_id, task_type, payload, model_name)
        with self.queue_lock:
            self.queue.append(task)
        return task.id

    def get_status(self):
        return {
            "queue_length": len(self.queue),
            "history_length": len(self.history),
            "queue": [{"id": t.id, "exam_id": t.exam_id, "type": t.task_type, "model": t.model_name, "status": t.status} for t in self.queue],
            "models_loaded": list(self.model_manager.models.keys())
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
                
            # PRIORIDADE 2: Fila Local (Token Bucket Preventivo)
            current_key = self.api_key_manager.get_current_key()
            if current_key and not rate_limit_manager.is_key_available(current_key):
                print(f"[Orchestrator] Chave atual sem capacidade. Tentando rotação preventiva...")
                if self.api_key_manager.rotate_key(self.model_manager):
                    current_key = self.api_key_manager.get_current_key()
                else:
                    wait_time = rate_limit_manager.get_wait_time(current_key)
                    if wait_time > 0:
                        print(f"[Orchestrator] Fila de Controle: Todas as chaves ocupadas. Aguardando {wait_time:.1f}s antes de enviar chunk...")
                        time.sleep(min(wait_time, 10)) # dorme no máximo 10s por ciclo para não travar a thread indefinidamente
                        task.status = "pendente"
                        continue
                
            try:
                if task.task_type == "extract_questions":
                    self._process_extraction(task)
                elif task.task_type == "fallback_create":
                    self._process_fallback_create(task)
                
                task.status = "concluida"
                if self.on_task_complete:
                    self.on_task_complete(task)
                    
            except Exception as e:
                error_msg = str(e)
                print(f"[Orchestrator] Erro na tarefa {task.id} (Exame {task.exam_id}): {error_msg}")
                
                # Handling limits and deprecated models
                if "429" in error_msg or "Quota" in error_msg or "exhausted" in error_msg.lower() or "404" in error_msg or "not found" in error_msg.lower():
                    # PRIORIDADE 3: Circuit Breaker
                    curr_key = self.api_key_manager.get_current_key()
                    if curr_key:
                        rate_limit_manager.block_key(curr_key, cooldown_secs=60)
                        
                    # 1. Tentar rotacionar chaves no MESMO modelo
                    rotate_attempts = task.payload.get('rotate_attempts', 0)
                    if rotate_attempts < len(self.api_key_manager.keys):
                        try:
                            if self.api_key_manager.rotate_key(self.model_manager):
                                print(f"[Orchestrator] Cota atingida no {task.model_name}. Retentando imediatamente com nova chave (Rotação {rotate_attempts+1})...")
                                if self.on_exam_progress:
                                    self.on_exam_progress(task.exam_id, f"Trocando Chave ({task.model_name})...", 50)
                                task.payload['rotate_attempts'] = rotate_attempts + 1
                                task.status = "pendente"
                                continue # Retenta imediatamente!
                        except Exception as rot_e:
                            print(f"[Orchestrator] Erro fatal na rotação: {rot_e}")
                            
                    # 2. Todas as chaves esgotadas. Tentar descer na cascata de modelos
                    task.payload['rotate_attempts'] = 0 # Reset keys rotation for next model
                    
                    if hasattr(task, 'cascade_index'):
                        next_idx = task.cascade_index + 1
                        if next_idx < len(MODEL_CASCADE):
                            task.cascade_index = next_idx
                            task.model_name = MODEL_CASCADE[next_idx]
                            print(f"[Orchestrator] Descendo na cascata de modelos: usando {task.model_name} agora.")
                            if self.on_exam_progress:
                                self.on_exam_progress(task.exam_id, f"Mudando para modelo reserva: {task.model_name}...", 50)
                            task.status = "pendente"
                            continue
                            
                    # 3. Todos os modelos falharam. Tentar sleep longo e reset completo
                    print("[Orchestrator] Limite de todos os modelos atingido. Pausando tarefa por 60s...")
                    if self.on_exam_progress:
                        self.on_exam_progress(task.exam_id, f"Cota esgotada na API. Pausando (60s)...", 60)
                    
                    # Track total complete cycle attempts
                    attempts = task.payload.get('attempts', 0)
                    if attempts < 50:
                        task.payload['attempts'] = attempts + 1
                        if hasattr(task, 'cascade_index'):
                            task.cascade_index = 0 # reset back to top model
                            task.model_name = MODEL_CASCADE[0]
                        time.sleep(60)
                        task.status = "pendente"
                        continue
                    else:
                        task.status = "erro"
                        task.error = error_msg
                else:
                    task.status = "erro"
                    task.error = error_msg
                
                if task.status == "erro" and self.on_task_complete:
                    self.on_task_complete(task)

            # Ao terminar a tarefa (sucesso ou erro final), remove da fila
            if task.status in ["concluida", "erro"]:
                with self.queue_lock:
                    if task in self.queue:
                        self.queue.remove(task)
                    self.history.append(task)
                    if len(self.history) > 100:
                        self.history.pop(0)

    def _process_extraction(self, task):
        text = task.payload.get("text", "")
        file_path = task.payload.get("file_path", None)
        chunk_info = task.payload.get("chunk_info", "")
        
        if self.on_exam_progress:
            self.on_exam_progress(task.exam_id, f"Extraindo bloco {chunk_info} com {task.model_name}...", 50)
            
        model = self.model_manager.get_model(task.model_name)
        
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
        
        prompt = """Você é um especialista em concursos públicos brasileiros. Analise o texto/arquivo de uma prova e extraia TODAS as questões.

Retorne APENAS um JSON válido — uma lista de objetos — sem texto adicional.

Formato obrigatório:
[
  {
    "enunciado": "Texto completo da questão, incluindo textos de apoio",
    "opcoes": {"A": "texto", "B": "texto", "C": "texto", "D": "texto", "E": "texto"},
    "resposta": "A letra correta (A, B, C, D ou E)",
    "disciplina": "Matéria da questão (ex: Língua Portuguesa, Matemática)"
  }
]

REGRAS:
- Extraia APENAS questões legítimas de prova (numeradas e estruturadas).
- IGNORE COMPLETAMENTE instruções de capa, tabelas de rascunho, textos motivadores avulsos da Redação e folhas de gabarito. Não invente questões a partir de textos institucionais.
- NUNCA invente ou crie questões adicionais que não estejam explicitamente presentes no texto original.
- Certifique-se de não duplicar questões. Cada questão real deve aparecer apenas uma vez.
- Respeite rigorosamente a numeração e a quantidade de questões do documento.
- Se Certo/Errado: use "opcoes": null e "resposta": "Certo" ou "Errado"
- Inclua o enunciado COMPLETO de cada questão, juntando os textos de apoio e imagens descritas no mesmo.
- Extraia TODAS as questões do bloco, sem excluir nenhuma
- NUNCA inclua o gabarito no enunciado (remova qualquer "(Correta: A)" etc.)
- Remova espaços excessivos ou quebras de linha quebradas no meio das frases.
- Se não houver NENHUMA questão real no texto (por ser apenas capa ou rascunho), retorne uma lista vazia: []
"""
        
        contents = [prompt]
        if text:
            contents[0] += f"\n\nTexto de Referência:\n{text}\n"
            
        uploaded_file = None
        # Faz upload do arquivo se use_vision foi ativado por ter imagens ou texto escasso
        if file_path and use_vision:
            import google.generativeai as genai
            try:
                uploaded_file = genai.upload_file(path=file_path, mime_type="application/pdf")
                contents.append(uploaded_file)
            except Exception as e:
                print(f"Erro no upload para Vision: {type(e).__name__}: {str(e)[:100]}")
                
        try:
            response = model.generate_content(contents, generation_config={"response_mime_type": "application/json"})
        finally:
            if uploaded_file:
                try:
                    import google.generativeai as genai
                    genai.delete_file(uploaded_file.name)
                except Exception:
                    pass
        

            
        raw = response.text.strip()
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0].strip()
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0].strip()
        
        # Remove escapes inválidos que o Gemini às vezes gera (ex: \N, \e, \i)
        import re as _re
        raw = _re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
        
        try:
            task.result = json.loads(raw)
        except json.JSONDecodeError as je:
            try:
                import json_repair
                task.result = json_repair.loads(raw)
                print(f"[REPAIR] JSON corrompido do chunk {chunk_info} resgatado com sucesso via json-repair!")
            except ImportError:
                print(f"JSON inválido (json-repair não instalado). (chunk {chunk_info}): {je}")
                task.result = []
            except Exception as repair_e:
                print(f"JSON inválido irrecuperável do Gemini (chunk {chunk_info}): {je} | Erro Repair: {repair_e}")
                print(f"[AVISO] Ignorando bloco de questões ininteligível. Retornando vazio para não abortar a prova.")
                task.result = []

        # Pós processamento: Atrelar imagens às questões usando PyMuPDF
        if file_path and task.result and isinstance(task.result, list):
            self._post_process_images(file_path, task.result, task.exam_id)
            
        # Cleanup arquivo temporário
        if file_path:
            try:
                import os
                os.remove(file_path)
            except Exception:
                pass

    def _post_process_images(self, file_path, questions, exam_id):
        import fitz
        import os
        
        try:
            doc = fitz.open(file_path)
            
            # Garante que a pasta static/pdfs/images exista
            img_dir = os.path.join("static", "pdfs", "images")
            os.makedirs(img_dir, exist_ok=True)
            
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
                enunciado = q.get("enunciado", "").lower()
                q_words = set(re.findall(r'\w+', enunciado))
                if not q_words:
                    question_positions.append({"index": i, "page": -1, "y": -1})
                    continue
                
                best_page = -1
                best_y = -1
                max_overlap = 0
                
                best_block_idx = -1
                
                for page_num, blocks in enumerate(page_blocks):
                    for idx, b in enumerate(blocks):
                        overlap = len(q_words.intersection(b["words"]))
                        if overlap > max_overlap and overlap > 5:
                            max_overlap = overlap
                            best_page = page_num
                            best_y = b["bbox"][1] # y0
                            best_block_idx = idx
                            
                question_positions.append({"index": i, "page": best_page, "y": best_y, "block_idx": best_block_idx})
            
            # Varrer as páginas buscando imagens
            for page_num in range(len(doc)):
                page = doc[page_num]
                blocks = page.get_text('dict')['blocks']
                
                images = page.get_images(full=True)
                if not images: continue
                
                # Pega as questões desta página, ordenadas por block_idx
                page_qs = [q for q in question_positions if q["page"] == page_num]
                page_qs.sort(key=lambda x: x["block_idx"])
                
                for img_idx, img in enumerate(images):
                    xref = img[0]
                    # PyMuPDF extrai as coordenadas da imagem
                    try:
                        rects = page.get_image_rects(xref)
                    except Exception:
                        continue
                    if not rects: continue
                    
                    # Ignorar imagens muito pequenas (geralmente logos de cabeçalho)
                    rect = rects[0]
                    if rect.width < 50 and rect.height < 50: continue
                    
                    img_y = rect.y0
                    
                    # Tenta descobrir o block_idx da imagem na lista de blocos
                    img_block_idx = -1
                    for idx, b in enumerate(blocks):
                        if b['type'] == 1 and abs(b['bbox'][1] - img_y) < 5:
                            img_block_idx = idx
                            break
                    
                    # Se houver questões na página, associa à mais próxima na ordem de leitura (block_idx)
                    if page_qs:
                        if img_block_idx != -1:
                            # Tenta achar a primeira questão DEPOIS da imagem na ordem de leitura
                            after_qs = [q for q in page_qs if q["block_idx"] >= img_block_idx]
                            if after_qs:
                                best_q = after_qs[0]
                            else:
                                best_q = page_qs[-1] # se a imagem for a última coisa, atrela à última questão
                        else:
                            # Fallback para distância Y se não achar o bloco
                            best_q = min(page_qs, key=lambda q: abs(q["y"] - img_y))
                            
                        assigned_q_idx = best_q["index"]
                        
                        # Extrai a imagem
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        img_filename = f"exam_{exam_id}_q_{assigned_q_idx}_img_{img_idx}.{image_ext}"
                        img_path = os.path.join(img_dir, img_filename)
                        
                        with open(img_path, "wb") as f:
                            f.write(image_bytes)
                            
                        # Anexa a imagem à questão
                        q_obj = questions[assigned_q_idx]
                        if "images" not in q_obj:
                            q_obj["images"] = []
                        q_obj["images"].append(f"/static/pdfs/images/{img_filename}")
                        print(f"[Orchestrator] Imagem extraída e atrelada à questão index {assigned_q_idx}")
                        
            doc.close()
        except Exception as e:
            print(f"[Orchestrator] Erro no pós-processamento de imagens: {e}")
        
    def _process_fallback_create(self, task):
        title = task.payload.get("title", "")
        if self.on_exam_progress:
            self.on_exam_progress(task.exam_id, f"Gerando prova simulada via {task.model_name}...", 50)
            
        model = self.model_manager.get_model(task.model_name)
        prompt = f"""
Você é um especialista em concursos públicos brasileiros. O download do PDF original falhou, mas precisamos entregar a prova para o usuário.
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
        response = model.generate_content(prompt)
        raw = response.text.strip()
        if '```json' in raw:
            raw = raw.split('```json')[1].split('```')[0].strip()
        elif '```' in raw:
            raw = raw.split('```')[1].split('```')[0].strip()
            
        task.result = json.loads(raw)

# Instância Global
orchestrator = TaskStack()
