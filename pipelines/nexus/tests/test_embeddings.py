"""Tests for the document_embeddings asset pure helpers."""

from collections.abc import Generator

import duckdb
import pytest

from nexus.assets.ml.embeddings import is_truncated, load_corpus

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
# load_corpus
# ---------------------------------------------------------------------------


@pytest.fixture()
def corpus_db() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """In-memory DuckDB mirroring the mart schema queried by load_corpus."""
    con = duckdb.connect()
    con.execute("CREATE SCHEMA main_marts")
    con.execute(
        "CREATE TABLE main_marts.dim_paper (work_id VARCHAR, abstract VARCHAR)"
    )
    con.execute(
        "CREATE TABLE main_marts.dim_patent (patent_id VARCHAR, title VARCHAR)"
    )
    # W001: good abstract; W002: NULL abstract (skip); W003: empty abstract (skip)
    con.execute("""
        INSERT INTO main_marts.dim_paper VALUES
            ('W001', 'Advances in EUV lithography for semiconductor fabrication.'),
            ('W002', NULL),
            ('W003', '');
    """)
    # P001: good title; P002: NULL title (skip)
    con.execute("""
        INSERT INTO main_marts.dim_patent VALUES
            ('P001', 'High-performance memristive memory device'),
            ('P002', NULL);
    """)
    yield con
    con.close()


def test_load_corpus_skips_nulls_and_empty(
    corpus_db: duckdb.DuckDBPyConnection,
) -> None:
    corpus = load_corpus(corpus_db)
    # W002 (NULL), W003 (empty), P002 (NULL) are all skipped
    assert len(corpus) == 2


def test_load_corpus_paper_fields(corpus_db: duckdb.DuckDBPyConnection) -> None:
    corpus = load_corpus(corpus_db)
    paper = next(d for d in corpus if d["doc_type"] == "paper")
    assert paper["doc_id"] == "W001"
    assert paper["text_source"] == "abstract"
    assert paper["text"] == "Advances in EUV lithography for semiconductor fabrication."


def test_load_corpus_patent_fields(corpus_db: duckdb.DuckDBPyConnection) -> None:
    corpus = load_corpus(corpus_db)
    patent = next(d for d in corpus if d["doc_type"] == "patent")
    assert patent["doc_id"] == "P001"
    assert patent["text_source"] == "title"
    assert patent["text"] == "High-performance memristive memory device"


def test_load_corpus_all_required_keys(corpus_db: duckdb.DuckDBPyConnection) -> None:
    corpus = load_corpus(corpus_db)
    required = {"doc_id", "doc_type", "text_source", "text"}
    for doc in corpus:
        assert required == set(doc.keys())
