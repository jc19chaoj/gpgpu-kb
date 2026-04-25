# kb/schemas.py
import datetime

from pydantic import BaseModel, Field

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

    model_config = {"from_attributes": True}


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


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=settings.chat_query_max_len)
    top_k: int = Field(5, ge=1, le=settings.chat_top_k_max)


class ChatResponse(BaseModel):
    answer: str
    sources: list[PaperOut]


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=settings.chat_query_max_len)
    top_k: int = Field(10, ge=1, le=settings.chat_top_k_max)
    semantic: bool = True
