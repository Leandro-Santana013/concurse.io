from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

class OptionSchema(BaseModel):
    key: str
    text: str

class QuestionSchema(BaseModel):
    id: Optional[int] = None
    numero_questao: str
    statement: str
    options: Dict[str, str] = Field(default_factory=dict)
    correct_answer: str
    subject: str = "Geral"
    images: Optional[List[str]] = None
    has_official_answer: bool = True
    latex_support: bool = False
    context_text: Optional[str] = None

class ExamSummarySchema(BaseModel):
    id: int
    title: str
    status: str
    question_count: int = 0
    best_score: Optional[float] = None
    last_score: Optional[float] = None
    attempt_count: int = 0
    has_official_answers: bool = False
    answer_key_source: str = "none"
    gabarito_coverage: float = 0.0
    gabarito_summary: Optional[str] = None
    source_url: Optional[str] = None
    gabarito_url: Optional[str] = None

class FolderSchema(BaseModel):
    id: Union[int, str]
    name: str
    exams: List[ExamSummarySchema] = Field(default_factory=list)

class ExamDetailSchema(BaseModel):
    id: int
    title: str
    status: str
    folder_id: Optional[int] = None
    source_url: Optional[str] = None
    gabarito_url: Optional[str] = None
    has_official_answers: bool = False
    gabarito_coverage: float = 0.0
    gabarito_text: Optional[str] = None
    questions: List[QuestionSchema] = Field(default_factory=list)

class SearchResultItem(BaseModel):
    id: Optional[int] = None
    title: str
    url: str
    gabarito_url: Optional[str] = None
    has_gabarito_link: Optional[bool] = False
    match_score: Optional[int] = 0
    source: Optional[str] = "web"
    status: Optional[str] = "Pendente"
    reuse_available: bool = False

class ExamIngestResponse(BaseModel):
    exam_id: int
    title: str
    status: str
    progress: int = 0
    message: str
    reused: bool = False
    already_in_library: bool = False

class ProgressEventSchema(BaseModel):
    exam_id: int
    status: str
    progress: int
    error_type: Optional[str] = None
    timestamp: float

class AttemptSubmission(BaseModel):
    exam_id: int
    elapsed_seconds: int
    answers: Dict[str, str]

class AttemptResult(BaseModel):
    attempt_id: int
    exam_id: int
    score: int
    total: int
    percentage: float
    elapsed_seconds: int
    detailed_answers: Dict[str, Dict[str, Any]]
    feedback_per_subject: Dict[str, Dict[str, Any]]
