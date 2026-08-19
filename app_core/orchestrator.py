import os
import time
import threading
import uuid
import json
from app_core.key_manager import AdvancedKeyManager

class Task:
    def __init__(self, exam_id, task_type, payload, model_name=None):
        self.id = str(uuid.uuid4())
        self.exam_id = exam_id
        self.task_type = task_type
        self.payload = payload
        self.model_name = "Motor Determinístico (PyMuPDF)"
        self.status = "concluído"
        self.result = None
        self.error = None
        self.created_at = time.time()

class ModelManager:
    def __init__(self):
        self.models = {
            "Motor Determinístico (PyMuPDF / Regex)": "Ativo (100% Sem IA)"
        }

    def get_model(self, name):
        return "Motor Determinístico"

class TaskStack:
    def __init__(self):
        self.queue = []
        self.queue_lock = threading.Lock()
        self.history = []
        self.key_manager = AdvancedKeyManager()
        self.model_manager = ModelManager()
        self.is_running = False
        self.workers = []
        self.on_task_complete = None
        self.on_exam_progress = None

    def start(self):
        if not self.is_running:
            self.is_running = True
            print("[Orchestrator] Motor Determinístico (100% Sem IA) inicializado com sucesso.")

    def push_task(self, exam_id, task_type, payload, model_name=None):
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
            "models_loaded": models,
            "mode": "100% Determinístico (Sem IA / Zero Latência)"
        }

orchestrator = TaskStack()
