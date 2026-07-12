"""dbt assets for the paper-to-patent warehouse — split around the ML/NPL boundary.

The dbt models are split into two Dagster @dbt_assets so the Python assets that
sit in the middle of the DAG (document_exclusions, the NPL matchers, and the
embedding/clustering/labelling chain) can be interleaved with honest
dependencies instead of the old empty-relation bootstrap + manual two-pass:

  * paper_to_patent_dbt_pre  — staging, dims, ER intermediate, the non-cluster
    facts: everything the Python matchers/ML read. Runs after document_exclusions
    (staging applies its excluded_documents) and the ingest/ER assets.
  * paper_to_patent_dbt_post — the cluster fact + labels + NPL fact + all marts:
    everything downstream of the clusters / cluster_labels / npl_links /
    mf_npl_links sources. Runs after the ML + NPL Python assets.

A DagsterDbtTranslator maps those five mid-pipeline dbt sources to the Python
asset keys that produce them, so Dagster resolves ONE acyclic graph (dim_paper no
longer backfills cluster_id, and staging's excluded_documents now comes from an
upstream asset — see docs/workflow.md). The build target defaults to `prod`
(MotherDuck); DBT_TARGET=dev builds the local dev.duckdb.

Produces: all dbt models (staging → intermediate → marts → queries).
Output: the MotherDuck warehouse (md:<MOTHERDUCK_DATABASE>) under target `prod`;
        a local dev.duckdb under target `dev`.
"""

import os
import pathlib
from collections.abc import Mapping
from typing import Any

from dagster import AssetKey
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, dbt_assets

_DBT_PROJECT_DIR = pathlib.Path(__file__).parent.parent.parent.parent.parent / "models"
_MANIFEST = _DBT_PROJECT_DIR / "target" / "manifest.json"

# Dagster is the production build path → MotherDuck (prod) by default.
# Set DBT_TARGET=dev to build the local dev.duckdb from Dagster instead.
_DBT_TARGET = os.environ.get("DBT_TARGET", "prod")

dbt_resource = DbtCliResource(
    project_dir=str(_DBT_PROJECT_DIR),
    profiles_dir=str(_DBT_PROJECT_DIR),
)

# The mid-graph dbt sources produced by Python assets. Mapping each to its
# producing asset key is what lets Dagster order dbt_pre → matchers/ML → dbt_post
# as one acyclic graph. Ingest/ER raw sources keep their default external keys —
# document_exclusions' own deps already order raw ingest → staging.
_SOURCE_TO_ASSET_KEY: dict[tuple[str, str], AssetKey] = {
    ("ml_intermediate", "clusters"): AssetKey("document_clusters"),
    ("ml_intermediate", "cluster_labels"): AssetKey("cluster_labels"),
    ("ml_intermediate", "excluded_documents"): AssetKey("document_exclusions"),
    ("er_intermediate", "npl_links"): AssetKey("npl_links_raw"),
    ("er_intermediate", "mf_npl_links"): AssetKey("mf_npl_links"),
}

# dbt selection for the POST segment: every model downstream of the four
# Python-produced sources that sit AFTER staging/dims (the two NPL matcher
# outputs and the two clustering outputs). excluded_documents is deliberately
# NOT here — it feeds staging, which belongs to the PRE segment.
_POST_SELECT = (
    "source:er_intermediate.npl_links+ "
    "source:er_intermediate.mf_npl_links+ "
    "source:ml_intermediate.clusters+ "
    "source:ml_intermediate.cluster_labels+"
)


class _NexusDbtTranslator(DagsterDbtTranslator):
    """Maps the mid-pipeline dbt sources to the Python asset keys that produce them."""

    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        if dbt_resource_props.get("resource_type") == "source":
            key = (dbt_resource_props["source_name"], dbt_resource_props["name"])
            mapped = _SOURCE_TO_ASSET_KEY.get(key)
            if mapped is not None:
                return mapped
        return super().get_asset_key(dbt_resource_props)  # type: ignore[no-untyped-call]


_translator = _NexusDbtTranslator()


@dbt_assets(
    manifest=_MANIFEST,
    exclude=_POST_SELECT,
    dagster_dbt_translator=_translator,
)
def paper_to_patent_dbt_pre(context, dbt: DbtCliResource):  # type: ignore[no-untyped-def]
    # PRE segment: staging + dims + ER intermediate + non-cluster facts. Runs
    # after document_exclusions (excluded_documents) and the ingest/ER assets.
    yield from dbt.cli(["build", "--target", _DBT_TARGET], context=context).stream()  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]


@dbt_assets(
    manifest=_MANIFEST,
    select=_POST_SELECT,
    dagster_dbt_translator=_translator,
)
def paper_to_patent_dbt_post(context, dbt: DbtCliResource):  # type: ignore[no-untyped-def]
    # POST segment: cluster fact + labels + NPL fact + marts. Runs after the ML
    # (document_clusters, cluster_labels) and NPL (npl_links_raw, mf_npl_links)
    # Python assets.
    yield from dbt.cli(["build", "--target", _DBT_TARGET], context=context).stream()  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
