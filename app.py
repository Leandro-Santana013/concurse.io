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

progress_lock = threading.Lock()
exam_progress = {}

def set_exam_progress(exam_id, status_msg, pct, error_type=None, total_chunks=0, done_chunks=0):
    with progress_lock:
        if len(exam_progress) > 1000:
            for k in list(exam_progress.keys())[:200]:
                del exam_progress[k]
        prev = exam_progress.get(exam_id, {})
        exam_progress[exam_id] = {
            "status": status_msg,
            "progress": pct,
            "error_type": error_type if error_type is not None else prev.get("error_type"),
            "total_chunks": total_chunks if total_chunks > 0 else prev.get("total_chunks", 0),
            "done_chunks": done_chunks if done_chunks > 0 else prev.get("done_chunks", 0)
        }

def get_exam_progress(exam_id):
    with progress_lock:
        return exam_progress.get(exam_id, {"status": "Pendente", "progress": 0})

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
