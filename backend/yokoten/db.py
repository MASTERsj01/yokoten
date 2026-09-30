"""SQLite (SQLModel) storage. Postgres-ready: only portable column types are used."""

from datetime import UTC, datetime

from sqlalchemy import JSON
from sqlmodel import Field, Session, SQLModel, create_engine, select

from yokoten.config import settings

engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})


def now() -> datetime:
    return datetime.now(UTC)


class Document(SQLModel, table=True):
    rev_key: str = Field(primary_key=True)  # f"{doc_id}@{revision}"
    doc_id: str = Field(index=True)  # e.g. 8D-INV-22-007 (revisions share it)
    title: str
    doc_type: str = Field(index=True)
    format: str
    file: str  # path relative to the corpus / uploads dir
    collection: str = Field(default="engineering", index=True)
    source: str = "corpus"  # corpus | upload | public
    year: int | None = Field(default=None, index=True)
    date: str | None = None
    product_line: str | None = Field(default=None, index=True)
    component: str | None = Field(default=None, index=True)
    project: str | None = Field(default=None, index=True)
    plant: str | None = Field(default=None, index=True)
    suppliers: list = Field(default_factory=list, sa_type=JSON)
    part_numbers: list = Field(default_factory=list, sa_type=JSON)
    revision: str = "A"
    supersedes: str | None = None
    superseded_by: str | None = None
    is_latest: bool = True
    classification: str = Field(default="internal", index=True)
    author: str | None = None
    sha256: str = ""
    status: str = "pending"  # pending | processing | ready | error
    error: str | None = None
    n_pages: int | None = None
    n_chunks: int = 0
    ocr_engine: str | None = None
    ocr_confidence: float | None = None
    extra: dict = Field(default_factory=dict, sa_type=JSON)  # title block, entities, timings
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Chunk(SQLModel, table=True):
    id: str = Field(primary_key=True)  # f"{rev_key}:{strategy}:{idx}"
    rev_key: str = Field(index=True)
    doc_id: str = Field(index=True)
    strategy: str = Field(index=True)  # fixed | recursive | structure | parent_child
    idx: int
    kind: str = "text"  # text | table | figure | ocr | parent
    section: str = ""
    text: str
    page: int | None = None
    bboxes: list = Field(default_factory=list, sa_type=JSON)  # [[page, x0, y0, x1, y1], ...]
    parent_id: str | None = Field(default=None, index=True)
    entities: dict = Field(default_factory=dict, sa_type=JSON)


class Figure(SQLModel, table=True):
    id: str = Field(primary_key=True)
    rev_key: str = Field(index=True)
    doc_id: str = Field(index=True)
    page: int
    bbox: list = Field(default_factory=list, sa_type=JSON)
    caption: str = ""
    path: str  # relative to var/


class FmeaItem(SQLModel, table=True):
    """Structured rows parsed from DFMEA/PFMEA spreadsheets (used by text-to-SQL)."""

    id: int | None = Field(default=None, primary_key=True)
    doc_id: str = Field(index=True)
    revision: str
    is_latest: bool = True
    fmea_type: str  # dfmea | pfmea
    component: str | None = Field(default=None, index=True)
    plant: str | None = None
    item_id: str
    item: str
    failure_mode: str
    effect: str
    cause: str
    severity: int
    occurrence: int
    detection: int
    action_priority: str
    recommended_action: str = ""
    status: str = ""
    revised_occurrence: int | None = None
    revised_detection: int | None = None
    revised_action_priority: str | None = None


class LlmCache(SQLModel, table=True):
    key: str = Field(primary_key=True)  # sha256(provider, model, messages)
    provider: str
    model: str
    response: str
    usage: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=now)


class ChatSession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str = ""
    role: str = "admin"
    created_at: datetime = Field(default_factory=now)


class ChatMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    role: str  # user | assistant
    content: str
    trace_id: str | None = None
    created_at: datetime = Field(default_factory=now)


class Trace(SQLModel, table=True):
    """Everything the explainability panel shows for one answer."""

    id: str = Field(primary_key=True)
    session_id: str | None = Field(default=None, index=True)
    question: str
    standalone: str = ""
    answer: str = ""
    abstained: bool = False
    confidence: float | None = None
    confidence_label: str = ""
    intent: str = ""
    role: str = "admin"
    provider: str = ""
    model: str = ""
    prompt_version: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0
    data: dict = Field(
        default_factory=dict, sa_type=JSON
    )  # steps, filters, retrieved, citations, sentences, config
    created_at: datetime = Field(default_factory=now, index=True)


class Feedback(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    trace_id: str = Field(index=True)
    rating: int = 0  # +1 / -1
    comment: str = ""
    role: str = "admin"
    created_at: datetime = Field(default_factory=now)


class VerifiedAnswer(SQLModel, table=True):
    """SME-verified or corrected answers (feature M); similar future questions get them as a boosted source."""

    id: int | None = Field(default=None, primary_key=True)
    trace_id: str = Field(index=True)
    question: str
    standalone: str
    answer: str
    status: str = "verified"  # verified | corrected
    note: str = ""
    role: str = "quality_sme"
    created_at: datetime = Field(default_factory=now)


class EvalRun(SQLModel, table=True):
    id: str = Field(primary_key=True)
    summary: dict = Field(default_factory=dict, sa_type=JSON)
    path: str = ""
    created_at: datetime = Field(default_factory=now)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def session() -> Session:
    return Session(engine, expire_on_commit=False)


__all__ = [
    "ChatMessage",
    "ChatSession",
    "Chunk",
    "Document",
    "Feedback",
    "Figure",
    "FmeaItem",
    "LlmCache",
    "Trace",
    "engine",
    "init_db",
    "select",
    "session",
]
