{% macro latest_snapshot_date(r2_prefix, filename) %}
  {#
    Returns the latest (ISO-sortable, lexicographic-max) snapshot date directory
    for a given R2 prefix + filename, or none if no snapshot exists yet.

    Every raw/intermediate asset writes to a date-partitioned path
    (r2://p2p-lake/{prefix}/v{date}/{filename}) and is meant to have exactly one
    live snapshot at a time (point-in-time build, not an accumulating history —
    see ARCHITECTURE.md Known Limitations). Globbing '*/*.parquet' across every
    version that was ever written silently unions overlapping snapshots once a
    second one exists (found live in intermediate/er/org_crosswalk: v2026-06-22
    + v2026-06-26 together produced 16,198 duplicate rows and 32 rows with
    genuinely conflicting org_id assignments for re-classified institutions).
    Resolving to the latest snapshot only avoids that class of bug.
  #}
  {% set date_query %}
    SELECT max(regexp_extract(file, '/v([0-9-]+)/', 1)) AS latest
    FROM glob('r2://p2p-lake/{{ r2_prefix }}/*/{{ filename }}')
  {% endset %}
  {% set result = run_query(date_query) %}
  {{ return(result.columns[0].values()[0]) }}
{% endmacro %}


{% macro create_external_sources() %}
  {#
    Creates DuckDB schemas and external views that back dbt sources.
    Called in on-run-start so {{ source() }} references resolve everywhere —
    in models, tests, and freshness checks.

    R2 secret is pre-configured in profiles.yml; httpfs extension is loaded there too.
    Each source view resolves to the latest snapshot only (see latest_snapshot_date
    above) — never a glob across every version ever written.
    Staging models that materialise as tables pull data from R2 once and cache it locally.
  #}
  {% if execute %}
    -- schemas
    {% do run_query("CREATE SCHEMA IF NOT EXISTS openalex_raw") %}
    {% do run_query("CREATE SCHEMA IF NOT EXISTS patentsview_raw") %}
    {% do run_query("CREATE SCHEMA IF NOT EXISTS er_intermediate") %}
    {% do run_query("CREATE SCHEMA IF NOT EXISTS ml_intermediate") %}

    -- openalex
    {% set oa_date = latest_snapshot_date('raw/openalex', 'works.parquet') %}
    {% do run_query("CREATE OR REPLACE VIEW openalex_raw.works AS SELECT * FROM read_parquet('r2://p2p-lake/raw/openalex/v" ~ oa_date ~ "/works.parquet')") %}

    -- patentsview
    {% set pv_patents_date = latest_snapshot_date('raw/patentsview/patents', 'patents.parquet') %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.patents AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/patents/v" ~ pv_patents_date ~ "/patents.parquet')") %}

    {% set pv_applications_date = latest_snapshot_date('raw/patentsview/applications', 'applications.parquet') %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.applications AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/applications/v" ~ pv_applications_date ~ "/applications.parquet')") %}

    {% set pv_patents_scoped_date = latest_snapshot_date('raw/patentsview/patents_scoped', 'patents_scoped.parquet') %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.patents_scoped AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/patents_scoped/v" ~ pv_patents_scoped_date ~ "/patents_scoped.parquet')") %}

    {% set pv_assignees_date = latest_snapshot_date('raw/patentsview/assignees', 'assignees.parquet') %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.assignees AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/assignees/v" ~ pv_assignees_date ~ "/assignees.parquet')") %}

    {% set pv_cpc_date = latest_snapshot_date('raw/patentsview/cpc', 'cpc.parquet') %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.cpc AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/cpc/v" ~ pv_cpc_date ~ "/cpc.parquet')") %}

    {% set pv_npl_date = latest_snapshot_date('raw/patentsview/npl', 'npl.parquet') %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.npl AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/npl/v" ~ pv_npl_date ~ "/npl.parquet')") %}

    {% set pv_citations_date = latest_snapshot_date('raw/patentsview/citations', 'citations.parquet') %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.citations AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/citations/v" ~ pv_citations_date ~ "/citations.parquet')") %}

    -- er intermediate
    {% set xwalk_date = latest_snapshot_date('intermediate/er/org_crosswalk', 'org_crosswalk.parquet') %}
    {% do run_query("CREATE OR REPLACE VIEW er_intermediate.org_crosswalk AS SELECT * FROM read_parquet('r2://p2p-lake/intermediate/er/org_crosswalk/v" ~ xwalk_date ~ "/org_crosswalk.parquet')") %}

    -- npl_links view only registered if the R2 path exists (Step 2 writes it)
    {% set npl_date = latest_snapshot_date('intermediate/npl', 'npl_links.parquet') %}
    {% if npl_date %}
      {% do run_query("CREATE OR REPLACE VIEW er_intermediate.npl_links AS SELECT * FROM read_parquet('r2://p2p-lake/intermediate/npl/v" ~ npl_date ~ "/npl_links.parquet')") %}
    {% endif %}

    -- ml_intermediate views — only registered once Part 5 ML assets have run
    {% set clusters_date = latest_snapshot_date('intermediate/clusters', 'clusters.parquet') %}
    {% if clusters_date %}
      {% do run_query("CREATE OR REPLACE VIEW ml_intermediate.clusters AS SELECT * FROM read_parquet('r2://p2p-lake/intermediate/clusters/v" ~ clusters_date ~ "/clusters.parquet')") %}
    {% endif %}

    {% set labels_date = latest_snapshot_date('intermediate/cluster_labels', 'cluster_labels.parquet') %}
    {% if labels_date %}
      {% do run_query("CREATE OR REPLACE VIEW ml_intermediate.cluster_labels AS SELECT * FROM read_parquet('r2://p2p-lake/intermediate/cluster_labels/v" ~ labels_date ~ "/cluster_labels.parquet')") %}
    {% endif %}
  {% endif %}

  -- hook must return SQL; this is a no-op sentinel
  SELECT 1
{% endmacro %}
