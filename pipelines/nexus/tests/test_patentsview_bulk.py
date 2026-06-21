"""Tests for nexus.assets.ingest.patentsview.load_bulk_tsv."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from nexus.assets.ingest.patentsview import load_bulk_tsv

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TSV_CONTENT = (
    "patent_id\tgrant_date\ttitle\n"
    "1\t2020-01-07\tFoo EUV\n"
    "2\t2021-03-02\tBar Photonics\n"
)
_FAKE_URL = "https://example.com/g_test.tsv.zip"


def _write_zip(directory: Path, tsv_name: str, content: str) -> Path:
    """Write a zip containing a single TSV file; return the zip path."""
    zip_path = directory / f"{tsv_name}.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(tsv_name, content)
    zip_path.write_bytes(buf.getvalue())
    return zip_path


# ---------------------------------------------------------------------------
# load_bulk_tsv — local .tsv
# ---------------------------------------------------------------------------


def test_load_from_local_tsv(tmp_path: Path) -> None:
    """When a .tsv already exists in data_dir, it is used without downloading."""
    tsv = tmp_path / "g_test.tsv"
    tsv.write_text(_TSV_CONTENT, encoding="utf-8")

    lf = load_bulk_tsv(_FAKE_URL, ["patent_id", "title"], data_dir=tmp_path)
    df = lf.collect()

    assert df.shape == (2, 3)
    assert df["patent_id"].to_list() == [1, 2]
    assert "title" in df.columns


def test_load_from_local_tsv_row_values(tmp_path: Path) -> None:
    """Values are parsed correctly from the fixture TSV."""
    tsv = tmp_path / "g_test.tsv"
    tsv.write_text(_TSV_CONTENT, encoding="utf-8")

    df = load_bulk_tsv(_FAKE_URL, ["patent_id"], data_dir=tmp_path).collect()

    assert df["title"].to_list() == ["Foo EUV", "Bar Photonics"]


# ---------------------------------------------------------------------------
# load_bulk_tsv — local .tsv.zip
# ---------------------------------------------------------------------------


def test_load_from_local_zip(tmp_path: Path) -> None:
    """When only a .zip exists in data_dir, the TSV is extracted and scanned."""
    _write_zip(tmp_path, "g_test.tsv", _TSV_CONTENT)

    lf = load_bulk_tsv(_FAKE_URL, ["patent_id", "grant_date"], data_dir=tmp_path)
    df = lf.collect()

    assert df.shape[0] == 2
    assert (tmp_path / "g_test.tsv").exists(), "TSV should be extracted to data_dir"


def test_load_from_zip_extracts_once(tmp_path: Path) -> None:
    """Calling load_bulk_tsv twice reuses the extracted .tsv without re-extracting."""
    _write_zip(tmp_path, "g_test.tsv", _TSV_CONTENT)

    load_bulk_tsv(_FAKE_URL, ["patent_id"], data_dir=tmp_path).collect()
    # Delete the zip to prove the second call uses the extracted file
    (tmp_path / "g_test.tsv.zip").unlink()
    df = load_bulk_tsv(_FAKE_URL, ["patent_id"], data_dir=tmp_path).collect()

    assert df.shape[0] == 2


# ---------------------------------------------------------------------------
# load_bulk_tsv — column validation
# ---------------------------------------------------------------------------


def test_missing_required_column_raises(tmp_path: Path) -> None:
    """ValueError is raised when a required column is absent."""
    tsv = tmp_path / "g_test.tsv"
    tsv.write_text(_TSV_CONTENT, encoding="utf-8")

    with pytest.raises(ValueError, match="Missing required columns"):
        load_bulk_tsv(_FAKE_URL, ["patent_id", "nonexistent_col"], data_dir=tmp_path)


def test_missing_column_message_names_columns(tmp_path: Path) -> None:
    """The ValueError message names the missing columns explicitly."""
    tsv = tmp_path / "g_test.tsv"
    tsv.write_text(_TSV_CONTENT, encoding="utf-8")

    with pytest.raises(ValueError, match="nonexistent_col"):
        load_bulk_tsv(_FAKE_URL, ["nonexistent_col"], data_dir=tmp_path)


def test_all_required_columns_present_no_raise(tmp_path: Path) -> None:
    """No exception when all required columns are present."""
    tsv = tmp_path / "g_test.tsv"
    tsv.write_text(_TSV_CONTENT, encoding="utf-8")

    lf = load_bulk_tsv(_FAKE_URL, ["patent_id", "grant_date", "title"], data_dir=tmp_path)
    assert lf is not None
