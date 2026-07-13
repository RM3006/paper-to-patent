{% macro duckdb__get_catalog(information_schema, schemas) -%}
  {#
    Overrides dbt-duckdb's built-in duckdb__get_catalog (models/macros in the
    root project take precedence over an adapter plugin's own macros of the
    same name). The stock version returns column metadata only -- no
    stats:*:* columns -- so dbt always reports has_stats: false for every
    relation in dbt docs.

    duckdb_tables() exposes estimated_size, a row count DuckDB already
    maintains in its storage layer (no live COUNT(*) needed). duckdb_views()
    has no equivalent, since a view isn't materialized -- views are left
    with row_count NULL and stats:row_count:include false, so they keep
    has_stats: false rather than showing a fake count.
  #}
  {%- call statement('catalog', fetch_result=True) -%}
    with relations AS (
      select
        t.table_name
        , t.database_name
        , t.schema_name
        , 'BASE TABLE' as table_type
        , t.comment as table_comment
        , t.estimated_size as row_count
      from duckdb_tables() t
      WHERE t.database_name = '{{ database }}'
      UNION ALL
      SELECT v.view_name as table_name
      , v.database_name
      , v.schema_name
      , 'VIEW' as table_type
      , v.comment as table_comment
      , NULL as row_count
      from duckdb_views() v
      WHERE v.database_name = '{{ database }}'
    )
    select
        '{{ database }}' as table_database,
        r.schema_name as table_schema,
        r.table_name,
        r.table_type,
        r.table_comment,
        c.column_name,
        c.column_index as column_index,
        c.data_type as column_type,
        c.comment as column_comment,
        NULL as table_owner,
        'Row Count' as "stats:row_count:label",
        r.row_count as "stats:row_count:value",
        'Approximate row count, from DuckDB''s own table metadata' as "stats:row_count:description",
        (r.row_count is not null) as "stats:row_count:include"
    FROM relations r JOIN duckdb_columns() c ON r.schema_name = c.schema_name AND r.table_name = c.table_name
    WHERE (
        {%- for schema in schemas -%}
          upper(r.schema_name) = upper('{{ schema }}'){%- if not loop.last %} or {% endif -%}
        {%- endfor -%}
    )
    ORDER BY
        r.schema_name,
        r.table_name,
        c.column_index
  {%- endcall -%}
  {{ return(load_result('catalog').table) }}
{%- endmacro %}
