# kb/schemas.py
import datetime

from pydantic import BaseModel, Field, field_validator

from kb.config import settings


class PaperOut(BaseModel):
    id: int
    title: str
    authors: list[str]
    organizations: list[str]
    abstract: str
    url: str
    pdf_url: str
    source_type: str
    source_name: str
    published_date: datetime.datetime | None
    ingested_date: datetime.datetime
    categories: list[str]
    venue: str
    citation_count: int
    summary: str
    originality_score: float
    impact_score: float
    impact_rationale: str
    # Universal score axes (all source_types). For papers these mirror
    # originality_score/impact_score/impact_rationale; non-papers have
    # type-specific dim labels resolved in the frontend.
    quality_score: float = 0.0
    relevance_score: float = 0.0
    score_rationale: str = ""

    model_config = {"from_attributes": True}

    @field_validator("categories", mode="before")
    @classmethod
    def _coerce_categories(cls, v):
        # Legacy RSS rows persisted feedparser tag dicts ({'term', 'scheme',
        # 'label'}) into the JSON column. Coerce to plain strings so old data
        # doesn't 500 the API after the upstream ingestion fix.
        if not v:
            return []
        out: list[str] = []
        for item in v:
            if isinstance(item, str):
                if item:
                    out.append(item)
            elif isinstance(item, dict):
                term = item.get("term") or item.get("label")
                if isinstance(term, str) and term:
                    out.append(term)
        return out


class PaperListOut(BaseModel):
    papers: list[PaperOut]
    total: int
    page: int
    page_size: int


class DailyReportOut(BaseModel):
    id: int
    date: datetime.datetime
    title: str
    content: str
    paper_ids: list[int]

    model_config = {"from_attributes": True}


class ChatMessage(BaseModel):
    """One turn of chat history.

    The frontend sends prior user/assistant turns so the backend can build a
    multi-turn prompt. System messages are not accepted from the client; the
    backend prepends its own instructions.
    """
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=settings.chat_query_max_len * 4)


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=settings.chat_query_max_len)
    top_k: int = Field(5, ge=1, le=settings.chat_top_k_max)
    # Optional: when set, anchor the conversation to a single source. The
    # backend skips RAG retrieval, loads the entire source content (downloads
    # the PDF for arxiv papers), and feeds it as the sole context.
    paper_id: int | None = None
    # Optional: prior conversation turns from this client-side session. Bounded
    # in length on the API side (drop earliest if too long); the per-message
    # max_length above also caps individual turns.
    history: list[ChatMessage] = Field(default_factory=list, max_length=40)


class ChatResponse(BaseModel):
    answer: str
    sources: list[PaperOut]


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=settings.chat_query_max_len)
    top_k: int = Field(10, ge=1, le=settings.chat_top_k_max)
    semantic: bool = True
