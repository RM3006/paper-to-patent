# SETUP.md — Prerequisites for the Paper → Patent Build

This checklist enumerates every account, token, and local tool required before Part 1 begins. Almost everything fits in a free tier. The only out-of-pocket cost is a few dollars of Anthropic API spend in Part 5 (cluster labelling — dozens of calls, not thousands), so realistically **under $5 total**. There is no GPU spend (embeddings run on CPU); the only managed service is MotherDuck, used on its free tier (the served marts are single-digit MB, comfortably within it).

**The critical path item is the Part 0 NPL feasibility spike**, not an API key. PatentsView bulk data (Phase D1) downloads immediately with no key. Run the spike before building any infrastructure — it gates everything.

On completion, the following six values exist in a gitignored `.env.local`:

```
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_R2_ACCESS_KEY_ID=...          # read-write, build machine only
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
MOTHERDUCK_TOKEN=...                      # read-write token for the build pipeline (dbt --target prod)
OPENALEX_MAILTO=...                       # your email — config for the OpenAlex polite pool, not a credential
ANTHROPIC_API_KEY=...
# PATENTSVIEW_API_KEY=...                 # optional — only needed for PatentSearch API supplementary queries
```

A second, **read-only** MotherDuck token (a read-scaling token) is preferred for the Streamlit app (Phase F) and would live in Streamlit Cloud's secrets, not here — but read-scaling tokens require a paid MotherDuck tier. On the free tier, the app reuses the same read-write `MOTHERDUCK_TOKEN` (see F1 for the accepted risk).

---

## Phase A — Tools running locally

One-time install on the development machine.

### A1. Git
- **Why**: version control; the project starts with `git init`.
- **Used in**: every Part.
- **Install**: `winget install Git.Git` (Windows) / `brew install git` (macOS) / package manager (Linux).
- **Verify**: `git --version` returns a version.

### A2. Python 3.11+
- **Why**: the project's language. Dagster requires ≥3.11.
- **Used in**: every Part.
- **Install**: `winget install Python.Python.3.12` (Windows) / `brew install python@3.12` (macOS) / pyenv (Linux).
- **Verify**: `python --version` returns 3.11.x or higher.

### A3. uv
- **Why**: the project's Python package manager. Replaces pip + virtualenv; far faster.
- **Used in**: every Part.
- **Install**: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows) / `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS / Linux).
- **Verify**: `uv --version` returns a version.

### A4. Terraform
- **Why**: provisions the Cloudflare R2 bucket via Infrastructure-as-Code in Part 1, and keeps the storage footprint reproducible.
- **Used in**: Part 1 (provisioning); occasional updates later.
- **Install**: `winget install Hashicorp.Terraform` (Windows) / `brew install terraform` (macOS) / HashiCorp's apt/yum repo or the zipped binary (Linux).
- **Verify**: `terraform version` returns a version (1.9+).

### A5. Claude Code
- **Why**: the agentic CLI used to build the project, session by session.
- **Used in**: every Part.
- **Install**: `npm install -g @anthropic-ai/claude-code` (requires Node 18+).
- **First-run setup**: `claude` inside the project folder triggers browser authentication.
- **Verify**: `claude --version` returns a version.

---

## Phase B — Code hosting

### B1. GitHub
- **Why**: code repository; CI runs on push.
- **Used in**: every Part. The public link goes on the portfolio in Part 8.
- **Cost**: free.
- **Steps**:
  1. Sign in or register at github.com.
  2. Create a new repository (e.g. `paper-to-patent`), **private** initially; flip to public in Part 8.
  3. Do **not** initialise with a README, .gitignore, or license — the local repo pushes as the source of truth.
- **Note**: no secret in `.env.local`. Git uses local credentials.

---

## Phase C — Storage and warehouse

### C1. Cloudflare R2 — the data lake (raw + intermediate Parquet)
- **Why**: holds every raw-layer and intermediate Parquet file from OpenAlex, PatentsView, entity resolution, and the ML stage. Zero egress fees, which matters because the dbt build (local DuckDB and MotherDuck) and the embedding asset all read from here.
- **Used in**: every Part from 1 onward.
- **Cost**: free up to 10 GB storage and 10M reads/month. The project uses ~1–2 GB total.
- **Catch**: Cloudflare requires a payment method on file even for free-tier R2. No charge unless usage exceeds the limit.
- **Steps**:
  1. Sign in or register at cloudflare.com.
  2. From the dashboard left sidebar, activate **R2** (add a payment method when prompted).
  3. **My Profile → API Tokens → Create Token → R2 → "Edit"** scope (read-write, for the build machine). Restrict to the account.
  4. Retain the **Access Key ID**, **Secret Access Key**, and the **Account ID** (visible in the R2 sidebar URL).
- **Secrets**: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_R2_ACCESS_KEY_ID`, `CLOUDFLARE_R2_SECRET_ACCESS_KEY`.

### C2. DuckDB + MotherDuck — the warehouse
- **Why**: DuckDB is the engine; **MotherDuck** (managed DuckDB) is the served warehouse. dbt-duckdb builds staging → intermediate → marts, reading raw Parquet from R2 via `httpfs`. The Dagster pipeline builds into MotherDuck (`dbt build --target prod`); a local `dev.duckdb` (`--target dev`) is kept for fast, offline iteration. The Streamlit app queries MotherDuck with in-process DuckDB (`md:`) — same engine, so the SQL and dbt adapter are unchanged.
- **Used in**: Parts 4, 5, 6, 7.
- **Cost**: DuckDB is a free Python library (no account). MotherDuck has a free tier that easily covers the single-digit-MB served marts; see C3.
- **Day-one check (do not skip)**: before designing the pipeline around it, confirm DuckDB can read a test Parquet file from R2 with the R2 secret (`CREATE SECRET` of type `r2`/`s3` + `SELECT * FROM read_parquet('s3://...')`). The R2 credential wiring is the single most common integration snag; prove it in 20 minutes, not in week three. The exact secret syntax lives in `docs/data_source_manifest.md`.
- **Running dbt (Part 4+)**: `cd models && dbt build` builds the local `dev.duckdb` (`dev` target); `dbt build --target prod` builds into MotherDuck. Both are configured in `profiles.yml`.
- **Cold-start build order (do not skip)**: `dbt build` alone is not a complete build the first time. Staging and marts read `ml_intermediate.excluded_documents`/`clusters`, which the Dagster ML assets produce, not dbt — so a first `dbt build` on an empty warehouse succeeds but resolves those as empty relations (no error, just an incomplete result). The correct cold-start order is: `dbt build` (Stage 4, staging/intermediate only) → run the Dagster ML assets (embeddings → clustering → cluster labels → NPL linkage) → `dbt build` again (Stage 9, picks up real `excluded_documents`/`clusters` and builds the cluster/NPL-dependent facts and gold marts). See `docs/workflow.md` Stages 4, 5, and 9 for the full mechanism.

### C3. MotherDuck — the served warehouse
- **Why**: managed DuckDB. dbt materialises the marts into it (`--target prod`) and the Streamlit app reads from it, because a hosted Streamlit Community Cloud container can't reach a laptop's local `dev.duckdb`. Same engine as DuckDB — identical SQL and dbt adapter (`md:` path).
- **Used in**: Parts 6, 7 (the production build target and the app's read path).
- **Cost**: free tier (verify current limits at motherduck.com — they change). The served marts are single-digit MB, well inside it.
- **Steps**:
  1. Sign up at `app.motherduck.com`.
  2. Create a database named `paper_to_patent` (or set `MOTHERDUCK_DATABASE`). Connecting to `md:paper_to_patent` also creates it on first write.
  3. **Settings → Access Tokens → Create Token** (read-write) for the build pipeline → `MOTHERDUCK_TOKEN` in `.env.local`.
  4. Prefer a **read-only** ("read-scaling") token for the app in Phase F — but this token type requires a paid MotherDuck tier. On the free tier, skip this step and reuse the read-write token for the app too (see F1).
- **Secrets**: `MOTHERDUCK_TOKEN` (read-write, build machine); `MOTHERDUCK_DATABASE` optional (default `paper_to_patent`).

---

## Phase D — Data-source access

### D1. PatentsView bulk data — **primary patent source, no key required**
- **Why**: US patent data — filings, disambiguated assignees, inventors, CPC classes, patent-to-patent citations, and the non-patent-literature ("other reference") citations that make the paper→patent bridge possible. The bulk files ship the same disambiguated data as the API without rate limits or pagination complexity.
- **Used in**: Part 0 spike (immediately) and Part 2 (full ingest).
- **Cost**: free. CC-BY-4.0 license.
- **Where**: data.uspto.gov → PatentsView datasets. Key files: `g_patent.tsv.zip`, `g_assignee.tsv.zip`, `g_cpc_current.tsv.zip`, `g_us_patent_citation.tsv.zip`, `g_other_reference.tsv.zip`.
- **Steps**:
  1. Open `https://data.uspto.gov` in a browser. The site is a JavaScript SPA — direct URL access does not work.
  2. Navigate to: **Datasets → PatentsView → Grant Data**.
  3. For the Part 0 spike, download: `g_patent.tsv.zip`, `g_cpc_current.tsv.zip`, `g_other_reference.tsv.zip`. Save all three to `data/raw/`.
  4. Download the remaining files (`g_assignee.tsv.zip`, `g_inventor.tsv.zip`, `g_us_patent_citation.tsv.zip`) at the start of Part 2.
- **Secrets**: none required for bulk download.
- **Note**: the legacy PatentsView website (patentsview.org) migrated to data.uspto.gov in March 2026. Always use data.uspto.gov.

### D1b. PatentsView PatentSearch API — **supplementary only**
- **Why**: targeted lookups where the bulk files are insufficient (e.g. querying a specific patent's metadata by ID).
- **Used in**: supplementary calls in Parts 2–4 only.
- **Cost**: free.
- **Important**: the legacy API (`api.patentsview.org`) was discontinued. Use the **PatentSearch API** at `search.patentsview.org`, which requires a key approved by a human. Request it if you anticipate needing supplementary API calls, but it is **not on the critical path** — the bulk files cover Part 2's full corpus pull.
- **Steps**: request a key via the PatentsView support/service desk. Test with `X-Api-Key` header.
- **Secrets**: `PATENTSVIEW_API_KEY` (optional; add to `.env.local` if obtained).

### D2. OpenAlex — global research output
- **Why**: papers, authors, institutions (with ROR IDs), topics, and abstracts (as an inverted index).
- **Used in**: Parts 1, 3, 5.
- **Cost**: free. No account, no key.
- **Steps**:
  1. No signup. Put your email in `OPENALEX_MAILTO` to use the **polite pool** (faster, courteous routing). This is config, not a credential, but it lives in `.env.local` so the ingest reads it the same way as everything else.
- **Secrets**: `OPENALEX_MAILTO` (your email).

---

### D3. Marx & Fuegi "Reliance on Science" dataset — **NPL gold eval set**
- **Why**: provides a published, peer-reviewed set of matched patent→paper citation pairs. Used in Part 0 to validate NPL density in scope, and in Part 4 as the gold eval set to measure our own NPL matcher's precision/recall.
- **Used in**: Part 0 spike (count gold pairs per family) and Part 4 (matcher quality measurement).
- **Cost**: free.
- **Where**: Zenodo record `8278104` — `https://zenodo.org/records/8278104`. The file to download is `_pcs_oa.csv` (~2 GB). This is the OpenAlex-matched version: `oaid` is the OpenAlex work ID (numeric; full URL = `https://openalex.org/W{oaid}`), `patent` is the USPTO patent in format `us-{number}-{kind}` (e.g. `us-11426570-b2`), `confscore` is 1–10 confidence, `wherefound` is `front`/`body`/`both`.
- **Steps**:
  1. Open `https://zenodo.org/records/8278104` in a browser and download `_pcs_oa.csv`.
  2. Save as `data/reference/marx_fuegi_pcs.csv` (gitignored — 2 GB).
  3. In the Part 0 spike, DuckDB joins on `REGEXP_EXTRACT(patent, '^us-([0-9]+)-', 1)` to match PatentsView `patent_number`.
- **Secrets**: none.
- **Note**: This version of the dataset uses OpenAlex IDs directly — no MAG bridge is required. The `oaid` column maps straight to `https://openalex.org/W{oaid}`. Patent coverage runs through ~2023; OpenAlex coverage through 2025 is an extension our own matcher adds.

---

## Phase E — LLM batch labelling

### E1. Anthropic API
- **Why**: Claude Haiku writes a short name and a plain-English description for each technology cluster, and the guided-tour narration. Grounded strictly in cluster top-terms and representative documents — no invented claims.
- **Used in**: Part 5 (cluster labels) and Part 7 (tour copy).
- **Cost**: a few dollars at most — you are labelling dozens of clusters, not rewriting every document.
- **Steps**:
  1. Register at console.anthropic.com (add a payment method).
  2. **Settings → Limits → set a monthly spend cap** (e.g. $10 — a safety net, not a budget).
  3. **API Keys → Create Key.** Retain the value.
- **Secrets**: `ANTHROPIC_API_KEY`.

---

## Phase F — Public hosting

### F1. Streamlit Community Cloud
- **Why**: free public hosting for the Streamlit UI. One-click deploy from GitHub.
- **Used in**: Parts 7 and 8.
- **Cost**: free for public apps.
- **Steps**:
  1. Sign in at share.streamlit.io via GitHub OAuth.
  2. Point the app at this repo's `main` branch, entrypoint `apps/ui/app.py` (not `streamlit_app.py`).
  3. Add the read-write `MOTHERDUCK_TOKEN` and `MOTHERDUCK_DATABASE=paper_to_patent` to Streamlit Cloud's **Secrets** UI. MotherDuck's free tier cannot issue a read-scaling (read-only) token, so the public app knowingly runs on the same read-write token as the build pipeline (Part 8, accepted risk — see `ARCHITECTURE.md` §9 and Known Limitations): the warehouse is fully derived from R2 and rebuilt by `dbt build --target prod` in about a minute, so a leaked token means downtime, not data loss. Rotate the token + redeploy if it ever leaks. Switch to a genuine read-only token the moment the MotherDuck account is upgraded.
- **Secrets**: configured in the Streamlit Cloud UI, not in `.env.local`.

### F2. Embedding the app in another site (iframe)
The iframe `src` carries one flag:

```html
<iframe src="https://paper-to-patent-a7iiegantbeucyxxwegpyz.streamlit.app/?embed=true"></iframe>
```

`embed=true` is Community Cloud's own flag. Without it the frame loads the non-embed host page, which starts a login redirect that cannot complete cross-site (browsers withhold the `SameSite=Lax` session cookie from a third-party frame), so it retries forever and dead-ends at `ERR_TOO_MANY_REDIRECTS`.

**No companion `e=1` marker is needed** (an earlier revision required one; drop it if it is still in the `src`). It existed because every in-app link was a plain `<a href>`, so each click was a full browser navigation that dropped the flag mid-session and re-entered the loop. All navigation now goes through `st.page_link` / `st.button`, which swap pages inside the running app without a browser navigation — the flag is never dropped, so there is nothing to re-attach.

**Never link to another page with `<a href>`.** Beyond the redirect loop, an anchor reboots the whole app, and Community Cloud re-frames that reboot *inside the current frame* — leaving one nested, still-running copy of the app per click. The visible symptoms are stacked "Built with Streamlit" badges piling up at the bottom of the frame and 404s on `/<page>/_stcore/health`. `apps/ui/tests/test_render.py` guards the tab strip's targets; the family pills, the map link and the Overview's "Explore family →" follow the same rule and are commented in place.

---

## Public data sources

| Source | What it provides | Access |
|---|---|---|
| OpenAlex | Global papers: abstracts (inverted index), authors, institutions (ROR), topics | `api.openalex.org` (polite pool via `mailto`); bulk snapshots on S3 if ever needed |
| PatentsView bulk (primary) | US patents: filings, assignees (disambiguated), CPC, citations, NPL other-references | data.uspto.gov bulk TSV downloads — **no key required**, CC-BY-4.0 |
| PatentSearch API (supplementary) | Same data as bulk; useful for targeted single-patent queries | `search.patentsview.org/api/v1/` — **API key required** (`X-Api-Key` header) |
| Marx & Fuegi (eval only) | Matched patent→paper citation pairs; used as NPL gold eval set | relianceonscience.org / Zenodo — free download |

---

## Out of scope (tools deliberately excluded)

- **Heavyweight managed warehouse (Snowflake / BigQuery)** — overkill at ~1–2 GB. MotherDuck (managed DuckDB) *is* used as the served warehouse (a hosted Streamlit container can't reach a local `dev.duckdb`), but a Snowflake/BigQuery-class service adds cost and a credential for no benefit at this scale.
- **Modal / any serverless GPU** — `all-MiniLM-L6-v2` runs on CPU in minutes; no GPU is justified. Reconsider only if a hosted FastAPI backend is added in v2.
- **Qdrant / dedicated vector DB** — the product is clustering, not similarity search. UMAP coords sit in the warehouse; in-warehouse cosine covers any future need.
- **AWS / GCP / Azure** — R2 + DuckDB are cheaper and simpler at this volume. (GCP's BigQuery + Google Patents Public Data is the right move only if v2 adds global patent coverage.)
- **Postgres / managed relational DB** — no relational store needed; DuckDB is the warehouse.
- **Neo4j / graph DB** — deferred to v2 if a citation-network view is built.
- **Dagster Cloud** — self-hosted OSS Dagster, to avoid credit limits.

---

## Verification checklist

**Part 0 spike can begin when:**

- [ ] `git --version`, `python --version`, `uv --version`, `terraform version`, `claude --version` all return a version.
- [ ] GitHub repo exists (private), no README initialised.
- [ ] `g_other_reference.tsv.zip` and `g_patent.tsv.zip` downloaded locally from data.uspto.gov.
- [ ] Marx & Fuegi dataset (`pcs_oa.tsv`) downloaded and stored at `data/reference/marx_fuegi_pcs.tsv` (gitignored).
- [ ] DuckDB installed (comes with project dependencies via `uv`).

**Part 1 can begin when every box is checked:**

- [ ] Part 0 spike exit criteria all pass (NPL counts, OpenAlex count, R2 credential check — see `ROADMAP.md` Part 0).
- [ ] `.env.local` exists in the project root with the five mandatory values listed at the top of this document.
- [ ] `.env.local` is in `.gitignore` and not committed.
- [ ] Cloudflare R2 dashboard shows the activated R2 service.
- [ ] **DuckDB can read a test Parquet file from R2** (proven in Part 0 spike).
- [ ] `OPENALEX_MAILTO` is set to your email.
- [ ] Anthropic console shows an API key and an active monthly spend cap.

When the checklist is green, open Claude Code in the project folder using the standard opening prompt from `ROADMAP.md` Part 1.
