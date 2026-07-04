"""Tests for the document_embeddings asset pure helpers."""

from collections.abc import Generator

import duckdb
import pytest

from nexus.assets.ml.embeddings import (
    is_truncated,
    is_version_style_title,
    load_corpus,
    resolve_paper_text,
)

# ---------------------------------------------------------------------------
# Mock tokenizer — word-count proxy; avoids downloading the real model in CI
# ---------------------------------------------------------------------------


class _MockTokenizer:
    """Tokenizer that returns one token per whitespace-split word.

    Special tokens are represented as two additional IDs (one at each end).
    Word count + 2 is the exact length when add_special_tokens=True.
    """

    def encode(
        self,
        text: str,
        add_special_tokens: bool = True,
        truncation: bool = False,
    ) -> list[int]:
        words = text.split()
        base = list(range(len(words)))
        return [0, *base, 1] if add_special_tokens else base


@pytest.fixture()
def mock_tokenizer() -> _MockTokenizer:
    return _MockTokenizer()


# ---------------------------------------------------------------------------
# is_truncated
# ---------------------------------------------------------------------------


def test_is_truncated_returns_false_for_short_text(mock_tokenizer: _MockTokenizer) -> None:
    # 5 words + 2 special tokens = 7 tokens; 7 ≤ 256 → not truncated
    assert not is_truncated("one two three four five", mock_tokenizer, max_len=256)


def test_is_truncated_returns_false_at_exact_limit(mock_tokenizer: _MockTokenizer) -> None:
    # 8 words + 2 special = 10 tokens; threshold = 10 → exactly at limit, not truncated
    text = " ".join(f"w{i}" for i in range(8))
    assert not is_truncated(text, mock_tokenizer, max_len=10)


def test_is_truncated_returns_true_one_over_limit(mock_tokenizer: _MockTokenizer) -> None:
    # 9 words + 2 special = 11 tokens; threshold = 10 → truncated
    text = " ".join(f"w{i}" for i in range(9))
    assert is_truncated(text, mock_tokenizer, max_len=10)


# ---------------------------------------------------------------------------
# is_version_style_title
# ---------------------------------------------------------------------------


def test_version_style_title_matches_bare_version() -> None:
    assert is_version_style_title("libBigWig 0.1.5")


def test_version_style_title_matches_v_prefixed_version() -> None:
    assert is_version_style_title("IDBac v0.0.15")


def test_version_style_title_matches_version_with_trailing_note() -> None:
    assert is_version_style_title("seL4 2.10 (minor release)")


def test_version_style_title_rejects_real_paper_title() -> None:
    assert not is_version_style_title(
        "Advances in EUV Lithography for Semiconductor Manufacturing"
    )


def test_version_style_title_rejects_title_with_embedded_number() -> None:
    # A real title mentioning a technology generation shouldn't match —
    # the pattern requires the ENTIRE title to be name + version, not a
    # version-like substring inside a longer descriptive title.
    assert not is_version_style_title(
        "Performance Analysis of 5G NR Release 16 Physical Layer Design"
    )


# ---------------------------------------------------------------------------
# resolve_paper_text — the quality gate
# ---------------------------------------------------------------------------

_GOOD_ABSTRACT = (
    "Advances in EUV lithography for semiconductor fabrication, focusing on "
    "photoresist chemistry and pattern transfer at sub-10nm feature sizes for "
    "next-generation microchip manufacturing processes."
)
_GOOD_TITLE = "Advances in EUV Lithography for Semiconductor Fabrication"


def test_resolve_paper_text_uses_abstract_when_good() -> None:
    result = resolve_paper_text(_GOOD_TITLE, _GOOD_ABSTRACT)
    assert result == (_GOOD_ABSTRACT, "abstract")


def test_resolve_paper_text_falls_back_on_placeholder_abstract() -> None:
    result = resolve_paper_text(_GOOD_TITLE, "Abstract not provided.")
    assert result == (_GOOD_TITLE, "title")


def test_resolve_paper_text_falls_back_on_placeholder_abstract_available_variant() -> None:
    result = resolve_paper_text(_GOOD_TITLE, "Abstract not Available.")
    assert result == (_GOOD_TITLE, "title")


def test_resolve_paper_text_falls_back_on_too_short_abstract() -> None:
    # Real content, but far too short to be a real scientific abstract —
    # doesn't match the placeholder regex, but fails the length floor.
    result = resolve_paper_text(_GOOD_TITLE, "A brief technical note on device performance.")
    assert result == (_GOOD_TITLE, "title")


def test_resolve_paper_text_keeps_short_but_real_abstract_above_floor() -> None:
    # A genuine journal "highlight" sentence (~84 chars) — the kind of real,
    # on-topic, terse abstract found in the corpus sample that motivated
    # lowering the floor from 100 to 50: short, but not a placeholder, and
    # not so thin it should be discarded in favour of the title.
    highlight_abstract = (
        "We present an in-depth analysis of the VeCSELs frequency and the intensity noise."
    )
    result = resolve_paper_text("Noise properties of NIR and MIR VeCSELs", highlight_abstract)
    assert result == (highlight_abstract, "abstract")


def test_resolve_paper_text_excludes_when_placeholder_and_no_title() -> None:
    result = resolve_paper_text("", "Abstract not provided.")
    assert result is None


def test_resolve_paper_text_falls_back_on_non_english_abstract_with_english_title() -> None:
    french_abstract = (
        "Cette etude examine les proprietes de commutation resistive dans les "
        "dispositifs a base d'oxydes metalliques pour applications memoire non "
        "volatile et les mecanismes physiques sous-jacents."
    )
    result = resolve_paper_text("Study of Resistive Switching in Oxide Memristors", french_abstract)
    assert result == ("Study of Resistive Switching in Oxide Memristors", "title")


def test_resolve_paper_text_excludes_when_both_title_and_abstract_non_english() -> None:
    french_title = "Etude de la commutation resistive dans les oxydes"
    french_abstract = (
        "Cette etude examine les proprietes de commutation resistive dans les "
        "dispositifs a base d'oxydes metalliques pour applications memoire non "
        "volatile et les mecanismes physiques sous-jacents."
    )
    result = resolve_paper_text(french_title, french_abstract)
    assert result is None


def test_resolve_paper_text_excludes_version_style_title_regardless_of_abstract() -> None:
    # Even a long, well-formed abstract doesn't save a software-release title —
    # the abstract is release-note prose in these cases, not science.
    release_note_abstract = (
        "Exported the unzoomed statistics functions. This was needed due to an "
        "upstream request. Changed how some of the testing was done, now all "
        "run via a script on Linux and OSX platforms for continuous integration."
    )
    result = resolve_paper_text("libBigWig 0.1.5", release_note_abstract)
    assert result is None


# ---------------------------------------------------------------------------
# load_corpus
# ---------------------------------------------------------------------------


@pytest.fixture()
def corpus_db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB mirroring the mart schema queried by load_corpus."""
    con = duckdb.connect()
    con.execute("CREATE SCHEMA main_marts")
    con.execute(
        "CREATE TABLE main_marts.dim_paper (work_id VARCHAR, title VARCHAR, abstract VARCHAR)"
    )
    con.execute(
        "CREATE TABLE main_marts.dim_patent (patent_id VARCHAR, title VARCHAR)"
    )
    con.execute(
        """
        INSERT INTO main_marts.dim_paper VALUES
            ('W001', ?, ?),
            ('W002', 'Some Title', NULL),
            ('W003', 'Some Title', '');
        """,
        [_GOOD_TITLE, _GOOD_ABSTRACT],
    )
    # P001: good title; P002: NULL title (skip); P003: version-style title (skip)
    con.execute("""
        INSERT INTO main_marts.dim_patent VALUES
            ('P001', 'High-performance memristive memory device'),
            ('P002', NULL),
            ('P003', 'libBigWig 0.1.5');
    """)
    yield con
    con.close()


def test_load_corpus_skips_nulls_and_empty(
    corpus_db: duckdb.DuckDBPyConnection,
) -> None:
    corpus = load_corpus(corpus_db)
    # W002 (NULL abstract), W003 (empty abstract), P002 (NULL title),
    # P003 (version-style title) are all skipped
    assert len(corpus) == 2


def test_load_corpus_paper_fields(corpus_db: duckdb.DuckDBPyConnection) -> None:
    corpus = load_corpus(corpus_db)
    paper = next(d for d in corpus if d["doc_type"] == "paper")
    assert paper["doc_id"] == "W001"
    assert paper["text_source"] == "abstract"
    assert paper["text"] == _GOOD_ABSTRACT


def test_load_corpus_patent_fields(corpus_db: duckdb.DuckDBPyConnection) -> None:
    corpus = load_corpus(corpus_db)
    patent = next(d for d in corpus if d["doc_type"] == "patent")
    assert patent["doc_id"] == "P001"
    assert patent["text_source"] == "title"
    assert patent["text"] == "High-performance memristive memory device"


def test_load_corpus_excludes_version_style_patent_title(
    corpus_db: duckdb.DuckDBPyConnection,
) -> None:
    corpus = load_corpus(corpus_db)
    assert all(d["doc_id"] != "P003" for d in corpus)


def test_load_corpus_all_required_keys(corpus_db: duckdb.DuckDBPyConnection) -> None:
    corpus = load_corpus(corpus_db)
    required = {"doc_id", "doc_type", "text_source", "text"}
    for doc in corpus:
        assert required == set(doc.keys())
