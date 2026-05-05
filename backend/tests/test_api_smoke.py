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


# ─── Chat: source-anchored mode + history ─────────────────────────

def _seed_paper_for_chat(prefix: str, *, pdf_url: str = "", full_text: str = "") -> int:
    """Insert one paper for chat-mode tests. Caller controls full_text so
    we can avoid network calls in tests."""
    import datetime
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    db = SessionLocal()
    try:
        p = Paper(
            title=f"chat-src-{prefix}",
            abstract="abstract body",
            summary="curated summary body",
            authors=["Author A"],
            organizations=["LabX"],
            source_type=SourceType.PAPER,
            source_name="arxiv",
            url=f"https://example.test/chat/{prefix}",
            pdf_url=pdf_url,
            full_text=full_text,
            published_date=datetime.datetime(2026, 4, 25, tzinfo=datetime.UTC),
            impact_score=8.0,
            originality_score=8.0,
            is_processed=1,
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return p.id
    finally:
        db.close()


def test_chat_with_paper_id_uses_full_source(client, monkeypatch):
    """source-anchored mode: prompt contains the source body and `sources`
    contains exactly the chosen paper."""
    pid = _seed_paper_for_chat("anchor", full_text="UNIQUE_FULL_BODY_TOKEN")

    captured: dict[str, str] = {}

    def _fake_call_llm(prompt: str, role: str = "fast") -> str:
        captured["prompt"] = prompt
        captured["role"] = role
        return "anchored answer"

    from kb import main as main_mod
    monkeypatch.setattr(main_mod, "call_llm", _fake_call_llm)

    r = client.post("/api/chat", json={"query": "what does this paper say", "paper_id": pid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "anchored answer"
    assert len(body["sources"]) == 1 and body["sources"][0]["id"] == pid
    assert "UNIQUE_FULL_BODY_TOKEN" in captured["prompt"]
    assert "FULL SOURCE CONTENT" in captured["prompt"]


def test_chat_with_paper_id_404(client):
    r = client.post("/api/chat", json={"query": "hi", "paper_id": 999_999})
    assert r.status_code == 404


def test_chat_with_history_injects_prior_turns(client, monkeypatch):
    captured: dict[str, str] = {}

    def _fake_call_llm(prompt: str, role: str = "fast") -> str:
        captured["prompt"] = prompt
        captured["role"] = role
        return "history-aware answer"

    from kb import main as main_mod
    monkeypatch.setattr(main_mod, "call_llm", _fake_call_llm)

    payload = {
        "query": "follow up",
        "history": [
            {"role": "user", "content": "FIRST_USER_TURN_TOKEN"},
            {"role": "assistant", "content": "FIRST_ASSISTANT_TURN_TOKEN"},
        ],
    }
    r = client.post("/api/chat", json=payload)
    assert r.status_code == 200, r.text
    assert "FIRST_USER_TURN_TOKEN" in captured["prompt"]
    assert "FIRST_ASSISTANT_TURN_TOKEN" in captured["prompt"]


def test_chat_history_role_validated(client):
    r = client.post(
        "/api/chat",
        json={
            "query": "hi",
            "history": [{"role": "system", "content": "rogue prompt"}],
        },
    )
    assert r.status_code == 422


def test_chat_history_max_length_capped(client):
    """history length is bounded — over-long arrays are rejected."""
    history = [{"role": "user", "content": str(i)} for i in range(100)]
    r = client.post("/api/chat", json={"query": "hi", "history": history})
    assert r.status_code == 422


# ─── Chat (streaming) — /api/chat/stream ──────────────────────────


def _drain_sse(client, payload: dict) -> tuple[int, str, list[tuple[str, dict]]]:
    """Send a POST to /api/chat/stream, drain the SSE body, and parse it
    into a list of (event_name, data_dict) tuples. Returns (status, content_type, frames)."""
    import json

    with client.stream("POST", "/api/chat/stream", json=payload) as r:
        status = r.status_code
        content_type = r.headers.get("content-type", "")
        if status != 200:
            # body fully consumed via iter_text so the connection can close.
            "".join(r.iter_text())
            return status, content_type, []
        body = "".join(r.iter_text())

    frames: list[tuple[str, dict]] = []
    for raw in body.split("\n\n"):
        if not raw.strip():
            continue
        event = ""
        data = ""
        for line in raw.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data += line[len("data:"):].strip()
        if event:
            frames.append((event, json.loads(data) if data else {}))
    return status, content_type, frames


def test_chat_stream_emits_sources_token_done(client, monkeypatch):
    """Happy path: source-anchored stream emits sources, token(s), then done
    in that order, in valid SSE format."""
    pid = _seed_paper_for_chat("stream-happy", full_text="STREAMING_BODY_TOKEN")

    captured: dict[str, str] = {}

    def _fake_stream_llm(prompt: str, role: str = "fast"):
        captured["prompt"] = prompt
        captured["role"] = role
        yield "Hello "
        yield "world"

    from kb import main as main_mod
    monkeypatch.setattr(main_mod, "stream_llm", _fake_stream_llm)

    status, ct, frames = _drain_sse(client, {"query": "what is this", "paper_id": pid})
    assert status == 200
    assert "text/event-stream" in ct
    # Source body made it into the prompt (paper_id mode).
    assert "STREAMING_BODY_TOKEN" in captured["prompt"]

    events = [name for name, _ in frames]
    # `model` is the very first frame so the UI can label the assistant turn
    # before any source / token data arrives.
    assert events[0] == "model"
    assert events[1] == "sources"
    assert events[-1] == "done"
    assert "token" in events
    # Model frame carries provider + model name; under the test default
    # KB_LLM_PROVIDER=hermes both fall back to "hermes".
    model_payload = next(d for n, d in frames if n == "model")
    assert model_payload.get("model")
    assert model_payload.get("provider")
    # Sources frame contains exactly the chosen paper.
    sources_payload = next(d for n, d in frames if n == "sources")
    assert len(sources_payload["sources"]) == 1
    assert sources_payload["sources"][0]["id"] == pid
    # Token chunks accumulate to the full output.
    token_text = "".join(d["content"] for n, d in frames if n == "token")
    assert token_text == "Hello world"


def test_chat_stream_history_injects_prior_turns(client, monkeypatch):
    captured: dict[str, str] = {}

    def _fake_stream_llm(prompt: str, role: str = "fast"):
        captured["prompt"] = prompt
        captured["role"] = role
        yield "ok"

    from kb import main as main_mod
    monkeypatch.setattr(main_mod, "stream_llm", _fake_stream_llm)

    payload = {
        "query": "follow up",
        "history": [
            {"role": "user", "content": "STREAM_HIST_TOKEN_A"},
            {"role": "assistant", "content": "STREAM_HIST_TOKEN_B"},
        ],
    }
    status, _, frames = _drain_sse(client, payload)
    assert status == 200
    assert "STREAM_HIST_TOKEN_A" in captured["prompt"]
    assert "STREAM_HIST_TOKEN_B" in captured["prompt"]
    assert any(n == "done" for n, _ in frames)


def test_chat_stream_paper_id_404(client):
    """paper_id pointing to a missing row returns HTTP 404 *before* the
    stream begins — clients see a normal error, not an empty stream."""
    status, _, _ = _drain_sse(client, {"query": "hi", "paper_id": 999_999})
    assert status == 404


def test_chat_stream_empty_output_yields_placeholder(client, monkeypatch):
    """If the provider yields nothing (e.g. hermes empty), the endpoint
    still emits a placeholder token so the client always sees one token
    event between sources and done — matches /api/chat's
    '(LLM produced no output)' contract."""

    def _fake_stream_llm(prompt: str, role: str = "fast"):
        return
        yield  # makes this a generator function

    from kb import main as main_mod
    monkeypatch.setattr(main_mod, "stream_llm", _fake_stream_llm)

    status, _, frames = _drain_sse(client, {"query": "hi"})
    assert status == 200
    token_payload = next(d for n, d in frames if n == "token")
    assert token_payload["content"] == "(LLM produced no output)"


def test_chat_stream_history_role_validated(client):
    """Same Pydantic guard as /api/chat — system role is rejected at 422
    before the stream begins."""
    status, _, _ = _drain_sse(
        client,
        {"query": "hi", "history": [{"role": "system", "content": "rogue"}]},
    )
    assert status == 422


# ─── Daily pipeline (manual trigger + SSE progress) ──────────────


def _drain_daily_sse(client) -> tuple[int, str, list[tuple[str, dict]]]:
    """POST /api/daily/stream and parse the SSE body. Mirrors _drain_sse
    but for the daily endpoint (which takes an empty JSON body)."""
    import json as _json

    with client.stream("POST", "/api/daily/stream", json={}) as r:
        st = r.status_code
        ct = r.headers.get("content-type", "")
        if st != 200:
            "".join(r.iter_text())
            return st, ct, []
        body = "".join(r.iter_text())

    frames: list[tuple[str, dict]] = []
    for raw in body.split("\n\n"):
        if not raw.strip():
            continue
        # Skip SSE comment frames (": keepalive").
        if all(line.startswith(":") or not line for line in raw.split("\n")):
            continue
        ev = ""
        data = ""
        for line in raw.split("\n"):
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data += line[len("data:"):].strip()
        if ev:
            frames.append((ev, _json.loads(data) if data else {}))
    return st, ct, frames


def _patch_daily(monkeypatch, fake_pipeline):
    """Replace `kb.daily.run_daily_pipeline` for the duration of one test.

    The worker thread does `from kb.daily import run_daily_pipeline` *inside*
    its body so the import happens after the patch is applied — patching
    via setattr on the module is therefore enough."""
    from kb import daily as daily_mod

    monkeypatch.setattr(daily_mod, "run_daily_pipeline", fake_pipeline)


def _reset_daily_state():
    """Force-clear the daily run singleton between tests so 409s and
    leftover events from one test don't leak into the next. The
    session-scoped TestClient shares the app instance across tests."""
    from kb.main import _daily_state

    with _daily_state._cond:
        _daily_state._running = False
        _daily_state._started_at = None
        _daily_state._current_stage = None
        _daily_state._terminal_emitted = False
        _daily_state._events.clear()
        _daily_state._next_id = 0
        # _run_id is monotonic across the process — don't reset it so
        # tests that observe it can detect run boundaries.
        # Wake any subscribers stuck on wait_for() so they exit promptly.
        _daily_state._cond.notify_all()


def _drain_get_daily_sse(client, since: int = -1) -> tuple[int, str, list[tuple[str, dict]]]:
    """GET /api/daily/stream?since=<n> and parse the SSE body. Mirrors
    `_drain_daily_sse` but for the reattach endpoint."""
    import json as _json

    with client.stream("GET", f"/api/daily/stream?since={since}") as r:
        st = r.status_code
        ct = r.headers.get("content-type", "")
        if st != 200:
            "".join(r.iter_text())
            return st, ct, []
        body = "".join(r.iter_text())

    frames: list[tuple[str, dict]] = []
    for raw in body.split("\n\n"):
        if not raw.strip():
            continue
        if all(line.startswith(":") or not line for line in raw.split("\n")):
            continue
        ev = ""
        data = ""
        for line in raw.split("\n"):
            if line.startswith("event:"):
                ev = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data += line[len("data:"):].strip()
        if ev:
            frames.append((ev, _json.loads(data) if data else {}))
    return st, ct, frames


def test_daily_status_idle_by_default(client):
    _reset_daily_state()
    r = client.get("/api/daily/status")
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is False
    assert body["started_at"] is None
    assert body["current_stage"] is None
    assert body["last_event_id"] == -1
    assert "run_id" in body


def test_daily_stream_emits_started_stages_and_done(client, monkeypatch):
    """Happy path: a fake pipeline that prints the same stage banners as
    kb/daily.py drives a full sequence of started → 4 stages → done."""
    _reset_daily_state()

    def _fake_pipeline():
        # Match the prefix kb/daily.py prints — _STAGE_PATTERN keys off [N/4].
        print("[1/4] INGESTION")
        print("[2/4] PROCESSING")
        print("[3/4] EMBEDDING")
        print("[4/4] DAILY REPORT")
        print("Pipeline complete!")

    _patch_daily(monkeypatch, _fake_pipeline)

    status_code, ct, frames = _drain_daily_sse(client)
    assert status_code == 200
    assert "text/event-stream" in ct

    events = [name for name, _ in frames]
    assert events[0] == "started"
    assert events[-1] == "done"

    # Exactly one stage event per [N/4] header, in order, even though log
    # events are interleaved.
    stages = [d for n, d in frames if n == "stage"]
    assert [s["index"] for s in stages] == [1, 2, 3, 4]
    assert [s["name"] for s in stages] == ["ingestion", "processing", "embedding", "report"]

    # The banner lines should also have made it through as `log` events.
    log_lines = [d["line"] for n, d in frames if n == "log"]
    assert any("INGESTION" in line for line in log_lines)
    assert any("Pipeline complete!" in line for line in log_lines)


def test_daily_stream_concurrent_returns_409(client, monkeypatch):
    """A second POST while a run is in flight must return HTTP 409 — the
    first run owns the singleton lock."""
    _reset_daily_state()

    import threading
    release = threading.Event()
    started = threading.Event()

    def _fake_pipeline():
        started.set()
        # Hold the worker open until the test releases it.
        release.wait(timeout=5)

    _patch_daily(monkeypatch, _fake_pipeline)

    # Start the first run in a background thread so we can poke the API
    # while it's still in-flight.
    first_result: dict[str, object] = {}

    def _drain_first():
        try:
            first_result["status"], _, first_result["frames"] = _drain_daily_sse(client)
        finally:
            release.set()

    t = threading.Thread(target=_drain_first, daemon=True)
    t.start()
    try:
        # Wait until the worker has actually started so the lock is held.
        assert started.wait(timeout=5), "fake pipeline did not start"

        # Status must reflect the in-flight run.
        st = client.get("/api/daily/status")
        assert st.status_code == 200
        assert st.json()["running"] is True

        # Second POST must conflict.
        with client.stream("POST", "/api/daily/stream", json={}) as r:
            assert r.status_code == 409
            "".join(r.iter_text())
    finally:
        release.set()
        t.join(timeout=10)

    # The first stream still completes cleanly.
    assert first_result.get("status") == 200


def test_daily_stream_pipeline_exception_emits_error(client, monkeypatch):
    """If the pipeline raises, the stream must surface an `error` frame
    (and NOT a `done` frame) before the terminator."""
    _reset_daily_state()

    def _fake_pipeline():
        raise RuntimeError("boom from fake pipeline")

    _patch_daily(monkeypatch, _fake_pipeline)

    status_code, _, frames = _drain_daily_sse(client)
    assert status_code == 200
    events = [name for name, _ in frames]
    assert "error" in events
    # The terminal `done` is suppressed when an error has already been
    # emitted — clients should treat `error` as terminal.
    assert events.count("done") == 0
    err_payload = next(d for n, d in frames if n == "error")
    assert "boom" in err_payload["message"]


def test_daily_endpoints_require_token_when_set(client, monkeypatch):
    """Both /api/daily/status and /api/daily/stream are guarded by the
    same Bearer token as /api/chat — must 401 on bad / missing token."""
    _reset_daily_state()
    from kb import config

    monkeypatch.setattr(config.settings, "chat_token", "daily-test-token")
    try:
        # Anonymous → 401
        r = client.get("/api/daily/status")
        assert r.status_code == 401, r.text
        with client.stream("POST", "/api/daily/stream", json={}) as resp:
            assert resp.status_code == 401
            "".join(resp.iter_text())

        # Wrong token → 401
        r = client.get(
            "/api/daily/status",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert r.status_code == 401, r.text

        # Correct token must NOT be 401 (200 expected for status; stream
        # may also 200 — we don't drain it here to keep state clean).
        r = client.get(
            "/api/daily/status",
            headers={"Authorization": "Bearer daily-test-token"},
        )
        assert r.status_code != 401, r.text
    finally:
        monkeypatch.setattr(config.settings, "chat_token", None)


def test_daily_stage_pattern_matches_chinese_banner(client, monkeypatch):
    """The pipeline prints localized stage headers when KB_LANGUAGE=zh —
    `[N/4]` prefix is identical, so stage detection must still fire."""
    _reset_daily_state()

    def _fake_pipeline():
        print("[1/4] 数据采集")
        print("[2/4] 处理（摘要 + 打分）")
        print("[3/4] 向量化")
        print("[4/4] 每日简报")

    _patch_daily(monkeypatch, _fake_pipeline)

    status_code, _, frames = _drain_daily_sse(client)
    assert status_code == 200
    stages = [d for n, d in frames if n == "stage"]
    assert [s["index"] for s in stages] == [1, 2, 3, 4]


def test_daily_attach_with_no_run_returns_immediately(client):
    """GET /api/daily/stream with nothing buffered must close cleanly with
    no events — fresh-backend / first-page-load case must not hang."""
    _reset_daily_state()
    st, ct, frames = _drain_get_daily_sse(client, since=-1)
    assert st == 200
    assert "text/event-stream" in ct
    assert frames == []


def test_daily_attach_after_completion_replays_buffered_events(client, monkeypatch):
    """A GET /api/daily/stream after a run finishes must replay the full
    event buffer (started + stages + logs + terminal) so a user opening
    /reports right after a run sees the final state instead of empty
    'idle'."""
    _reset_daily_state()

    def _fake_pipeline():
        print("[1/4] INGESTION")
        print("hello world")
        print("[2/4] PROCESSING")

    _patch_daily(monkeypatch, _fake_pipeline)

    # Run the pipeline to completion via the POST stream.
    status_code, _, frames = _drain_daily_sse(client)
    assert status_code == 200
    assert frames[-1][0] == "done"

    # Status should now report not-running but with last_event_id > 0.
    snap = client.get("/api/daily/status").json()
    assert snap["running"] is False
    assert snap["last_event_id"] >= 2

    # Reattach via GET — the buffer should still hold everything.
    st2, ct2, frames2 = _drain_get_daily_sse(client, since=-1)
    assert st2 == 200
    assert "text/event-stream" in ct2
    events2 = [n for n, _ in frames2]
    assert events2[0] == "started"
    assert events2[-1] == "done"
    stages = [d for n, d in frames2 if n == "stage"]
    assert [s["index"] for s in stages] == [1, 2]
    log_lines = [d["line"] for n, d in frames2 if n == "log"]
    assert any("hello world" in line for line in log_lines)


def test_daily_attach_tails_running_pipeline(client, monkeypatch):
    """GET reattach during an in-flight run must drain buffered events
    AND keep tailing until the worker terminates — this is the page-
    refresh / dropped-network case the user actually experiences."""
    _reset_daily_state()

    import threading
    started = threading.Event()
    release = threading.Event()

    def _fake_pipeline():
        print("[1/4] INGESTION")
        started.set()
        # Hold the worker open until the test releases it so the GET
        # subscriber really attaches mid-run, not after.
        release.wait(timeout=10)
        print("[4/4] DAILY REPORT")

    _patch_daily(monkeypatch, _fake_pipeline)

    first_result: dict[str, object] = {}

    def _drain_first():
        try:
            first_result["status"], _, first_result["frames"] = _drain_daily_sse(client)
        finally:
            release.set()

    t1 = threading.Thread(target=_drain_first, daemon=True)
    t1.start()

    attach_result: dict[str, object] = {}

    def _drain_attach():
        attach_result["status"], _, attach_result["frames"] = (
            _drain_get_daily_sse(client, since=-1)
        )

    try:
        assert started.wait(timeout=5), "fake pipeline did not start"

        # Status snapshot mid-run must reflect the active run.
        snap = client.get("/api/daily/status").json()
        assert snap["running"] is True
        assert snap["current_stage"] == "ingestion"
        assert snap["last_event_id"] >= 1

        # Reattach via GET while the worker is paused.
        t2 = threading.Thread(target=_drain_attach, daemon=True)
        t2.start()

        # Release the worker so the pipeline finishes and both streams
        # drain to `done`.
        release.set()
        t1.join(timeout=10)
        t2.join(timeout=10)
    finally:
        release.set()

    assert first_result.get("status") == 200
    assert attach_result.get("status") == 200

    # Both streams must end in `done` and see the same stage transitions.
    attach_frames = attach_result["frames"]  # type: ignore[index]
    events = [n for n, _ in attach_frames]
    assert events[0] == "started"
    assert events[-1] == "done"
    stages = [d for n, d in attach_frames if n == "stage"]
    assert [s["index"] for s in stages] == [1, 4]


def test_daily_attach_get_endpoint_requires_token(client, monkeypatch):
    """The reattach endpoint inherits the same Bearer guard as the rest
    of the daily endpoints."""
    _reset_daily_state()
    from kb import config

    monkeypatch.setattr(config.settings, "chat_token", "daily-test-token")
    try:
        with client.stream("GET", "/api/daily/stream") as r:
            assert r.status_code == 401
            "".join(r.iter_text())
        with client.stream(
            "GET",
            "/api/daily/stream",
            headers={"Authorization": "Bearer daily-test-token"},
        ) as r:
            assert r.status_code != 401
            "".join(r.iter_text())
    finally:
        monkeypatch.setattr(config.settings, "chat_token", None)


# ─── Source list endpoint (browse page tag filter) ────────────────

def _seed_source_papers(prefix: str) -> None:
    """Insert 5 papers across 3 source_names so /api/sources can group/count.

    Layout: 2 arxiv (paper, processed=1), 1 OpenAI (blog, processed=1),
    1 SemiAnalysis (blog, processed=2 → low quality, must be hidden),
    1 github (project, processed=0 → pending, must be hidden).
    """
    import datetime
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    db = SessionLocal()
    try:
        for i, (sname, stype, processed) in enumerate([
            ("arxiv", SourceType.PAPER, 1),
            ("arxiv", SourceType.PAPER, 1),
            ("OpenAI", SourceType.BLOG, 1),
            ("SemiAnalysis", SourceType.BLOG, 2),
            ("trending-repo", SourceType.PROJECT, 0),
        ]):
            db.add(Paper(
                title=f"src-{prefix}-{i}",
                abstract="",
                summary="s" if processed else "",
                authors=[],
                organizations=[],
                source_type=stype,
                source_name=sname,
                url=f"https://example.test/sources/{prefix}/{i}",
                published_date=datetime.datetime(2026, 4, 25, tzinfo=datetime.UTC),
                is_processed=processed,
                quality_score=8.0 if processed == 1 else 0.0,
                relevance_score=8.0 if processed == 1 else 0.0,
            ))
        db.commit()
    finally:
        db.close()


def test_list_sources_returns_distinct_names_with_counts(client):
    _seed_source_papers("counts")
    r = client.get("/api/sources")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sources" in body
    by_name = {s["name"]: s for s in body["sources"]}
    # arxiv: 2 active rows, OpenAI: 1 active row.
    assert by_name["arxiv"]["count"] >= 2
    assert by_name["arxiv"]["type"] == "paper"
    assert by_name["OpenAI"]["count"] >= 1
    assert by_name["OpenAI"]["type"] == "blog"


def test_list_sources_excludes_low_quality_and_pending(client):
    _seed_source_papers("excl")
    r = client.get("/api/sources")
    body = r.json()
    names = {s["name"] for s in body["sources"]}
    assert "SemiAnalysis" not in names  # is_processed=2
    assert "trending-repo" not in names  # is_processed=0


def test_list_sources_orders_by_count_desc(client):
    _seed_source_papers("order")
    r = client.get("/api/sources")
    body = r.json()
    counts = [s["count"] for s in body["sources"]]
    assert counts == sorted(counts, reverse=True), body


# ─── /api/papers source_name filter (browse page) ─────────────────

def _seed_namespaced_source_papers(prefix: str) -> dict[str, str]:
    """Insert 4 active papers across 3 prefix-namespaced source_names so the
    /api/papers source_name filter tests can assert exact counts even when
    the session-scoped DB carries rows from earlier tests.

    Returns a name map: {"arxiv_key", "openai_key", "semi_key"} → actual
    namespaced source_name strings. Layout:
      - 2 arxiv_key (paper, processed=1)
      - 1 openai_key (blog, processed=1)
      - 1 semi_key (blog, processed=1)
    """
    import datetime
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType

    names = {
        "arxiv": f"arxiv-{prefix}",
        "openai": f"openai-{prefix}",
        "semi": f"semi-{prefix}",
    }
    rows = [
        (names["arxiv"], SourceType.PAPER),
        (names["arxiv"], SourceType.PAPER),
        (names["openai"], SourceType.BLOG),
        (names["semi"], SourceType.BLOG),
    ]
    db = SessionLocal()
    try:
        for i, (sname, stype) in enumerate(rows):
            db.add(Paper(
                title=f"flt-{prefix}-{i}",
                abstract="",
                summary="s",
                authors=[],
                organizations=[],
                source_type=stype,
                source_name=sname,
                url=f"https://example.test/flt/{prefix}/{i}",
                published_date=datetime.datetime(2026, 4, 25, tzinfo=datetime.UTC),
                is_processed=1,
                quality_score=8.0,
                relevance_score=8.0,
            ))
        db.commit()
    finally:
        db.close()
    return names


def test_list_papers_filters_by_single_source_name(client):
    names = _seed_namespaced_source_papers("single")
    r = client.get("/api/papers", params={"source_name": names["arxiv"], "page_size": 100})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert all(p["source_name"] == names["arxiv"] for p in body["papers"])


def test_list_papers_filters_by_multiple_source_names(client):
    names = _seed_namespaced_source_papers("multi")
    r = client.get(
        "/api/papers",
        params={"source_name": f"{names['arxiv']},{names['openai']}", "page_size": 100},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 2 arxiv + 1 OpenAI = 3 active rows.
    assert body["total"] == 3
    returned_names = {p["source_name"] for p in body["papers"]}
    assert returned_names == {names["arxiv"], names["openai"]}


def test_list_papers_source_name_empty_value_is_ignored(client):
    """Defensive: ?source_name= (empty string) must NOT filter to zero rows.
    The frontend may emit an empty value during URL rewrite races; this test
    locks in the 'empty == no filter' behavior."""
    _seed_namespaced_source_papers("empty")
    r = client.get("/api/papers", params={"source_name": "", "page_size": 100})
    assert r.status_code == 200, r.text
    body = r.json()
    # Without filter, total should include at least our 4 seeded active rows.
    assert body["total"] >= 4


def test_list_papers_source_name_combined_with_source_type(client):
    """AND combination with the existing source_type filter: arxiv is
    type=paper, so combining source_type=blog with source_name including
    arxiv should leave only the OpenAI blog row."""
    names = _seed_namespaced_source_papers("combo")
    r = client.get(
        "/api/papers",
        params={
            "source_type": "blog",
            "source_name": f"{names['arxiv']},{names['openai']}",
            "page_size": 100,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["papers"][0]["source_name"] == names["openai"]
