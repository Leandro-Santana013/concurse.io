from flask import Blueprint, request, jsonify, render_template, url_for, redirect, current_app, send_file, session
import os, json, threading, shutil
from flask_login import login_user, login_required, logout_user, current_user
from app_core.orchestrator import orchestrator
from models import Session, User, Folder, Exam, Question, AppConfig, ExamAttempt
from app_core.extensions import login_manager, oauth
import datetime

config_bp = Blueprint('config', __name__)

from models import Session, User, Folder, Exam, Question, AppConfig, ExamAttempt, ApiKey

def get_glm_key():
    # Legacy helper, some old code might call this. We just return a placeholder or the first key.
    with Session() as session:
        key = session.query(ApiKey).filter_by(status='ACTIVE').first()
        return key.key_value if key else os.environ.get('GLM_API_KEY')

@config_bp.route('/api/config/keys/bulk', methods=['POST'])
@login_required
def manage_keys_bulk():
    """Inserts or updates an array of API keys into the Advanced Key Manager pool, linked to the user."""
    data = request.json or {}
    keys_input = data.get('keys', [])
    if isinstance(keys_input, str):
        keys_input = [k.strip() for k in keys_input.split(',') if k.strip()]
        
    added = 0
    with Session() as session:
        for k in keys_input:
            if not k:
                continue
            provider = 'nvidia' if k.startswith('nvapi-') else 'gemini'
            existing = session.query(ApiKey).filter_by(key_value=k).first()
            if not existing:
                new_key = ApiKey(key_value=k, provider=provider, status='ACTIVE', weight=10, user_id=current_user.id)
                session.add(new_key)
                added += 1
            else:
                existing.status = 'ACTIVE' # Reactivate if it was invalid
                existing.cooldown_until = None
        session.commit()
    
    # Force sync on the manager
    orchestrator.key_manager.sync(force=True)
    return jsonify({'success': True, 'added': added, 'message': f'{added} chaves processadas.'})

@config_bp.route('/api/config/keys_status', methods=['GET'])
@config_bp.route('/api/config/keys/status', methods=['GET'])
@login_required
def get_keys_status_route():
    """Returns the health status of keys contributed by the current user."""
    try:
        with Session() as session:
            keys = session.query(ApiKey).filter_by(user_id=current_user.id).all()
            statuses = []
            for i, k in enumerate(keys):
                masked = f"...{k.key_value[-4:]}" if len(k.key_value) >= 4 else "***"
                label = 'Ativa'
                if k.status == 'RATE_LIMITED':
                    label = f'Castigo até {k.cooldown_until}'
                elif k.status == 'INVALID':
                    label = 'Revogada (Inválida)'
                    
                statuses.append({
                    "id": k.id,
                    "index": i + 1,
                    "provider": k.provider,
                    "suffix": masked,
                    "status": k.status,
                    "label": label,
                    "weight": k.weight
                })
        return jsonify({'keys': statuses, 'total': len(statuses), 'success': True})
    except Exception as e:
        return jsonify({'keys': [], 'total': 0, 'error': str(e), 'success': False})

