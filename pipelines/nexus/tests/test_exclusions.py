"""Tests for the document_exclusions pure gate (compute_exclusions)."""

from nexus.assets.ml.exclusions import compute_exclusions

_GOOD_ABSTRACT = (
    "Advances in EUV lithography for semiconductor fabrication, focusing on "
    "photoresist chemistry and pattern transfer at sub-10nm feature sizes for "
    "next-generation microchip manufacturing processes."
)
_GOOD_TITLE = "Advances in EUV Lithography for Semiconductor Fabrication"
_FRENCH_TITLE = "Etude de la commutation resistive dans les oxydes"
_FRENCH_ABSTRACT = (
    "Cette etude examine les proprietes de commutation resistive dans les "
    "dispositifs a base d'oxydes metalliques pour applications memoire non "
    "volatile et les mecanismes physiques sous-jacents."
)


def _by_id(excluded: list[dict[str, str]], doc_id: str) -> dict[str, str] | None:
    return next((d for d in excluded if d["doc_id"] == doc_id), None)


def test_compute_exclusions_keeps_good_paper() -> None:
    excluded = compute_exclusions([("W001", _GOOD_TITLE, _GOOD_ABSTRACT)], [])
    assert excluded == []


def test_compute_exclusions_version_style_paper() -> None:
    excluded = compute_exclusions([("W005", "seL4: seL4 3.0.1", "")], [])
    row = _by_id(excluded, "W005")
    assert row is not None
    assert row["doc_type"] == "paper"
    assert row["exclusion_reason"] == "version_style_title"


def test_compute_exclusions_non_english_paper() -> None:
    excluded = compute_exclusions([("W004", _FRENCH_TITLE, _FRENCH_ABSTRACT)], [])
    row = _by_id(excluded, "W004")
    assert row is not None
    assert row["exclusion_reason"] == "non_english_content"


def test_compute_exclusions_keeps_english_title_french_abstract() -> None:
    # resolve_paper_text falls back to the English title, so this paper is kept.
    excluded = compute_exclusions(
        [("W010", "Study of Resistive Switching in Oxide Memristors", _FRENCH_ABSTRACT)], []
    )
    assert _by_id(excluded, "W010") is None


def test_compute_exclusions_patent_no_title() -> None:
    excluded = compute_exclusions([], [("P002", "")])
    row = _by_id(excluded, "P002")
    assert row is not None
    assert row["doc_type"] == "patent"
    assert row["exclusion_reason"] == "no_usable_text"


def test_compute_exclusions_patent_version_style_title() -> None:
    excluded = compute_exclusions([], [("P003", "libBigWig 0.1.5")])
    row = _by_id(excluded, "P003")
    assert row is not None
    assert row["exclusion_reason"] == "version_style_title"


def test_compute_exclusions_keeps_good_patent() -> None:
    excluded = compute_exclusions([], [("P001", "High-performance memristive memory device")])
    assert excluded == []


def test_compute_exclusions_required_keys() -> None:
    excluded = compute_exclusions(
        [("W004", _FRENCH_TITLE, _FRENCH_ABSTRACT), ("W005", "seL4 3.0.1", "")],
        [("P002", ""), ("P003", "libBigWig 0.1.5")],
    )
    required = {"doc_id", "doc_type", "exclusion_reason"}
    assert excluded  # non-empty
    for doc in excluded:
        assert required == set(doc.keys())
