from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class JobStatus(str, Enum):
    UPLOADED = "uploaded"
    ANALYZING = "analyzing"
    AWAITING_GLOSSARY_REVIEW = "awaiting_glossary_review"
    TRANSLATING = "translating"
    REVIEWING = "reviewing"
    ASSEMBLING = "assembling"
    DONE = "done"
    FAILED = "failed"


class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str
    mime_type: str
    size_bytes: int
    page_count: int = 0
    word_count: int = 0
    token_count: int = 0
    stored_path: str
    detected_lang: Optional[str] = None
    detected_lang_confidence: Optional[float] = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id")
    status: JobStatus = Field(default=JobStatus.UPLOADED)
    source_lang: str
    target_lang: str
    model_adapter: str
    model_name: str
    chunk_count: int = 0
    translated_chunks: int = 0
    estimated_seconds: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class Chunk(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    idx: int
    source_text: str
    translated_text: Optional[str] = None
    reviewed_text: Optional[str] = None
    token_count: int = 0
    translated_at: Optional[datetime] = None


class GlossaryTerm(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    source_term: str
    target_term: str
    notes: Optional[str] = None
    locked: bool = Field(default=True)
    occurrences: int = 0
