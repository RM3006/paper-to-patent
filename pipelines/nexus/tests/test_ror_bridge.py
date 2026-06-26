"""Tests for ror_bridge pure helpers."""

import polars as pl
import pytest

from nexus.assets.entity_resolution.ror_bridge import (
    _tokens_match,  # type: ignore[reportPrivateUsage]
    build_ror_bridge,
    get_pv_only_orgs,
)

# ---------------------------------------------------------------------------
# _tokens_match
# ---------------------------------------------------------------------------


def test_tokens_match_subset():
    assert _tokens_match("IBM", "IBM Research - Almaden") is True


def test_tokens_match_exact():
    assert _tokens_match("Samsung Display", "Samsung Display") is True


def test_tokens_match_geographic_qualifier():
    assert _tokens_match("Samsung Display", "Samsung Display America") is True


def test_tokens_match_rejects_parent():
    # "Samsung Display" tokens must all appear in result — "Samsung" alone is not enough
    assert _tokens_match("Samsung Display", "Samsung") is False


def test_tokens_match_rejects_sibling():
    assert _tokens_match("Samsung Display", "Samsung Electronics") is False


def test_tokens_match_empty_canonical():
    assert _tokens_match("", "IBM Research") is False


# ---------------------------------------------------------------------------
# get_pv_only_orgs
# ---------------------------------------------------------------------------


def _seed_df(rows: list[tuple[str, str, str]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=["org_id", "canonical_name", "assignee_id"], orient="row")


def _seed_oa_df(org_ids: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [(o, f"https://openalex.org/I{i}") for i, o in enumerate(org_ids)],
        schema=["org_id", "institution_id"],
        orient="row",
    )


def _fuzzy_df(assignee_ids: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [("some_institution", a) for a in assignee_ids],
        schema=["institution_id", "assignee_id"],
        orient="row",
    )


def test_get_pv_only_orgs_basic():
    seed = _seed_df([("org_ibm", "IBM", "asgn_ibm"), ("org_asml", "ASML", "asgn_asml")])
    seed_oa = _seed_oa_df(["org_asml"])  # ASML already has OA entry
    fuzzy = pl.DataFrame(schema={"institution_id": pl.String, "assignee_id": pl.String})
    result = get_pv_only_orgs(seed, seed_oa, fuzzy)
    assert len(result) == 1
    assert result[0]["org_id"] == "org_ibm"


def test_get_pv_only_orgs_fuzzy_covered():
    seed = _seed_df([("org_ibm", "IBM", "asgn_ibm"), ("org_asml", "ASML", "asgn_asml")])
    seed_oa = pl.DataFrame(schema={"org_id": pl.String, "institution_id": pl.String})
    fuzzy = _fuzzy_df(["asgn_asml"])  # ASML covered via fuzzy bridge
    result = get_pv_only_orgs(seed, seed_oa, fuzzy)
    assert len(result) == 1
    assert result[0]["org_id"] == "org_ibm"


def test_get_pv_only_orgs_all_covered():
    seed = _seed_df([("org_ibm", "IBM", "asgn_ibm")])
    seed_oa = _seed_oa_df(["org_ibm"])
    fuzzy = pl.DataFrame(schema={"institution_id": pl.String, "assignee_id": pl.String})
    result = get_pv_only_orgs(seed, seed_oa, fuzzy)
    assert result == []


# ---------------------------------------------------------------------------
# build_ror_bridge
# ---------------------------------------------------------------------------


def _mock_query_ibm(name: str, mailto: str) -> list[dict[str, str]]:
    if name == "IBM":
        return [
            {"id": "https://openalex.org/I4210085935", "display_name": "IBM Research - Almaden"},
            {"id": "https://openalex.org/I1341412227", "display_name": "IBM (United States)"},
            {"id": "https://openalex.org/I4210156936", "display_name": "IBM Research - Austin"},
            {"id": "https://openalex.org/IOTHER", "display_name": "Totally Unrelated Corp"},
        ]
    return []


def test_build_ror_bridge_ibm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "nexus.assets.entity_resolution.ror_bridge._REQUEST_DELAY_S", 0.0
    )
    pv_only = [{"org_id": "org_ibm", "canonical_name": "IBM"}]
    df = build_ror_bridge(pv_only, "test@test.com", query_fn=_mock_query_ibm, request_delay_s=0.0)

    assert len(df) == 3  # Totally Unrelated Corp rejected
    assert set(df["org_id"].to_list()) == {"org_ibm"}
    assert "https://openalex.org/IOTHER" not in df["institution_id"].to_list()
    assert all(m == "ror_bridge" for m in df["match_method"].to_list())
    assert all(c == "high" for c in df["confidence"].to_list())


def test_build_ror_bridge_specificity_ordering() -> None:
    """More-specific orgs claim institutions before less-specific parent orgs can absorb them."""

    def mock_query(name: str, mailto: str) -> list[dict[str, str]]:
        if name == "Samsung Display":
            return [
                {"id": "https://openalex.org/I_SD", "display_name": "Samsung Display"},
                {"id": "https://openalex.org/I_SDA", "display_name": "Samsung Display America"},
            ]
        if name == "Samsung":
            return [
                {"id": "https://openalex.org/I_SE", "display_name": "Samsung Electronics"},
                # already claimed by org_samsung_display:
                {"id": "https://openalex.org/I_SD", "display_name": "Samsung Display"},
            ]
        return []

    pv_only = [
        {"org_id": "org_samsung_display", "canonical_name": "Samsung Display"},
        {"org_id": "org_samsung", "canonical_name": "Samsung"},
    ]
    df = build_ror_bridge(pv_only, "test@test.com", query_fn=mock_query, request_delay_s=0.0)

    sd_rows = df.filter(pl.col("org_id") == "org_samsung_display")
    samsung_rows = df.filter(pl.col("org_id") == "org_samsung")

    assert "https://openalex.org/I_SD" in sd_rows["institution_id"].to_list()
    assert "https://openalex.org/I_SE" in samsung_rows["institution_id"].to_list()
    # I_SD must NOT be claimed twice
    assert "https://openalex.org/I_SD" not in samsung_rows["institution_id"].to_list()


def test_build_ror_bridge_no_results() -> None:
    def mock_query(name: str, mailto: str) -> list[dict[str, str]]:
        return []

    df = build_ror_bridge(
        [{"org_id": "org_troll", "canonical_name": "Strong Force IoT Portfolio"}],
        "test@test.com",
        query_fn=mock_query,
        request_delay_s=0.0,
    )
    assert len(df) == 0


def test_build_ror_bridge_empty_input() -> None:
    df = build_ror_bridge([], "test@test.com", request_delay_s=0.0)
    assert len(df) == 0
