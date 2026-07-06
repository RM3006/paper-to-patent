"""Tests for the warehouse connection-target selection (dev.duckdb vs MotherDuck)."""

import pathlib

import duckdb
import pytest

from nexus.resources.warehouse import connect_warehouse, warehouse_target


def test_warehouse_target_motherduck(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "tok")
    monkeypatch.setenv("MOTHERDUCK_DATABASE", "custom_db")
    assert warehouse_target() == "md:custom_db"


def test_warehouse_target_default_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTHERDUCK_TOKEN", "tok")
    monkeypatch.delenv("MOTHERDUCK_DATABASE", raising=False)
    assert warehouse_target() == "md:paper_to_patent"


def test_warehouse_target_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    monkeypatch.setenv("DBT_DUCKDB_PATH", "build/dev.duckdb")
    assert warehouse_target() == "build/dev.duckdb"


def test_connect_warehouse_missing_local_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    monkeypatch.setenv("DBT_DUCKDB_PATH", str(tmp_path / "nope.duckdb"))
    with pytest.raises(FileNotFoundError):
        connect_warehouse()


def test_connect_warehouse_opens_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.delenv("MOTHERDUCK_TOKEN", raising=False)
    db = tmp_path / "dev.duckdb"
    duckdb.connect(str(db)).close()  # create a valid, empty database file
    monkeypatch.setenv("DBT_DUCKDB_PATH", str(db))
    con = connect_warehouse()
    try:
        row = con.execute("SELECT 1 AS x").fetchone()
        assert row is not None
        assert row[0] == 1
    finally:
        con.close()
