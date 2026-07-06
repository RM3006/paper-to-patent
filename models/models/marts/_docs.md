{% docs __overview__ %}
# Paper → Patent — dbt project

**"The Chips Behind AI"** — tracing science-adjacent microchip hardware (EUV
lithography, silicon photonics, neuromorphic & in-memory compute) from research
paper to US patent. This project transforms two raw corpora landed in
Cloudflare R2 by a separate Dagster pipeline — OpenAlex scientific works and
PatentsView US patents — into a Gold star schema that links papers to the
patents citing them, clusters everything into named technology families, and
measures citation lag, IP concentration, and research-to-patent breadth.

**Layout**

- `staging/` — one model per scope-filtered source table (OpenAlex works,
  PatentsView patents/assignees/CPC/NPL/citations), type-cast and filtered to
  the CPC + topic scope contract.
- `intermediate/` — `int_org_crosswalk`, which re-exposes the entity-resolution
  crosswalk (built in the Dagster pipeline, Part 3) inside the dbt graph.
- `marts/` — the Gold star schema: `dim_organization`, `dim_cpc`,
  `dim_technology_cluster`, `dim_paper`, `dim_patent`, their fact tables, and
  the presentation marts (`mart_competitive`, `mart_gap`, `mart_velocity`,
  `mart_family`) that back the Streamlit UI.
- `queries/` — `idea_journey`, the canonical per-organisation paper→patent
  narrative query.

**Where to start**: `dim_organization` is the entity that both papers and
patents resolve to; `dim_technology_cluster` is the entity every document is
assigned to. Open either model's page and follow the lineage graph.

Source-by-source detail (URLs, license, refresh cadence, gotchas) lives in
[`docs/data_source_manifest.md`](https://github.com/RM3006/paper-to-patent/blob/main/docs/data_source_manifest.md);
design rationale lives in
[`ARCHITECTURE.md`](https://github.com/RM3006/paper-to-patent/blob/main/ARCHITECTURE.md);
the CPC/topic scope contract lives in `ROADMAP.md` Part 0.

**US-only lens**: PatentsView covers US patents only. Every patent-side count
and share in this project is a US-patenting statistic, never a global-filing
one (CLAUDE.md rule 4).
{% enddocs %}

{% docs org_id %}
Canonical organisation identifier spanning both OpenAlex institutions and
PatentsView assignees (e.g. `org_nvidia`, `org_pv_…`, `org_oa_…`), resolved via
`int_organization_crosswalk` (CLAUDE.md rule 1: cross-dataset org joins never
use a raw name string). Primary key of `dim_organization`.
{% enddocs %}

{% docs match_method %}
Provenance of this row's match — one of `native_id`, `ror`, `seed_crosswalk`,
`ror_bridge`, `fuzzy_high`, `fuzzy_review`, `npl_citation`, `org_cooccurrence`.
Always paired with `confidence`; no org match or paper↔patent edge exists in a
mart without both (CLAUDE.md provenance & confidence pattern). `fuzzy_review`
rows never reach a mart silently — they are resolved or excluded upstream.
{% enddocs %}

{% docs confidence %}
Trust tier for this match or link — `high`, `medium`, or `low`. Paired with
`match_method`. The UI shows this distinction; an NPL-citation-linked edge is
never presented the same way as an org-cooccurrence signal (CLAUDE.md
provenance & confidence pattern).
{% enddocs %}

{% docs cluster_id %}
Technology cluster identifier from the UMAP + HDBSCAN pipeline (e.g. `c_0`,
`c_1`), including the noise cluster `c_noise` for documents HDBSCAN could not
assign. Primary key of `dim_technology_cluster`; NULL on fact rows until the
Part 5 ML pipeline has run and dbt has rebuilt.
{% enddocs %}

{% docs work_id %}
OpenAlex short work ID (e.g. `W2741809807`) — primary key of `dim_paper` and
the join key for every paper-side fact and link in the project.
{% enddocs %}

{% docs patent_id %}
USPTO patent number — primary key of `dim_patent` and the join key for every
patent-side fact and link in the project.
{% enddocs %}

{% docs filing_date %}
Patent filing date (YYYY-MM-DD), from PatentsView `g_application`. The
citation-lag anchor for every patent-side time metric (CLAUDE.md rule 2) —
grant date (`patent_date`) is never used for timing, only shown as metadata.
{% enddocs %}

{% docs publication_date %}
OpenAlex publication date (YYYY-MM-DD) — the citation-lag anchor for every
paper-side time metric (CLAUDE.md rule 2).
{% enddocs %}

{% docs citation_lag %}
The interval between a paper's `publication_date` and a citing patent's
`filing_date`, via a resolved NPL link. Called **citation lag**, never "lead
time" or "time to market" — those phrases imply an R&D-to-commercialisation
causation this data does not support (CLAUDE.md rule 2). Grant date carries
years of administrative lag and is never used for this metric.
{% enddocs %}
