import json
import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from dotenv import load_dotenv

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
    google_id = Column(String(200), unique=True, nullable=False, index=True)
    email = Column(String(200), nullable=False)
    name = Column(String(200), nullable=True)
    picture = Column(String(500), nullable=True)
    
    folders = relationship("Folder", back_populates="user")
    exams = relationship("Exam", back_populates="user")
    attempts = relationship("ExamAttempt", back_populates="user")
    exam_library = relationship(
        "UserExam",
        back_populates="user",
        cascade="all, delete-orphan",
    )

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
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")
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

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"[DB Init Warning] {e}")

init_db()
