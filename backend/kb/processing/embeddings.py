# kb/processing/embeddings.py
"""Generate embeddings and store in ChromaDB for semantic search and RAG.

Heavy dependencies (chromadb, sentence-transformers) are optional.
Install with: pip install -e '.[ml]'
Without them, semantic search falls back to keyword search.
"""

import logging
import threading
import uuid

from kb.config import settings
from kb.database import SessionLocal
from kb.models import Paper

logger = logging.getLogger(__name__)

# Lazy imports for heavy ML deps
_chromadb = None
_SentenceTransformer = None

try:
    import chromadb as _chromadb  # type: ignore
except ImportError:
    pass

try:
    from sentence_transformers import SentenceTransformer as _SentenceTransformer  # type: ignore
except ImportError:
    pass


class EmbeddingStore:
    """Vector embedding store for semantic search.
    Falls back to a no-op stub if ML deps aren't installed.
    """

    def __init__(self, persist_dir: str | None = None, model_name: str | None = None):
        if _chromadb is None or _SentenceTransformer is None:
            self._available = False
            self.client = None
            self.collection = None
            self.model = None
            return

        self._available = True
        self.client = _chromadb.PersistentClient(path=persist_dir or settings.chroma_dir)
        self.collection = self.client.get_or_create_collection(
            name="papers",
            metadata={"hnsw:space": "cosine"},
        )
        self.model = _SentenceTransformer(model_name or settings.embedding_model)

    @property
    def available(self) -> bool:
        return self._available

    def embed_text(self, text: str) -> list[float] | None:
        if not self._available:
            return None
        return self.model.encode(text).tolist()

    def index_paper(self, paper_id: int, title: str, summary: str, abstract: str) -> str:
        """Index a paper in ChromaDB. Returns chroma_id or empty string if unavailable."""
        if not self._available:
            return ""
        text = f"Title: {title}\n\nAbstract: {abstract}\n\nSummary: {summary}"
        embedding = self.embed_text(text)
        chroma_id = str(uuid.uuid4())
        self.collection.add(
            ids=[chroma_id],
            embeddings=[embedding],
            metadatas=[{"paper_id": paper_id, "title": title[:500]}],
            documents=[text[:5000]],
        )
        return chroma_id

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Semantic search. Returns [{paper_id, title, score}, ...] or empty list."""
        if not self._available:
            return []
        query_embedding = self.embed_text(query)
        if query_embedding is None:
            return []
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
                    "score": 1.0 - dist,
                })
        return out


def index_unindexed_papers(batch_size: int = 50) -> int:
    """Find papers without embeddings and index them. Returns count."""
    store = get_embedding_store()
    if not store.available:
        logger.info("ML deps not installed — skipping indexing")
        return 0

    db = SessionLocal()
    try:
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
            except Exception:
                logger.exception("Failed to index paper %d", paper.id)

        db.commit()
        logger.info("Indexed %d papers", count)
        return count
    finally:
        db.close()


# ─── Thread-safe singleton ────────────────────────────────────────
_store: EmbeddingStore | None = None
_store_lock = threading.Lock()


def get_embedding_store() -> EmbeddingStore:
    """Return the process-wide embedding store, initialising lazily under a lock.

    The first call may be slow (5-10s) because it loads the SentenceTransformer
    model. Subsequent calls are O(1). Concurrent first-callers won't race —
    only one initialisation happens.
    """
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is None:
            _store = EmbeddingStore()
        return _store
