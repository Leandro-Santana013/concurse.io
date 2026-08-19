from flask import Blueprint, request, jsonify, render_template, url_for, redirect, current_app, send_file, session
import os, json, threading, shutil
from flask_login import login_user, login_required, logout_user, current_user
from app_core.orchestrator import orchestrator
from models import Session, User, Folder, Exam, Question, AppConfig, ExamAttempt
from app_core.extensions import login_manager, oauth
import datetime

auth_bp = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    session = Session()
    user = session.query(User).get(int(user_id))
    session.close()
    return user

@auth_bp.before_app_request
def require_login():
    if request.path.startswith('/api/') and (not request.path.startswith('/api/config')) and (not current_user.is_authenticated):
        return (jsonify({'error': 'Unauthorized'}), 401)

@auth_bp.route('/login')
def login():
    redirect_uri = url_for('auth.auth_callback', _external=True)
    google = oauth.create_client('google')
    return google.authorize_redirect(redirect_uri)

@auth_bp.route('/callback')
def auth_callback():
    google = oauth.create_client('google')
    token = google.authorize_access_token()
    user_info = google.parse_id_token(token, None)
    if not user_info:
        user_info = google.userinfo()
    session_db = Session()
    user = session_db.query(User).filter_by(google_id=user_info.get('sub')).first()
    if not user:
        user = User(google_id=user_info.get('sub'), email=user_info.get('email'), name=user_info.get('name'), picture=user_info.get('picture'))
        session_db.add(user)
        session_db.commit()
    user.picture = user_info.get('picture')
    user.name = user_info.get('name')
    session_db.commit()
    login_user(user)
    session_db.close()
    return redirect(url_for('views.index'))

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('views.index'))

