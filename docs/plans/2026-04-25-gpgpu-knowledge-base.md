# GPGPU Knowledge Base — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a self-updating knowledge base that collects, summarizes, and scores high-impact research (papers, blogs, talks, OSS projects) for a GPGPU chip architect, with a Next.js web UI for browsing and RAG-powered chat.

**Architecture:** Python FastAPI backend serves a REST API. SQLite stores metadata + summaries. ChromaDB stores vector embeddings for semantic search and RAG. A cron-driven ingestion pipeline fetches from ArXiv, RSS feeds, and GitHub Trending. An LLM-powered processing pipeline summarizes, scores originality/impact, and generates embeddings. A Next.js App Router frontend with Tailwind + shadcn/ui provides browse, search, detail, and chat views. Everything runs locally; user exposes the UI port via cpolar.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, ChromaDB, sentence-transformers, feedparser, httpx, Next.js 15, TypeScript, Tailwind CSS, shadcn/ui

---

## Phase 1: Project Scaffolding

### Task 1: Initialize Python backend project

**Objective:** Create the Python project structure with dependencies and config.

**Files:**
- Create: `~/gpgpu-kb/backend/pyproject.toml`
- Create: `~/gpgpu-kb/backend/requirements.txt`
- Create: `~/gpgpu-kb/backend/.env.example`
- Create: `~/gpgpu-kb/backend/kb/__init__.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "gpgpu-kb"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy>=2.0.0",
    "chromadb>=0.5.0",
    "sentence-transformers>=3.0.0",
    "feedparser>=6.0.0",
    "httpx>=0.28.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "python-dotenv>=1.0.0",
    "arxiv>=2.1.0",
]
```

**Step 2: Create initial module**

```python
# kb/__init__.py
"""GPGPU Knowledge Base — backend."""
```

**Step 3: Install deps and verify**

Run: `cd ~/gpgpu-kb/backend && pip install -e .`

Expected: All packages install without error.

---

### Task 2: Initialize Next.js frontend project

**Objective:** Scaffold the Next.js app with TypeScript, Tailwind, and shadcn/ui.

**Files:**
- Create: `~/gpgpu-kb/frontend/` (via create-next-app)

**Step 1: Scaffold Next.js**

```bash
cd ~/gpgpu-kb
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --no-turbopack
```

**Step 2: Add shadcn/ui**

```bash
cd ~/gpgpu-kb/frontend
npx shadcn@latest init -d
npx shadcn@latest add button card input badge separator dialog scroll-area tabs skeleton
```

**Step 3: Add additional deps**

```bash
cd ~/gpgpu-kb/frontend
npm install react-markdown remark-gfm lucide-react
npm install -D @types/node
```

**Step 4: Verify build**

Run: `npm run build`

Expected: Build succeeds with no errors.

---

## Phase 2: Data Models & Database

### Task 3: Define SQLAlchemy models

**Objective:** Create the Paper and DailyReport database models.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/models.py`
- Create: `~/gpgpu-kb/backend/kb/database.py`

**Step 1: Create database.py**

```python
# kb/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

SQLALCHEMY_DATABASE_URL = "sqlite:///./data/kb.sqlite"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    import kb.models  # noqa: F401 — ensure models registered
    Base.metadata.create_all(bind=engine)
```

**Step 2: Create models.py**

```python
# kb/models.py
import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON, Enum as SAEnum
from kb.database import Base
import enum


class SourceType(str, enum.Enum):
    PAPER = "paper"
    BLOG = "blog"
    TALK = "talk"
    PROJECT = "project"


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    authors = Column(JSON, default=[])
    organizations = Column(JSON, default=[])
    abstract = Column(Text, default="")
    url = Column(String(1000), default="")
    pdf_url = Column(String(1000), default="")
    source_type = Column(SAEnum(SourceType), default=SourceType.PAPER)
    source_name = Column(String(200), default="")  # "arxiv", "distill", "github", etc.
    published_date = Column(DateTime, nullable=True)
    ingested_date = Column(DateTime, default=datetime.datetime.utcnow)
    categories = Column(JSON, default=[])
    venue = Column(String(200), default="")
    citation_count = Column(Integer, default=0)

    # Processed fields
    summary = Column(Text, default="")
    originality_score = Column(Float, default=0.0)
    impact_score = Column(Float, default=0.0)
    impact_rationale = Column(Text, default="")
    is_processed = Column(Integer, default=0)  # 0=pending, 1=done, 2=skipped

    # Vector embedding ref (stored in ChromaDB separately)
    chroma_id = Column(String(100), default="")


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, unique=True)
    title = Column(String(300), default="")
    content = Column(Text, default="")  # Markdown
    paper_ids = Column(JSON, default=[])  # [int, int, ...]
    generated_date = Column(DateTime, default=datetime.datetime.utcnow)
```

Run: `python -c "from kb.database import init_db; init_db()"`

Expected: `data/kb.sqlite` created with papers and daily_reports tables.

---

### Task 4: Create Pydantic schemas

**Objective:** Define request/response schemas for the API.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/schemas.py`

```python
# kb/schemas.py
import datetime
from pydantic import BaseModel


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
    query: str
    top_k: int = 5


class ChatResponse(BaseModel):
    answer: str
    sources: list[PaperOut]


class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    semantic: bool = True
```

---

## Phase 3: Ingestion Pipeline

### Task 5: Create ArXiv ingestion module

**Objective:** Fetch papers from ArXiv categories relevant to GPGPU/chip/AI.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/ingestion/__init__.py`
- Create: `~/gpgpu-kb/backend/kb/ingestion/arxiv.py`

```python
# kb/ingestion/arxiv.py
import arxiv
import datetime
from kb.database import SessionLocal
from kb.models import Paper, SourceType


ARXIV_CATEGORIES = [
    "cs.AR",   # Architecture
    "cs.AI",   # Artificial Intelligence
    "cs.LG",   # Machine Learning
    "cs.CL",   # Computation and Language (LLMs)
    "cs.ET",   # Emerging Technologies
    "cs.DC",   # Distributed/Parallel Computing
    "cs.PF",   # Performance
    "cs.SE",   # Software Engineering
    "cs.NE",   # Neural and Evolutionary Computing
]

MAX_RESULTS = 50


def fetch_recent_papers(days_back: int = 1) -> list[dict]:
    """Fetch recent papers from ArXiv and return as dicts."""
    client = arxiv.Client()
    search = arxiv.Search(
        query=" OR ".join(f"cat:{cat}" for cat in ARXIV_CATEGORIES),
        max_results=MAX_RESULTS,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
    papers = []

    for result in client.results(search):
        if result.published < cutoff:
            continue

        paper = {
            "title": result.title,
            "authors": [a.name for a in result.authors],
            "organizations": [],  # ArXiv doesn't provide orgs directly
            "abstract": result.summary.replace("\n", " "),
            "url": result.entry_id,
            "pdf_url": result.pdf_url,
            "source_type": SourceType.PAPER.value,
            "source_name": "arxiv",
            "published_date": result.published,
            "categories": result.categories,
            "venue": "",  # Often in comments; can be extracted later
        }
        papers.append(paper)

    return papers


def save_papers(papers: list[dict]) -> int:
    """Save papers to DB, skip duplicates by URL. Returns count of new papers."""
    db = SessionLocal()
    new_count = 0
    for p in papers:
        existing = db.query(Paper).filter(Paper.url == p["url"]).first()
        if existing:
            continue
        db.add(Paper(**p))
        new_count += 1
    db.commit()
    db.close()
    return new_count
```

---

### Task 6: Create RSS/blog ingestion module

**Objective:** Fetch posts from key GPGPU/AI/LLM blogs.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/ingestion/rss.py`

```python
# kb/ingestion/rss.py
import feedparser
import datetime
from kb.database import SessionLocal
from kb.models import Paper, SourceType

# Curated list of high-signal feeds
FEEDS = [
    # Chip / Architecture
    ("https://semiengineering.com/feed/", "Semiconductor Engineering"),
    ("https://chipsandcheese.com/feed/", "Chips and Cheese"),
    ("https://www.anandtech.com/rss", "AnandTech"),
    ("https://fuse.wikichip.org/feed/", "WikiChip Fuse"),
    # AI / ML
    ("https://openai.com/blog/rss.xml", "OpenAI Blog"),
    ("https://www.anthropic.com/blog/rss.xml", "Anthropic Blog"),
    ("https://blog.google/technology/ai/rss/", "Google AI Blog"),
    ("https://ai.meta.com/blog/feed/", "Meta AI Blog"),
    ("https://huggingface.co/blog/feed.xml", "Hugging Face Blog"),
    ("https://distill.pub/feed.xml", "Distill"),
    # Systems / Performance
    ("https://lilianweng.github.io/feed.xml", "Lilian Weng (OpenAI)"),
    ("https://karpathy.github.io/feed.xml", "Andrej Karpathy"),
    ("https://www.interconnects.ai/feed", "Interconnects (Nathan Lambert)"),
]


def fetch_recent_posts(days_back: int = 1) -> list[dict]:
    """Fetch recent blog posts from RSS feeds."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_back)
    posts = []

    for feed_url, source_name in FEEDS:
        try:
            feed = feedparser.parse(feed_url)
        except Exception:
            continue

        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime.datetime(*entry.published_parsed[:6], tzinfo=datetime.timezone.utc)

            if published and published < cutoff:
                continue

            posts.append({
                "title": entry.get("title", ""),
                "authors": [entry.get("author", "")] if entry.get("author") else [],
                "organizations": [],
                "abstract": entry.get("summary", "")[:2000],
                "url": entry.get("link", ""),
                "pdf_url": "",
                "source_type": SourceType.BLOG.value,
                "source_name": source_name,
                "published_date": published,
                "categories": entry.get("tags", []),
                "venue": "",
            })

    return posts


def save_posts(posts: list[dict]) -> int:
    """Save blog posts to DB (same Paper table), skip duplicates."""
    db = SessionLocal()
    new_count = 0
    for p in posts:
        existing = db.query(Paper).filter(Paper.url == p["url"]).first()
        if existing:
            continue
        db.add(Paper(**p))
        new_count += 1
    db.commit()
    db.close()
    return new_count
```

---

### Task 7: Create GitHub Trending ingestion module

**Objective:** Fetch trending open-source projects in AI/ML/systems.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/ingestion/github_trending.py`

```python
# kb/ingestion/github_trending.py
import httpx
import datetime
from kb.database import SessionLocal
from kb.models import Paper, SourceType

TRENDING_URLS = [
    "https://github.com/trending/python?since=daily",
    "https://github.com/trending/c%2B%2B?since=daily",
    "https://github.com/trending/c?since=daily",
]

KEYWORDS = [
    "llm", "gpu", "cuda", "triton", "mlir", "transformer",
    "inference", "training", "benchmark", "compiler", "kernel",
    "attention", "quantization", "sparsity", "tpu", "npu",
    "deep-learning", "machine-learning", "ai-", "-ai",
]


def fetch_trending_repos() -> list[dict]:
    """Scrape GitHub Trending and filter for relevant repos."""
    # Note: GitHub Trending has no official API. We parse the page.
    # For a more robust approach, use the GitHub Search API instead.
    repos = []

    # Use GitHub Search API for repos with stars pushed recently
    # This is more reliable than scraping Trending
    yesterday = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)).strftime("%Y-%m-%d")

    with httpx.Client(timeout=15) as client:
        for keyword in ["gpu", "cuda", "triton", "llm", "mlir", "transformer", "kernel"]:
            try:
                resp = client.get(
                    "https://api.github.com/search/repositories",
                    params={
                        "q": f"{keyword} pushed:>{yesterday}",
                        "sort": "stars",
                        "order": "desc",
                        "per_page": 10,
                    },
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                data = resp.json()
                for item in data.get("items", []):
                    repos.append({
                        "title": item["full_name"],
                        "authors": [item["owner"]["login"]],
                        "organizations": [item["owner"]["login"]] if item["owner"]["type"] == "Organization" else [],
                        "abstract": item.get("description", "") or "",
                        "url": item["html_url"],
                        "pdf_url": "",
                        "source_type": SourceType.PROJECT.value,
                        "source_name": "github",
                        "published_date": datetime.datetime.fromisoformat(
                            item["pushed_at"].replace("Z", "+00:00")
                        ),
                        "categories": item.get("topics", []),
                        "venue": "",
                    })
            except Exception:
                continue

    return repos


def save_repos(repos: list[dict]) -> int:
    """Save GitHub repos to DB, skip duplicates."""
    db = SessionLocal()
    new_count = 0
    for r in repos:
        existing = db.query(Paper).filter(Paper.url == r["url"]).first()
        if existing:
            continue
        db.add(Paper(**r))
        new_count += 1
    db.commit()
    db.close()
    return new_count
```

---

### Task 8: Create ingestion orchestrator

**Objective:** Single entry point that runs all ingestion sources.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/ingestion/run.py`

```python
# kb/ingestion/run.py
"""Run all ingestion pipelines. Called by cron job."""

from kb.ingestion.arxiv import fetch_recent_papers, save_papers
from kb.ingestion.rss import fetch_recent_posts, save_posts
from kb.ingestion.github_trending import fetch_trending_repos, save_repos


def run_ingestion(days_back: int = 1) -> dict:
    """Run all ingestion sources. Returns counts."""
    results = {}

    print("[ingestion] Fetching ArXiv papers...")
    papers = fetch_recent_papers(days_back=days_back)
    results["arxiv"] = save_papers(papers)
    print(f"[ingestion]   {results['arxiv']} new papers")

    print("[ingestion] Fetching blog posts...")
    posts = fetch_recent_posts(days_back=days_back)
    results["blogs"] = save_posts(posts)
    print(f"[ingestion]   {results['blogs']} new posts")

    print("[ingestion] Fetching GitHub repos...")
    repos = fetch_trending_repos()
    results["github"] = save_repos(repos)
    print(f"[ingestion]   {results['github']} new repos")

    total = sum(results.values())
    print(f"[ingestion] Done. {total} total new items.")
    return results


if __name__ == "__main__":
    run_ingestion()
```

---

## Phase 4: Processing Pipeline

### Task 9: Create LLM processing module (summarization + scoring)

**Objective:** Summarize papers and score originality/impact using LLM.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/processing/__init__.py`
- Create: `~/gpgpu-kb/backend/kb/processing/llm.py`

```python
# kb/processing/llm.py
"""LLM-powered summarization and scoring. Uses the Hermes agent's model."""
import json
import subprocess
from kb.database import SessionLocal
from kb.models import Paper


# IMPORTANT: This is a CLI invocation of the Hermes agent.
# In production, this should use the OpenAI-compatible API directly.
# Adjust the command based on your Hermes setup.

def _call_llm(prompt: str) -> str:
    """Call the LLM via Hermes CLI with a one-shot prompt.
    Returns the model's response text.
    """
    # Use hermes CLI in non-interactive mode
    result = subprocess.run(
        ["hermes", "ask", "--prompt", prompt, "--quiet", "--skip-context-files"],
        capture_output=True, text=True, timeout=120,
    )
    return result.stdout.strip()


def summarize_and_score(paper_id: int) -> bool:
    """Summarize a paper and score its originality/impact.
    Returns True on success, False on failure.
    """
    db = SessionLocal()
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        db.close()
        return False

    authors_str = ", ".join(paper.authors[:8]) if paper.authors else "unknown"
    orgs_str = ", ".join(paper.organizations[:5]) if paper.organizations else "unknown"

    # Step 1: Summarization
    summary_prompt = f"""You are an expert GPGPU chip architect reviewing a research paper.

Title: {paper.title}
Authors: {authors_str}
Organizations: {orgs_str}
Published: {paper.published_date}
Abstract: {paper.abstract}

Write a detailed technical summary of this paper. Cover:
1. The core technical contribution or idea
2. The approach/methodology
3. Key results and their significance
4. Any novel techniques (new algorithms, architectures, optimizations)

Write 3-5 paragraphs. Be technical and precise. Do not use fluff.
Only output the summary, nothing else."""

    summary = _call_llm(summary_prompt)

    # Step 2: Originality and Impact Assessment
    impact_prompt = f"""You are an expert GPGPU chip architect evaluating a research paper's originality and impact.

Paper Title: {paper.title}
Authors: {authors_str}
Organizations: {orgs_str}
Type: {paper.source_type.value if hasattr(paper.source_type, 'value') else paper.source_type}
Venue: {paper.venue or 'unknown'}

Summary:
{summary}

Evaluate this work on two dimensions (0-10 scale):

ORIGINALITY (0-10): How novel is the core idea?
- 8-10: Fundamentally new paradigm, technique, or insight
- 5-7: Significant extension or clever combination of existing ideas
- 2-4: Incremental improvement on well-known approach
- 0-1: Trivial or known result

IMPACT (0-10): How likely to influence the field?
Consider: author track record, organization prestige, venue quality, problem importance, generality of solution.
- 8-10: Will change how people think/work in the field (FAANG lab + top venue)
- 5-7: Important contribution, likely to be cited and built upon
- 2-4: Solid work but narrow applicability
- 0-1: Unlikely to be noticed

Output ONLY a JSON object:
{{
  "originality_score": <float>,
  "impact_score": <float>,
  "impact_rationale": "<2-3 sentences explaining the impact score>"
}}"""

    try:
        result_text = _call_llm(impact_prompt)
        # Try to extract JSON from the response
        start = result_text.find("{")
        end = result_text.rfind("}") + 1
        if start >= 0 and end > start:
            result_json = json.loads(result_text[start:end])
        else:
            result_json = {"originality_score": 5.0, "impact_score": 5.0, "impact_rationale": "Could not parse assessment."}
    except Exception:
        result_json = {"originality_score": 5.0, "impact_score": 5.0, "impact_rationale": "Assessment failed."}

    # Update
    paper.summary = summary
    paper.originality_score = result_json.get("originality_score", 5.0)
    paper.impact_score = result_json.get("impact_score", 5.0)
    paper.impact_rationale = result_json.get("impact_rationale", "")
    paper.is_processed = 1

    db.commit()
    db.close()
    return True


def run_processing(batch_size: int = 20) -> int:
    """Process all unprocessed papers. Returns count processed."""
    db = SessionLocal()
    unprocessed = db.query(Paper).filter(Paper.is_processed == 0).limit(batch_size).all()
    db.close()

    count = 0
    for paper in unprocessed:
        print(f"[processing] Paper {paper.id}: {paper.title[:80]}...")
        try:
            ok = summarize_and_score(paper.id)
            if ok:
                count += 1
                print(f"[processing]   Done. Orig={paper.originality_score}, Impact={paper.impact_score}")
        except Exception as e:
            print(f"[processing]   Failed: {e}")

    print(f"[processing] Processed {count}/{len(unprocessed)} papers.")
    return count
```

---

### Task 10: Create embedding pipeline (ChromaDB)

**Objective:** Generate embeddings for semantic search and RAG.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/processing/embeddings.py`

```python
# kb/processing/embeddings.py
"""Generate embeddings and store in ChromaDB."""
import uuid
import chromadb
from sentence_transformers import SentenceTransformer
from kb.database import SessionLocal
from kb.models import Paper


class EmbeddingStore:
    def __init__(self, persist_dir: str = "./data/chroma"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="papers",
            metadata={"hnsw:space": "cosine"},
        )
        self.model = SentenceTransformer("all-MiniLM-L6-v2")  # Fast, good quality

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        return self.model.encode(text).tolist()

    def index_paper(self, paper_id: int, title: str, summary: str, abstract: str) -> str:
        """Index a paper in ChromaDB. Returns chroma_id."""
        # Combine title + abstract + summary for a rich embedding
        text = f"Title: {title}\n\nAbstract: {abstract}\n\nSummary: {summary}"
        embedding = self.embed_text(text)
        chroma_id = str(uuid.uuid4())

        self.collection.add(
            ids=[chroma_id],
            embeddings=[embedding],
            metadatas=[{"paper_id": paper_id, "title": title[:500]}],
            documents=[text[:5000]],  # Keep reasonable size
        )
        return chroma_id

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Semantic search. Returns [{paper_id, title, score}, ...]."""
        query_embedding = self.embed_text(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
        )

        out = []
        if results["ids"] and results["ids"][0]:
            for i, chroma_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                dist = results["distances"][0][i] if results["distances"] else 0.0
                out.append({
                    "chroma_id": chroma_id,
                    "paper_id": meta.get("paper_id", 0),
                    "title": meta.get("title", ""),
                    "score": 1.0 - dist,  # Convert cosine distance to similarity
                })
        return out


def index_unindexed_papers(batch_size: int = 50) -> int:
    """Find papers without embeddings and index them."""
    store = EmbeddingStore()
    db = SessionLocal()
    unindexed = db.query(Paper).filter(
        Paper.is_processed == 1,
        Paper.chroma_id == "",
    ).limit(batch_size).all()

    count = 0
    for paper in unindexed:
        try:
            chroma_id = store.index_paper(paper.id, paper.title, paper.summary, paper.abstract)
            paper.chroma_id = chroma_id
            count += 1
        except Exception as e:
            print(f"[embeddings] Failed to index paper {paper.id}: {e}")

    db.commit()
    db.close()
    print(f"[embeddings] Indexed {count} papers.")
    return count


# Singleton for API use
_store: EmbeddingStore | None = None


def get_embedding_store() -> EmbeddingStore:
    global _store
    if _store is None:
        _store = EmbeddingStore()
    return _store
```

---

## Phase 5: Backend API (FastAPI)

### Task 11: Create main FastAPI app

**Objective:** Set up the FastAPI application with all endpoints.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/main.py`
- Create: `~/gpgpu-kb/backend/kb/config.py`

**Step 1: Create config**

```python
# kb/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "GPGPU Knowledge Base"
    cors_origins: list[str] = ["http://localhost:3000"]  # Next.js dev
    data_dir: str = "./data"

    class Config:
        env_file = ".env"
        env_prefix = "KB_"


settings = Settings()
```

**Step 2: Create main API**

```python
# kb/main.py
import os
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from kb.database import get_db, init_db
from kb.models import Paper, DailyReport, SourceType
from kb.schemas import PaperOut, PaperListOut, DailyReportOut, ChatRequest, ChatResponse
from kb.processing.embeddings import get_embedding_store
from kb.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    os.makedirs(settings.data_dir, exist_ok=True)
    init_db()


# ─── Papers ───────────────────────────────────────────

@app.get("/api/papers", response_model=PaperListOut)
def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: str | None = None,
    sort_by: str = Query("impact_score", pattern="^(published_date|impact_score|originality_score|ingested_date)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    q = db.query(Paper)
    if source_type:
        q = q.filter(Paper.source_type == source_type)

    if sort_dir == "desc":
        q = q.order_by(getattr(Paper, sort_by).desc())
    else:
        q = q.order_by(getattr(Paper, sort_by).asc())

    total = q.count()
    papers = q.offset((page - 1) * page_size).limit(page_size).all()

    return PaperListOut(
        papers=[PaperOut.model_validate(p) for p in papers],
        total=total,
        page=page,
        page_size=page_size,
    )


@app.get("/api/papers/{paper_id}", response_model=PaperOut)
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return PaperOut.model_validate(paper)


@app.get("/api/papers/search", response_model=PaperListOut)
def search_papers(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    semantic: bool = Query(True),
    db: Session = Depends(get_db),
):
    if semantic:
        store = get_embedding_store()
        results = store.search(q, top_k=page * page_size)

        # Fetch full paper objects
        paper_ids = [r["paper_id"] for r in results]
        papers_by_id = {}
        for pid in paper_ids:
            p = db.query(Paper).filter(Paper.id == pid).first()
            if p:
                papers_by_id[pid] = p

        # Preserve relevance order
        ordered = [papers_by_id[pid] for pid in paper_ids if pid in papers_by_id]
        paged = ordered[(page - 1) * page_size : page * page_size]

        return PaperListOut(
            papers=[PaperOut.model_validate(p) for p in paged],
            total=len(ordered),
            page=page,
            page_size=page_size,
        )
    else:
        # Keyword search fallback
        query = q.lower()
        results = db.query(Paper).filter(
            (Paper.title.ilike(f"%{query}%")) |
            (Paper.abstract.ilike(f"%{query}%")) |
            (Paper.summary.ilike(f"%{query}%"))
        ).order_by(Paper.impact_score.desc())

        total = results.count()
        paged = results.offset((page - 1) * page_size).limit(page_size).all()

        return PaperListOut(
            papers=[PaperOut.model_validate(p) for p in paged],
            total=total,
            page=page,
            page_size=page_size,
        )


# ─── Chat (RAG) ───────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    # 1. Semantic search for relevant papers
    store = get_embedding_store()
    results = store.search(req.query, top_k=req.top_k)

    # 2. Build context from retrieved papers
    context_parts = []
    sources = []
    for r in results:
        paper = db.query(Paper).filter(Paper.id == r["paper_id"]).first()
        if paper and paper.summary:
            context_parts.append(f"## {paper.title}\nAuthors: {', '.join(paper.authors[:5])}\n{paper.summary}\n")
            sources.append(PaperOut.model_validate(paper))

    context = "\n---\n".join(context_parts) if context_parts else "No relevant papers found."

    # 3. Build RAG prompt and call LLM
    prompt = f"""You are an expert GPGPU chip architect assistant. Answer the user's question based on the research papers below. If the papers don't contain enough information, say so and provide your best knowledge.

USER QUESTION: {req.query}

RELEVANT RESEARCH PAPERS:
{context}

Answer the question concisely but thoroughly. Cite specific papers by title when using their information."""

    from kb.processing.llm import _call_llm
    answer = _call_llm(prompt)

    return ChatResponse(answer=answer, sources=sources)


# ─── Daily Reports ────────────────────────────────────

@app.get("/api/reports", response_model=list[DailyReportOut])
def list_reports(
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    reports = db.query(DailyReport).order_by(DailyReport.date.desc()).limit(limit).all()
    return [DailyReportOut.model_validate(r) for r in reports]


@app.get("/api/reports/{report_id}", response_model=DailyReportOut)
def get_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(DailyReport).filter(DailyReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return DailyReportOut.model_validate(report)


# ─── Stats ────────────────────────────────────────────

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(Paper).count()
    processed = db.query(Paper).filter(Paper.is_processed == 1).count()
    by_type = {}
    for st in SourceType:
        count = db.query(Paper).filter(Paper.source_type == st).count()
        by_type[st.value] = count
    top_impact = (
        db.query(Paper)
        .filter(Paper.is_processed == 1)
        .order_by(Paper.impact_score.desc())
        .limit(5)
        .all()
    )
    return {
        "total_papers": total,
        "processed": processed,
        "by_type": by_type,
        "top_impact": [
            {"id": p.id, "title": p.title, "impact_score": p.impact_score}
            for p in top_impact
        ],
    }
```

---

### Task 12: Create API startup script

**Objective:** Script to start the FastAPI server.

**Files:**
- Create: `~/gpgpu-kb/backend/run_api.sh`

```bash
#!/bin/bash
# run_api.sh — Start the FastAPI server
cd "$(dirname "$0")"
mkdir -p data
uvicorn kb.main:app --host 0.0.0.0 --port 8000 --reload
```

Run: `chmod +x ~/gpgpu-kb/backend/run_api.sh`

---

## Phase 6: Frontend (Next.js)

### Task 13: Create API client layer

**Objective:** TypeScript API client for the backend.

**Files:**
- Create: `~/gpgpu-kb/frontend/src/lib/api.ts`
- Create: `~/gpgpu-kb/frontend/src/lib/types.ts`

**Step 1: Create types**

```typescript
// src/lib/types.ts
export interface Paper {
  id: number;
  title: string;
  authors: string[];
  organizations: string[];
  abstract: string;
  url: string;
  pdf_url: string;
  source_type: "paper" | "blog" | "talk" | "project";
  source_name: string;
  published_date: string | null;
  ingested_date: string;
  categories: string[];
  venue: string;
  citation_count: number;
  summary: string;
  originality_score: number;
  impact_score: number;
  impact_rationale: string;
}

export interface PaperListResponse {
  papers: Paper[];
  total: number;
  page: number;
  page_size: number;
}

export interface DailyReport {
  id: number;
  date: string;
  title: string;
  content: string;
  paper_ids: number[];
}

export interface ChatRequest {
  query: string;
  top_k?: number;
}

export interface ChatResponse {
  answer: string;
  sources: Paper[];
}

export interface Stats {
  total_papers: number;
  processed: number;
  by_type: Record<string, number>;
  top_impact: { id: number; title: string; impact_score: number }[];
}
```

**Step 2: Create API client**

```typescript
// src/lib/api.ts
import { Paper, PaperListResponse, DailyReport, ChatRequest, ChatResponse, Stats } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
  return res.json();
}

export async function listPapers(params?: {
  page?: number;
  page_size?: number;
  source_type?: string;
  sort_by?: string;
  sort_dir?: string;
}): Promise<PaperListResponse> {
  const sp = new URLSearchParams();
  if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) sp.set(k, String(v)); });
  return fetchJSON<PaperListResponse>(`/api/papers?${sp.toString()}`);
}

export async function getPaper(id: number): Promise<Paper> {
  return fetchJSON<Paper>(`/api/papers/${id}`);
}

export async function searchPapers(q: string, params?: {
  page?: number;
  page_size?: number;
  semantic?: boolean;
}): Promise<PaperListResponse> {
  const sp = new URLSearchParams({ q });
  if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) sp.set(k, String(v)); });
  return fetchJSON<PaperListResponse>(`/api/papers/search?${sp.toString()}`);
}

export async function chat(request: ChatRequest): Promise<ChatResponse> {
  return fetchJSON<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export async function listReports(limit?: number): Promise<DailyReport[]> {
  const sp = new URLSearchParams();
  if (limit) sp.set("limit", String(limit));
  return fetchJSON<DailyReport[]>(`/api/reports?${sp.toString()}`);
}

export async function getReport(id: number): Promise<DailyReport> {
  return fetchJSON<DailyReport>(`/api/reports/${id}`);
}

export async function getStats(): Promise<Stats> {
  return fetchJSON<Stats>("/api/stats");
}
```

---

### Task 14: Create main layout and navigation

**Objective:** Create the app layout with sidebar navigation.

**Files:**
- Create: `~/gpgpu-kb/frontend/src/components/layout/sidebar.tsx`
- Create: `~/gpgpu-kb/frontend/src/components/layout/header.tsx`
- Modify: `~/gpgpu-kb/frontend/src/app/layout.tsx`

**Step 1: Create sidebar**

```tsx
// src/components/layout/sidebar.tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { BookOpen, MessageCircle, Newspaper, BarChart3, Cpu } from "lucide-react";

const navItems = [
  { href: "/", label: "Browse", icon: BookOpen },
  { href: "/chat", label: "Chat (RAG)", icon: MessageCircle },
  { href: "/reports", label: "Daily Reports", icon: Newspaper },
  { href: "/stats", label: "Stats", icon: BarChart3 },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-60 border-r bg-zinc-950 text-zinc-100 flex flex-col h-screen">
      <div className="p-4 border-b border-zinc-800 flex items-center gap-2">
        <Cpu className="h-5 w-5 text-emerald-400" />
        <span className="font-semibold text-sm">GPGPU KB</span>
      </div>
      <nav className="flex-1 p-2">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
              pathname === item.href
                ? "bg-zinc-800 text-white"
                : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
            )}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
```

**Step 2: Create header**

```tsx
// src/components/layout/header.tsx
export function Header() {
  return (
    <header className="h-12 border-b border-zinc-800 flex items-center px-4 bg-zinc-950/50">
      <div className="flex-1" />
      <span className="text-xs text-zinc-500">GPGPU Knowledge Base v0.1</span>
    </header>
  );
}
```

**Step 3: Update layout**

```tsx
// src/app/layout.tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Sidebar } from "@/components/layout/sidebar";
import { Header } from "@/components/layout/header";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "GPGPU Knowledge Base",
  description: "Curated research knowledge base for GPGPU chip architecture",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-zinc-950 text-zinc-100`}>
        <div className="flex h-screen">
          <Sidebar />
          <div className="flex-1 flex flex-col overflow-hidden">
            <Header />
            <main className="flex-1 overflow-auto">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
```

---

### Task 15: Create Browse page (main list view)

**Objective:** Main page with paper list, filtering, sorting, and search.

**Files:**
- Create: `~/gpgpu-kb/frontend/src/app/page.tsx`
- Create: `~/gpgpu-kb/frontend/src/components/paper-card.tsx`
- Create: `~/gpgpu-kb/frontend/src/components/search-bar.tsx`

**Step 1: Create PaperCard component**

```tsx
// src/components/paper-card.tsx
import { Paper } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";
import { ExternalLink, FileText, Github, Video } from "lucide-react";

const sourceIcons: Record<string, React.ReactNode> = {
  paper: <FileText className="h-3 w-3" />,
  blog: <FileText className="h-3 w-3" />,
  talk: <Video className="h-3 w-3" />,
  project: <Github className="h-3 w-3" />,
};

function ScoreBar({ label, score }: { label: string; score: number }) {
  const width = Math.round(score * 10);
  const color = score >= 7 ? "bg-emerald-500" : score >= 4 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-zinc-500 w-20">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${width}%` }} />
      </div>
      <span className="text-zinc-400 w-8 text-right">{score.toFixed(1)}</span>
    </div>
  );
}

export function PaperCard({ paper }: { paper: Paper }) {
  return (
    <Card className="bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <Link href={`/paper/${paper.id}`} className="hover:text-emerald-400 transition-colors">
              <h3 className="font-medium text-sm leading-snug line-clamp-2">{paper.title}</h3>
            </Link>
            <p className="text-xs text-zinc-400 mt-1">
              {paper.authors.slice(0, 3).join(", ")}
              {paper.authors.length > 3 ? ` +${paper.authors.length - 3} more` : ""}
              {paper.venue ? ` · ${paper.venue}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <Badge variant="outline" className="text-[10px] h-5 px-1.5 gap-1 border-zinc-700 text-zinc-400">
              {sourceIcons[paper.source_type]}
              {paper.source_name}
            </Badge>
          </div>
        </div>

        {paper.summary ? (
          <p className="text-xs text-zinc-400 mt-2 line-clamp-2">{paper.summary}</p>
        ) : (
          <p className="text-xs text-zinc-500 mt-2 line-clamp-2 italic">Processing...</p>
        )}

        <div className="mt-3 space-y-1">
          <ScoreBar label="Originality" score={paper.originality_score} />
          <ScoreBar label="Impact" score={paper.impact_score} />
        </div>

        <div className="flex items-center gap-3 mt-3">
          {paper.url && (
            <a href={paper.url} target="_blank" rel="noopener noreferrer"
               className="text-xs text-zinc-500 hover:text-zinc-300 flex items-center gap-1">
              <ExternalLink className="h-3 w-3" /> Source
            </a>
          )}
          {paper.pdf_url && (
            <a href={paper.pdf_url} target="_blank" rel="noopener noreferrer"
               className="text-xs text-zinc-500 hover:text-zinc-300 flex items-center gap-1">
              <FileText className="h-3 w-3" /> PDF
            </a>
          )}
          <span className="text-[10px] text-zinc-600 ml-auto">
            {paper.published_date ? new Date(paper.published_date).toLocaleDateString() : ""}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
```

**Step 2: Create search bar**

```tsx
// src/components/search-bar.tsx
"use client";

import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

export function SearchBar() {
  const router = useRouter();
  const [q, setQ] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (q.trim()) {
      router.push(`/search?q=${encodeURIComponent(q.trim())}`);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search papers, blogs, projects..."
        className="pl-9 bg-zinc-900 border-zinc-800 text-sm h-9"
      />
    </form>
  );
}
```

**Step 3: Create Browse page**

```tsx
// src/app/page.tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { listPapers, searchPapers } from "@/lib/api";
import { Paper, PaperListResponse } from "@/lib/types";
import { PaperCard } from "@/components/paper-card";
import { SearchBar } from "@/components/search-bar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowUpDown, ArrowDown, ArrowUp, Loader2 } from "lucide-react";

const SORT_OPTIONS = [
  { value: "impact_score", label: "Impact" },
  { value: "originality_score", label: "Originality" },
  { value: "published_date", label: "Date" },
];

const TYPE_FILTERS = [
  { value: "", label: "All" },
  { value: "paper", label: "Papers" },
  { value: "blog", label: "Blogs" },
  { value: "project", label: "Projects" },
  { value: "talk", label: "Talks" },
];

export default function BrowsePage({ searchParams }: { searchParams?: { q?: string } }) {
  const [data, setData] = useState<PaperListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("impact_score");
  const [sortDir, setSortDir] = useState("desc");
  const [typeFilter, setTypeFilter] = useState("");

  const query = searchParams?.q;

  const fetchPapers = useCallback(async () => {
    setLoading(true);
    try {
      let res: PaperListResponse;
      if (query) {
        res = await searchPapers(query, { page, sort_by: sortBy, sort_dir: sortDir });
      } else {
        res = await listPapers({
          page,
          source_type: typeFilter || undefined,
          sort_by: sortBy,
          sort_dir: sortDir,
        });
      }
      setData(res);
    } catch (e) {
      console.error("Failed to fetch papers:", e);
    } finally {
      setLoading(false);
    }
  }, [page, sortBy, sortDir, typeFilter, query]);

  useEffect(() => { fetchPapers(); }, [fetchPapers]);

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="space-y-4 mb-6">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold">
            {query ? `Search: "${query}"` : "Browse"}
          </h1>
          {data && (
            <span className="text-sm text-zinc-500">{data.total} items</span>
          )}
        </div>

        <SearchBar />

        <div className="flex items-center gap-3 flex-wrap">
          {/* Source type filter */}
          <div className="flex gap-1">
            {TYPE_FILTERS.map((f) => (
              <Badge
                key={f.value}
                variant={typeFilter === f.value ? "default" : "outline"}
                className="cursor-pointer text-xs"
                onClick={() => { setTypeFilter(f.value); setPage(1); }}
              >
                {f.label}
              </Badge>
            ))}
          </div>

          <div className="h-4 w-px bg-zinc-800" />

          {/* Sort */}
          <div className="flex items-center gap-2 text-xs text-zinc-400">
            <span>Sort:</span>
            {SORT_OPTIONS.map((opt) => (
              <Button
                key={opt.value}
                variant={sortBy === opt.value ? "secondary" : "ghost"}
                size="sm"
                className="h-7 text-xs px-2"
                onClick={() => {
                  if (sortBy === opt.value) {
                    setSortDir((d) => (d === "desc" ? "asc" : "desc"));
                  } else {
                    setSortBy(opt.value);
                    setSortDir("desc");
                  }
                  setPage(1);
                }}
              >
                {opt.label}
                {sortBy === opt.value && (
                  sortDir === "desc" ? <ArrowDown className="ml-1 h-3 w-3" /> : <ArrowUp className="ml-1 h-3 w-3" />
                )}
              </Button>
            ))}
          </div>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full bg-zinc-900" />
          ))}
        </div>
      )}

      {/* Paper list */}
      {!loading && data && (
        <>
          <div className="space-y-3">
            {data.papers.map((paper) => (
              <PaperCard key={paper.id} paper={paper} />
            ))}
          </div>

          {/* Pagination */}
          {data.total > data.page_size && (
            <div className="flex items-center justify-center gap-2 mt-6">
              <Button
                variant="outline" size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-zinc-400">
                Page {data.page} of {Math.ceil(data.total / data.page_size)}
              </span>
              <Button
                variant="outline" size="sm"
                disabled={page >= Math.ceil(data.total / data.page_size)}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}

      {!loading && data?.papers.length === 0 && (
        <div className="text-center py-16 text-zinc-500">
          <p className="text-lg mb-2">No papers found</p>
          <p className="text-sm">Try adjusting your filters or run the ingestion pipeline first.</p>
        </div>
      )}
    </div>
  );
}
```

---

### Task 16: Create Paper detail page

**Objective:** Full paper view with summary, scores, and links to original.

**Files:**
- Create: `~/gpgpu-kb/frontend/src/app/paper/[id]/page.tsx`

```tsx
// src/app/paper/[id]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getPaper } from "@/lib/api";
import { Paper } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ExternalLink, FileText, Calendar, Users, Building2, Tag, Trophy } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";

function ScoreCircle({ value, label, color }: { value: number; label: string; color: string }) {
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 10) * circumference;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r={radius} fill="none" stroke="rgb(39,39,42)" strokeWidth="5" />
        <circle
          cx="36" cy="36" r={radius} fill="none" stroke={color} strokeWidth="5"
          strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset}
          transform="rotate(-90 36 36)" className="transition-all duration-700"
        />
        <text x="36" y="36" textAnchor="middle" dy="6" className="text-sm font-bold fill-zinc-100">
          {value.toFixed(1)}
        </text>
      </svg>
      <span className="text-[10px] text-zinc-500">{label}</span>
    </div>
  );
}

export default function PaperDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [paper, setPaper] = useState<Paper | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    getPaper(Number(id)).then(setPaper).finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-4">
        <Skeleton className="h-8 w-3/4 bg-zinc-900" />
        <Skeleton className="h-4 w-1/2 bg-zinc-900" />
        <Skeleton className="h-64 w-full bg-zinc-900" />
      </div>
    );
  }

  if (!paper) {
    return (
      <div className="max-w-3xl mx-auto p-6 text-center py-16">
        <p className="text-zinc-500">Paper not found.</p>
        <Link href="/" className="text-sm text-emerald-400 hover:underline mt-2 inline-block">
          Back to browse
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <Link href="/" className="text-xs text-zinc-500 hover:text-zinc-300 mb-4 inline-block">
        ← Back to browse
      </Link>

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-start justify-between gap-4">
          <h1 className="text-xl font-semibold leading-snug">{paper.title}</h1>
          <Badge variant="outline" className="shrink-0 border-zinc-700 text-zinc-400 text-xs">
            {paper.source_type}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-3 text-sm text-zinc-400">
          {paper.authors.length > 0 && (
            <span className="flex items-center gap-1.5">
              <Users className="h-3.5 w-3.5" />
              {paper.authors.slice(0, 4).join(", ")}
              {paper.authors.length > 4 ? ` +${paper.authors.length - 4}` : ""}
            </span>
          )}
          {paper.organizations.length > 0 && (
            <span className="flex items-center gap-1.5">
              <Building2 className="h-3.5 w-3.5" />
              {paper.organizations.join(", ")}
            </span>
          )}
          {paper.published_date && (
            <span className="flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5" />
              {new Date(paper.published_date).toLocaleDateString()}
            </span>
          )}
          {paper.venue && (
            <span className="flex items-center gap-1.5 text-emerald-400">
              <Trophy className="h-3.5 w-3.5" />
              {paper.venue}
            </span>
          )}
        </div>

        {/* Links */}
        <div className="flex items-center gap-4 mt-3">
          {paper.url && (
            <a href={paper.url} target="_blank" rel="noopener noreferrer"
               className="text-sm text-emerald-400 hover:underline flex items-center gap-1">
              <ExternalLink className="h-3.5 w-3.5" /> Open source
            </a>
          )}
          {paper.pdf_url && (
            <a href={paper.pdf_url} target="_blank" rel="noopener noreferrer"
               className="text-sm text-emerald-400 hover:underline flex items-center gap-1">
              <FileText className="h-3.5 w-3.5" /> PDF
            </a>
          )}
        </div>

        {/* Categories */}
        {paper.categories.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {paper.categories.map((cat, i) => (
              <Badge key={i} variant="secondary" className="text-[10px] bg-zinc-800 text-zinc-400">
                <Tag className="h-3 w-3 mr-1" /> {cat}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Scores */}
      <Card className="bg-zinc-900 border-zinc-800 mb-6">
        <CardContent className="p-4">
          <div className="flex items-center justify-center gap-12">
            <ScoreCircle value={paper.originality_score} label="Originality" color="#10b981" />
            <ScoreCircle value={paper.impact_score} label="Impact" color="#3b82f6" />
          </div>
          {paper.impact_rationale && (
            <p className="text-sm text-zinc-400 mt-4 text-center italic">{paper.impact_rationale}</p>
          )}
        </CardContent>
      </Card>

      {/* Summary */}
      {paper.summary ? (
        <Card className="bg-zinc-900 border-zinc-800 mb-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="prose prose-invert prose-sm max-w-none text-zinc-300">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {paper.summary}
              </ReactMarkdown>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="bg-zinc-900 border-zinc-800 mb-6">
          <CardContent className="p-6 text-center text-zinc-500">
            <p>This paper is still being processed. Summary coming soon.</p>
          </CardContent>
        </Card>
      )}

      {/* Abstract */}
      {paper.abstract && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Original Abstract</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-zinc-400 leading-relaxed">{paper.abstract}</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
```

---

### Task 17: Create Chat (RAG) page

**Objective:** Chat interface that queries the knowledge base via RAG.

**Files:**
- Create: `~/gpgpu-kb/frontend/src/app/chat/page.tsx`

```tsx
// src/app/chat/page.tsx
"use client";

import { useState, useRef, useEffect } from "react";
import { chat } from "@/lib/api";
import { Paper } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Send, Cpu, User, FileText, Loader2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Paper[];
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "👋 I'm your GPGPU research assistant. Ask me anything about papers, architectures, optimizations, or trends in the knowledge base. I'll search the most relevant papers and answer based on the latest research.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const query = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: query }]);
    setLoading(true);

    try {
      const res = await chat({ query, top_k: 5 });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, sources: res.sources },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, I couldn't process that query. Is the backend running?" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto">
      {/* Messages */}
      <ScrollArea className="flex-1 px-6">
        <div className="space-y-4 py-4">
          {messages.map((msg, i) => (
            <div key={i} className="flex gap-3">
              <div className="shrink-0 mt-1">
                {msg.role === "assistant" ? (
                  <Cpu className="h-5 w-5 text-emerald-400" />
                ) : (
                  <User className="h-5 w-5 text-blue-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium text-zinc-400 mb-1">
                  {msg.role === "assistant" ? "Assistant" : "You"}
                </div>
                <div className="prose prose-invert prose-sm max-w-none text-zinc-300">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-zinc-800">
                    <p className="text-xs text-zinc-500 mb-2">Sources:</p>
                    <div className="flex flex-wrap gap-2">
                      {msg.sources.map((s) => (
                        <Link key={s.id} href={`/paper/${s.id}`}>
                          <Badge variant="outline" className="cursor-pointer hover:bg-zinc-800 text-xs border-zinc-700 text-zinc-400">
                            <FileText className="h-3 w-3 mr-1" />
                            {s.title.slice(0, 60)}{s.title.length > 60 ? "..." : ""}
                          </Badge>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex gap-3">
              <Loader2 className="h-5 w-5 text-emerald-400 animate-spin shrink-0 mt-1" />
              <div className="text-sm text-zinc-500">Searching knowledge base...</div>
            </div>
          )}
          <div ref={scrollRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t border-zinc-800 p-4">
        <form
          onSubmit={(e) => { e.preventDefault(); handleSend(); }}
          className="flex items-center gap-2"
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about GPU architectures, attention mechanisms, LLM training..."
            className="flex-1 bg-zinc-900 border-zinc-800 text-sm"
            disabled={loading}
          />
          <Button type="submit" size="icon" disabled={loading || !input.trim()}
                  className="bg-emerald-600 hover:bg-emerald-700">
            <Send className="h-4 w-4" />
          </Button>
        </form>
        <p className="text-[10px] text-zinc-600 mt-2">
          Answers are based on papers in the knowledge base. Results may vary by processing state.
        </p>
      </div>
    </div>
  );
}
```

---

### Task 18: Create Daily Reports page

**Objective:** List and view daily reports.

**Files:**
- Create: `~/gpgpu-kb/frontend/src/app/reports/page.tsx`
- Create: `~/gpgpu-kb/frontend/src/app/reports/[id]/page.tsx`

```tsx
// src/app/reports/page.tsx
"use client";

import { useEffect, useState } from "react";
import { listReports } from "@/lib/api";
import { DailyReport } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Calendar } from "lucide-react";
import Link from "next/link";

export default function ReportsPage() {
  const [reports, setReports] = useState<DailyReport[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listReports(30).then(setReports).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full bg-zinc-900" />
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-lg font-semibold mb-4">Daily Reports</h1>
      <div className="space-y-3">
        {reports.map((report) => (
          <Link key={report.id} href={`/reports/${report.id}`}>
            <Card className="bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors cursor-pointer">
              <CardContent className="p-4">
                <div className="flex items-center gap-3">
                  <Calendar className="h-4 w-4 text-emerald-400 shrink-0" />
                  <div>
                    <h3 className="text-sm font-medium">{report.title}</h3>
                    <p className="text-xs text-zinc-500 mt-0.5">
                      {new Date(report.date).toLocaleDateString("en-US", {
                        weekday: "long", year: "numeric", month: "long", day: "numeric",
                      })}
                      {" · "}
                      {report.paper_ids.length} papers covered
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
        {reports.length === 0 && (
          <p className="text-zinc-500 text-center py-12">No reports generated yet.</p>
        )}
      </div>
    </div>
  );
}
```

```tsx
// src/app/reports/[id]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getReport } from "@/lib/api";
import { DailyReport } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Calendar } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<DailyReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    getReport(Number(id)).then(setReport).finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-4">
        <Skeleton className="h-8 w-3/4 bg-zinc-900" />
        <Skeleton className="h-96 w-full bg-zinc-900" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="max-w-3xl mx-auto p-6 text-center py-16 text-zinc-500">
        <p>Report not found.</p>
        <Link href="/reports" className="text-sm text-emerald-400 hover:underline mt-2 inline-block">
          Back to reports
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6">
      <Link href="/reports" className="text-xs text-zinc-500 hover:text-zinc-300 mb-4 inline-block">
        ← Back to reports
      </Link>
      <div className="flex items-center gap-3 mb-6">
        <Calendar className="h-5 w-5 text-emerald-400" />
        <div>
          <h1 className="text-lg font-semibold">{report.title}</h1>
          <p className="text-sm text-zinc-500">
            {new Date(report.date).toLocaleDateString("en-US", {
              weekday: "long", year: "numeric", month: "long", day: "numeric",
            })}
          </p>
        </div>
      </div>
      <Card className="bg-zinc-900 border-zinc-800">
        <CardContent className="p-6">
          <div className="prose prose-invert prose-sm max-w-none text-zinc-300">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {report.content}
            </ReactMarkdown>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

---

### Task 19: Create Stats page

**Objective:** Dashboard showing KB statistics.

**Files:**
- Create: `~/gpgpu-kb/frontend/src/app/stats/page.tsx`

```tsx
// src/app/stats/page.tsx
"use client";

import { useEffect, useState } from "react";
import { getStats } from "@/lib/api";
import { Stats } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { BookOpen, CheckCircle, Cpu, Star } from "lucide-react";
import Link from "next/link";

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStats().then(setStats).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto p-6 space-y-4">
        <Skeleton className="h-32 w-full bg-zinc-900" />
        <Skeleton className="h-48 w-full bg-zinc-900" />
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-lg font-semibold mb-4">Knowledge Base Stats</h1>

      {/* Overview cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="p-4 text-center">
            <BookOpen className="h-5 w-5 text-zinc-500 mx-auto mb-1" />
            <div className="text-2xl font-bold">{stats.total_papers}</div>
            <div className="text-xs text-zinc-500">Total Items</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="p-4 text-center">
            <CheckCircle className="h-5 w-5 text-emerald-400 mx-auto mb-1" />
            <div className="text-2xl font-bold">{stats.processed}</div>
            <div className="text-xs text-zinc-500">Processed</div>
          </CardContent>
        </Card>
        {Object.entries(stats.by_type).map(([type, count]) => (
          <Card key={type} className="bg-zinc-900 border-zinc-800">
            <CardContent className="p-4 text-center">
              <Cpu className="h-5 w-5 text-zinc-500 mx-auto mb-1" />
              <div className="text-2xl font-bold">{count}</div>
              <div className="text-xs text-zinc-500 capitalize">{type}s</div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Top impact */}
      <Card className="bg-zinc-900 border-zinc-800 mb-6">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Star className="h-4 w-4 text-amber-400" />
            Highest Impact Papers
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {stats.top_impact.map((p) => (
              <Link key={p.id} href={`/paper/${p.id}`}>
                <div className="flex items-center justify-between text-sm hover:text-emerald-400 transition-colors">
                  <span className="truncate flex-1">{p.title}</span>
                  <Badge className="ml-2 shrink-0 bg-emerald-900 text-emerald-300 text-xs">
                    {p.impact_score.toFixed(1)}
                  </Badge>
                </div>
              </Link>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// Need to import Badge (add to stats page)
import { Badge } from "@/components/ui/badge";
```

---

## Phase 7: Daily Reports & Cron Integration

### Task 20: Create daily report generator

**Objective:** Script that generates a daily report from new papers.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/reports.py`

```python
# kb/reports.py
"""Generate a daily research report."""
import datetime
from kb.database import SessionLocal
from kb.models import Paper, DailyReport
from kb.processing.llm import _call_llm


def generate_daily_report(date: datetime.date | None = None) -> DailyReport:
    """Generate a report for the given date (default: yesterday)."""
    if date is None:
        date = datetime.date.today() - datetime.timedelta(days=1)

    start = datetime.datetime.combine(date, datetime.time.min)
    end = datetime.datetime.combine(date, datetime.time.max)

    db = SessionLocal()

    # Get papers from that day
    papers = db.query(Paper).filter(
        Paper.ingested_date >= start,
        Paper.ingested_date <= end,
        Paper.is_processed == 1,
    ).order_by(Paper.impact_score.desc()).all()

    if not papers:
        # Check for any recent papers if none from that exact day
        papers = db.query(Paper).filter(
            Paper.is_processed == 1,
        ).order_by(Paper.ingested_date.desc()).limit(20).all()

    if not papers:
        report = DailyReport(
            date=date,
            title=f"Daily Research Report — {date.isoformat()}",
            content=f"No new papers were ingested on {date.isoformat()}. Check the ingestion pipeline.",
            paper_ids=[],
        )
        db.add(report)
        db.commit()
        db.close()
        return report

    # Build a summary of top papers for the LLM
    paper_summaries = []
    for p in papers[:15]:  # Top 15
        paper_summaries.append(
            f"### {p.title}\n"
            f"*Authors:* {', '.join(p.authors[:5])}\n"
            f"*Type:* {p.source_type} | *Source:* {p.source_name}\n"
            f"*Originality:* {p.originality_score:.1f}/10 | *Impact:* {p.impact_score:.1f}/10\n"
            f"*Summary:* {p.summary[:500]}\n"
        )

    context = "\n\n".join(paper_summaries)

    prompt = f"""You are an expert GPGPU chip architect writing a daily research briefing.

DATE: {date.isoformat()}

Below are the top papers and articles from today. Write a comprehensive daily report in Markdown format with the following sections:

1. **Executive Summary** — 2-3 sentences on the most important developments
2. **Top Papers** — The 3-5 most impactful papers with 2-3 sentence descriptions each
3. **Key Themes** — What patterns or trends do you see across today's research?
4. **Hidden Gems** — 1-2 papers that scored lower on impact but are actually quite interesting or original
5. **Recommended Reading** — Which 2-3 papers should be read in full today?

PAPERS:
{context}

Write a professional, technical report. No fluff. Keep it concise but informative."""

    content = _call_llm(prompt)

    report = DailyReport(
        date=date,
        title=f"Daily Research Report — {date.isoformat()}",
        content=content,
        paper_ids=[p.id for p in papers[:15]],
    )
    db.add(report)
    db.commit()
    db.close()

    print(f"[reports] Generated report for {date.isoformat()}: {len(papers)} papers covered.")
    return report


if __name__ == "__main__":
    generate_daily_report()
```

---

### Task 21: Create daily pipeline runner

**Objective:** Single script that runs ingestion → processing → report.

**Files:**
- Create: `~/gpgpu-kb/backend/kb/daily.py`

```python
#!/usr/bin/env python3
# kb/daily.py — Full daily pipeline
"""Run the complete daily pipeline: ingest → process → embed → report."""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb.ingestion.run import run_ingestion
from kb.processing.llm import run_processing
from kb.processing.embeddings import index_unindexed_papers
from kb.reports import generate_daily_report


def run_daily_pipeline():
    print("=" * 60)
    print("  GPGPU Knowledge Base — Daily Pipeline")
    print("=" * 60)

    # Step 1: Ingest
    print("\n[1/4] INGESTION")
    results = run_ingestion(days_back=1)

    # Step 2: Process
    print("\n[2/4] PROCESSING (Summarization + Scoring)")
    processed = run_processing(batch_size=30)

    # Step 3: Embed
    print("\n[3/4] EMBEDDING")
    indexed = index_unindexed_papers(batch_size=100)

    # Step 4: Report
    print("\n[4/4] DAILY REPORT")
    generate_daily_report()

    print("\n" + "=" * 60)
    print("  Pipeline complete!")
    print(f"  New items: {sum(results.values())}")
    print(f"  Processed: {processed}")
    print(f"  Indexed: {indexed}")
    print("=" * 60)


if __name__ == "__main__":
    run_daily_pipeline()
```

Make executable: `chmod +x ~/gpgpu-kb/backend/kb/daily.py`

---

### Task 22: Set up Hermes cron job for daily pipeline

**Objective:** Schedule the daily pipeline to run automatically.

Run via Hermes:
```
/cron create --name "GPGPU KB Daily Pipeline" \
  --schedule "0 7 * * *" \
  --workdir ~/gpgpu-kb/backend \
  --prompt "Run the daily knowledge base pipeline: cd ~/gpgpu-kb/backend && python -m kb.daily"
```

---

## Phase 8: Search Page & Polish

### Task 23: Create search results page

**Objective:** Dedicated search page that shows results and redirects from search bar.

**Files:**
- Create: `~/gpgpu-kb/frontend/src/app/search/page.tsx`

This is already mostly handled by the Browse page accepting `searchParams.q`. Create a simple wrapper:

```tsx
// src/app/search/page.tsx
import BrowsePage from "@/app/page";

export default function SearchPage({ searchParams }: { searchParams?: { q?: string } }) {
  return <BrowsePage searchParams={searchParams} />;
}
```

---

### Task 24: Create startup convenience script

**Objective:** One script to start both backend and frontend.

**Files:**
- Create: `~/gpgpu-kb/start.sh`

```bash
#!/bin/bash
# start.sh — Start both backend and frontend
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Starting GPGPU Knowledge Base ==="

# Start backend
echo "[backend] Starting FastAPI on port 8000..."
cd "$SCRIPT_DIR/backend"
mkdir -p data
uvicorn kb.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend (dev mode)
echo "[frontend] Starting Next.js on port 3000..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000 (API docs: http://localhost:8000/docs)"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
```

Make executable: `chmod +x ~/gpgpu-kb/start.sh`

---

## Phase 9: Seed & Verify

### Task 25: Run first ingestion to seed the KB

**Objective:** Run the ingestion pipeline once to get initial content.

Run: `cd ~/gpgpu-kb/backend && python -m kb.daily`

Expected: Papers fetched from ArXiv, RSS feeds, and GitHub. Database populated.

### Task 26: Verify end-to-end

**Objective:** Confirm everything works together.

1. Start the backend: `cd ~/gpgpu-kb/backend && uvicorn kb.main:app --port 8000`
2. Start the frontend: `cd ~/gpgpu-kb/frontend && npm run dev`
3. Open http://localhost:3000
4. Verify: Browse shows papers, detail pages work, chat returns RAG responses, stats page shows data
5. Verify daily report was generated and appears on Reports page

---

## Summary

| Phase | Tasks | What it delivers |
|-------|-------|-----------------|
| 1. Scaffolding | 1-2 | Project structure, deps installed |
| 2. Data Models | 3-4 | SQLite DB, Pydantic schemas |
| 3. Ingestion | 5-8 | ArXiv, RSS, GitHub scrapers |
| 4. Processing | 9-10 | LLM summary + scoring + embeddings |
| 5. Backend API | 11-12 | FastAPI with /papers, /chat, /reports, /stats |
| 6. Frontend | 13-19 | Next.js UI with browse, detail, chat, reports, stats |
| 7. Daily Reports | 20-22 | Report generator + cron schedule |
| 8. Polish | 23-24 | Search page, startup script |
| 9. Verify | 25-26 | Seed data, end-to-end testing |
