"""Generate zero-row Parquet fixture stubs for offline CI dbt docs builds.

Each stub captures the exact column schema of the corresponding R2 source
view, as currently materialized in the local dev.duckdb (itself built from
real R2 data via `dbt build`). Zero rows let the dbt-docs CI workflow build
every model and generate a fully, correctly-typed catalog without ever
touching R2 or MotherDuck (source_root is overridden to this fixtures/
directory — see dbt_project.yml and macros/create_external_sources.sql).

Run once whenever a source schema changes (requires real R2 credentials in
the environment, since it reads the live dev.duckdb source views):
    cd models && uv run python fixtures/build_source_stubs.py
Commit the generated .parquet files alongside this script.
"""

import os
from pathlib import Path

import duckdb

FIXTURES_ROOT = Path(__file__).parent
DEV_DB = FIXTURES_ROOT.parent / "dev.duckdb"

# snapshot version dir is arbitrary and fixed — CI only needs *a* snapshot to
# exist, not a real one, since latest_snapshot_date() just globs for the max.
VERSION = "2024-01-01"

# (relation in dev.duckdb, output path relative to fixtures/)
SOURCES = [
    ("openalex_raw.works", f"raw/openalex/v{VERSION}/works.parquet"),
    ("patentsview_raw.patents", f"raw/patentsview/patents/v{VERSION}/patents.parquet"),
    ("patentsview_raw.applications", f"raw/patentsview/applications/v{VERSION}/applications.parquet"),
    ("patentsview_raw.patents_scoped", f"raw/patentsview/patents_scoped/v{VERSION}/patents_scoped.parquet"),
    ("patentsview_raw.assignees", f"raw/patentsview/assignees/v{VERSION}/assignees.parquet"),
    ("patentsview_raw.cpc", f"raw/patentsview/cpc/v{VERSION}/cpc.parquet"),
    ("patentsview_raw.npl", f"raw/patentsview/npl/v{VERSION}/npl.parquet"),
    ("patentsview_raw.citations", f"raw/patentsview/citations/v{VERSION}/citations.parquet"),
    ("er_intermediate.org_crosswalk", f"intermediate/er/org_crosswalk/v{VERSION}/org_crosswalk.parquet"),
    ("er_intermediate.npl_links", f"intermediate/npl/v{VERSION}/npl_links.parquet"),
    ("ml_intermediate.clusters", f"intermediate/clusters/v{VERSION}/clusters.parquet"),
    ("ml_intermediate.cluster_labels", f"intermediate/cluster_labels/v{VERSION}/cluster_labels.parquet"),
    ("ml_intermediate.excluded_documents", f"intermediate/excluded_documents/v{VERSION}/excluded_documents.parquet"),
]


def main() -> None:
    con = duckdb.connect(str(DEV_DB), read_only=True)
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(
        """
        CREATE SECRET r2 (
            TYPE r2,
            KEY_ID ?,
            SECRET ?,
            ACCOUNT_ID ?
        )
        """,
        [
            os.environ["CLOUDFLARE_R2_ACCESS_KEY_ID"],
            os.environ["CLOUDFLARE_R2_SECRET_ACCESS_KEY"],
            os.environ["CLOUDFLARE_ACCOUNT_ID"],
        ],
    )

    for relation, rel_path in SOURCES:
        out_path = FIXTURES_ROOT / rel_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        con.execute(
            f"COPY (SELECT * FROM {relation} LIMIT 0) TO '{out_path.as_posix()}' (FORMAT PARQUET)"
        )
        n_cols = con.execute(f"SELECT * FROM {relation} LIMIT 0").df().shape[1]
        print(f"wrote fixtures/{rel_path} ({n_cols} columns, 0 rows)")


if __name__ == "__main__":
    main()
