{{
  config(
    materialized='table'
  )
}}

/*
  Staging: OpenAlex works in scope.
  - Casts and cleans the raw Parquet fields.
  - Extracts the short work ID (W123…) from the URL for joins.
  - Keeps institution list columns for the org attachment step.
  - Excludes doc_ids in ml_intermediate.excluded_documents (papers the quality
    gate screened out entirely -- version-style title, or title+abstract both
    non-English). That list is produced UPSTREAM by the document_exclusions
    Dagster asset (it reads the raw corpus, not this staging model), so this is
    an ordinary upstream dependency, not a cycle: exclusions are computed first,
    staging simply applies them. Before document_exclusions has ever run,
    create_external_sources() resolves the source to an empty relation so the
    filter is a harmless no-op rather than an error.
  Depends on: sources.openalex_raw.works, sources.ml_intermediate.excluded_documents
  Output: dev.duckdb staging.stg_openalex_works
*/

select
    -- identifiers
    openalex_id                                        as work_url,
    regexp_extract(openalex_id, 'W([0-9]+)', 0)       as work_id,  -- e.g. 'W2741809807'
    doi,
    lower(
        regexp_replace(
            coalesce(doi, ''),
            'https?://(dx\.)?doi\.org/',
            ''
        )
    )                                                  as doi_bare,  -- normalised for joins

    -- content
    title,
    type,
    publication_date::date                             as publication_date,
    publication_year::integer                          as publication_year,
    language,
    abstract,

    -- topic
    primary_topic_id,
    primary_topic_name,

    -- institutions (kept as lists; exploded in int_ layer or dim join)
    institution_ids,
    institution_rors,
    institution_display_names

from {{ source('openalex_raw', 'works') }}
where openalex_id is not null
  and title is not null
  and publication_date is not null
  -- Exclude Harvard Dataverse dataset entries (10.7910 = Harvard DVN; these are
  -- image/data files, not papers — OpenAlex incorrectly tags them as works).
  -- NULL doi is kept (preprints without a DOI are legitimate).
  and (doi is null or doi not like '%10.7910/%')
  -- Exclude file-like titles from any dataset repository (filename = not a paper)
  and not (
      title ilike '%.jpg'  or title ilike '%.jpeg' or title ilike '%.png'
      or title ilike '%.tif' or title ilike '%.tiff' or title ilike '%.csv'
      or title ilike '%.xlsx' or title ilike '%.nc'  or title ilike '%.mat'
      or title ilike '%.zip'
  )
  -- Exclude software-release-note entries (e.g. "seL4: seL4 3.0.1", "IDBac
  -- v0.0.15") that OpenAlex mistypes as type:article -- the `type` filter at
  -- ingest cannot catch these since OpenAlex's own field says "article".
  -- Verified against the live corpus: matches only genuine software release
  -- records (seL4, IDBac, libBigWig, InChI, mygit, meowallet, clipper), no
  -- false positives on real paper titles.
  and not regexp_matches(
      title,
      '^[A-Za-z][A-Za-z0-9_-]*\s*:\s*[A-Za-z][A-Za-z0-9_-]*\s+v?[0-9]+\.[0-9]+(\.[0-9]+)?(\s*\(.*\))?$'
      || '|^[A-Za-z][A-Za-z0-9_-]*\s+v?[0-9]+\.[0-9]+(\.[0-9]+)?(\s*\(.*\))?$'
  )
  -- Exclude documents the quality gate screened out entirely (version-style
  -- title, or title+abstract both detected non-English). Produced upstream by
  -- the document_exclusions asset (which reads the raw corpus), so this is an
  -- ordinary upstream dependency applied here, not a re-derivation.
  and regexp_extract(openalex_id, 'W([0-9]+)', 0) not in (
      select doc_id from {{ source('ml_intermediate', 'excluded_documents') }}
      where doc_type = 'paper'
  )
