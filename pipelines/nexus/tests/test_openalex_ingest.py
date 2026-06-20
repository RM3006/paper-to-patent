"""Tests for nexus.assets.ingest.openalex — written before the implementation."""

from __future__ import annotations

from typing import Any

from nexus.assets.ingest.openalex import parse_work, reconstruct_abstract

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
                }
            ]
        },
        {
            "institutions": [
                {
                    "id": "https://openalex.org/I63966007",
                    "ror": "https://ror.org/042nb2s44",
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
    assert "https://openalex.org/I136199984" in record["institution_ids"]
    assert "https://ror.org/042nb2s44" in record["institution_rors"]


def test_parse_work_missing_abstract() -> None:
    work: dict[str, Any] = {**FIXTURE_WORK, "abstract_inverted_index": None}
    record = parse_work(work)
    assert record["abstract"] is None


def test_parse_work_no_institutions() -> None:
    work: dict[str, Any] = {**FIXTURE_WORK, "authorships": []}
    record = parse_work(work)
    assert record["institution_ids"] == []
    assert record["institution_rors"] == []


def test_parse_work_no_topic() -> None:
    work: dict[str, Any] = {**FIXTURE_WORK, "primary_topic": None}
    record = parse_work(work)
    assert record["primary_topic_id"] is None
    assert record["primary_topic_name"] is None
