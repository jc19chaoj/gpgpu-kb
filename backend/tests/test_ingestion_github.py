# tests/test_ingestion_github.py
"""Tests for kb/ingestion/github_trending.py — no network, httpx patched."""
from __future__ import annotations

import datetime
from contextlib import contextmanager
from unittest.mock import MagicMock, patch, call

import pytest

from kb.ingestion.github_trending import fetch_trending_repos, save_repos, _build_headers
from kb.models import Paper, SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(full_name: str, owner_type: str = "User", topics: list | None = None) -> dict:
    owner_login = full_name.split("/")[0]
    return {
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "description": f"Description for {full_name}",
        "pushed_at": "2026-04-25T10:00:00Z",
        "owner": {"login": owner_login, "type": owner_type},
        "topics": topics or [],
    }


def _mock_response(status_code: int = 200, json_data: dict | None = None, headers: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {"total_count": 0, "items": []}
    resp.headers = headers or {}
    resp.text = ""
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError, Request, Response
        resp.raise_for_status.side_effect = HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=MagicMock(status_code=status_code),
        )
    return resp


@contextmanager
def _patch_httpx_client(responses: list[MagicMock]):
    """Patch httpx.Client as a context manager whose .get() returns responses in order."""
    mock_client = MagicMock()
    mock_client.get.side_effect = responses

    with patch("kb.ingestion.github_trending.httpx.Client") as MockHttpxClient:
        MockHttpxClient.return_value.__enter__ = MagicMock(return_value=mock_client)
        MockHttpxClient.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_client


# ---------------------------------------------------------------------------
# _build_headers
# ---------------------------------------------------------------------------

class TestBuildHeaders:
    def test_includes_authorization_when_token_set(self):
        with patch("kb.ingestion.github_trending.settings") as mock_settings:
            mock_settings.github_token = "ghp_test_token"
            headers = _build_headers()
        assert headers.get("Authorization") == "Bearer ghp_test_token"

    def test_no_authorization_header_when_token_unset(self):
        with patch("kb.ingestion.github_trending.settings") as mock_settings:
            mock_settings.github_token = None
            headers = _build_headers()
        assert "Authorization" not in headers

    def test_accept_header_always_present(self):
        with patch("kb.ingestion.github_trending.settings") as mock_settings:
            mock_settings.github_token = None
            headers = _build_headers()
        assert "Accept" in headers


# ---------------------------------------------------------------------------
# fetch_trending_repos
# ---------------------------------------------------------------------------

class TestFetchTrendingRepos:
    def test_repos_returned_on_success(self):
        item = _make_item("org/cuda-kernels", owner_type="Organization", topics=["cuda"])
        resp = _mock_response(200, {"total_count": 1, "items": [item]})

        with patch("kb.ingestion.github_trending.KEYWORDS", ["cuda"]):
            with patch("kb.ingestion.github_trending.time.sleep"):
                with _patch_httpx_client([resp]):
                    repos = fetch_trending_repos()

        assert len(repos) == 1
        r = repos[0]
        assert r["title"] == "org/cuda-kernels"
        assert r["source_type"] == SourceType.PROJECT
        assert r["source_name"] == "github"
        assert r["url"] == "https://github.com/org/cuda-kernels"
        assert r["organizations"] == ["org"]

    def test_user_owner_has_empty_organizations(self):
        item = _make_item("user/triton-exp", owner_type="User")
        resp = _mock_response(200, {"total_count": 1, "items": [item]})

        with patch("kb.ingestion.github_trending.KEYWORDS", ["triton"]):
            with patch("kb.ingestion.github_trending.time.sleep"):
                with _patch_httpx_client([resp]):
                    repos = fetch_trending_repos()

        assert repos[0]["organizations"] == []

    def test_rate_limit_403_short_circuits_loop(self):
        rate_limit_resp = _mock_response(
            status_code=403,
            json_data={"message": "api rate limit exceeded"},
            headers={"X-RateLimit-Reset": "1745000000"},
        )
        rate_limit_resp.text = "api rate limit exceeded"
        rate_limit_resp.raise_for_status = MagicMock()  # 403 handled before raise_for_status

        with patch("kb.ingestion.github_trending.KEYWORDS", ["cuda", "triton", "mlir"]):
            with patch("kb.ingestion.github_trending.time.sleep"):
                with _patch_httpx_client([rate_limit_resp]) as mock_client:
                    repos = fetch_trending_repos()
                    # Only one call should have been made before aborting
                    assert mock_client.get.call_count == 1

        assert repos == []

    def test_time_sleep_called_between_keywords(self):
        resp1 = _mock_response(200, {"total_count": 0, "items": []})
        resp2 = _mock_response(200, {"total_count": 0, "items": []})

        with patch("kb.ingestion.github_trending.KEYWORDS", ["cuda", "triton"]):
            with patch("kb.ingestion.github_trending.time.sleep") as mock_sleep:
                with _patch_httpx_client([resp1, resp2]):
                    fetch_trending_repos()

        assert mock_sleep.call_count == 2

    def test_http_error_skips_keyword_continues_loop(self):
        from httpx import HTTPStatusError
        err_resp = _mock_response(422)
        ok_resp  = _mock_response(200, {"total_count": 1, "items": [_make_item("user/repo2")]})

        with patch("kb.ingestion.github_trending.KEYWORDS", ["bad-kw", "cuda"]):
            with patch("kb.ingestion.github_trending.time.sleep"):
                with _patch_httpx_client([err_resp, ok_resp]):
                    repos = fetch_trending_repos()

        # The second keyword should still produce a result
        assert len(repos) == 1
        assert repos[0]["title"] == "user/repo2"

    def test_authorization_header_sent_with_token(self):
        resp = _mock_response(200, {"total_count": 0, "items": []})

        with patch("kb.ingestion.github_trending.KEYWORDS", ["cuda"]):
            with patch("kb.ingestion.github_trending.time.sleep"):
                with patch("kb.ingestion.github_trending.settings") as mock_settings:
                    mock_settings.github_token = "ghp_abc123"
                    with _patch_httpx_client([resp]) as mock_client:
                        fetch_trending_repos()

        call_kwargs = mock_client.get.call_args
        headers_sent = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert headers_sent.get("Authorization") == "Bearer ghp_abc123"

    def test_no_authorization_header_without_token(self):
        resp = _mock_response(200, {"total_count": 0, "items": []})

        with patch("kb.ingestion.github_trending.KEYWORDS", ["cuda"]):
            with patch("kb.ingestion.github_trending.time.sleep"):
                with patch("kb.ingestion.github_trending.settings") as mock_settings:
                    mock_settings.github_token = None
                    with _patch_httpx_client([resp]) as mock_client:
                        fetch_trending_repos()

        call_kwargs = mock_client.get.call_args
        headers_sent = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
        assert "Authorization" not in headers_sent

    def test_days_back_param_shifts_pushed_cutoff(self):
        """fetch_trending_repos(days_back=N) sets `pushed:>(today-N days)` in
        the search query — letting the orchestrator widen the window after
        long gaps."""
        resp = _mock_response(200, {"total_count": 0, "items": []})
        expected_cutoff = (
            datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10)
        ).strftime("%Y-%m-%d")

        with patch("kb.ingestion.github_trending.KEYWORDS", ["cuda"]):
            with patch("kb.ingestion.github_trending.time.sleep"):
                with _patch_httpx_client([resp]) as mock_client:
                    fetch_trending_repos(days_back=10)

        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params") or call_kwargs[1].get("params")
        assert f"pushed:>{expected_cutoff}" in params["q"]


# ---------------------------------------------------------------------------
# save_repos
# ---------------------------------------------------------------------------

class TestSaveRepos:
    def _repo_dict(self, url: str, title: str = "org/repo") -> dict:
        return {
            "title": title,
            "authors": ["org"],
            "organizations": ["org"],
            "abstract": "A repo description",
            "url": url,
            "pdf_url": "",
            "source_type": SourceType.PROJECT,
            "source_name": "github",
            "published_date": datetime.datetime.now(datetime.UTC),
            "categories": ["cuda"],
            "venue": "",
        }

    def test_saves_new_repos(self):
        repos = [self._repo_dict("https://github.com/org/repo-gh-001")]
        count = save_repos(repos)
        assert count == 1

    def test_idempotent_on_duplicate(self):
        url = "https://github.com/org/repo-gh-idem001"
        first  = save_repos([self._repo_dict(url)])
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
