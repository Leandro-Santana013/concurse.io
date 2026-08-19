from flask import Flask, request, jsonify, render_template, url_for, redirect
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import os
import shutil
import threading
import requests
from bs4 import BeautifulSoup
import json
from dotenv import load_dotenv
from app_core.orchestrator import orchestrator
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from authlib.integrations.flask_client import OAuth

def set_exam_progress(exam_id, status_msg, pct, error_type=None, total_chunks=0, done_chunks=0):
    """Persiste o progresso do exame no banco de dados de forma segura para multi-worker."""
    try:
        from models import Session, Exam
        with Session() as session:
            exam = session.query(Exam).filter_by(id=exam_id).first()
            if exam:
                exam.progress = pct
                exam.progress_message = status_msg
                if error_type is not None:
                    exam.error_type = error_type
                if pct == 100:
                    exam.status = 'Aprovada'
                elif pct == -1:
                    exam.status = 'Erro'
                session.commit()
    except Exception as e:
        print(f"[Progress Error] Falha ao salvar progresso do exame {exam_id}: {e}", flush=True)

def get_exam_progress(exam_id):
    """Obtém o progresso do exame diretamente do banco de dados."""
    try:
        from models import Session, Exam
        with Session() as session:
            exam = session.query(Exam).filter_by(id=exam_id).first()
            if exam:
                return {
                    "status": exam.progress_message or exam.status or "Pendente",
                    "progress": exam.progress or 0,
                    "error_type": exam.error_type
                }
    except Exception as e:
        print(f"[Progress Error] Falha ao ler progresso do exame {exam_id}: {e}", flush=True)
    return {"status": "Pendente", "progress": 0}

# Callbacks para o Orchestrator atualizar o progresso de forma thread-safe
def _on_orchestrator_progress(exam_id, status_msg, pct):
    set_exam_progress(exam_id, status_msg, pct)

orchestrator.on_exam_progress = _on_orchestrator_progress
orchestrator.start()

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "super-secret-default-key-change-me")

# Configuração do Flask-Login
from app_core.extensions import login_manager, oauth
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configuração do OAuth
oauth.init_app(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

from models import (
    engine, Session, Base, User, Folder, Exam, Question, AppConfig, ExamAttempt, init_db
)

# Inicializar o banco de dados
init_db()



from routes import auth_bp, config_bp, exam_bp, stats_bp, views_bp
app.register_blueprint(auth_bp)
app.register_blueprint(config_bp)
app.register_blueprint(exam_bp)
app.register_blueprint(stats_bp)
app.register_blueprint(views_bp)

if __name__ == '__main__':
    orchestrator.start()
    app.run(debug=True, port=5000)
