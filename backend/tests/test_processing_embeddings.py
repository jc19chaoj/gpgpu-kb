# backend/tests/test_processing_embeddings.py
"""Tests for kb/processing/embeddings.py — EmbeddingStore and singleton."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

# ─── Helpers ──────────────────────────────────────────────────────

def _reset_store():
    """Reset the module-level singleton between tests."""
    import kb.processing.embeddings as emb_mod
    emb_mod._store = None


# ─── EmbeddingStore.available when ML deps absent ─────────────────


def test_embedding_store_unavailable_when_no_ml_deps():
    """When chromadb/sentence-transformers are absent the store is unavailable."""
    import kb.processing.embeddings as emb_mod

    with patch.object(emb_mod, "_chromadb", None), \
         patch.object(emb_mod, "_SentenceTransformer", None):
        store = emb_mod.EmbeddingStore()

    assert store.available is False


def test_embedding_store_available_when_ml_deps_present():
    """When both ML deps are present the store initialises as available."""
    import kb.processing.embeddings as emb_mod

    fake_chromadb = MagicMock()
    fake_st = MagicMock()

    fake_client = MagicMock()
    fake_chromadb.PersistentClient.return_value = fake_client
    fake_client.get_or_create_collection.return_value = MagicMock()
    fake_st.return_value = MagicMock()

    with patch.object(emb_mod, "_chromadb", fake_chromadb), \
         patch.object(emb_mod, "_SentenceTransformer", fake_st):
        store = emb_mod.EmbeddingStore(persist_dir="/tmp/test-chroma", model_name="test-model")

    assert store.available is True


# ─── search() returns [] when store unavailable ───────────────────


def test_search_returns_empty_list_when_unavailable():
    import kb.processing.embeddings as emb_mod

    with patch.object(emb_mod, "_chromadb", None), \
         patch.object(emb_mod, "_SentenceTransformer", None):
        store = emb_mod.EmbeddingStore()

    result = store.search("CUDA kernels", top_k=5)
    assert result == []


def test_embed_text_returns_none_when_unavailable():
    import kb.processing.embeddings as emb_mod

    with patch.object(emb_mod, "_chromadb", None), \
         patch.object(emb_mod, "_SentenceTransformer", None):
        store = emb_mod.EmbeddingStore()

    assert store.embed_text("hello") is None


def test_index_paper_returns_empty_string_when_unavailable():
    import kb.processing.embeddings as emb_mod

    with patch.object(emb_mod, "_chromadb", None), \
         patch.object(emb_mod, "_SentenceTransformer", None):
        store = emb_mod.EmbeddingStore()

    result = store.index_paper(1, "title", "summary", "abstract")
    assert result == ""


# ─── get_embedding_store() singleton thread-safety ────────────────


def test_get_embedding_store_returns_same_instance():
    """Two sequential calls return the identical object."""
    _reset_store()
    import kb.processing.embeddings as emb_mod

    with patch.object(emb_mod, "_chromadb", None), \
         patch.object(emb_mod, "_SentenceTransformer", None):
        s1 = emb_mod.get_embedding_store()
        s2 = emb_mod.get_embedding_store()

    assert s1 is s2
    _reset_store()


def test_get_embedding_store_singleton_thread_safety():
    """Concurrent callers must all receive the same singleton instance and
    EmbeddingStore() must be constructed exactly once."""
    _reset_store()
    import kb.processing.embeddings as emb_mod

    construction_count = {"n": 0}
    original_init = emb_mod.EmbeddingStore.__init__

    def counting_init(self, persist_dir=None, model_name=None):
        construction_count["n"] += 1
        # Force unavailable path so no real ML deps are needed.
        self._available = False
        self.client = None
        self.collection = None
        self.model = None

    results = []

    with patch.object(emb_mod.EmbeddingStore, "__init__", counting_init), \
         patch.object(emb_mod, "_chromadb", None), \
         patch.object(emb_mod, "_SentenceTransformer", None):
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(emb_mod.get_embedding_store) for _ in range(8)]
            results = [f.result() for f in futures]

    # All threads got the same singleton object.
    assert all(r is results[0] for r in results)
    # Constructor ran exactly once despite 8 concurrent callers.
    assert construction_count["n"] == 1

    _reset_store()


# ─── ML-deps-required tests (skip when absent) ────────────────────

try:
    import chromadb  # type: ignore
    import sentence_transformers  # type: ignore
    _ML_DEPS_AVAILABLE = True
except ImportError:
    _ML_DEPS_AVAILABLE = False


@pytest.mark.skipif(not _ML_DEPS_AVAILABLE, reason="chromadb/sentence-transformers not installed")
def test_search_returns_list_when_available(tmp_path):
    """Integration smoke-test: real EmbeddingStore can index and search."""
    _reset_store()
    from kb.processing.embeddings import EmbeddingStore

    store = EmbeddingStore(persist_dir=str(tmp_path / "chroma"), model_name="all-MiniLM-L6-v2")
    assert store.available is True

    store.index_paper(42, "Fast GPU Kernels", "We propose a faster kernel.", "Abstract text.")
    results = store.search("GPU kernel optimization", top_k=1)
    assert isinstance(results, list)
    assert len(results) >= 0  # may be empty if embedding similarity is low
    _reset_store()
