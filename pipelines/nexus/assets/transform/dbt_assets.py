"""dbt assets for the paper-to-patent warehouse.

Wraps the dbt project under models/ as a single Dagster asset group.
The dbt profile reads R2 credentials from env vars. The build target defaults to
`prod` (MotherDuck, md:) and is overridable via DBT_TARGET; the `dev` target builds
a local dev.duckdb (path from DBT_DUCKDB_PATH) for offline iteration.

Produces: all dbt models (staging → intermediate → marts → queries).
Depends on: all Dagster ingest and entity_resolution assets that write to R2.
Output: the MotherDuck warehouse (md:<MOTHERDUCK_DATABASE>) under target `prod`;
        a local dev.duckdb under target `dev`.
"""

import os
import pathlib

from dagster_dbt import DbtCliResource, dbt_assets

_DBT_PROJECT_DIR = pathlib.Path(__file__).parent.parent.parent.parent.parent / "models"

# Dagster is the production build path → MotherDuck (prod) by default.
# Set DBT_TARGET=dev to build the local dev.duckdb from Dagster instead.
_DBT_TARGET = os.environ.get("DBT_TARGET", "prod")

dbt_resource = DbtCliResource(
    project_dir=str(_DBT_PROJECT_DIR),
    profiles_dir=str(_DBT_PROJECT_DIR),
)


@dbt_assets(manifest=_DBT_PROJECT_DIR / "target" / "manifest.json")
def paper_to_patent_dbt_assets(context, dbt: DbtCliResource):  # type: ignore[no-untyped-def]
    # npl_links source is registered by the on-run-start macro only when present;
    # fact_npl_link and idea_journey build cleanly once npl_links_raw has run.
    yield from dbt.cli(["build", "--target", _DBT_TARGET], context=context).stream()  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
