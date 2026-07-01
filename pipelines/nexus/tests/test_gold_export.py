"""Tests for gold_export pure helpers."""

from nexus.assets.transform.gold_export import (
    _GOLD_MODELS,  # type: ignore[reportPrivateUsage]
    _gold_r2_path,  # type: ignore[reportPrivateUsage]
)


def test_gold_r2_path_dims() -> None:
    path = _gold_r2_path("p2p-lake", "dim_paper", "dims", "2026-06-26")
    assert path == "r2://p2p-lake/gold/dims/dim_paper/v2026-06-26/dim_paper.parquet"


def test_gold_r2_path_facts() -> None:
    path = _gold_r2_path("p2p-lake", "fact_npl_link", "facts", "2026-06-26")
    assert path == "r2://p2p-lake/gold/facts/fact_npl_link/v2026-06-26/fact_npl_link.parquet"


def test_gold_models_contains_all_dims() -> None:
    expected_dims = {
        "dim_cpc", "dim_organization", "dim_paper",
        "dim_patent", "dim_technology_cluster",
    }
    actual_dims = {m for m, sub in _GOLD_MODELS.items() if sub == "dims"}
    assert actual_dims == expected_dims


def test_gold_models_contains_all_facts() -> None:
    expected_facts = {
        "fact_document_cluster", "fact_npl_link", "fact_patent_citation",
        "fact_patent_filing", "fact_publication",
    }
    actual_facts = {m for m, sub in _GOLD_MODELS.items() if sub == "facts"}
    assert actual_facts == expected_facts


def test_gold_models_subdirs_are_only_dims_or_facts() -> None:
    for model, subdir in _GOLD_MODELS.items():
        assert subdir in ("dims", "facts", "marts", "seeds"), f"{model} has unexpected subdir: {subdir}"


def test_gold_models_contains_all_marts() -> None:
    expected_marts = {"mart_competitive", "mart_family", "mart_gap", "mart_velocity"}
    actual_marts = {m for m, sub in _GOLD_MODELS.items() if sub == "marts"}
    assert actual_marts == expected_marts
