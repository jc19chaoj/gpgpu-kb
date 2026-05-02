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
        "quality_score": 8.0,
        "relevance_score": 7.5,
        "score_rationale": "Strong work from a top lab."
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
        "quality_score": 4.0,
        "relevance_score": 5.5,
        "score_rationale": "Niche follow-up work."
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


def _seed_typed(source_type, url_prefix: str) -> int:
    """Create a non-paper row and return its id."""
    from kb.database import SessionLocal
    from kb.models import Paper
    import datetime
    import uuid

    db = SessionLocal()
    try:
        row = Paper(
            title=f"{source_type.value} title",
            abstract="Some text.",
            authors=["someone"],
            organizations=[],
            source_type=source_type,
            source_name=source_type.value,
            url=f"{url_prefix}/{uuid.uuid4()}",
            published_date=datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id
    finally:
        db.close()


def test_blog_score_uses_depth_actionability_rubric():
    """Blog posts now go through the universal scoring path with a blog-specific
    rubric. Two LLM calls (summary + score), is_processed=1 regardless of score."""
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType
    from kb.processing import llm as llm_mod

    captured_prompts: list[str] = []

    score_json = json.dumps({
        "quality_score": 6.5,
        "relevance_score": 8.0,
        "score_rationale": "Solid technical depth and immediately actionable.",
    })
    responses = ["Blog summary.", score_json]

    def fake_call_llm(prompt):
        captured_prompts.append(prompt)
        return responses.pop(0)

    post_id = _seed_typed(SourceType.BLOG, "https://example.com/blog")

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        success = llm_mod.summarize_and_score(post_id)

    assert success is True
    # Both summary and score prompts were issued.
    assert len(captured_prompts) == 2
    score_prompt = captured_prompts[1]
    assert "TECHNICAL DEPTH" in score_prompt
    assert "ACTIONABILITY" in score_prompt
    # Paper-only language must NOT appear in a blog rubric.
    assert "FAANG" not in score_prompt

    db = SessionLocal()
    try:
        updated = db.query(Paper).filter(Paper.id == post_id).first()
        assert updated.is_processed == 1
        assert updated.summary == "Blog summary."
        assert updated.quality_score == pytest.approx(6.5)
        assert updated.relevance_score == pytest.approx(8.0)
        assert "actionable" in updated.score_rationale.lower()
        # Legacy paper fields are NOT mirrored for non-papers.
        assert updated.originality_score == pytest.approx(0.0)
        assert updated.impact_score == pytest.approx(0.0)
    finally:
        db.close()


def test_project_score_uses_innovation_maturity_rubric():
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType
    from kb.processing import llm as llm_mod

    captured: list[str] = []
    score_json = json.dumps({
        "quality_score": 7.0,
        "relevance_score": 4.5,
        "score_rationale": "Novel kernel approach but early-stage repo.",
    })
    responses = ["Repo summary.", score_json]

    def fake_call_llm(prompt):
        captured.append(prompt)
        return responses.pop(0)

    repo_id = _seed_typed(SourceType.PROJECT, "https://github.com/x")

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        assert llm_mod.summarize_and_score(repo_id) is True

    assert "INNOVATION" in captured[1]
    assert "MATURITY" in captured[1]

    db = SessionLocal()
    try:
        updated = db.query(Paper).filter(Paper.id == repo_id).first()
        assert updated.is_processed == 1
        assert updated.quality_score == pytest.approx(7.0)
        assert updated.relevance_score == pytest.approx(4.5)
    finally:
        db.close()


def test_talk_score_uses_depth_actionability_rubric():
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType
    from kb.processing import llm as llm_mod

    captured: list[str] = []
    score_json = json.dumps({
        "quality_score": 5.0,
        "relevance_score": 6.0,
        "score_rationale": "Useful overview.",
    })
    responses = ["Talk summary.", score_json]

    def fake_call_llm(prompt):
        captured.append(prompt)
        return responses.pop(0)

    talk_id = _seed_typed(SourceType.TALK, "https://example.com/talk")

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        assert llm_mod.summarize_and_score(talk_id) is True

    assert "DEPTH" in captured[1]
    assert "ACTIONABILITY" in captured[1]

    db = SessionLocal()
    try:
        updated = db.query(Paper).filter(Paper.id == talk_id).first()
        assert updated.is_processed == 1
        assert updated.quality_score == pytest.approx(5.0)
        assert updated.relevance_score == pytest.approx(6.0)
    finally:
        db.close()


def test_blog_low_score_still_processed():
    """2(a): non-papers always go to is_processed=1 on parse success, even
    when scores are at the floor. Curated RSS list is the gate, not the LLM."""
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType
    from kb.processing import llm as llm_mod

    score_json = json.dumps({
        "quality_score": 1.0,
        "relevance_score": 1.0,
        "score_rationale": "Marketing fluff.",
    })
    responses = ["Summary.", score_json]

    def fake_call_llm(prompt):
        return responses.pop(0)

    post_id = _seed_typed(SourceType.BLOG, "https://example.com/blog-low")

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        assert llm_mod.summarize_and_score(post_id) is True

    db = SessionLocal()
    try:
        updated = db.query(Paper).filter(Paper.id == post_id).first()
        # Crucially is_processed=1 (NOT 2): non-papers bypass the quality gate.
        assert updated.is_processed == 1
    finally:
        db.close()


def test_paper_mirrors_universal_to_legacy_fields():
    """For papers, quality/relevance must mirror to originality/impact so
    older API consumers and stored daily reports keep working."""
    from kb.database import SessionLocal
    from kb.models import Paper
    from kb.processing import llm as llm_mod

    score_json = json.dumps({
        "quality_score": 8.5,
        "relevance_score": 7.0,
        "score_rationale": "Mirror test.",
    })
    responses = ["Summary.", score_json]

    def fake_call_llm(prompt):
        return responses.pop(0)

    db = SessionLocal()
    try:
        paper = _make_paper(db)
        paper_id = paper.id
    finally:
        db.close()

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        assert llm_mod.summarize_and_score(paper_id) is True

    db = SessionLocal()
    try:
        updated = db.query(Paper).filter(Paper.id == paper_id).first()
        assert updated.quality_score == pytest.approx(8.5)
        assert updated.relevance_score == pytest.approx(7.0)
        assert updated.originality_score == pytest.approx(8.5)
        assert updated.impact_score == pytest.approx(7.0)
        assert updated.score_rationale == updated.impact_rationale
    finally:
        db.close()


def test_non_paper_json_failure_leaves_pending():
    """JSON parse failure on a non-paper must leave is_processed=0 (retry),
    matching the existing paper retry semantics."""
    from kb.database import SessionLocal
    from kb.models import Paper, SourceType
    from kb.processing import llm as llm_mod

    responses = ["Summary.", "NOT JSON"]

    def fake_call_llm(prompt):
        return responses.pop(0)

    post_id = _seed_typed(SourceType.BLOG, "https://example.com/blog-fail")

    with patch.object(llm_mod, "call_llm", side_effect=fake_call_llm):
        assert llm_mod.summarize_and_score(post_id) is False

    db = SessionLocal()
    try:
        updated = db.query(Paper).filter(Paper.id == post_id).first()
        assert updated.is_processed == 0
        assert updated.quality_score == pytest.approx(0.0)
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
        "quality_score": 8.5,
        "relevance_score": 4.0,
        "score_rationale": "Novel idea but unknown lab."
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
        "quality_score": 8.0,
        "relevance_score": 7.5,
        "score_rationale": "优秀的工作。",
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
        "quality_score": 8.0,
        "relevance_score": 7.5,
        "score_rationale": "Strong work.",
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
        "质量": 8.0,
        "相关性": 7.0,
        "score_rationale": "优秀的工作。",
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
        "quality_score": 8.0,
        "relevance_score": 7.5,
        "score_rationale": "优秀的工作。",
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
    score_prompt = captured_prompts[1]
    assert "Write your entire response in Chinese" not in score_prompt
    assert "score_rationale" in score_prompt
    assert "Chinese" in score_prompt
