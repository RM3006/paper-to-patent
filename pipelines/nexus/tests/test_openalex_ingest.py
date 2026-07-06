"""Tests for nexus.assets.ingest.openalex — written before the implementation."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx

from nexus.assets.ingest.openalex import (
    MAX_RETRY_WAIT_S,
    delete_r2_object,
    paginate_works,
    parse_work,
    reconstruct_abstract,
)

# ---------------------------------------------------------------------------
# reconstruct_abstract
# ---------------------------------------------------------------------------


def test_reconstruct_abstract_basic() -> None:
    inv = {"Hello": [0], "world": [1]}
    assert reconstruct_abstract(inv) == "Hello world"


def test_reconstruct_abstract_repeated_word() -> None:
    # Word appearing at multiple positions
    inv = {"the": [0, 3], "cat": [1], "sat": [2]}
    assert reconstruct_abstract(inv) == "the cat sat the"


def test_reconstruct_abstract_empty() -> None:
    assert reconstruct_abstract({}) == ""


def test_reconstruct_abstract_single_token() -> None:
    assert reconstruct_abstract({"Abstract": [0]}) == "Abstract"


def test_reconstruct_abstract_gap_positions() -> None:
    # Positions 0 and 2 only — position 1 is empty string (gap)
    inv = {"start": [0], "end": [2]}
    result = reconstruct_abstract(inv)
    parts = result.split(" ")
    assert parts[0] == "start"
    assert parts[2] == "end"
    assert len(parts) == 3


# ---------------------------------------------------------------------------
# parse_work
# ---------------------------------------------------------------------------

FIXTURE_WORK: dict[str, Any] = {
    "id": "https://openalex.org/W1234567",
    "doi": "https://doi.org/10.1234/test.paper",
    "title": "Advances in EUV Lithography",
    "type": "article",
    "publication_date": "2021-06-15",
    "publication_year": 2021,
    "language": "en",
    "abstract_inverted_index": {
        "This": [0],
        "paper": [1],
        "discusses": [2],
        "EUV": [3],
    },
    "primary_topic": {
        "id": "https://openalex.org/T11338",
        "display_name": "Advancements in Photolithography Techniques",
    },
    "authorships": [
        {
            "institutions": [
                {
                    "id": "https://openalex.org/I136199984",
                    "ror": "https://ror.org/01nrxwf90",
                    "display_name": "MIT",
                }
            ]
        },
        {
            "institutions": [
                {
                    "id": "https://openalex.org/I63966007",
                    "ror": "https://ror.org/042nb2s44",
                    "display_name": "Stanford University",
                }
            ]
        },
    ],
}


def test_parse_work_scalar_fields() -> None:
    record = parse_work(FIXTURE_WORK)
    assert record["openalex_id"] == "https://openalex.org/W1234567"
    assert record["doi"] == "https://doi.org/10.1234/test.paper"
    assert record["title"] == "Advances in EUV Lithography"
    assert record["publication_date"] == "2021-06-15"
    assert record["publication_year"] == 2021
    assert record["language"] == "en"


def test_parse_work_abstract_reconstructed() -> None:
    record = parse_work(FIXTURE_WORK)
    assert record["abstract"] == "This paper discusses EUV"


def test_parse_work_topic_fields() -> None:
    record = parse_work(FIXTURE_WORK)
    assert record["primary_topic_id"] == "https://openalex.org/T11338"
    assert "Photolithography" in record["primary_topic_name"]


def test_parse_work_institutions_collected() -> None:
    record = parse_work(FIXTURE_WORK)
    assert len(record["institution_ids"]) == 2
    assert len(record["institution_rors"]) == 2
    assert len(record["institution_display_names"]) == 2
    assert "https://openalex.org/I136199984" in record["institution_ids"]
    assert "https://ror.org/042nb2s44" in record["institution_rors"]
    assert "MIT" in record["institution_display_names"]
    assert "Stanford University" in record["institution_display_names"]


def test_parse_work_missing_abstract() -> None:
    work: dict[str, Any] = {**FIXTURE_WORK, "abstract_inverted_index": None}
    record = parse_work(work)
    assert record["abstract"] is None


def test_parse_work_type_field() -> None:
    record = parse_work(FIXTURE_WORK)
    assert record["type"] == "article"


def test_parse_work_missing_type() -> None:
    work: dict[str, Any] = {k: v for k, v in FIXTURE_WORK.items() if k != "type"}
    record = parse_work(work)
    assert record["type"] is None


def test_parse_work_no_institutions() -> None:
    work: dict[str, Any] = {**FIXTURE_WORK, "authorships": []}
    record = parse_work(work)
    assert record["institution_ids"] == []
    assert record["institution_rors"] == []
    assert record["institution_display_names"] == []


def test_parse_work_no_topic() -> None:
    work: dict[str, Any] = {**FIXTURE_WORK, "primary_topic": None}
    record = parse_work(work)
    assert record["primary_topic_id"] is None
    assert record["primary_topic_name"] is None


# ---------------------------------------------------------------------------
# paginate_works — HTTP layer (mocked)
# ---------------------------------------------------------------------------


def _make_page(results: list[dict[str, Any]], next_cursor: str | None) -> MagicMock:
    """Build a mock httpx Response for one OpenAlex page."""
    resp: MagicMock = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"results": results, "meta": {"next_cursor": next_cursor}}
    resp.raise_for_status = MagicMock()
    return resp


def test_paginate_works_single_page() -> None:
    """Single page with null cursor yields results then stops."""
    client: MagicMock = MagicMock(spec=httpx.Client)
    client.get.return_value = _make_page([FIXTURE_WORK], next_cursor=None)

    with patch("nexus.assets.ingest.openalex.time.sleep"):
        works = list(paginate_works(client, "test-filter", "test@example.com"))

    assert len(works) == 1
    assert works[0]["id"] == FIXTURE_WORK["id"]
    assert client.get.call_count == 1


def test_paginate_works_two_pages() -> None:
    """Cursor is threaded across pages; stops when next_cursor is None."""
    client: MagicMock = MagicMock(spec=httpx.Client)
    client.get.side_effect = [
        _make_page([FIXTURE_WORK], next_cursor="cursor-abc"),
        _make_page([FIXTURE_WORK], next_cursor=None),
    ]

    with patch("nexus.assets.ingest.openalex.time.sleep"):
        works = list(paginate_works(client, "test-filter", "test@example.com"))

    assert len(works) == 2
    assert client.get.call_count == 2
    # Second call must carry the cursor from the first response
    second_call_params: dict[str, Any] = client.get.call_args_list[1].kwargs["params"]
    assert second_call_params["cursor"] == "cursor-abc"


def test_paginate_works_429_short_wait_retries() -> None:
    """429 with Retry-After below threshold sleeps then retries successfully."""
    client: MagicMock = MagicMock(spec=httpx.Client)

    rate_limited: MagicMock = MagicMock(spec=httpx.Response)
    rate_limited.status_code = 429
    rate_limited.headers = {"Retry-After": "5"}

    ok: MagicMock = _make_page([FIXTURE_WORK], next_cursor=None)

    client.get.side_effect = [rate_limited, ok]

    with patch("nexus.assets.ingest.openalex.time.sleep") as mock_sleep:
        works = list(paginate_works(client, "test-filter", "test@example.com"))

    assert len(works) == 1
    mock_sleep.assert_called_once_with(5)
    assert client.get.call_count == 2


# ---------------------------------------------------------------------------
# delete_r2_object
# ---------------------------------------------------------------------------


def test_delete_r2_object_success() -> None:
    """200 response does not raise."""
    mock_resp: MagicMock = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    with patch("nexus.assets.ingest.openalex.httpx.delete", return_value=mock_resp) as mock_del:
        delete_r2_object("acct", "token", "bucket", "raw/works.parquet")
    mock_del.assert_called_once()


def test_delete_r2_object_404_is_ok() -> None:
    """404 (already gone) is treated as success."""
    mock_resp: MagicMock = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404
    with patch("nexus.assets.ingest.openalex.httpx.delete", return_value=mock_resp):
        delete_r2_object("acct", "token", "bucket", "raw/works.parquet")  # must not raise


def test_delete_r2_object_error_raises() -> None:
    """Non-200/204/404 status raises RuntimeError."""
    mock_resp: MagicMock = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 403
    mock_resp.text = "Forbidden"
    with patch("nexus.assets.ingest.openalex.httpx.delete", return_value=mock_resp):
        import pytest as _pytest

        with _pytest.raises(RuntimeError, match="Failed to delete"):
            delete_r2_object("acct", "token", "bucket", "raw/works.parquet")


def test_paginate_works_429_long_wait_raises() -> None:
    """429 with Retry-After above threshold raises RuntimeError immediately."""
    client: MagicMock = MagicMock(spec=httpx.Client)

    rate_limited: MagicMock = MagicMock(spec=httpx.Response)
    rate_limited.status_code = 429
    rate_limited.headers = {"Retry-After": str(MAX_RETRY_WAIT_S + 1)}

    client.get.return_value = rate_limited

    import pytest as _pytest

    with patch("nexus.assets.ingest.openalex.time.sleep"):
        with _pytest.raises(RuntimeError, match="rate-limited|cooldown"):
            list(paginate_works(client, "test-filter", "test@example.com"))
