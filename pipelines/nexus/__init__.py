from dagster import Definitions, EnvVar

from nexus.assets.entity_resolution.assemble import org_crosswalk
from nexus.assets.entity_resolution.crosswalk import (
    openalex_institutions_staging,
    patentsview_orgs_staging,
)
from nexus.assets.entity_resolution.fuzzy_bridge import fuzzy_org_bridge
from nexus.assets.entity_resolution.seed import seed_crosswalk_matched, seed_crosswalk_oa_matched
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
from nexus.assets.ml.cluster_labels import cluster_labels
from nexus.assets.ml.clustering import document_clusters
from nexus.assets.ml.embeddings import document_embeddings
from nexus.assets.transform.dbt_assets import dbt_resource, paper_to_patent_dbt_assets
from nexus.assets.transform.gold_export import gold_export
from nexus.assets.transform.npl_matcher import npl_links_raw
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
        patentsview_orgs_staging,
        openalex_institutions_staging,
        seed_crosswalk_matched,
        seed_crosswalk_oa_matched,
        fuzzy_org_bridge,
        org_crosswalk,
        paper_to_patent_dbt_assets,
        npl_links_raw,
        gold_export,
        document_embeddings,
        document_clusters,
        cluster_labels,
    ],
    resources={
        "r2": _r2,
        "duckdb": _duckdb,
        "dbt": dbt_resource,
    },
)
