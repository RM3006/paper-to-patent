"""dbt assets for the paper-to-patent warehouse.

Wraps the dbt project under models/ as a single Dagster asset group.
The dbt profile reads R2 credentials from env vars; DuckDB path defaults
to `dev.duckdb` in the working directory and can be overridden via
DBT_DUCKDB_PATH.

Produces: all dbt models (staging → intermediate → marts → queries).
Depends on: all Dagster ingest and entity_resolution assets that write to R2.
Output: dev.duckdb (DuckDB file in the working directory).
"""

import pathlib

from dagster_dbt import DbtCliResource, dbt_assets

_DBT_PROJECT_DIR = pathlib.Path(__file__).parent.parent.parent.parent.parent / "models"

dbt_resource = DbtCliResource(
    project_dir=str(_DBT_PROJECT_DIR),
    profiles_dir=str(_DBT_PROJECT_DIR),
)


@dbt_assets(manifest=_DBT_PROJECT_DIR / "target" / "manifest.json")
def paper_to_patent_dbt_assets(context, dbt: DbtCliResource):  # type: ignore[no-untyped-def]
    # npl_links source is registered by the on-run-start macro only when present;
    # fact_npl_link and idea_journey build cleanly once npl_links_raw has run.
    yield from dbt.cli(["build"], context=context).stream()  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
