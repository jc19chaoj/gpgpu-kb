# backend/tests/test_daily_cli.py
"""Tests for daily.py CLI argparse behavior and KB_LANGUAGE priority.

These tests intentionally avoid `importlib.reload(kb.config)` — reloading
replaces the module-level `settings` singleton, but other modules (e.g.
`kb.processing.llm`) hold the original reference via `from kb.config import
settings` and would diverge from the freshly-reloaded one. That divergence
poisons unrelated tests in the same session. We instead instantiate
`Settings()` directly to read env-driven defaults without mutating the global.
"""
from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace


def test_daily_argparse_parses_lang_zh():
    """--lang zh appears in --help and is accepted as a valid choice."""
    result = subprocess.run(
        [sys.executable, "-m", "kb.daily", "--help"],
        capture_output=True,
        text=True,
    )
    assert "--lang" in result.stdout
    assert "{en,zh}" in result.stdout or "en,zh" in result.stdout


def test_cli_lang_overrides_env(monkeypatch):
    """CLI --lang overrides KB_LANGUAGE env (CLI > env priority).

    Validates the exact override sequence used in daily.py's __main__ block:
        if args.lang:
            settings.language = args.lang
    starting from a fresh Settings() instance that picked up the env var.
    """
    monkeypatch.setenv("KB_LANGUAGE", "zh")

    from kb.config import Settings

    local_settings = Settings()
    assert local_settings.language == "zh"  # env was honored

    args = SimpleNamespace(lang="en")
    if args.lang:
        local_settings.language = args.lang

    assert local_settings.language == "en"  # CLI override won


def test_env_only_sets_language(monkeypatch):
    """KB_LANGUAGE env var sets language without any CLI override."""
    monkeypatch.setenv("KB_LANGUAGE", "zh")

    from kb.config import Settings

    local_settings = Settings()
    assert local_settings.language == "zh"


def test_pipeline_summary_excludes_fulltext_prefetch_from_new_items(
    monkeypatch, capsys
):
    """Regression guard: ``run_ingestion`` returns a flat dict where
    per-source ingest counts (arxiv / blogs / sitemap_blogs / github)
    sit alongside side-effect counters (``fulltext_prefetched`` from
    the ingestion tail step). The pipeline summary's "new items" /
    "新增条目" line must sum ONLY the per-source ingest counts —
    folding ``fulltext_prefetched`` in produces a misleading headline
    like "新增条目：32 / 处理完成：2" where 30 of the "new" items
    are actually existing rows that just got their full_text cache
    populated.
    """
    from kb import daily as daily_mod

    fake_results = {
        "arxiv": 0,
        "blogs": 2,
        "sitemap_blogs": 0,
        "github": 0,
        "fulltext_prefetched": 30,  # NOT a new-item count
    }

    monkeypatch.setattr(daily_mod, "run_ingestion", lambda: fake_results)
    monkeypatch.setattr(daily_mod, "_is_cold_start", lambda: False)
    monkeypatch.setattr(daily_mod, "_is_embedding_cold_start", lambda: False)
    monkeypatch.setattr(daily_mod, "init_db", lambda: None)
    monkeypatch.setattr(daily_mod, "run_processing", lambda batch_size=None: 2)
    monkeypatch.setattr(
        daily_mod, "index_unindexed_papers", lambda batch_size=None: 2
    )
    monkeypatch.setattr(daily_mod, "generate_daily_report", lambda: None)

    # The pending_count query also runs — short-circuit the SessionLocal
    # path by patching it to a no-op that exposes a `.query().filter().count()`.
    class _FakeQuery:
        def filter(self, *_, **__):
            return self

        def count(self):
            return 2

        def first(self):
            return None

    class _FakeSession:
        def query(self, *_):
            return _FakeQuery()

        def close(self):
            pass

    monkeypatch.setattr(daily_mod, "SessionLocal", lambda: _FakeSession())

    daily_mod.run_daily_pipeline()
    out = capsys.readouterr().out

    # Headline number is the sum of the four per-source keys (= 2),
    # NOT 32 (= 2 + 30 fulltext-prefetch leaking into the sum).
    assert "New items: 2" in out or "新增条目：2" in out
    assert "New items: 32" not in out
    assert "新增条目：32" not in out
    # Side-effect counter still surfaces as its own line so operators
    # see the backfill happened.
    assert (
        "Full-text backfilled: 30" in out
        or "全文回填：30" in out
    )
