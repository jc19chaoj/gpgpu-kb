# tests/test_ingestion_github.py
"""Tests for kb/ingestion/github_trending.py — no network, httpx patched.

The fetcher walks the public ``https://github.com/trending`` HTML across
``daily`` / ``weekly`` / ``monthly`` periods and takes the top
``TOP_N_PER_PERIOD`` repos from each. Tests cover:

* per-block HTML extraction (owner/repo, description, language)
* ``TOP_N_PER_PERIOD`` truncation
* dedup within a single page
* dedup across periods + ``trending-<period>`` category accumulation
* graceful failure on HTTP error / malformed HTML
* ``days_back`` parameter signature parity (no influence on output)
* ``save_repos`` insert / dedup invariants
"""
from __future__ import annotations

import datetime
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from kb.ingestion import github_trending as gh
from kb.ingestion.github_trending import (
    PERIODS,
    TOP_N_PER_PERIOD,
    _clean_text,
    _scrape_trending,
    fetch_trending_repos,
    save_repos,
)
from kb.models import SourceType


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _article(owner: str, repo: str, description: str = "", language: str = "") -> str:
    """Build one ``<article class="Box-row">`` block matching trending markup."""
    desc_html = (
        f'<p class="col-9 color-fg-muted my-1 pr-4">{description}</p>'
        if description
        else ""
    )
    lang_html = (
        f'<span itemprop="programmingLanguage">{language}</span>'
        if language
        else ""
    )
    return f"""
    <article class="Box-row">
      <h2 class="h3 lh-condensed">
        <a href="/{owner}/{repo}" class="Link">
          <span class="text-normal">{owner} /</span>
          {repo}
        </a>
      </h2>
      {desc_html}
      <div class="f6 color-fg-muted mt-2">
        {lang_html}
        <a href="/{owner}/{repo}/stargazers" class="Link Link--muted">
          <span>1,234</span>
        </a>
      </div>
    </article>
    """


def _trending_html(*articles: str) -> str:
    """Wrap article fragments in a minimal trending page envelope."""
    body = "\n".join(articles)
    return f"<html><body><main>{body}</main></body></html>"


def _mock_response(status_code: int = 200, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError

        resp.raise_for_status.side_effect = HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    return resp


@contextmanager
def _patch_httpx_client(responses: list[MagicMock]):
    """Patch ``httpx.Client`` as a context manager whose ``.get()`` returns
    ``responses`` in order, one per call."""
    mock_client = MagicMock()
    mock_client.get.side_effect = responses

    with patch("kb.ingestion.github_trending.httpx.Client") as MockHttpxClient:
        MockHttpxClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockHttpxClient.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_client


def _three_period_responses(
    daily: list[str] | None = None,
    weekly: list[str] | None = None,
    monthly: list[str] | None = None,
) -> list[MagicMock]:
    """One mocked HTTP response per period in PERIODS order."""
    payload_by_period = {
        "daily": daily or [],
        "weekly": weekly or [],
        "monthly": monthly or [],
    }
    return [
        _mock_response(200, _trending_html(*payload_by_period[p]))
        for p in PERIODS
    ]


# ---------------------------------------------------------------------------
# _clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    def test_strips_inline_tags(self):
        assert _clean_text("<em>hello</em> <strong>world</strong>") == "hello world"

    def test_collapses_whitespace(self):
        assert _clean_text("  hello\n   world\t!") == "hello world !"

    def test_unescapes_html_entities(self):
        assert _clean_text("AT&amp;T &lt;3") == "AT&T <3"

    def test_empty_returns_empty(self):
        assert _clean_text("") == ""


# ---------------------------------------------------------------------------
# _scrape_trending
# ---------------------------------------------------------------------------


class TestScrapeTrending:
    def test_extracts_owner_repo_description_language(self):
        html = _trending_html(
            _article("acme", "kernel-fast", "A fast kernel", "Cuda"),
        )
        client = MagicMock()
        client.get.return_value = _mock_response(200, html)

        out = _scrape_trending(client, "daily")

        assert len(out) == 1
        row = out[0]
        assert (row.owner, row.repo) == ("acme", "kernel-fast")
        assert row.description == "A fast kernel"
        assert row.language == "Cuda"

    def test_caps_at_top_n_per_period(self):
        # Build TOP_N_PER_PERIOD + 5 articles; expect exactly TOP_N_PER_PERIOD back.
        articles = [
            _article(f"owner{i}", f"repo{i}", f"desc {i}", "Python")
            for i in range(TOP_N_PER_PERIOD + 5)
        ]
        client = MagicMock()
        client.get.return_value = _mock_response(200, _trending_html(*articles))

        out = _scrape_trending(client, "daily")

        assert len(out) == TOP_N_PER_PERIOD
        assert out[0].owner == "owner0"
        assert out[-1].owner == f"owner{TOP_N_PER_PERIOD - 1}"

    def test_dedupes_within_one_page(self):
        # GitHub never duplicates within a page in practice, but the regex
        # could pick up the same href twice if markup ever changes.
        html = _trending_html(
            _article("acme", "tool", "first", "Rust"),
            _article("acme", "tool", "second", "Rust"),
            _article("other", "thing", "third", "Go"),
        )
        client = MagicMock()
        client.get.return_value = _mock_response(200, html)

        out = _scrape_trending(client, "weekly")

        names = [(r.owner, r.repo) for r in out]
        assert names == [("acme", "tool"), ("other", "thing")]

    def test_returns_empty_on_http_error(self):
        client = MagicMock()
        client.get.return_value = _mock_response(500, "boom")

        out = _scrape_trending(client, "daily")

        assert out == []

    def test_returns_empty_on_malformed_html(self):
        client = MagicMock()
        client.get.return_value = _mock_response(200, "<html>no articles here</html>")

        out = _scrape_trending(client, "monthly")

        assert out == []

    def test_missing_description_yields_empty_string(self):
        html = _trending_html(_article("a", "b", description="", language="C"))
        client = MagicMock()
        client.get.return_value = _mock_response(200, html)

        out = _scrape_trending(client, "daily")

        assert len(out) == 1
        assert out[0].description == ""
        assert out[0].language == "C"

    def test_missing_language_yields_empty_string(self):
        html = _trending_html(_article("a", "b", description="x", language=""))
        client = MagicMock()
        client.get.return_value = _mock_response(200, html)

        out = _scrape_trending(client, "daily")

        assert len(out) == 1
        assert out[0].language == ""
        assert out[0].description == "x"

    def test_unescapes_owner_and_repo(self):
        # Owner/repo should never contain entities in practice, but if they
        # did the unescape pass should kick in. Test via description instead
        # to exercise the same code path more naturally.
        html = _trending_html(_article("a", "b", "PKO &amp; friends", ""))
        client = MagicMock()
        client.get.return_value = _mock_response(200, html)

        out = _scrape_trending(client, "daily")

        assert out[0].description == "PKO & friends"


# ---------------------------------------------------------------------------
# fetch_trending_repos
# ---------------------------------------------------------------------------


class TestFetchTrendingRepos:
    def test_walks_all_three_periods(self):
        responses = _three_period_responses(
            daily=[_article("acme", "daily-only", "d", "Python")],
            weekly=[_article("foo", "weekly-only", "w", "Rust")],
            monthly=[_article("bar", "monthly-only", "m", "Go")],
        )

        with patch("kb.ingestion.github_trending.time.sleep"):
            with _patch_httpx_client(responses) as client:
                repos = fetch_trending_repos(days_back=1)

        # One GET per period.
        assert client.get.call_count == 3
        called_periods = [c.kwargs["params"]["since"] for c in client.get.call_args_list]
        assert called_periods == list(PERIODS)

        titles = sorted(r["title"] for r in repos)
        assert titles == ["acme/daily-only", "bar/monthly-only", "foo/weekly-only"]

    def test_each_repo_tagged_with_its_periods(self):
        responses = _three_period_responses(
            daily=[_article("acme", "shared", "d", "Python")],
            weekly=[_article("acme", "shared", "w", "Python"),
                    _article("solo", "weekly", "w2", "")],
            monthly=[_article("acme", "shared", "m", "Python")],
        )

        with patch("kb.ingestion.github_trending.time.sleep"):
            with _patch_httpx_client(responses):
                repos = fetch_trending_repos()

        by_title = {r["title"]: r for r in repos}
        # Cross-period dedup: "acme/shared" appears once, with all three tags.
        assert "acme/shared" in by_title
        shared = by_title["acme/shared"]
        cats = shared["categories"]
        assert "trending-daily" in cats
        assert "trending-weekly" in cats
        assert "trending-monthly" in cats
        # Language gets tagged once (lowercased).
        assert "python" in cats

        solo = by_title["solo/weekly"]
        assert solo["categories"] == ["trending-weekly"]

    def test_no_keyword_arg_is_present(self):
        # Regression guard: the previous keyword-fanout implementation used
        # ``params={"q": "<kw> pushed:>...", ...}``. The scrape path must
        # only send ``params={"since": <period>}`` so a future contributor
        # can't reintroduce keyword filtering by accident.
        responses = _three_period_responses()

        with patch("kb.ingestion.github_trending.time.sleep"):
            with _patch_httpx_client(responses) as client:
                fetch_trending_repos()

        for c in client.get.call_args_list:
            params = c.kwargs.get("params") or {}
            assert set(params.keys()) == {"since"}
            assert "q" not in params

    def test_record_shape_matches_save_repos_contract(self):
        responses = _three_period_responses(
            daily=[_article("acme", "tool", "Cool tool", "Rust")],
        )

        with patch("kb.ingestion.github_trending.time.sleep"):
            with _patch_httpx_client(responses):
                repos = fetch_trending_repos()

        assert len(repos) == 1
        r = repos[0]
        # All fields save_repos / Paper(**r) needs are present and the right type.
        assert r["title"] == "acme/tool"
        assert r["url"] == "https://github.com/acme/tool"
        assert r["authors"] == ["acme"]
        assert r["organizations"] == []
        assert r["abstract"] == "Cool tool"
        assert r["pdf_url"] == ""
        assert r["source_type"] == SourceType.PROJECT
        assert r["source_name"] == "github"
        assert r["venue"] == ""
        assert isinstance(r["published_date"], datetime.datetime)
        assert r["published_date"].tzinfo is not None
        assert "trending-daily" in r["categories"]
        assert "rust" in r["categories"]

    def test_polite_sleep_between_periods(self):
        responses = _three_period_responses()

        with patch("kb.ingestion.github_trending.time.sleep") as mock_sleep:
            with _patch_httpx_client(responses):
                fetch_trending_repos()

        # 3 periods → 2 spacer sleeps (skipped after the last one).
        assert mock_sleep.call_count == len(PERIODS) - 1

    def test_one_period_failure_does_not_stop_others(self):
        responses = [
            _mock_response(500, "boom"),  # daily fails
            _mock_response(
                200, _trending_html(_article("foo", "weekly", "w", "Rust"))
            ),
            _mock_response(
                200, _trending_html(_article("bar", "monthly", "m", "Go"))
            ),
        ]

        with patch("kb.ingestion.github_trending.time.sleep"):
            with _patch_httpx_client(responses):
                repos = fetch_trending_repos()

        titles = sorted(r["title"] for r in repos)
        assert titles == ["bar/monthly", "foo/weekly"]

    def test_days_back_param_does_not_filter_results(self):
        """``days_back`` is signature parity only; output must not depend on it."""
        responses_a = _three_period_responses(
            daily=[_article("acme", "tool", "d", "Rust")]
        )
        responses_b = _three_period_responses(
            daily=[_article("acme", "tool", "d", "Rust")]
        )

        with patch("kb.ingestion.github_trending.time.sleep"):
            with _patch_httpx_client(responses_a):
                got_with_int = fetch_trending_repos(days_back=10)
            with _patch_httpx_client(responses_b):
                got_with_zero = fetch_trending_repos(days_back=0)

        assert {r["title"] for r in got_with_int} == {r["title"] for r in got_with_zero}

    def test_days_back_none_resolves_via_lookback_helper(self):
        """``days_back=None`` should call ``_lookback_for_source('github')`` —
        keeping log parity with the other fetchers — but not change output."""
        responses = _three_period_responses()

        with patch("kb.ingestion.github_trending.time.sleep"):
            with patch("kb.ingestion.run._lookback_for_source", return_value=42) as look:
                with _patch_httpx_client(responses):
                    fetch_trending_repos(days_back=None)

        look.assert_called_once_with("github")

    def test_no_authorization_header_sent_to_trending(self):
        """Trending HTML is unauthenticated; sending a token is unnecessary
        and would tie the fetch to an account's request volume."""
        responses = _three_period_responses()

        with patch("kb.ingestion.github_trending.time.sleep"):
            with _patch_httpx_client(responses):
                fetch_trending_repos()

        # The Authorization header is not built into the client, and no
        # per-call header overrides it. Inspect both surfaces to be sure.
        with patch("kb.ingestion.github_trending.time.sleep"):
            with patch("kb.ingestion.github_trending.httpx.Client") as MockClient:
                inst = MagicMock()
                inst.get.return_value = _mock_response(200, _trending_html())
                MockClient.return_value.__enter__ = MagicMock(return_value=inst)
                MockClient.return_value.__exit__ = MagicMock(return_value=False)
                fetch_trending_repos()

        client_kwargs = MockClient.call_args.kwargs
        client_headers = client_kwargs.get("headers") or {}
        assert "Authorization" not in client_headers


# ---------------------------------------------------------------------------
# Module surface — guard against regressions
# ---------------------------------------------------------------------------


class TestModuleSurface:
    def test_keywords_constant_is_gone(self):
        """Regression guard: the previous keyword-fanout API has been retired.
        Anyone re-introducing a ``KEYWORDS`` list should hit this test."""
        assert not hasattr(gh, "KEYWORDS")

    def test_periods_constant_present(self):
        assert gh.PERIODS == ("daily", "weekly", "monthly")

    def test_top_n_per_period_is_ten(self):
        assert gh.TOP_N_PER_PERIOD == 10


# ---------------------------------------------------------------------------
# save_repos (unchanged contract)
# ---------------------------------------------------------------------------


class TestSaveRepos:
    def _repo_dict(self, url: str, title: str = "org/repo") -> dict:
        return {
            "title": title,
            "authors": ["org"],
            "organizations": [],
            "abstract": "A repo description",
            "url": url,
            "pdf_url": "",
            "source_type": SourceType.PROJECT,
            "source_name": "github",
            "published_date": datetime.datetime.now(datetime.UTC),
            "categories": ["trending-daily", "rust"],
            "venue": "",
        }

    def test_saves_new_repos(self):
        repos = [self._repo_dict("https://github.com/org/repo-gh-001")]
        count = save_repos(repos)
        assert count == 1

    def test_idempotent_on_duplicate(self):
        url = "https://github.com/org/repo-gh-idem001"
        first = save_repos([self._repo_dict(url)])
        second = save_repos([self._repo_dict(url)])
        assert first == 1
        assert second == 0

    def test_skips_entry_without_url(self):
        count = save_repos([self._repo_dict("")])
        assert count == 0

    def test_intra_batch_duplicate_does_not_raise(self):
        url = "https://github.com/org/repo-gh-batchdup"
        count = save_repos([self._repo_dict(url), self._repo_dict(url)])
        assert count == 1
