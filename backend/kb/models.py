# kb/models.py
import datetime
import enum
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON, Enum as SAEnum
from kb.database import Base


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class SourceType(str, enum.Enum):
    PAPER = "paper"
    BLOG = "blog"
    TALK = "talk"
    PROJECT = "project"


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    authors = Column(JSON, default=list)
    organizations = Column(JSON, default=list)
    abstract = Column(Text, default="")
    url = Column(String(1000), default="", index=True, unique=True)
    pdf_url = Column(String(1000), default="")
    source_type = Column(SAEnum(SourceType), default=SourceType.PAPER, index=True)
    source_name = Column(String(200), default="")
    published_date = Column(DateTime(timezone=True), nullable=True)
    ingested_date = Column(DateTime(timezone=True), default=_utcnow, index=True)
    categories = Column(JSON, default=list)
    venue = Column(String(200), default="")
    citation_count = Column(Integer, default=0)

    # Processed fields
    summary = Column(Text, default="")
    # Paper-specific legacy axes (also mirrored from quality/relevance for papers).
    originality_score = Column(Float, default=0.0)
    impact_score = Column(Float, default=0.0, index=True)
    impact_rationale = Column(Text, default="")
    # Universal axes used by all source_types. Per-type rubrics map their own
    # dimension labels to these two fields; see kb/processing/llm.py.
    quality_score = Column(Float, default=0.0, index=True)
    relevance_score = Column(Float, default=0.0)
    score_rationale = Column(Text, default="")
    is_processed = Column(Integer, default=0, index=True)  # 0=pending, 1=done, 2=skipped

    # Vector embedding ref (stored in ChromaDB separately)
    chroma_id = Column(String(100), default="")


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime(timezone=True), nullable=False, unique=True)
    title = Column(String(300), default="")
    content = Column(Text, default="")  # Markdown
    paper_ids = Column(JSON, default=list)  # [int, int, ...]
    generated_date = Column(DateTime(timezone=True), default=_utcnow)
