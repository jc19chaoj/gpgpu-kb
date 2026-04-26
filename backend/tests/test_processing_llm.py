# backend/tests/test_processing_llm.py
"""Tests for kb/processing/llm.py — provider switching, helpers, and pipeline."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ─── call_llm provider switching ──────────────────────────────────


def test_call_llm_uses_hermes_by_default(monkeypatch):
    from kb import config
    from kb.processing import llm as llm_mod

    mock_h = MagicMock(return_value="hermes response")
    monkeypatch.setattr(config.settings, "llm_provider", "hermes")
    monkeypatch.setitem(llm_mod._PROVIDERS, "hermes", mock_h)
    result = llm_mod.call_llm("test prompt")
    mock_h.assert_called_once_with("test prompt")
    assert result == "hermes response"


def test_call_llm_routes_to_anthropic(monkeypatch):
    from kb import config
    from kb.processing import llm as llm_mod

    mock_a = MagicMock(return_value="anthropic response")
    monkeypatch.setattr(config.settings, "llm_provider", "anthropic")
    monkeypatch.setitem(llm_mod._PROVIDERS, "anthropic", mock_a)
    result = llm_mod.call_llm("test prompt")
    mock_a.assert_called_once_with("test prompt")
    assert result == "anthropic response"


def test_call_llm_routes_to_openai(monkeypatch):
    from kb import config
    from kb.processing import llm as llm_mod

    mock_o = MagicMock(return_value="openai response")
    monkeypatch.setattr(config.settings, "llm_provider", "openai")
    monkeypatch.setitem(llm_mod._PROVIDERS, "openai", mock_o)
    result = llm_mod.call_llm("test prompt")
    mock_o.assert_called_once_with("test prompt")
    assert result == "openai response"


def test_call_llm_unknown_provider_falls_back_to_hermes(monkeypatch):
    from kb import config
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "llm_provider", "nonexistent")
    with patch.object(llm_mod, "_call_hermes", return_value="fallback") as mock_h:
        # Also remove "nonexistent" from _PROVIDERS in case it was added
        result = llm_mod.call_llm("test prompt")
    mock_h.assert_called_once_with("test prompt")
    assert result == "fallback"


def test_call_llm_swallows_provider_exceptions(monkeypatch):
    from kb import config
    from kb.processing import llm as llm_mod

    mock_h = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(config.settings, "llm_provider", "hermes")
    monkeypatch.setitem(llm_mod._PROVIDERS, "hermes", mock_h)
    result = llm_mod.call_llm("test prompt")
    assert result == ""


# ─── missing API key returns "" (not exception) ───────────────────


def test_call_anthropic_missing_key_returns_empty(monkeypatch):
    from kb import config
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "anthropic_api_key", None)
    result = llm_mod._call_anthropic("prompt")
    assert result == ""


def test_call_openai_missing_key_returns_empty(monkeypatch):
    from kb import config
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "openai_api_key", None)
    result = llm_mod._call_openai("prompt")
    assert result == ""


# ─── _clamp_score edge cases ──────────────────────────────────────


def test_clamp_score_above_max():
    from kb.processing.llm import _clamp_score
    assert _clamp_score(11) == 10.0


def test_clamp_score_below_min():
    from kb.processing.llm import _clamp_score
    assert _clamp_score(-3) == 0.0


def test_clamp_score_non_numeric_string_returns_default():
    from kb.processing.llm import _clamp_score
    assert _clamp_score("abc") == 5.0


def test_clamp_score_float_within_range():
    from kb.processing.llm import _clamp_score
    assert _clamp_score(7.2) == pytest.approx(7.2)


def test_clamp_score_none_returns_default():
    from kb.processing.llm import _clamp_score
    assert _clamp_score(None) == 5.0


def test_clamp_score_custom_default():
    from kb.processing.llm import _clamp_score
    assert _clamp_score("bad", default=3.0) == 3.0


def test_clamp_score_boundary_zero():
    from kb.processing.llm import _clamp_score
    assert _clamp_score(0) == 0.0


def test_clamp_score_boundary_ten():
    from kb.processing.llm import _clamp_score
    assert _clamp_score(10) == 10.0


# ─── _sanitize ────────────────────────────────────────────────────


def test_sanitize_replaces_backtick_sequences():
    from kb.processing.llm import _sanitize
    result = _sanitize("hello ```world```")
    assert "```" not in result
    assert "ʼʼʼ" in result


def test_sanitize_truncates_at_max_len():
    from kb.processing.llm import _sanitize
    long_text = "x" * 10_000
    result = _sanitize(long_text, max_len=8000)
    assert len(result) == 8000


def test_sanitize_custom_max_len():
    from kb.processing.llm import _sanitize
    result = _sanitize("abcde", max_len=3)
    assert result == "abc"


def test_sanitize_none_returns_empty():
    from kb.processing.llm import _sanitize
    assert _sanitize(None) == ""


def test_sanitize_empty_string_returns_empty():
    from kb.processing.llm import _sanitize
    assert _sanitize("") == ""


# ─── summarize_and_score happy path ───────────────────────────────


def _make_paper(db):
    """Insert a minimal Paper and return it.

    URL must be process-unique because the session-scoped test DB persists
    across tests and Paper.url has a unique index. `id(db)` was previously
    used here but Python re-uses memory addresses after GC, occasionally
    producing collisions across multiple _make_paper() calls in the same run.
    """
    from kb.models import Paper, SourceType
    import datetime
    import uuid

    paper = Paper(
        title="Test Paper Title",
        abstract="This is a test abstract.",
        authors=["Alice", "Bob"],
        organizations=["Uni A"],
        source_type=SourceType.PAPER,
        source_name="arxiv",
        url=f"https://example.com/paper/{uuid.uuid4()}",
        published_date=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


def test_summarize_and_score_happy_path():
    from kb.database import SessionLocal
    from kb.processing import llm as llm_mod

    good_json = json.dumps({
        "originality_score": 8.0,
        "impact_score": 7.5,
        "impact_rationale": "Strong work from a top lab."
    })

    call_responses = ["This is a detailed summary.", good_json]

    def fake_call_llm(prompt):
        return call_responses.pop(0)

    db = SessionLocal()
    try:
        paper = _make_paper(db)
        paper_id = paper.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        success = llm_mod.summarize_and_score(paper_id)

    assert success is True

    db = SessionLocal()
    try:
        from kb.models import Paper
        updated = db.query(Paper).filter(Paper.id == paper_id).first()
        assert updated.is_processed == 1
        assert updated.summary == "This is a detailed summary."
        assert updated.originality_score == pytest.approx(8.0)
        assert updated.impact_score == pytest.approx(7.5)
        assert "top lab" in updated.impact_rationale
    finally:
        db.close()


def test_summarize_and_score_non_json_leaves_pending_for_retry():
    """When the scoring LLM returns non-JSON, the paper must NOT be classified
    with default 5.0/5.0 (which would be a permanent misjudgment). Instead
    is_processed stays 0 so the next batch can retry."""
    from kb.database import SessionLocal
    from kb.processing import llm as llm_mod

    call_responses = ["Summary text.", "NOT JSON AT ALL"]

    def fake_call_llm(prompt):
        return call_responses.pop(0)

    db = SessionLocal()
    try:
        paper = _make_paper(db)
        paper_id = paper.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        success = llm_mod.summarize_and_score(paper_id)

    assert success is False

    db = SessionLocal()
    try:
        from kb.models import Paper
        updated = db.query(Paper).filter(Paper.id == paper_id).first()
        assert updated.is_processed == 0
        # Score fields untouched (still column defaults)
        assert updated.summary == ""
        assert updated.originality_score == pytest.approx(0.0)
        assert updated.impact_score == pytest.approx(0.0)
    finally:
        db.close()


def test_summarize_and_score_low_quality_marks_skipped(monkeypatch):
    """max(originality, impact) < threshold → is_processed=2.

    Pin the threshold to 7.0 so the test doesn't break when an operator
    overrides KB_QUALITY_SCORE_THRESHOLD via .env (4.0/5.5 must fall below).
    """
    from kb import config
    from kb.database import SessionLocal
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "quality_score_threshold", 7.0)

    low_json = json.dumps({
        "originality_score": 4.0,
        "impact_score": 5.5,
        "impact_rationale": "Niche follow-up work."
    })
    call_responses = ["Summary text.", low_json]

    def fake_call_llm(prompt):
        return call_responses.pop(0)

    db = SessionLocal()
    try:
        paper = _make_paper(db)
        paper_id = paper.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        success = llm_mod.summarize_and_score(paper_id)

    assert success is True

    db = SessionLocal()
    try:
        from kb.models import Paper
        updated = db.query(Paper).filter(Paper.id == paper_id).first()
        assert updated.is_processed == 2  # quarantined as low-quality
        assert updated.impact_score == pytest.approx(5.5)
    finally:
        db.close()


def test_summarize_and_score_blog_skips_quality_gate():
    """Blog posts use a paper-centric rubric unfairly, so they bypass scoring
    and go straight to is_processed=1 with summary-only output. The scoring
    LLM call must NOT be made (only one call_llm response consumed)."""
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType
    from kb.processing import llm as llm_mod
    import datetime
    import uuid

    summary_only = ["Summary of the blog post."]

    def fake_call_llm(prompt):
        return summary_only.pop(0)

    db = SessionLocal()
    try:
        post = Paper(
            title="A Deep Dive Into GPU Memory",
            abstract="An informal blog summary.",
            authors=["Some Engineer"],
            organizations=[],
            source_type=SourceType.BLOG,
            source_name="Some Blog",
            url=f"https://example.com/blog/{uuid.uuid4()}",
            published_date=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        )
        db.add(post)
        db.commit()
        db.refresh(post)
        post_id = post.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        success = llm_mod.summarize_and_score(post_id)

    assert success is True
    assert summary_only == []  # only the summary call was made; no scoring

    db = SessionLocal()
    try:
        updated = db.query(Paper).filter(Paper.id == post_id).first()
        assert updated.is_processed == 1
        assert updated.summary == "Summary of the blog post."
        assert updated.originality_score == pytest.approx(0.0)
        assert updated.impact_score == pytest.approx(0.0)
        assert "blog" in updated.impact_rationale.lower()
    finally:
        db.close()


def test_summarize_and_score_project_skips_quality_gate():
    """Same as the blog case but for SourceType.PROJECT (GitHub repos)."""
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType
    from kb.processing import llm as llm_mod
    import datetime
    import uuid

    responses = ["Summary of the repo."]

    def fake_call_llm(prompt):
        return responses.pop(0)

    db = SessionLocal()
    try:
        repo = Paper(
            title="org/awesome-cuda",
            abstract="A README description.",
            authors=["org"],
            organizations=["org"],
            source_type=SourceType.PROJECT,
            source_name="github",
            url=f"https://github.com/org/{uuid.uuid4()}",
            published_date=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        repo_id = repo.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        success = llm_mod.summarize_and_score(repo_id)

    assert success is True
    assert responses == []

    db = SessionLocal()
    try:
        updated = db.query(Paper).filter(Paper.id == repo_id).first()
        assert updated.is_processed == 1
        assert updated.impact_score == pytest.approx(0.0)
    finally:
        db.close()


def test_summarize_and_score_threshold_uses_max_of_two_dimensions(monkeypatch):
    """A paper that is novel (high originality) but from an unknown author
    (low impact) should still pass the gate — max(o,i) >= threshold."""
    from kb import config
    from kb.database import SessionLocal
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "quality_score_threshold", 7.0)

    high_orig_low_impact = json.dumps({
        "originality_score": 8.5,
        "impact_score": 4.0,
        "impact_rationale": "Novel idea but unknown lab."
    })
    call_responses = ["Summary.", high_orig_low_impact]

    def fake_call_llm(prompt):
        return call_responses.pop(0)

    db = SessionLocal()
    try:
        paper = _make_paper(db)
        paper_id = paper.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        llm_mod.summarize_and_score(paper_id)

    db = SessionLocal()
    try:
        from kb.models import Paper
        updated = db.query(Paper).filter(Paper.id == paper_id).first()
        assert updated.is_processed == 1  # passes via originality
    finally:
        db.close()


def test_summarize_and_score_missing_paper_returns_false():
    from kb.processing import llm as llm_mod

    with patch.object(llm_mod, "call_llm", return_value="irrelevant"):
        result = llm_mod.summarize_and_score(999_999_999)
    assert result is False


# ─── _lang_instruction / _impact_lang_instruction ─────────────────


def test_lang_instruction_returns_empty_for_en(monkeypatch):
    from kb import config
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "language", "en")
    assert llm_mod._lang_instruction() == ""
    assert llm_mod._impact_lang_instruction() == ""


def test_lang_instruction_returns_chinese_suffix_for_zh(monkeypatch):
    from kb import config
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "language", "zh")
    assert "Chinese" in llm_mod._lang_instruction()
    assert "简体中文" in llm_mod._lang_instruction()
    assert "Chinese" in llm_mod._impact_lang_instruction()
    assert "简体中文" in llm_mod._impact_lang_instruction()


def test_summarize_prompt_includes_lang_instruction_zh(monkeypatch):
    from kb import config
    from kb.database import SessionLocal
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "language", "zh")

    captured_prompts = []

    good_json = json.dumps({
        "originality_score": 8.0,
        "impact_score": 7.5,
        "impact_rationale": "优秀的工作。",
    })

    def fake_call_llm(prompt):
        captured_prompts.append(prompt)
        if len(captured_prompts) == 1:
            return "摘要内容。"
        return good_json

    db = SessionLocal()
    try:
        paper = _make_paper(db)
        paper_id = paper.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        llm_mod.summarize_and_score(paper_id)

    assert len(captured_prompts) >= 1
    summary_prompt = captured_prompts[0]
    assert "Write your entire response in Chinese" in summary_prompt
    assert "=== UNTRUSTED START ===" in summary_prompt


def test_summarize_prompt_unchanged_for_en(monkeypatch):
    from kb import config
    from kb.database import SessionLocal
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "language", "en")

    captured_prompts = []

    good_json = json.dumps({
        "originality_score": 8.0,
        "impact_score": 7.5,
        "impact_rationale": "Strong work.",
    })

    def fake_call_llm(prompt):
        captured_prompts.append(prompt)
        if len(captured_prompts) == 1:
            return "Summary text."
        return good_json

    db = SessionLocal()
    try:
        paper = _make_paper(db)
        paper_id = paper.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        llm_mod.summarize_and_score(paper_id)

    assert len(captured_prompts) == 2
    for prompt in captured_prompts:
        assert "Chinese" not in prompt
        assert "简体中文" not in prompt


def test_summarize_json_keys_translated_returns_false():
    """If LLM returns JSON with translated keys (not English), defensive check returns False."""
    from kb.database import SessionLocal
    from kb.processing import llm as llm_mod

    translated_json = json.dumps({
        "原创性": 8.0,
        "影响力": 7.0,
        "impact_rationale": "优秀的工作。",
    })
    call_responses = ["Summary text.", translated_json]

    def fake_call_llm(prompt):
        return call_responses.pop(0)

    db = SessionLocal()
    try:
        paper = _make_paper(db)
        paper_id = paper.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        result = llm_mod.summarize_and_score(paper_id)

    assert result is False

    db = SessionLocal()
    try:
        from kb.models import Paper
        updated = db.query(Paper).filter(Paper.id == paper_id).first()
        assert updated.is_processed == 0
    finally:
        db.close()


def test_impact_prompt_no_entire_response_chinese(monkeypatch):
    """impact_prompt must NOT say 'Write your entire response in Chinese';
    it should only instruct the model to write impact_rationale in Chinese."""
    from kb import config
    from kb.database import SessionLocal
    from kb.processing import llm as llm_mod

    monkeypatch.setattr(config.settings, "language", "zh")

    captured_prompts = []

    good_json = json.dumps({
        "originality_score": 8.0,
        "impact_score": 7.5,
        "impact_rationale": "优秀的工作。",
    })

    def fake_call_llm(prompt):
        captured_prompts.append(prompt)
        if len(captured_prompts) == 1:
            return "摘要内容。"
        return good_json

    db = SessionLocal()
    try:
        paper = _make_paper(db)
        paper_id = paper.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        llm_mod.summarize_and_score(paper_id)

    assert len(captured_prompts) == 2
    impact_prompt = captured_prompts[1]
    assert "Write your entire response in Chinese" not in impact_prompt
    assert "impact_rationale" in impact_prompt
    assert "Chinese" in impact_prompt
