"""Pydantic schemas for API request/response models."""
from pydantic import BaseModel


class EvidenceItem(BaseModel):
    tag: str
    before: str = ""
    after: str = ""


class ComparisonItem(BaseModel):
    article_number: str
    dieu_number: str | None = None
    khoan_number: str | None = None
    article_title: str = ""
    status: str
    match_score: float = 0.0
    matched_article_v2: str | None = None
    conclusion: str = ""
    grounded: bool = False
    llm_used: bool = False
    evidence: list[EvidenceItem] = []


class ReportConfig(BaseModel):
    file_v1: str
    file_v2: str
    llm_model: str
    embed_model: str
    total_khoans: int
    status_counts: dict[str, int]
    grounded_count: int
    llm_used_count: int


class CompareResponse(BaseModel):
    session_id: str
    config: ReportConfig
    results: list[ComparisonItem]
    has_docx_v1: bool
    has_docx_v2: bool


class HealthResponse(BaseModel):
    embedder: str  # "ready" | "loading"
    ollama: str    # "ready" | "error"
