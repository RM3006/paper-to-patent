"""
Family Detail — Surface 2.

Header card, 4 metric cards, scrollable leaderboards, velocity trend,
and cluster breakdown table. Entered from Surface 1 "Explore family →"
or via the sidebar family selector.

Source marts: mart_family, mart_competitive, mart_velocity, mart_gap,
              seed_cluster_family.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from render import FAMILY_COLORS
from streamlit_searchbox import st_searchbox

from data import (
    load_family_clusters,
    load_family_org_leaderboard,
    load_family_scorecard,
    load_family_velocity,
)

st.set_page_config(
    page_title="Family Detail — The Chips Behind AI",
    page_icon="🔬",
    layout="wide",
)

_FONT = '"Space Grotesk", -apple-system, system-ui, sans-serif'

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&display=swap');
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
.st-key-leaderboard_pat,
.st-key-leaderboard_res {
    border: 1px solid #e6e6e6 !important;
    border-radius: 8px !important;
    box-shadow: none !important;
}
</style>
""", unsafe_allow_html=True)

_FAMILIES: dict[str, str] = {
    "euv":          "EUV Lithography",
    "si_photonics": "Silicon Photonics & Optical I/O",
    "lasers":       "Lasers & Light Sources",
    "neuromorphic": "Neuromorphic / Brain-inspired",
    "in_memory":    "In-Memory & Emerging Memory",
}

_FAMILY_DESC: dict[str, str] = {
    "euv": (
        "Extreme-UV optics that print transistors smaller than a virus — "
        "the bottleneck of the entire chip industry."
    ),
    "si_photonics": (
        "Moving data as light pulses through silicon, replacing copper wires "
        "to cut latency and power inside AI servers."
    ),
    "lasers": (
        "Coherent light sources integrated at chip scale, enabling the transceivers "
        "that hold data-centre networks together."
    ),
    "neuromorphic": (
        "Brain-inspired chips that process data the way neurons fire, trading raw "
        "clock speed for dramatic energy efficiency."
    ),
    "in_memory": (
        "Processing data where it is stored so the chip never has to fetch it "
        "across slow memory buses."
    ),
}


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Determine active family ────────────────────────────────────────────────────
family_id: str = (
    st.query_params.get("family")
    or st.session_state.get("selected_family", "euv")
)
if family_id not in _FAMILIES:
    family_id = "euv"

# ── Load data ──────────────────────────────────────────────────────────────────
scorecard_df = load_family_scorecard()
family_row_df = scorecard_df.filter(pl.col("family_id") == family_id)
if len(family_row_df) == 0:
    st.error(f"No data found for family '{family_id}'.")
    st.stop()

frow         = family_row_df.row(0, named=True)
family_color = FAMILY_COLORS.get(family_id, "#888888")
family_name  = _FAMILIES.get(family_id, family_id)
family_desc  = _FAMILY_DESC.get(family_id, "")

pat_df   = load_family_org_leaderboard(family_id, "patent", 50)
res_df   = load_family_org_leaderboard(family_id, "paper", 50)
clusters = load_family_clusters(family_id)

# ── Sidebar — same design as Map page ─────────────────────────────────────────
_cluster_opts = clusters.sort("tagline").select(["cluster_id", "tagline"]).to_dicts()
_cluster_map: dict[str, str] = {r["cluster_id"]: r["tagline"] for r in _cluster_opts}

_STYLE = {"searchbox": {"option": {"highlightColor": "#f0f0f0"}}}

_fam_scope = [(lbl, fid) for fid, lbl in _FAMILIES.items()]
_clust_scope = [(r["tagline"], r["cluster_id"]) for r in _cluster_opts]

def _search_fam(query: str) -> list[tuple[str, str]]:
    if not query:
        return _fam_scope
    q = query.lower()
    return [(lbl, fid) for lbl, fid in _fam_scope if q in lbl.lower()]

def _search_clust(query: str) -> list[tuple[str, str]]:
    if not query:
        return _clust_scope[:20]
    q = query.lower()
    return [(lbl, cid) for lbl, cid in _clust_scope if q in lbl.lower()]

if "_fam_sel_clusters" not in st.session_state:
    st.session_state["_fam_sel_clusters"] = []

with st.sidebar:
    st.markdown("#### Filters")
    st.caption(f"Technology family · {family_name}")
    _fam_pick = st_searchbox(
        _search_fam,
        placeholder="Switch family…",
        key="family_selector_sb",
        edit_after_submit="option",
        style_overrides=_STYLE,
        default_options=_fam_scope,
    )
    if _fam_pick and _fam_pick != family_id:
        st.session_state.selected_family = _fam_pick
        st.session_state["_fam_sel_clusters"] = []
        st.rerun()

    st.caption("Cluster")
    _clust_pick = st_searchbox(
        _search_clust,
        placeholder="Add cluster…",
        key="family_cluster_sb",
        clear_on_submit=True,
        style_overrides=_STYLE,
        default_options=_clust_scope[:20],
    )
    if _clust_pick and _clust_pick not in st.session_state["_fam_sel_clusters"]:
        st.session_state["_fam_sel_clusters"].append(_clust_pick)
        st.rerun()
    for _cid in list(st.session_state["_fam_sel_clusters"]):
        _lbl = _cluster_map.get(_cid, _cid)
        _short = _lbl[:30] + "…" if len(_lbl) > 30 else _lbl
        if st.button(f"× {_short}", key=f"rm_fc_{_cid}",
                     use_container_width=True, type="secondary"):
            st.session_state["_fam_sel_clusters"].remove(_cid)
            st.rerun()

    st.divider()
    st.page_link("app.py", label="← Back to overview")

selected_clusters: list[str] = st.session_state["_fam_sel_clusters"]

# Cluster filter applies only to the breakdown table at the bottom.
_clusters_filtered = (
    clusters.filter(pl.col("cluster_id").is_in(selected_clusters))
    if selected_clusters else clusters
)

# ── Header card ────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='padding:24px 0 16px 0;'>"
    f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
    f"text-transform:uppercase;color:{family_color};margin-bottom:8px;'>"
    f"Technology family</div>"
    f"<div style='font-family:{_FONT};font-size:26px;font-weight:800;"
    f"color:#111111;line-height:1.1;margin-bottom:10px;'>{family_name}</div>"
    f"<div style='font-size:14px;color:#555555;line-height:1.6;'>{family_desc}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# ── 4 metric cards ─────────────────────────────────────────────────────────────
pct       = (frow["patent_share"] or 0.0) * 100
lag       = frow["median_lag_years_weighted"]
lag_str   = f"{lag:.1f} yr" if lag is not None else "—"
n_patents = frow["n_patents"] or 0
n_papers  = frow["n_papers"] or 0

m1, m2, m3, m4 = st.columns(4)
for col, value, label in [
    (m1, f"{pct:.0f}%",    "patent share"),
    (m2, lag_str,           "citation lag"),
    (m3, f"{n_patents:,}", "granted US patents"),
    (m4, f"{n_papers:,}",  "research papers"),
]:
    with col:
        st.markdown(
            f"<div style='border:1px solid #e6e6e6;border-radius:8px;"
            f"padding:18px 8px;text-align:center;height:90px;"
            f"display:flex;flex-direction:column;align-items:center;"
            f"justify-content:center;margin-bottom:1rem;'>"
            f"<div style='font-family:{_FONT};font-size:28px;font-weight:800;"
            f"color:{family_color};line-height:1;'>{value}</div>"
            f"<div style='font-size:12px;color:#888888;margin-top:6px;"
            f"white-space:nowrap;'>{label}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ── Bar chart builder ──────────────────────────────────────────────────────────
def _bar_chart(df: pl.DataFrame, color: str) -> go.Figure:
    names  = [n[:28] + "…" if len(n) > 28 else n for n in df["canonical_name"].to_list()]
    counts = [int(v) for v in df["doc_count"].to_list()]
    chart_height = max(len(df), 3) * 38 + 60
    f = go.Figure(go.Bar(
        orientation="h", x=counts, y=names,
        marker_color=color, marker_opacity=0.85,
        text=counts, textposition="outside",
        textfont=dict(size=11, color="#111111"),
    ))
    f.update_layout(
        height=chart_height,
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        yaxis=dict(autorange="reversed", tickfont=dict(size=11),
                   automargin=True, showgrid=False, zeroline=False),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   range=[0, max(counts) * 1.25]),
        margin=dict(l=8, r=60, t=8, b=8),
    )
    return f


def _chart_title(main: str, sub: str) -> None:
    st.markdown(
        f"<div style='padding:0 4px 8px 4px;'>"
        f"<span style='font-size:12px;font-weight:700;color:#555555;"
        f"letter-spacing:.04em;'>{main}</span>"
        f"<span style='font-size:11px;color:#aaaaaa;font-weight:400;"
        f"margin-left:5px;'>{sub}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ── Leaderboard charts ─────────────────────────────────────────────────────────
st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
col_pat, col_res = st.columns(2)
_scroll_h = 10 * 38 + 70

with col_pat:
    if len(pat_df) > 0:
        total_patenters = int(pat_df["total_orgs"][0])
        with st.container(height=_scroll_h, border=True, key="leaderboard_pat"):
            _chart_title(f"TOP {len(pat_df)} PATENTERS", f"out of {total_patenters:,}")
            st.plotly_chart(
                _bar_chart(pat_df, family_color),
                use_container_width=True,
                config={"displayModeBar": False},
                key="bar_patent",
            )
    else:
        st.caption("No patent data for this family.")

with col_res:
    if len(res_df) > 0:
        total_researchers = int(res_df["total_orgs"][0])
        with st.container(height=_scroll_h, border=True, key="leaderboard_res"):
            _chart_title(f"TOP {len(res_df)} RESEARCHERS", f"out of {total_researchers:,}")
            st.plotly_chart(
                _bar_chart(res_df, family_color),
                use_container_width=True,
                config={"displayModeBar": False},
                key="bar_paper",
            )
    else:
        st.caption("No researcher data for this family.")

# ── Velocity: research & patenting over time ───────────────────────────────────
vel_df = load_family_velocity(family_id)
if len(vel_df) > 0:
    years   = [int(y) for y in vel_df["year"].to_list()]
    papers  = [int(v) for v in vel_df["paper_count"].to_list()]
    patents = [int(v) for v in vel_df["patent_count"].to_list()]
    max_year = max(years)

    _raw_lag = frow["median_lag_years_weighted"]
    _provisional_years = max(1, round(float(_raw_lag))) if _raw_lag is not None else 3
    cutoff = max_year - _provisional_years

    pat_solid = [p if y <= cutoff else None for y, p in zip(years, patents, strict=True)]
    pat_prov  = [p if y >= cutoff else None for y, p in zip(years, patents, strict=True)]
    col_papers  = _hex_rgba(family_color, 0.45)
    col_patents = family_color

    st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-family:{_FONT};font-size:14px;font-weight:700;"
        f"color:#111111;'>Research &amp; patenting over time</div>"
        f"<div style='font-size:12px;color:#888888;margin-bottom:8px;'>"
        f"Annual research papers (by publication year) and granted US patents "
        f"(by filing year) in {family_name}. The shaded years are still moving "
        f"through the grant pipeline and undercount real patenting — not a decline."
        f"</div>",
        unsafe_allow_html=True,
    )

    fig_vel = go.Figure()
    fig_vel.add_trace(go.Scatter(
        x=years, y=papers, name="Research papers",
        mode="lines+markers", line=dict(color=col_papers, width=2.5),
        marker=dict(size=5, color=col_papers),
        hovertemplate="%{x}<br>%{y:,} papers<extra></extra>",
    ))
    fig_vel.add_trace(go.Scatter(
        x=years, y=pat_solid, name="Granted US patents",
        mode="lines+markers", line=dict(color=col_patents, width=2.5),
        marker=dict(size=5, color=col_patents), connectgaps=False,
        hovertemplate="%{x}<br>%{y:,} patents<extra></extra>",
    ))
    fig_vel.add_trace(go.Scatter(
        x=years, y=pat_prov, name="Patents — filings still pending",
        mode="lines+markers", line=dict(color=col_patents, width=2.5, dash="dot"),
        marker=dict(size=5, color=col_patents), opacity=0.35, connectgaps=False,
        hovertemplate="%{x}<br>%{y:,} patents (incomplete)<extra></extra>",
    ))
    fig_vel.add_vrect(
        x0=cutoff + 0.5, x1=max_year + 0.5,
        fillcolor="#f5f5f5", opacity=0.7, line_width=0, layer="below",
    )
    fig_vel.update_layout(
        height=340,
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        font=dict(size=12, color="#111111"),
        margin=dict(l=10, r=20, t=10, b=40),
        xaxis=dict(dtick=2, showgrid=False, zeroline=False,
                   showline=True, linecolor="#e6e6e6", tickfont=dict(size=11)),
        yaxis=dict(gridcolor="#f0f0f0", zeroline=False, rangemode="tozero",
                   tickfont=dict(size=11)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=11), title=None),
        hovermode="x unified",
    )
    st.plotly_chart(
        fig_vel, use_container_width=True,
        config={"displayModeBar": False}, key="velocity_chart",
    )

# ── Cluster breakdown table ────────────────────────────────────────────────────
if len(_clusters_filtered) > 0:
    n_shown = len(_clusters_filtered)
    n_total = len(clusters)
    count_label = (
        f"{n_shown} of {n_total} clusters"
        if selected_clusters else
        f"{n_total} clusters"
    )

    st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)

    _hdr_col, _link_col = st.columns([3, 1])
    with _hdr_col:
        st.markdown(
            f"<div style='font-family:{_FONT};font-size:14px;font-weight:700;"
            f"color:#111111;margin-bottom:4px;'>{count_label} in {family_name}</div>"
            f"<div style='font-size:12px;color:#888888;margin-bottom:10px;'>"
            f"Sorted by number of patents. Hover over 'Lag (yr)' and 'HHI' columns for definitions."
            f"</div>",
            unsafe_allow_html=True,
        )
    with _link_col:
        st.markdown(
            "<div style='text-align:right;padding-top:6px;'>"
            "<a href='/Map' target='_self' style='font-size:13px;color:#111111;"
            "text-decoration:underline;text-underline-offset:3px;'>"
            "See all clusters on the map →</a>"
            "</div>",
            unsafe_allow_html=True,
        )

    _sorted = _clusters_filtered.sort("n_patents", descending=True)

    _display = (
        _sorted
        .with_columns([
            pl.when(pl.col("npl_reportable"))
              .then(pl.col("npl_median_lag_years"))
              .otherwise(None)
              .cast(pl.Float64)
              .alias("lag_years"),
            pl.when(pl.col("hhi_reportable"))
              .then(pl.col("hhi"))
              .otherwise(None)
              .cast(pl.Float64)
              .alias("hhi_display"),
        ])
        .select([
            pl.col("tagline").alias("Cluster"),
            pl.col("n_papers").alias("Papers"),
            pl.col("n_patents").alias("Patents"),
            pl.col("lag_years").alias("Lag (yr)"),
            pl.col("hhi_display").alias("HHI"),
            pl.col("n_research_orgs").alias("# of Researchers"),
            pl.col("n_assignees").alias("# of Patenters"),
        ])
    )

    st.dataframe(
        _display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Cluster": st.column_config.TextColumn(width="large"),
            "Papers": st.column_config.NumberColumn(format="%d"),
            "Patents": st.column_config.NumberColumn(format="%d"),
            "Lag (yr)": st.column_config.NumberColumn(
                format="%.1f",
                width="small",
                help=(
                    "NPL = Non-Patent Literature. When a patent is filed it may cite "
                    "scientific papers as prior art — those are NPL citations. "
                    "This is the median time (years) between a paper publication date "
                    "and the filing date of a patent that cited it. "
                    "Shown only when ≥20 NPL citations exist for this cluster."
                ),
            ),
            "HHI": st.column_config.NumberColumn(
                format="%.2f",
                width="small",
                help=(
                    "Herfindahl-Hirschman Index — measures how concentrated patent "
                    "ownership is in this cluster. "
                    "0 = many assignees each with a tiny share. "
                    "1 = one assignee holds everything. "
                    "Above 0.25 is already highly concentrated. "
                    "Shown only when ≥10 resolved patents exist."
                ),
            ),
            "# of Researchers": st.column_config.NumberColumn(format="%d", width="small"),
            "# of Patenters": st.column_config.NumberColumn(format="%d", width="small"),
        },
    )

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown(
    "<span style='font-size:11px;color:#888888;'>"
    "Granted US patents only (PatentsView / USPTO). "
    "Papers from OpenAlex (2012–2025). "
    "Lag = paper publication date → citing patent filing date via NPL citations. "
    "Org counts exclude 'Unresolved' entries."
    "</span>",
    unsafe_allow_html=True,
)
