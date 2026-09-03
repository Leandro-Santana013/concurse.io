import json
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey, event, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from dotenv import load_dotenv

from app_security import (
    decrypt_user_data,
    encrypt_user_data,
    is_encrypted_with_active_key,
    is_encrypted_user_data,
    is_pseudonymous_email,
    is_protected_identifier,
    protect_identifier,
    pseudonymous_email,
)

load_dotenv()

Base = declarative_base()

db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if db_url and db_url.startswith("sqlite"):
    engine = create_engine(
        db_url,
        echo=False,
        connect_args={'check_same_thread': False, 'timeout': 30},
        pool_pre_ping=True,
    )
elif db_url:
    engine = create_engine(
        db_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )
else:
    engine = create_engine(
        'sqlite:///concurse.db',
        echo=False,
        connect_args={'check_same_thread': False, 'timeout': 30},
        pool_pre_ping=True
    )

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if engine.dialect.name == 'sqlite':
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.execute("PRAGMA foreign_keys=ON;")
        except Exception:
            pass
        finally:
            cursor.close()

Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    """Dependency generator para injeção de sessão nos endpoints FastAPI."""
    db = Session()
    try:
        yield db
    finally:
        db.close()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    google_subject_hash = Column("google_id", String(200), unique=True, nullable=False, index=True)
    _email_legacy = Column("email", String(200), nullable=False)
    _name_legacy = Column("name", String(200), nullable=True)
    _picture_legacy = Column("picture", String(500), nullable=True)
    _email_encrypted = Column("email_encrypted", Text, nullable=True)
    _name_encrypted = Column("name_encrypted", Text, nullable=True)
    _picture_encrypted = Column("picture_encrypted", Text, nullable=True)
    
    folders = relationship("Folder", back_populates="user", cascade="all, delete-orphan")
    exams = relationship("Exam", back_populates="user", cascade="all, delete-orphan")
    attempts = relationship("ExamAttempt", back_populates="user", cascade="all, delete-orphan")
    exam_library = relationship(
        "UserExam",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def google_id(self):
        """Identificador pseudonimizado; o `sub` bruto do Google não é persistido."""
        return self.google_subject_hash

    @google_id.setter
    def google_id(self, value):
        self.google_subject_hash = protect_identifier(value)

    @property
    def email(self):
        if self._email_encrypted:
            return decrypt_user_data(self._email_encrypted, "email")
        return self._email_legacy

    @email.setter
    def email(self, value):
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("E-mail do usuário não pode ser vazio.")
        self._email_encrypted = encrypt_user_data(normalized, "email")
        self._email_legacy = pseudonymous_email(normalized)

    @property
    def name(self):
        if self._name_encrypted:
            return decrypt_user_data(self._name_encrypted, "name")
        return self._name_legacy

    @name.setter
    def name(self, value):
        normalized = str(value or "").strip()
        self._name_encrypted = encrypt_user_data(normalized, "name") if normalized else None
        self._name_legacy = None

    @property
    def picture(self):
        if self._picture_encrypted:
            return decrypt_user_data(self._picture_encrypted, "picture")
        return self._picture_legacy

    @picture.setter
    def picture(self, value):
        normalized = str(value or "").strip()
        self._picture_encrypted = encrypt_user_data(normalized, "picture") if normalized else None
        self._picture_legacy = None

class Folder(Base):
    __tablename__ = 'folders'
    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    
    exams = relationship("Exam", back_populates="folder", cascade="all, delete-orphan")
    user = relationship("User", back_populates="folders")

class Exam(Base):
    __tablename__ = 'exams'
    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    status = Column(String(20), default='Pendente', index=True)
    folder_id = Column(Integer, ForeignKey('folders.id'), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    source_url = Column(String(500), nullable=True, index=True)
    gabarito_url = Column(String(500), nullable=True)
    has_official_answers = Column(Integer, default=0)
    answer_key_source = Column(String(50), default='none')
    doc_type = Column(String(50), default='caderno_questoes')
    gabarito_coverage = Column(Float, default=0.0)
    gabarito_text = Column(Text, nullable=True)
    match_score = Column(Integer, default=0)
    progress = Column(Integer, default=0)
    progress_message = Column(String(300), default='Pendente')
    error_type = Column(String(50), nullable=True)
    
    folder = relationship("Folder", back_populates="exams")
    questions = relationship("Question", order_by="Question.id", back_populates="exam", cascade="all, delete-orphan")
    attempts = relationship("ExamAttempt", back_populates="exam", cascade="all, delete-orphan")
    generated_session = relationship(
        "GeneratedExamSession",
        back_populates="exam",
        cascade="all, delete-orphan",
        uselist=False,
    )
    library_entries = relationship(
        "UserExam",
        back_populates="exam",
        cascade="all, delete-orphan",
    )
    source_aliases = relationship(
        "ExamSource",
        back_populates="exam",
        cascade="all, delete-orphan",
    )
    user = relationship("User", back_populates="exams")

class Question(Base):
    __tablename__ = 'questions'
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey('exams.id'), index=True)
    statement = Column(Text, nullable=False)
    options = Column(Text, nullable=True)
    correct_answer = Column(String(10), nullable=False)
    subject = Column(String(100), nullable=True, default='Geral', index=True)
    images = Column(Text, nullable=True)
    numero_questao = Column(String(50), nullable=True)
    # Índice Canônico: posição estável 0..N-1 na ordem da Cadeia de Encadeamento,
    # desacoplada do rótulo textual `numero_questao` (que pode repetir/falhar
    # na extração, ex: subitens "1. 2. 3. 4." da DATAPREV). O async worker
    # sempre (re)atribui o Número Canônico a partir deste índice quando a
    # sequência de rótulos apresenta duplicatas, lacunas ou valores não numéricos.
    question_index = Column(Integer, nullable=True, index=True)
    latex_support = Column(Integer, default=0)
    difficulty_level = Column(String(20), default='Média')
    
    exam = relationship("Exam", back_populates="questions")

class ExamAttempt(Base):
    __tablename__ = 'exam_attempts'
    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey('exams.id'), index=True)
    score = Column(Integer, default=0)
    total = Column(Integer, default=0)
    percentage = Column(Float, default=0.0)
    elapsed_seconds = Column(Integer, default=0)
    answers_json = Column(Text, nullable=True)
    created_at = Column(String(30), nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    
    exam = relationship("Exam", back_populates="attempts")
    user = relationship("User", back_populates="attempts")


class AnswerKeyMatchAudit(Base):
    """Historico da decisao automatica que vinculou ou rejeitou um gabarito."""

    __tablename__ = 'answer_key_match_audits'

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey('exams.id'), nullable=False, index=True)
    accepted = Column(Integer, default=0, nullable=False)
    status = Column(String(30), nullable=False, default='not_found', index=True)
    confidence = Column(Float, default=0.0, nullable=False)
    answer_source = Column(String(50), nullable=False, default='none')
    method = Column(String(50), nullable=False, default='none')
    candidate_page = Column(Integer, nullable=True)
    decision_json = Column(Text, nullable=False, default='{}')
    created_at = Column(String(30), nullable=False)


class UserExam(Base):
    """Vincula uma prova canônica à biblioteca de cada usuário."""

    __tablename__ = 'user_exams'

    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    exam_id = Column(Integer, ForeignKey('exams.id'), primary_key=True)
    created_at = Column(String(30), nullable=False)

    user = relationship("User", back_populates="exam_library")
    exam = relationship("Exam", back_populates="library_entries")


class ExamSource(Base):
    """Identidade canônica de uma origem; uma prova pode ter mais de uma URL alias."""

    __tablename__ = 'exam_sources'

    source_key = Column(String(64), primary_key=True)
    source_url = Column(String(500), nullable=False)
    exam_id = Column(Integer, ForeignKey('exams.id'), nullable=False, index=True)
    created_at = Column(String(30), nullable=False)

    exam = relationship("Exam", back_populates="source_aliases")


class GeneratedExamSession(Base):
    """Referência persistente às questões originais de um simulado gerado."""

    __tablename__ = 'generated_exam_sessions'

    exam_id = Column(Integer, ForeignKey('exams.id'), primary_key=True)
    kind = Column(String(50), nullable=False, index=True)
    question_ids_json = Column(Text, nullable=False, default='[]')
    created_at = Column(String(30), nullable=False)

    exam = relationship("Exam", back_populates="generated_session")


def _normalize_question_ids(question_ids):
    """Remove IDs inválidos/repetidos sem alterar a ordem do simulado."""
    normalized = []
    seen = set()
    for raw_id in question_ids:
        try:
            question_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if question_id <= 0 or question_id in seen:
            continue
        seen.add(question_id)
        normalized.append(question_id)
    return normalized


def create_generated_exam_session(db, *, title, kind, question_ids, user_id=1):
    """Cria o Exam real e sua lista ordenada de referências em uma transação."""
    normalized_ids = _normalize_question_ids(question_ids)
    exam = Exam(
        title=title,
        status='Sessão',
        user_id=user_id,
        has_official_answers=1,
        answer_key_source='generated',
        doc_type='generated_session',
        gabarito_coverage=100.0,
        progress=100,
        progress_message='Sessão pronta',
    )
    db.add(exam)
    db.flush()
    db.add(GeneratedExamSession(
        exam_id=exam.id,
        kind=kind,
        question_ids_json=json.dumps(normalized_ids),
        created_at=datetime.now().isoformat(),
    ))
    db.commit()
    db.refresh(exam)
    return exam


def resolve_exam_questions(db, exam):
    """Retorna questões originais na ordem da sessão, ou as questões da prova comum."""
    generated_session = db.query(GeneratedExamSession).filter_by(exam_id=exam.id).first()
    if generated_session is None:
        return list(exam.questions), False

    try:
        raw_ids = json.loads(generated_session.question_ids_json or '[]')
    except (TypeError, ValueError, json.JSONDecodeError):
        raw_ids = []
    question_ids = _normalize_question_ids(raw_ids if isinstance(raw_ids, list) else [])
    if not question_ids:
        return [], True

    questions = db.query(Question).filter(Question.id.in_(question_ids)).all()
    questions_by_id = {question.id: question for question in questions}
    return [questions_by_id[question_id] for question_id in question_ids if question_id in questions_by_id], True

class ExamCatalog(Base):
    __tablename__ = 'exam_catalog'
    id = Column(Integer, primary_key=True)
    query_key = Column(String(100), index=True)
    title = Column(String(300), nullable=False)
    source_url = Column(String(500), unique=True, nullable=False, index=True)
    gabarito_url = Column(String(500), nullable=True)
    match_score = Column(Integer, default=0)
    source = Column(String(50), default='web')
    created_at = Column(String(30), nullable=True)

def _ensure_question_index_column():
    """Garante a coluna `questions.question_index` (Índice da Cadeia de Encadeamento)
    em bancos pré-existentes, pois create_all não altera tabelas já criadas."""
    from sqlalchemy import inspect
    inspector = inspect(engine)
    if 'questions' not in inspector.get_table_names():
        return
    cols = {c['name'] for c in inspector.get_columns('questions')}
    if 'question_index' in cols:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE questions ADD COLUMN question_index INTEGER"))
    print("[Schema] Coluna 'question_index' adicionada à tabela 'questions'.")


def _ensure_user_security_columns():
    """Migração aditiva mínima para bancos criados antes da criptografia de PII."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("users")}
    missing = [
        column
        for column in ("email_encrypted", "name_encrypted", "picture_encrypted")
        if column not in existing
    ]
    if not missing:
        return

    with engine.begin() as connection:
        for column in missing:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {column} TEXT"))


def _migrate_user_security_rows() -> int:
    """Criptografa PII legada e remove os valores pessoais das colunas antigas."""
    migrated = 0
    with engine.begin() as connection:
        rows = connection.execute(text(
            "SELECT id, google_id, email, name, picture, "
            "email_encrypted, name_encrypted, picture_encrypted FROM users"
        )).mappings().all()

        for row in rows:
            raw_identifier = str(row["google_id"] or "").strip()
            protected_identifier = (
                raw_identifier if is_protected_identifier(raw_identifier)
                else protect_identifier(raw_identifier)
            )

            email_plain = (
                decrypt_user_data(row["email_encrypted"], "email")
                if is_encrypted_user_data(row["email_encrypted"])
                else str(row["email"] or "").strip()
            )
            if not email_plain:
                raise RuntimeError(f"Usuário {row['id']} não possui e-mail migrável.")

            name_plain = (
                decrypt_user_data(row["name_encrypted"], "name")
                if is_encrypted_user_data(row["name_encrypted"])
                else str(row["name"] or "").strip() or None
            )
            picture_plain = (
                decrypt_user_data(row["picture_encrypted"], "picture")
                if is_encrypted_user_data(row["picture_encrypted"])
                else str(row["picture"] or "").strip() or None
            )

            already_protected = (
                is_protected_identifier(raw_identifier)
                and is_pseudonymous_email(row["email"])
                and row["name"] is None
                and row["picture"] is None
                and is_encrypted_with_active_key(row["email_encrypted"])
                and (
                    name_plain is None
                    or is_encrypted_with_active_key(row["name_encrypted"])
                )
                and (
                    picture_plain is None
                    or is_encrypted_with_active_key(row["picture_encrypted"])
                )
            )
            if already_protected:
                continue

            values = {
                "id": row["id"],
                "google_id": protected_identifier,
                "email": pseudonymous_email(email_plain),
                "email_encrypted": encrypt_user_data(email_plain, "email"),
                "name_encrypted": encrypt_user_data(name_plain, "name") if name_plain else None,
                "picture_encrypted": encrypt_user_data(picture_plain, "picture") if picture_plain else None,
            }
            connection.execute(text(
                "UPDATE users SET google_id = :google_id, email = :email, "
                "name = NULL, picture = NULL, email_encrypted = :email_encrypted, "
                "name_encrypted = :name_encrypted, picture_encrypted = :picture_encrypted "
                "WHERE id = :id"
            ), values)
            migrated += 1
    return migrated


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_question_index_column()
    _ensure_user_security_columns()
    migrated = _migrate_user_security_rows()
    if migrated:
        print(f"[User Security] {migrated} usuário(s) com dados protegidos em repouso.")

init_db()
