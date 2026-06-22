{% macro create_external_sources() %}
  {#
    Creates DuckDB schemas and external views that back dbt sources.
    Called in on-run-start so {{ source() }} references resolve everywhere —
    in models, tests, and freshness checks.

    R2 secret is pre-configured in profiles.yml; httpfs extension is loaded there too.
    Each source view wraps a read_parquet() glob so DuckDB scans R2 directly.
    Staging models that materialise as tables pull data from R2 once and cache it locally.
  #}
  {% if execute %}
    -- schemas
    {% do run_query("CREATE SCHEMA IF NOT EXISTS openalex_raw") %}
    {% do run_query("CREATE SCHEMA IF NOT EXISTS patentsview_raw") %}
    {% do run_query("CREATE SCHEMA IF NOT EXISTS er_intermediate") %}

    -- openalex
    {% do run_query("CREATE OR REPLACE VIEW openalex_raw.works AS SELECT * FROM read_parquet('r2://p2p-lake/raw/openalex/*/*.parquet')") %}

    -- patentsview
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.patents AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/patents/*/*.parquet')") %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.applications AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/applications/*/*.parquet')") %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.patents_scoped AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/patents_scoped/*/*.parquet')") %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.assignees AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/assignees/*/*.parquet')") %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.cpc AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/cpc/*/*.parquet')") %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.npl AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/npl/*/*.parquet')") %}
    {% do run_query("CREATE OR REPLACE VIEW patentsview_raw.citations AS SELECT * FROM read_parquet('r2://p2p-lake/raw/patentsview/citations/*/*.parquet')") %}

    -- er intermediate
    {% do run_query("CREATE OR REPLACE VIEW er_intermediate.org_crosswalk AS SELECT * FROM read_parquet('r2://p2p-lake/intermediate/er/org_crosswalk/*/*.parquet')") %}

    -- npl_links view only registered if the R2 path exists (Step 2 writes it)
    {% set npl_check %}
      SELECT COUNT(*) FROM glob('r2://p2p-lake/intermediate/npl/*/*.parquet')
    {% endset %}
    {% set npl_exists = run_query(npl_check).columns[0].values()[0] > 0 %}
    {% if npl_exists %}
      {% do run_query("CREATE OR REPLACE VIEW er_intermediate.npl_links AS SELECT * FROM read_parquet('r2://p2p-lake/intermediate/npl/*/*.parquet')") %}
    {% endif %}
  {% endif %}

  -- hook must return SQL; this is a no-op sentinel
  SELECT 1
{% endmacro %}
