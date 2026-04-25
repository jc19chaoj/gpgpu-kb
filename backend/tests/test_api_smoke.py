# backend/tests/test_api_smoke.py
"""Smoke tests for the public API.

The `client` fixture comes from conftest.py, which sets up an isolated
SQLite database before any kb.* module is imported.
"""
from __future__ import annotations


def test_papers_list_returns_paginated(client):
    r = client.get("/api/papers")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"papers", "total", "page", "page_size"}
    assert isinstance(body["papers"], list)


def test_search_route_does_not_collide_with_paper_id(client):
    """Regression for audit issue #1: /api/papers/search must not be eaten by
    the /api/papers/{paper_id:int} route."""
    r = client.get("/api/papers/search", params={"q": "gpu"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "papers" in body


def test_get_nonexistent_paper_returns_404(client):
    r = client.get("/api/papers/999999")
    assert r.status_code == 404


def test_stats_shape(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"total_papers", "processed", "by_type", "top_impact"}


def test_chat_request_validation_rejects_huge_top_k(client):
    r = client.post("/api/chat", json={"query": "hi", "top_k": 999})
    assert r.status_code == 422  # Pydantic rejects ge/le violations


def test_chat_request_validation_rejects_empty_query(client):
    r = client.post("/api/chat", json={"query": "", "top_k": 5})
    assert r.status_code == 422


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
