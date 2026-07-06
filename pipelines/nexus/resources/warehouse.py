"""Connection target for the dbt-built warehouse (staging → intermediate → marts).

Prod: MotherDuck (``md:<MOTHERDUCK_DATABASE>``) when ``MOTHERDUCK_TOKEN`` is set;
      DuckDB's motherduck extension reads the token from the environment on connect.
Dev:  the local ``dev.duckdb`` file (``DBT_DUCKDB_PATH``), opened read-only for readers.

Declared once here so no asset re-derives the dev/prod switch — the same pattern the
Streamlit app uses in ``apps/ui/data.py``, per the CLAUDE.md convention of configuring
the connection in one shared helper rather than per call site.
"""

from __future__ import annotations

import os
import pathlib

import duckdb


def warehouse_target() -> str:
    """DuckDB connection string for the warehouse.

    ``md:<db>`` in prod (``MOTHERDUCK_TOKEN`` set), else the local ``dev.duckdb`` path.
    """
    if os.environ.get("MOTHERDUCK_TOKEN"):
        return f"md:{os.environ.get('MOTHERDUCK_DATABASE', 'paper_to_patent')}"
    return os.environ.get("DBT_DUCKDB_PATH", "dev.duckdb")


def connect_warehouse(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Open a connection to the dbt-built warehouse.

    ``read_only`` applies only to the local ``dev.duckdb`` file; on MotherDuck, access
    is governed by the ``MOTHERDUCK_TOKEN``'s own scope (the app uses a read-only token).
    """
    target = warehouse_target()
    if target.startswith("md:"):
        return duckdb.connect(target)
    path = pathlib.Path(target)
    if not path.exists():
        raise FileNotFoundError(
            f"Warehouse not found at {path}. Run 'dbt build' first, "
            "or set MOTHERDUCK_TOKEN to read from MotherDuck."
        )
    return duckdb.connect(str(path), read_only=read_only)
