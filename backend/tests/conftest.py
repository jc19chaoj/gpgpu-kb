# backend/tests/conftest.py
"""Test fixtures.

Sets up an isolated SQLite database BEFORE any kb.* module is imported,
so Settings, the engine, and the declarative Base all see the test config
on first import. Avoids importlib.reload races that break the SQLAlchemy
class registry.
"""
from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="gpgpu-kb-test-")
os.environ.setdefault("KB_DATABASE_URL", f"sqlite:///{_TMP_DIR}/kb.sqlite")
os.environ.setdefault("KB_DATA_DIR", _TMP_DIR)
# Force the local hermes-shaped provider; tests don't issue real LLM calls.
os.environ.setdefault("KB_LLM_PROVIDER", "hermes")


@pytest.fixture(scope="session", autouse=True)
def _init_db() -> None:
    from kb.database import init_db
    init_db()


@pytest.fixture(scope="session")
def client() -> Iterator:
    from fastapi.testclient import TestClient
    from kb.main import app

    with TestClient(app) as c:
        yield c
