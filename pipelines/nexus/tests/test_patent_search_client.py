"""Tests for nexus.resources.patentsview.PatentSearchClient."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from nexus.resources.patentsview import MAX_RETRY_WAIT_S, PatentSearchClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_KEY = "test-api-key-123"


def _make_client() -> PatentSearchClient:
    return PatentSearchClient(api_key=_FAKE_KEY)


def _mock_response(
    status: int, body: dict[str, Any], headers: dict[str, str] | None = None
) -> MagicMock:
    resp: MagicMock = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = body
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# get() — auth header
# ---------------------------------------------------------------------------


def test_get_sends_api_key_header() -> None:
    """X-Api-Key header is always included in the request."""
    ok = _mock_response(200, {"hits": []})
    with patch("nexus.resources.patentsview.httpx.get", return_value=ok) as mock_get:
        _make_client().get("patent/")
    assert mock_get.call_args.kwargs["headers"]["X-Api-Key"] == _FAKE_KEY


def test_get_returns_parsed_json() -> None:
    """200 response returns the parsed JSON body."""
    body = {"hits": [{"patent_id": "9999999"}], "total": 1}
    ok = _mock_response(200, body)
    with patch("nexus.resources.patentsview.httpx.get", return_value=ok):
        result = _make_client().get("patent/")
    assert result == body


def test_get_uses_base_url() -> None:
    """URL is constructed from base_url + endpoint."""
    ok = _mock_response(200, {})
    with patch("nexus.resources.patentsview.httpx.get", return_value=ok) as mock_get:
        _make_client().get("patent/9999999")
    url: str = mock_get.call_args.args[0]
    assert "search.patentsview.org" in url
    assert "patent/9999999" in url


# ---------------------------------------------------------------------------
# get() — retry / backoff
# ---------------------------------------------------------------------------


def test_get_retries_on_429_short_wait() -> None:
    """429 with Retry-After below threshold sleeps then retries successfully."""
    rate_limited = _mock_response(429, {}, headers={"Retry-After": "2"})
    ok = _mock_response(200, {"hits": []})

    with patch("nexus.resources.patentsview.httpx.get", side_effect=[rate_limited, ok]):
        with patch("nexus.resources.patentsview.time.sleep") as mock_sleep:
            result = _make_client().get("patent/")

    mock_sleep.assert_called_once_with(2)
    assert result == {"hits": []}


def test_get_raises_on_429_long_wait() -> None:
    """429 with Retry-After above threshold raises RuntimeError immediately."""
    long_wait = MAX_RETRY_WAIT_S + 1
    rate_limited = _mock_response(429, {}, headers={"Retry-After": str(long_wait)})

    with patch("nexus.resources.patentsview.httpx.get", return_value=rate_limited):
        with patch("nexus.resources.patentsview.time.sleep"):
            with pytest.raises(RuntimeError, match="rate-limited"):
                _make_client().get("patent/")


def test_get_raises_after_all_retries_exhausted() -> None:
    """If every attempt returns 429 with short wait, RuntimeError is raised."""
    rate_limited = _mock_response(429, {}, headers={"Retry-After": "1"})

    with patch("nexus.resources.patentsview.httpx.get", return_value=rate_limited):
        with patch("nexus.resources.patentsview.time.sleep"):
            with pytest.raises(RuntimeError, match="failed after"):
                _make_client().get("patent/")


# ---------------------------------------------------------------------------
# paginate() — cursor threading
# ---------------------------------------------------------------------------


def test_paginate_single_page() -> None:
    """Single page with no 'next' cursor yields its hits and stops."""
    body = {"hits": [{"patent_id": "1"}, {"patent_id": "2"}], "next": None}
    ok = _mock_response(200, body)

    with patch("nexus.resources.patentsview.httpx.get", return_value=ok):
        records = list(_make_client().paginate("patent/", per_page=100))

    assert len(records) == 2
    assert records[0]["patent_id"] == "1"


def test_paginate_two_pages_threads_cursor() -> None:
    """Second page request carries the _after cursor from the first response."""
    page1 = _mock_response(
        200, {"hits": [{"patent_id": str(i)} for i in range(2)], "next": "cursor-abc"}
    )
    page2 = _mock_response(200, {"hits": [{"patent_id": "99"}], "next": None})

    with patch("nexus.resources.patentsview.httpx.get", side_effect=[page1, page2]) as mock_get:
        records = list(_make_client().paginate("patent/", per_page=2))

    assert len(records) == 3
    assert mock_get.call_args_list[1].kwargs["params"]["_after"] == "cursor-abc"


def test_paginate_stops_when_page_is_short() -> None:
    """Stops when a page returns fewer hits than per_page (no cursor needed)."""
    body = {"hits": [{"patent_id": "1"}]}  # 1 hit, per_page=10 → done
    ok = _mock_response(200, body)

    with patch("nexus.resources.patentsview.httpx.get", return_value=ok) as mock_get:
        records = list(_make_client().paginate("patent/", per_page=10))

    assert len(records) == 1
    assert mock_get.call_count == 1
