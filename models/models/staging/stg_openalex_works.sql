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
  Depends on: sources.openalex_raw.works
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
