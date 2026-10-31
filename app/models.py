from typing import Any, Literal
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    source_id: str = Field('demo', pattern=r'^(demo|[0-9a-f]{32})$')
    question: str = Field(min_length=3, max_length=2000)
    sql: str | None = Field(None, max_length=20000)
    clarification: str | None = Field(None, max_length=1000)
    session_id: str = Field('local', max_length=100)


class Generation(BaseModel):
    sql: str = ''
    explanation: str = ''
    referenced_tables: list[str] = []
    referenced_columns: list[str] = []
    assumptions: list[str] = []
    clarification_options: list[str] = []


class Interpretation(BaseModel):
    question: str


class QueryResponse(BaseModel):
    id: int | None = None
    source_id: str = 'demo'
    source_name: str = 'Demo database'
    status: Literal['success', 'clarification_required', 'blocked', 'validation_failed', 'execution_failed', 'low_confidence']
    question: str
    clarification: str | None = None
    answer: str = ''
    sql: str = ''
    explanation: str = ''
    results: list[dict[str, Any]] = []
    columns: list[str] = []
    row_count: int = 0
    execution_time_ms: float = 0
    confidence: dict[str, float | None] = {}
    validation: dict[str, Any] = {}
    warnings: list[str] = []
    options: list[str] = []
    reason: str = ''
    guardrail: str = ''


class FeedbackRequest(BaseModel):
    query_id: int
    correct: bool
    comment: str = Field('', max_length=2000)


class HealthResponse(BaseModel):
    api: str = 'ok'
    database: str
    metadata: str
    ollama: str = 'not_used'
    llm: str = 'unavailable'
    model: str
    provider: str = 'ollama'
    schema_status: str
    message: str = ''


class SchemaResponse(BaseModel):
    tables: dict[str, Any]


class HistoryResponse(BaseModel):
    items: list[dict[str, Any]]
    offset: int
    total: int = 0


class FeedbackResponse(BaseModel):
    saved: bool


class TranscriptionResponse(BaseModel):
    text: str
    language: str
    duration_seconds: float


class TableRecordsResponse(BaseModel):
    table: str
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    limit: int
    offset: int
    warnings: list[str] = []
