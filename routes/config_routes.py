from flask import Blueprint, request, jsonify, render_template, url_for, redirect, current_app, send_file, session
import os, json, threading, shutil
from flask_login import login_user, login_required, logout_user, current_user
from app_core.orchestrator import orchestrator
from models import Session, User, Folder, Exam, Question, AppConfig, ExamAttempt
from app_core.extensions import login_manager, oauth
import datetime

config_bp = Blueprint('config', __name__)

def get_glm_key():
    session = Session()
    config = session.query(AppConfig).filter_by(key='GLM_API_KEY').first()
    db_key = config.value if config else None
    session.close()
    return db_key or os.environ.get('GLM_API_KEY')

@config_bp.route('/api/config/glm_key', methods=['GET', 'POST'])
@config_bp.route('/api/config/gemini_key', methods=['GET', 'POST'])
def manage_glm_key():
    session = Session()
    if request.method == 'GET':
        config = session.query(AppConfig).filter_by(key='GLM_API_KEY').first()
        val = config.value if config and config.value else ''
        session.close()
        return jsonify({'api_key': val, 'has_key': bool(val), 'success': True})
    data = request.json or {}
    api_key = data.get('api_key', '')
    action = data.get('action', 'set')
    if action == 'set':
        config = session.query(AppConfig).filter_by(key='GLM_API_KEY').first()
        if config:
            config.value = api_key
        else:
            config = AppConfig(key='GLM_API_KEY', value=api_key)
            session.add(config)
    elif action == 'append':
        config = session.query(AppConfig).filter_by(key='GLM_API_KEY').first()
        if config:
            current_keys = [k.strip() for k in config.value.split(',') if k.strip()]
            new_keys = [k.strip() for k in api_key.split(',') if k.strip()]
            for k in new_keys:
                if k not in current_keys:
                    current_keys.append(k)
            config.value = ','.join(current_keys)
        else:
            config = AppConfig(key='GLM_API_KEY', value=api_key)
            session.add(config)
    elif action == 'remove':
        config = session.query(AppConfig).filter_by(key='GLM_API_KEY').first()
        if config:
            current_keys = [k.strip() for k in config.value.split(',') if k.strip()]
            if api_key in current_keys:
                current_keys.remove(api_key)
                config.value = ','.join(current_keys)
    session.commit()
    config = session.query(AppConfig).filter_by(key='GLM_API_KEY').first()
    if config:
        final_keys_list = [k.strip() for k in config.value.split(',') if k.strip()]
        if final_keys_list:
            orchestrator.api_key_manager.keys = final_keys_list
            orchestrator.api_key_manager.current_index = 0
            print(f'Orchestrator atualizado com {len(final_keys_list)} chaves do GLM.')
    session.close()
    return jsonify({'success': True})

@config_bp.route('/api/config/keys_status', methods=['GET'])
def get_keys_status_route():
    try:
        session = Session()
        config = session.query(AppConfig).filter_by(key='GLM_API_KEY').first()
        if config and config.value:
            keys_list = [k.strip() for k in config.value.split(',') if k.strip()]
            if keys_list:
                orchestrator.api_key_manager.keys = keys_list
        session.close()
        statuses = orchestrator.api_key_manager.get_keys_status()
        return jsonify({'keys': statuses, 'total': len(statuses), 'success': True})
    except Exception as e:
        return jsonify({'keys': [], 'total': 0, 'error': str(e), 'success': False})

@config_bp.route('/api/config/keys_status', methods=['GET'])
def get_keys_status():
    """Testa cada chave da API e retorna o status."""
    session = Session()
    config = session.query(AppConfig).filter_by(key='GLM_API_KEY').first()
    session.close()
    if not config or not config.value:
        return jsonify({'keys': [], 'message': 'Nenhuma chave configurada.'})
    keys = [k.strip() for k in config.value.split(',') if k.strip()]
    results = []
    for (i, key) in enumerate(keys):
        key_suffix = '...' + key[-4:] if len(key) > 4 else key
        try:
            import openai
            import app_core.orchestrator as orch_module
            client = orch_module.api_key_manager.create_client_for_key(key)
            model_name = orchestrator.api_key_manager.get_current_model_name()
            client.chat.completions.create(model=model_name, messages=[{'role': 'user', 'content': 'Olá'}])
            results.append({'index': i + 1, 'suffix': key_suffix, 'status': 'active', 'label': 'Ativa'})
        except Exception as e:
            print(f'DEBUG EXCEPTION: {repr(e)}')
            err = str(e).lower()
            if '429' in str(e) or 'quota' in err or 'exhausted' in err or ('rate' in err):
                results.append({'index': i + 1, 'suffix': key_suffix, 'status': 'exhausted', 'label': 'Esgotada'})
            else:
                results.append({'index': i + 1, 'suffix': key_suffix, 'status': 'invalid', 'label': 'Inválida'})
    pass
    return jsonify({'keys': results})

