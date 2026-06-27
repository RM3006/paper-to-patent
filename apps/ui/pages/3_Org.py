"""
Organisation Profile — Surface 3.

Search for an org → org card (name + match badges) → three data panels:
  - Patent output: patents by family, top 5 clusters, filing year histogram.
  - Research intake: orgs whose papers this org cites in its patents.
  - Influence: patenters whose patents cite this org's research.
Plus flagship documents (most-cited paper, most-citing patent).

Entry: search box on this page, or st.session_state.selected_org_id from Surface 2.
Source: dim_organization, fact_patent_filing, fact_publication, fact_npl_link,
        mart_competitive, seed_cluster_family.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from render import (
    FAMILY_COLORS,
    PAPER_COLOR,
    PATENT_COLOR,
    confidence_badge,
    method_badge,
)

from data import (
    load_org_filing_years,
    load_org_flagship_paper,
    load_org_flagship_patent,
    load_org_influence,
    load_org_intake,
    load_org_output_by_family,
    load_org_profile,
    load_org_top_patent_clusters,
    search_orgs,
)

st.set_page_config(
    page_title="Org Profile — The Chips Behind AI",
    page_icon="🏢",
    layout="wide",
)

st.markdown("""
<style>
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.page_link("app.py",            label="← Overview")
    st.page_link("pages/2_Family.py", label="← Family detail")

# ── Header ───────────────────────────────────────────────────────────────────────
st.markdown("## Organisation Profile")
st.markdown(
    "<p style='color:#888888;margin-top:-0.4rem;margin-bottom:1rem;font-size:15px;'>"
    "Search any organisation that appears in the dataset — academic, corporate, or government."
    "</p>",
    unsafe_allow_html=True,
)

# ── Search section ────────────────────────────────────────────────────────────────
query = st.text_input(
    "Search organisation",
    placeholder="e.g. ASML, MIT, Samsung, IMEC ...",
    key="org_query",
    label_visibility="collapsed",
)

selected_org_id: str | None = st.session_state.get("selected_org_id")

if query and len(query) >= 2:
    results = search_orgs(query)
    if len(results) == 0:
        st.caption("No organisations found — try a shorter or different term.")
    else:
        names = results["canonical_name"].to_list()
        ids = results["org_id"].to_list()
        chosen_name = st.radio(
            "Select organisation",
            names,
            key="org_search_radio",
            label_visibility="collapsed",
            horizontal=False,
        )
        chosen_idx = names.index(chosen_name)
        selected_org_id = ids[chosen_idx]
        st.session_state.selected_org_id = selected_org_id

if not selected_org_id:
    st.info(
        "Type an organisation name above to search. "
        "You can also arrive here from the Family Detail page leaderboard."
    )
    st.stop()

# ── Load profile ──────────────────────────────────────────────────────────────────
profile_df = load_org_profile(selected_org_id)
if len(profile_df) == 0:
    st.error(f"Organisation '{selected_org_id}' not found in the dataset.")
    st.stop()

profile = profile_df.row(0, named=True)
org_name = profile["canonical_name"]
match_method = profile["primary_match_method"]
confidence = profile["primary_confidence"]

# ── Org card ──────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='border:1px solid #e6e6e6;border-radius:6px;"
    f"padding:16px 20px;margin-bottom:1.2rem;'>"
    f"<div style='font-size:22px;font-weight:700;color:#111111;margin-bottom:8px;'>"
    f"{org_name}</div>"
    f"<div style='display:flex;gap:8px;align-items:center;'>"
    f"{method_badge(match_method)} {confidence_badge(confidence)}"
    f"<span style='font-size:11px;color:#888888;margin-left:4px;'>"
    f"match method · confidence</span></div>"
    f"</div>",
    unsafe_allow_html=True,
)

# ── Load data (parallel) ──────────────────────────────────────────────────────────
with st.spinner("Loading organisation data…"):
    output_by_family  = load_org_output_by_family(selected_org_id)
    top_clusters      = load_org_top_patent_clusters(selected_org_id)
    filing_years      = load_org_filing_years(selected_org_id)
    intake            = load_org_intake(selected_org_id)
    influence         = load_org_influence(selected_org_id)
    flagship_paper    = load_org_flagship_paper(selected_org_id)
    flagship_patent   = load_org_flagship_patent(selected_org_id)

has_patents   = len(output_by_family) > 0
has_intake    = len(intake) > 0
has_influence = len(influence) > 0

# ── Patent output section ─────────────────────────────────────────────────────────
st.markdown("#### Patent output")

if not has_patents:
    st.caption("No resolved US patents found for this organisation in the dataset.")
else:
    col_fam, col_cl = st.columns(2)

    with col_fam:
        family_ids   = output_by_family["family_id"].to_list()
        family_names = output_by_family["family_name"].to_list()
        n_patents    = output_by_family["n_patents"].to_list()
        bar_colors   = [FAMILY_COLORS.get(fid, "#888888") for fid in family_ids]

        pairs = sorted(zip(n_patents, family_names, bar_colors, strict=False))
        pv, pn, pc = map(list, zip(*pairs, strict=False))

        fig_fam = go.Figure(go.Bar(
            x=pv, y=pn, orientation="h",
            marker_color=pc,
            text=[f"{v:,}" for v in pv],
            textposition="outside",
            cliponaxis=False,
        ))
        fig_fam.update_layout(
            title=dict(text="US patents by family", font=dict(size=12, color="#111111"), x=0),
            height=max(180, 45 * len(pairs)),
            margin=dict(l=0, r=60, t=30, b=5),
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            font=dict(size=11, color="#111111"),
            xaxis=dict(showgrid=True, gridcolor="#e6e6e6", zeroline=False, title="US patents"),
            yaxis=dict(showgrid=False),
            showlegend=False,
        )
        st.plotly_chart(fig_fam, use_container_width=True, config={"displayModeBar": False})

    with col_cl:
        st.markdown(
            "<div style='font-size:12px;font-weight:600;color:#111111;"
            "margin-bottom:6px;'>Top patent clusters</div>",
            unsafe_allow_html=True,
        )
        for row in top_clusters.to_dicts():
            pct = (row["share"] or 0) * 100
            st.markdown(
                f"<div style='padding:8px 0;border-bottom:1px solid #f0f0f0;'>"
                f"<div style='font-size:12px;color:#111111;font-weight:500;'>"
                f"{row['tagline']}</div>"
                f"<div style='font-size:11px;color:#888888;'>"
                f"{row['doc_count']:,} patents · {pct:.1f}% cluster share"
                f"</div></div>",
                unsafe_allow_html=True,
            )

    if len(filing_years) > 0:
        yrs = filing_years["year"].to_list()
        nps = filing_years["n_patents"].to_list()
        fig_hist = go.Figure(go.Bar(
            x=yrs, y=nps,
            marker_color=PATENT_COLOR,
            text=[str(v) for v in nps],
            textposition="outside",
            cliponaxis=False,
        ))
        fig_hist.update_layout(
            title=dict(
                text="Filing year distribution (US patents)",
                font=dict(size=12, color="#111111"), x=0,
            ),
            height=180,
            margin=dict(l=0, r=10, t=30, b=5),
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            font=dict(size=11, color="#111111"),
            xaxis=dict(showgrid=False, zeroline=False, dtick=2),
            yaxis=dict(showgrid=True, gridcolor="#e6e6e6", zeroline=False),
            showlegend=False,
        )
        st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False})
        st.markdown(
            "<span style='font-size:11px;color:#888888;'>"
            "Filing counts after 2019 are understated — recently filed patents take "
            "2–4 years to be granted and appear in PatentsView."
            "</span>",
            unsafe_allow_html=True,
        )

st.divider()

# ── Research intake section ───────────────────────────────────────────────────────
st.markdown("#### Research intake")
st.markdown(
    "<span style='font-size:12px;color:#888888;'>"
    "Organisations whose research papers this org cites in its US patents "
    "(via NPL citation links)."
    "</span>",
    unsafe_allow_html=True,
)

if not has_intake:
    st.caption(
        "No NPL-linked intake data found — this org's patents either have no "
        "traceable NPL citations or cite papers from unresolved orgs."
    )
else:
    intake_names  = intake["paper_org_name"].to_list()
    intake_counts = intake["n_papers_cited"].to_list()
    intake_ids    = intake["paper_org_id"].to_list()

    pairs_i = sorted(zip(intake_counts, intake_names, intake_ids, strict=False))
    ic, inn, iid = map(list, zip(*pairs_i, strict=False))

    def _intake_color(org_id_val: str) -> str:
        return PAPER_COLOR if org_id_val != selected_org_id else "#888888"

    colors_i = [_intake_color(x) for x in iid]

    fig_intake = go.Figure(go.Bar(
        x=ic, y=inn, orientation="h",
        marker_color=colors_i,
        text=[f"{v:,}" for v in ic],
        textposition="outside",
        cliponaxis=False,
    ))
    fig_intake.update_layout(
        height=max(200, 35 * len(pairs_i)),
        margin=dict(l=0, r=60, t=5, b=5),
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        font=dict(size=11, color="#111111"),
        xaxis=dict(
            showgrid=True, gridcolor="#e6e6e6", zeroline=False,
            title="Distinct papers cited",
        ),
        yaxis=dict(showgrid=False),
        showlegend=False,
    )
    st.plotly_chart(fig_intake, use_container_width=True, config={"displayModeBar": False})

    self_rows = intake.filter(pl.col("paper_org_id") == selected_org_id)
    n_self = int(self_rows["n_papers_cited"].sum()) if len(self_rows) > 0 else 0
    n_total = int(intake["n_papers_cited"].sum())
    if n_self > 0:
        st.markdown(
            f"<span style='font-size:11px;color:#888888;'>"
            f"Includes {n_self:,} self-citations ({n_self / n_total:.0%} of total). "
            f"Grey bar = this organisation."
            f"</span>",
            unsafe_allow_html=True,
        )

st.divider()

# ── Influence section ─────────────────────────────────────────────────────────────
st.markdown("#### Who patents this organisation's research")
st.markdown(
    "<span style='font-size:12px;color:#888888;'>"
    "Organisations that filed US patents citing this org's research papers "
    "(via NPL links). Self-citations excluded."
    "</span>",
    unsafe_allow_html=True,
)

if not has_influence:
    st.caption(
        "No NPL-linked influence data found — this org's papers are either not "
        "cited in any in-scope US patent, or the links are unresolved."
    )
else:
    inf_names  = influence["patenter_name"].to_list()
    inf_counts = influence["n_patents"].to_list()

    pairs_inf = sorted(zip(inf_counts, inf_names, strict=False))
    infv, infn = map(list, zip(*pairs_inf, strict=False))

    fig_inf = go.Figure(go.Bar(
        x=infv, y=infn, orientation="h",
        marker_color=PATENT_COLOR,
        text=[f"{v:,}" for v in infv],
        textposition="outside",
        cliponaxis=False,
    ))
    fig_inf.update_layout(
        height=max(200, 35 * len(pairs_inf)),
        margin=dict(l=0, r=60, t=5, b=5),
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        font=dict(size=11, color="#111111"),
        xaxis=dict(
            showgrid=True, gridcolor="#e6e6e6", zeroline=False,
            title="Patents citing this org's research",
        ),
        yaxis=dict(showgrid=False),
        showlegend=False,
    )
    st.plotly_chart(fig_inf, use_container_width=True, config={"displayModeBar": False})

st.divider()

# ── Flagship documents section ────────────────────────────────────────────────────
has_fp = len(flagship_paper) > 0
has_fpt = len(flagship_patent) > 0

if has_fp or has_fpt:
    st.markdown("#### Flagship documents")
    fc1, fc2 = st.columns(2)

    with fc1:
        if has_fp:
            fp_row = flagship_paper.row(0, named=True)
            pub_yr = fp_row["publication_date"].year if fp_row["publication_date"] else "—"
            abstract = (fp_row["abstract"] or "")[:280]
            if len(fp_row["abstract"] or "") > 280:
                abstract += "…"
            st.markdown(
                f"<div style='border:1px solid #e6e6e6;border-left:4px solid {PAPER_COLOR};"
                f"border-radius:4px;padding:14px;'>"
                f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
                f"text-transform:uppercase;color:#888888;margin-bottom:6px;'>"
                f"Most-cited paper · {fp_row['n_citing_patents']:,} patents cite this</div>"
                f"<div style='font-size:14px;font-weight:600;color:#111111;"
                f"margin-bottom:6px;line-height:1.4;'>{fp_row['title']}</div>"
                f"<div style='font-size:11px;color:#888888;margin-bottom:8px;'>"
                f"Published {pub_yr}</div>"
                f"<div style='font-size:11px;color:#555555;line-height:1.5;'>"
                f"{abstract}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with fc2:
        if has_fpt:
            fpt_row = flagship_patent.row(0, named=True)
            filing_yr = fpt_row["filing_date"].year if fpt_row["filing_date"] else "—"
            st.markdown(
                f"<div style='border:1px solid #e6e6e6;border-left:4px solid {PATENT_COLOR};"
                f"border-radius:4px;padding:14px;'>"
                f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
                f"text-transform:uppercase;color:#888888;margin-bottom:6px;'>"
                f"Most NPL-citing patent · cites {fpt_row['n_papers_cited']:,} papers"
                f"</div>"
                f"<div style='font-size:14px;font-weight:600;color:#111111;"
                f"margin-bottom:6px;line-height:1.4;'>{fpt_row['title']}</div>"
                f"<div style='font-size:11px;color:#888888;'>"
                f"Filed {filing_yr} · US{fpt_row['patent_id']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.divider()

# ── Footer ────────────────────────────────────────────────────────────────────────
st.markdown(
    "<span style='font-size:11px;color:#888888;'>"
    "<strong>Data quality:</strong> "
    "Org matches use the crosswalk (seed → ROR → fuzzy). "
    "Confidence badge reflects the match tier. "
    "Intake and influence panels are based on NPL citation links only "
    "(5,921 high/medium-confidence links total). "
    "An org with many patents but no NPL-linked intake data filed patents that "
    "cite non-matching or non-OpenAlex reference strings. "
    "US patents only (PatentsView / USPTO)."
    "</span>",
    unsafe_allow_html=True,
)
