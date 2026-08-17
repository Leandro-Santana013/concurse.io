import os
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, ForeignKey, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from flask_login import UserMixin
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

if db_url:
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
        except Exception:
            pass
        finally:
            cursor.close()

Session = sessionmaker(bind=engine)

class User(UserMixin, Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    google_id = Column(String(200), unique=True, nullable=False, index=True)
    email = Column(String(200), nullable=False)
    name = Column(String(200), nullable=True)
    picture = Column(String(500), nullable=True)
    
    folders = relationship("Folder", back_populates="user")
    exams = relationship("Exam", back_populates="user")
    attempts = relationship("ExamAttempt", back_populates="user")

class Folder(Base):
    __tablename__ = 'folders'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    
    exams = relationship("Exam", back_populates="folder", cascade="all, delete-orphan")
    user = relationship("User", back_populates="folders")

class Exam(Base):
    __tablename__ = 'exams'
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    status = Column(String(20), default='Pendente', index=True)
    folder_id = Column(Integer, ForeignKey('folders.id'), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    source_url = Column(String(500), nullable=True, index=True)
    match_score = Column(Integer, default=0)
    
    folder = relationship("Folder", back_populates="exams")
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")
    attempts = relationship("ExamAttempt", back_populates="exam", cascade="all, delete-orphan")
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
    
    exam = relationship("Exam", back_populates="questions")

class ApiKey(Base):
    __tablename__ = 'api_keys'
    id = Column(Integer, primary_key=True)
    key_value = Column(String(200), unique=True, nullable=False, index=True)
    provider = Column(String(50), nullable=False, default='gemini')
    status = Column(String(20), default='ACTIVE', index=True) # ACTIVE, RATE_LIMITED, EXHAUSTED, INVALID
    weight = Column(Integer, default=10) # Higher weight = higher priority
    cooldown_until = Column(String(30), nullable=True) # Store ISO formatted datetime string
    created_at = Column(String(30), nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, index=True)
    
    user = relationship("User")

class AppConfig(Base):
    __tablename__ = 'app_config'
    key = Column(String(50), primary_key=True)
    value = Column(String(500))

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

def init_db():
    Base.metadata.create_all(engine)
    try:
        from sqlalchemy import text
        for alter_query in [
            "ALTER TABLE exams ADD COLUMN match_score INTEGER DEFAULT 0",
            "ALTER TABLE folders ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE exams ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE exam_attempts ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE api_keys ADD COLUMN user_id INTEGER REFERENCES users(id)"
        ]:
            try:
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                    conn.execute(text(alter_query))
            except Exception:
                pass
                
        # Optional manual schema updates can go here
    except Exception:
        pass
