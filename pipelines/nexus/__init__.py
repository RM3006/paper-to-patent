from dagster import Definitions, EnvVar

from nexus.assets.ingest.openalex import openalex_works_raw
from nexus.assets.ingest.patentsview import (
    patents_scoped,
    patentsview_applications_raw,
    patentsview_assignees_raw,
    patentsview_citations_raw,
    patentsview_cpc_raw,
    patentsview_inventors_raw,
    patentsview_npl_raw,
    patentsview_patents_raw,
)
from nexus.resources.duckdb import DuckDBR2Resource
from nexus.resources.r2 import R2Resource

_r2 = R2Resource(
    account_id=EnvVar("CLOUDFLARE_ACCOUNT_ID"),
    access_key_id=EnvVar("CLOUDFLARE_R2_ACCESS_KEY_ID"),
    secret_access_key=EnvVar("CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
)

_duckdb = DuckDBR2Resource(
    account_id=EnvVar("CLOUDFLARE_ACCOUNT_ID"),
    access_key_id=EnvVar("CLOUDFLARE_R2_ACCESS_KEY_ID"),
    secret_access_key=EnvVar("CLOUDFLARE_R2_SECRET_ACCESS_KEY"),
)

defs = Definitions(
    assets=[
        openalex_works_raw,
        patentsview_patents_raw,
        patentsview_applications_raw,
        patentsview_assignees_raw,
        patentsview_cpc_raw,
        patentsview_npl_raw,
        patentsview_citations_raw,
        patentsview_inventors_raw,
        patents_scoped,
    ],
    resources={
        "r2": _r2,
        "duckdb": _duckdb,
    },
)
