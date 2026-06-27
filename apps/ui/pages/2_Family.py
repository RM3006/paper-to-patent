"""
Family Detail — Surface 2.

Asymmetry panel + top org leaderboards + citation-lag spectrum scatter + cluster list.
Entered from Surface 1 "Explore →" button (family_id in st.session_state.selected_family)
or via the sidebar selector.

Source marts: mart_gap, mart_competitive, mart_family, seed_cluster_family.
"""
from __future__ import annotations

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from render import FAMILY_COLORS, PAPER_COLOR, PATENT_COLOR, hhi_color

from data import load_family_clusters, load_family_scorecard, load_top_orgs

st.set_page_config(
    page_title="Family Detail — The Chips Behind AI",
    page_icon="🔬",
    layout="wide",
)

st.markdown("""
<style>
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── Constants ───────────────────────────────────────────────────────────────────
_FAMILIES: dict[str, str] = {
    "euv":          "EUV Lithography",
    "si_photonics": "Silicon Photonics & Optical I/O",
    "lasers":       "Lasers & Light Sources",
    "neuromorphic": "Neuromorphic / Brain-inspired",
    "in_memory":    "In-Memory & Emerging Memory",
}

# ── Family selector (sidebar) ───────────────────────────────────────────────────
family_id: str = st.session_state.get("selected_family", "euv")
if family_id not in _FAMILIES:
    family_id = "euv"

with st.sidebar:
    st.markdown(
        "<div style='font-weight:700;color:#111111;font-size:0.95rem;"
        "margin-bottom:6px;'>Technology family</div>",
        unsafe_allow_html=True,
    )
    chosen = st.selectbox(
        "Technology family",
        options=list(_FAMILIES.keys()),
        format_func=lambda k: _FAMILIES[k],
        index=list(_FAMILIES.keys()).index(family_id),
        label_visibility="collapsed",
        key="family_selector",
    )
    if chosen != family_id:
        st.session_state.selected_family = chosen
        st.rerun()

    st.divider()
    st.page_link("app.py", label="← Back to overview")

# ── Load data ───────────────────────────────────────────────────────────────────
scorecard_df = load_family_scorecard()
family_row_df = scorecard_df.filter(pl.col("family_id") == family_id)
if len(family_row_df) == 0:
    st.error(f"No data found for family '{family_id}'.")
    st.stop()

frow = family_row_df.row(0, named=True)
family_color = FAMILY_COLORS.get(family_id, "#888888")
family_name = _FAMILIES.get(family_id, family_id)

clusters = load_family_clusters(family_id)
cluster_ids = tuple(clusters["cluster_id"].to_list())

top_patenters = load_top_orgs(cluster_ids, "patent", top_n=10)
top_researchers = load_top_orgs(cluster_ids, "paper", top_n=10)

# ── Header ──────────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='border-left:4px solid {family_color};padding-left:12px;"
    f"margin-bottom:0.8rem;'>"
    f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
    f"text-transform:uppercase;color:#888888;'>Technology family</div>"
    f"<div style='font-size:26px;font-weight:700;color:#111111;'>{family_name}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# ── Asymmetry panel ─────────────────────────────────────────────────────────────
st.markdown("#### Research breadth vs patent concentration")
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Papers", f"{frow['n_papers']:,}")
    st.markdown(
        f"<span style='font-size:11px;color:#888888;'>"
        f"from ~{frow['n_research_orgs_sum']:,} research orgs</span>",
        unsafe_allow_html=True,
    )
with c2:
    st.metric("US Patents", f"{frow['n_patents']:,}")
    st.markdown(
        f"<span style='font-size:11px;color:#888888;'>"
        f"by ~{frow['n_assignees_sum']:,} assignees</span>",
        unsafe_allow_html=True,
    )
with c3:
    pct = (frow["patent_share"] or 0) * 100
    st.metric("Patent share", f"{pct:.0f}%")
    ratio = (frow["n_research_orgs_sum"] or 1) / max(frow["n_assignees_sum"] or 1, 1)
    st.markdown(
        f"<span style='font-size:11px;color:#888888;'>"
        f"{ratio:.1f}× more research orgs than assignees</span>",
        unsafe_allow_html=True,
    )
with c4:
    lag = frow["median_lag_years_weighted"]
    lag_str = f"{lag:.2f} yr" if lag is not None else "—"
    st.metric("Median citation lag", lag_str)
    st.markdown(
        "<span style='font-size:11px;color:#888888;'>"
        "paper pub → patent filing (NPL links)</span>",
        unsafe_allow_html=True,
    )

st.divider()

# ── Top organisations ────────────────────────────────────────────────────────────
st.markdown("#### Top organisations")
c_pat, c_res = st.columns(2)


def _org_bar(
    df: pl.DataFrame, title: str, bar_color: str, x_label: str
) -> go.Figure:
    names = df["canonical_name"].to_list()
    counts = df["doc_count"].to_list()
    # Sort ascending so highest is at top of horizontal chart
    pairs = sorted(zip(counts, names, strict=False))
    cv, nv = map(list, zip(*pairs, strict=False))
    fig = go.Figure(go.Bar(
        x=cv,
        y=nv,
        orientation="h",
        marker_color=bar_color,
        text=[f"{v:,}" for v in cv],
        textposition="outside",
        cliponaxis=False,
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=12, color="#111111"), x=0),
        height=300,
        margin=dict(l=0, r=60, t=30, b=5),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(size=11, color="#111111"),
        xaxis=dict(showgrid=True, gridcolor="#e6e6e6", zeroline=False, title=x_label),
        yaxis=dict(showgrid=False),
        showlegend=False,
    )
    return fig


with c_pat:
    if len(top_patenters) > 0:
        st.plotly_chart(
            _org_bar(top_patenters, "Top 10 patenters", PATENT_COLOR, "US patents"),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    else:
        st.caption("No patent data for this family.")

with c_res:
    if len(top_researchers) > 0:
        st.plotly_chart(
            _org_bar(top_researchers, "Top 10 research orgs", PAPER_COLOR, "Papers"),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    else:
        st.caption("No research org data for this family.")

st.divider()

# ── Citation lag spectrum ────────────────────────────────────────────────────────
reportable = clusters.filter(pl.col("npl_reportable") == True)  # noqa: E712
if len(reportable) > 0:
    st.markdown("#### Citation lag spectrum")
    st.markdown(
        "<span style='font-size:12px;color:#888888;'>"
        "Each bubble is a cluster. X = median lag from paper pub to patent filing. "
        "Y = number of traceable NPL links. Colour = HHI patent concentration "
        "(green = diffuse, red = concentrated). Size ∝ log(papers + patents)."
        "</span>",
        unsafe_allow_html=True,
    )

    max_docs = int(reportable.select(
        (pl.col("n_papers") + pl.col("n_patents")).max()
    ).item())
    max_docs = max(max_docs, 1)

    sizes = [
        max(8, 40 * math.log1p(n_p + n_t) / math.log1p(max_docs))
        for n_p, n_t in zip(
            reportable["n_papers"].to_list(),
            reportable["n_patents"].to_list(),
            strict=False,
        )
    ]
    colors = [
        hhi_color(h) if (r and h is not None) else "#aaaaaa"
        for h, r in zip(
            reportable["hhi"].to_list(),
            reportable["hhi_reportable"].to_list(),
            strict=False,
        )
    ]
    hover = [
        (
            f"{tag}<br>"
            f"Lag: {lag:.2f} yr<br>"
            f"NPL links: {nlinks}<br>"
            f"HHI: {hhi:.2f}" if hhi is not None else f"{tag}<br>Lag: {lag:.2f} yr"
        )
        for tag, lag, nlinks, hhi in zip(
            reportable["tagline"].to_list(),
            reportable["npl_median_lag_years"].to_list(),
            reportable["npl_n_links"].to_list(),
            reportable["hhi"].to_list(),
            strict=False,
        )
    ]

    fig_lag = go.Figure(go.Scatter(
        x=reportable["npl_median_lag_years"].to_list(),
        y=reportable["npl_n_links"].to_list(),
        mode="markers",
        marker=dict(
            size=sizes,
            color=colors,
            opacity=0.8,
            line=dict(width=0.5, color="#ffffff"),
        ),
        text=hover,
        hovertemplate="%{text}<extra></extra>",
    ))
    fig_lag.update_layout(
        height=340,
        margin=dict(l=0, r=20, t=10, b=40),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(size=12, color="#111111"),
        xaxis=dict(
            title="Median citation lag (years)",
            showgrid=True,
            gridcolor="#e6e6e6",
            zeroline=False,
        ),
        yaxis=dict(
            title="NPL citation links",
            showgrid=True,
            gridcolor="#e6e6e6",
            zeroline=False,
        ),
        hovermode="closest",
    )
    st.plotly_chart(fig_lag, use_container_width=True, config={"displayModeBar": False})
    st.markdown(
        "<span style='font-size:11px;color:#888888;'>"
        f"Showing {len(reportable)} clusters with ≥20 NPL links (required for a reportable lag). "
        f"{len(clusters) - len(reportable)} clusters in this family have "
        f"too few links to report a lag."
        "</span>",
        unsafe_allow_html=True,
    )
    st.divider()

# ── Cluster list ─────────────────────────────────────────────────────────────────
with st.expander(f"All {len(clusters)} clusters in {family_name}", expanded=False):
    display = clusters.select([
        pl.col("tagline").alias("Cluster"),
        pl.col("n_papers").alias("Papers"),
        pl.col("n_patents").alias("US Patents"),
        pl.col("npl_median_lag_years").alias("Median Lag (yr)"),
        pl.col("hhi").alias("HHI"),
        pl.col("n_research_orgs").alias("Research Orgs"),
        pl.col("n_assignees").alias("Assignees"),
    ])
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Median Lag (yr)": st.column_config.NumberColumn(format="%.2f"),
            "HHI": st.column_config.NumberColumn(format="%.3f"),
        },
    )

# ── Footer ───────────────────────────────────────────────────────────────────────
st.markdown(
    "<span style='font-size:11px;color:#888888;'>"
    "<strong>Scope:</strong> US patents only (PatentsView / USPTO). "
    "Lag = paper publication date → patent filing date via NPL citations. "
    "Org counts are approximate (cross-cluster dedup not applied). "
    "HHI = Herfindahl-Hirschman Index over resolved assignees; NULL when fewer than 10 "
    "resolved patents in the cluster."
    "</span>",
    unsafe_allow_html=True,
)
