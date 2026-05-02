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
    assert set(body) >= {
        "total_papers", "processed", "skipped_low_quality", "pending",
        "by_type", "top_impact",
    }


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


# ─── Chat auth (Step 0 of next-step plan) ─────────────────────────

def test_chat_open_when_token_unset(client):
    """Default behavior: /api/chat is reachable (validation may still 422)
    when KB_CHAT_TOKEN is unset. We assert it does NOT 401."""
    r = client.post("/api/chat", json={"query": "hi", "top_k": 1})
    assert r.status_code != 401, r.text


def test_chat_rejects_unauthenticated_when_token_set(client, monkeypatch):
    """When a chat token is configured, anonymous calls must be rejected."""
    from kb import config

    monkeypatch.setattr(config.settings, "chat_token", "s3cret-test-token")
    try:
        r = client.post("/api/chat", json={"query": "hi", "top_k": 1})
        assert r.status_code == 401, r.text

        r = client.post(
            "/api/chat",
            json={"query": "hi", "top_k": 1},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert r.status_code == 401, r.text

        # Correct token: must NOT be 401 (could be 200 or 5xx depending on LLM
        # availability, but never the auth layer's 401).
        r = client.post(
            "/api/chat",
            json={"query": "hi", "top_k": 1},
            headers={"Authorization": "Bearer s3cret-test-token"},
        )
        assert r.status_code != 401, r.text
    finally:
        monkeypatch.setattr(config.settings, "chat_token", None)


# ─── Quality gate (is_processed=2 hidden by default) ──────────────

def _seed_quality_papers(prefix: str) -> tuple[int, int, int]:
    """Insert one each of pending(0)/active(1)/low-quality(2) papers.

    Returns (pending_id, active_id, low_id). URLs are namespaced so multiple
    test runs on the shared session-scoped DB don't collide.
    """
    import datetime
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    db = SessionLocal()
    try:
        rows = []
        for i, state in enumerate([0, 1, 2]):
            p = Paper(
                title=f"qg-{prefix}-{state}",
                abstract="abs",
                summary="sum" if state else "",
                authors=["A"],
                organizations=[],
                source_type=SourceType.PAPER,
                source_name="arxiv",
                url=f"https://example.test/qg/{prefix}/{i}",
                published_date=datetime.datetime(2026, 4, 25, tzinfo=datetime.UTC),
                impact_score=8.0 if state == 1 else (3.0 if state == 2 else 0.0),
                originality_score=8.0 if state == 1 else (3.0 if state == 2 else 0.0),
                is_processed=state,
            )
            db.add(p)
            rows.append(p)
        db.commit()
        for p in rows:
            db.refresh(p)
        return rows[0].id, rows[1].id, rows[2].id
    finally:
        db.close()


def test_list_papers_default_hides_low_quality_and_pending(client):
    pending_id, active_id, low_id = _seed_quality_papers("list-default")

    r = client.get("/api/papers", params={"page_size": 100})
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["papers"]}

    assert active_id in ids
    assert low_id not in ids
    assert pending_id not in ids


def test_list_papers_include_low_quality_returns_all_states(client):
    pending_id, active_id, low_id = _seed_quality_papers("list-incl")

    r = client.get("/api/papers", params={"page_size": 100, "include_low_quality": "true"})
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["papers"]}

    assert {pending_id, active_id, low_id}.issubset(ids)


def test_get_paper_detail_works_for_low_quality(client):
    """Direct /api/papers/{id} must NOT filter — needed for inspecting
    why a particular paper was quarantined."""
    _, _, low_id = _seed_quality_papers("detail-low")

    r = client.get(f"/api/papers/{low_id}")
    assert r.status_code == 200
    assert r.json()["id"] == low_id


def test_search_keyword_default_hides_low_quality(client):
    _, active_id, low_id = _seed_quality_papers("search-kw")

    # semantic=false to force the keyword path; both rows match the prefix
    r = client.get(
        "/api/papers/search",
        params={"q": "qg-search-kw", "semantic": "false", "page_size": 100},
    )
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["papers"]}
    assert active_id in ids
    assert low_id not in ids


def test_search_keyword_include_low_quality(client):
    _, active_id, low_id = _seed_quality_papers("search-incl")

    r = client.get(
        "/api/papers/search",
        params={
            "q": "qg-search-incl",
            "semantic": "false",
            "include_low_quality": "true",
            "page_size": 100,
        },
    )
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["papers"]}
    assert {active_id, low_id}.issubset(ids)


def test_stats_counts_split_by_processing_state(client):
    pending_id, active_id, low_id = _seed_quality_papers("stats")

    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    # All counts are >= 1 because we just inserted one of each (other tests
    # may have inserted more, but the seeded rows guarantee a lower bound).
    assert body["processed"] >= 1
    assert body["skipped_low_quality"] >= 1
    assert body["pending"] >= 1


# ─── Search regressions ──────────────────────────────────────────

def _seed_paper(
    *,
    title: str,
    url: str,
    categories,
    is_processed: int = 1,
    impact: float = 8.0,
    originality: float = 8.0,
) -> int:
    import datetime
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    db = SessionLocal()
    try:
        p = Paper(
            title=title,
            abstract="abs",
            summary="sum",
            authors=["A"],
            organizations=[],
            source_type=SourceType.BLOG,
            source_name="rss",
            url=url,
            published_date=datetime.datetime(2026, 4, 25, tzinfo=datetime.UTC),
            categories=categories,
            impact_score=impact,
            originality_score=originality,
            is_processed=is_processed,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def test_search_keyword_returns_paper_with_string_categories(client):
    """Happy path: searched paper round-trips its string categories intact."""
    pid = _seed_paper(
        title="qg-search-strcats hbm reuse",
        url="https://example.test/qg/search-strcats/0",
        categories=["arch", "memory"],
    )
    r = client.get(
        "/api/papers/search",
        params={"q": "qg-search-strcats", "semantic": "false"},
    )
    assert r.status_code == 200, r.text
    by_id = {p["id"]: p for p in r.json()["papers"]}
    assert pid in by_id
    assert by_id[pid]["categories"] == ["arch", "memory"]


def test_search_handles_legacy_dict_categories(client):
    """Regression: legacy RSS rows stored categories as feedparser tag dicts
    (e.g. ``{'term': 'AI', 'scheme': '...', 'label': None}``). The search
    endpoint must coerce them to strings instead of 500-ing on PaperOut
    validation."""
    pid = _seed_paper(
        title="qg-search-dictcats marker",
        url="https://example.test/qg/search-dictcats/0",
        categories=[
            {"term": "Agentic AI", "scheme": "http://x", "label": None},
            {"term": "Top Stories", "scheme": "http://x", "label": None},
            {"label": "Fallback Label"},     # term missing; label fills in
            {"scheme": "http://x"},           # neither — must be dropped
            "plain-string-tag",
        ],
    )

    r = client.get(
        "/api/papers/search",
        params={"q": "qg-search-dictcats marker", "semantic": "false"},
    )
    assert r.status_code == 200, r.text
    by_id = {p["id"]: p for p in r.json()["papers"]}
    assert pid in by_id
    assert by_id[pid]["categories"] == [
        "Agentic AI",
        "Top Stories",
        "Fallback Label",
        "plain-string-tag",
    ]


def test_paper_detail_handles_legacy_dict_categories(client):
    """Same coercion must protect /api/papers/{id} so direct links don't 500
    on legacy RSS rows."""
    pid = _seed_paper(
        title="qg-detail-dictcats",
        url="https://example.test/qg/detail-dictcats/0",
        categories=[{"term": "Hardware", "scheme": "http://x", "label": None}],
    )

    r = client.get(f"/api/papers/{pid}")
    assert r.status_code == 200, r.text
    assert r.json()["categories"] == ["Hardware"]


def test_search_q_required(client):
    r = client.get("/api/papers/search")
    assert r.status_code == 422


def test_search_rejects_empty_q(client):
    r = client.get("/api/papers/search", params={"q": ""})
    assert r.status_code == 422


def test_search_keyword_escapes_like_wildcards(client):
    """A `%`/`_` in q must match literally, not as SQL LIKE wildcards.
    Seed a row whose title contains a literal `%`; a query containing the
    `%` must hit it, but a bare wildcard substring must NOT spuriously
    match unrelated rows."""
    pid = _seed_paper(
        title="qg-escape 50% throughput",
        url="https://example.test/qg/escape/0",
        categories=["perf"],
    )
    other = _seed_paper(
        title="qg-escape baseline",
        url="https://example.test/qg/escape/1",
        categories=["perf"],
    )

    # Literal `%` query: must match only the row containing `%`
    r = client.get(
        "/api/papers/search",
        params={"q": "50%", "semantic": "false", "page_size": 100},
    )
    assert r.status_code == 200, r.text
    ids = {p["id"] for p in r.json()["papers"]}
    assert pid in ids
    assert other not in ids


def test_search_pagination_caps_page_size(client):
    """page_size > 100 must be rejected by Query(le=100)."""
    r = client.get("/api/papers/search", params={"q": "gpu", "page_size": 999})
    assert r.status_code == 422


# ─── Universal score axes (sort + stats) ─────────────────────────

def test_papers_sort_by_quality_score(client):
    r = client.get("/api/papers", params={"sort_by": "quality_score"})
    assert r.status_code == 200, r.text


def test_papers_sort_by_relevance_score(client):
    r = client.get("/api/papers", params={"sort_by": "relevance_score"})
    assert r.status_code == 200, r.text


def test_papers_invalid_sort_by_rejected(client):
    r = client.get("/api/papers", params={"sort_by": "made_up_field"})
    assert r.status_code == 422


def test_stats_includes_top_overall(client):
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert "top_overall" in body
    assert isinstance(body["top_overall"], list)
    # Each entry has the universal-axis shape (when present).
    for entry in body["top_overall"]:
        assert {"id", "title", "source_type", "quality_score", "relevance_score"}.issubset(entry)
