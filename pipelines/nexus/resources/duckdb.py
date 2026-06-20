from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import duckdb
from dagster import ConfigurableResource


class DuckDBR2Resource(ConfigurableResource):  # pyright: ignore[reportMissingTypeArgument]
    """DuckDB connection with the Cloudflare R2 httpfs secret pre-configured.

    Credentials are declared once here and never re-stated per query,
    per the project convention in CLAUDE.md.
    """

    account_id: str
    access_key_id: str
    secret_access_key: str

    @contextmanager
    def get_connection(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        con = duckdb.connect()
        con.execute(
            f"""
            CREATE OR REPLACE SECRET r2 (
                TYPE r2,
                ACCOUNT_ID '{self.account_id}',
                KEY_ID '{self.access_key_id}',
                SECRET '{self.secret_access_key}'
            )
            """
        )
        try:
            yield con
        finally:
            con.close()
