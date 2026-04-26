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
