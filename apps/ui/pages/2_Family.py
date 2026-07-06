# pyright: basic
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

from data import (
    load_family_clusters,
    load_family_org_leaderboard,
    load_family_scorecard,
    load_family_velocity,
)
from render import (
    FAMILY_COLORS,
    FAMILY_LABELS,
    render_chip_multiselect,
    render_nav,
    render_tour_banner,
)

st.set_page_config(
    page_title="Family Deepdive — The Chips Behind AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
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
.js-plotly-plot .plotly .cursor-crosshair { cursor: default !important; }
.js-plotly-plot .cartesianlayer .spikeline { display: none !important; }
</style>
""", unsafe_allow_html=True)

render_nav("Family Deepdive", filter_sidebar=True)
render_tour_banner(2)

_HEADLINE_FAMILIES = {k: v for k, v in FAMILY_LABELS.items() if k not in ("adjacent", "noise")}

_FAMILY_DESC: dict[str, str] = {
    "euv": (
        "Extreme-UV optics that print transistors smaller than a virus — "
        "the bottleneck of the entire chip industry."
    ),
    "silicon_photonics": (
        "Moving data as light instead of electricity — from the on-chip lasers "
        "that generate it to the silicon waveguides that route it — cutting "
        "latency and power inside AI data centres."
    ),
    "neuromorphic_in_memory": (
        "Chips that compute the way neurons do and store data where they compute "
        "it, trading raw clock speed for dramatic energy efficiency by skipping "
        "the slow trip to memory."
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
if family_id not in _HEADLINE_FAMILIES:
    family_id = "euv"

# ── Load data ──────────────────────────────────────────────────────────────────
scorecard_df = load_family_scorecard()
family_row_df = scorecard_df.filter(pl.col("family_id") == family_id)
if len(family_row_df) == 0:
    st.error(f"No data found for family '{family_id}'.")
    st.stop()

frow         = family_row_df.row(0, named=True)
family_color = FAMILY_COLORS.get(family_id, "#888888")
family_name  = FAMILY_LABELS.get(family_id, family_id)
family_desc  = _FAMILY_DESC.get(family_id, "")

clusters = load_family_clusters(family_id)

# Reset the cluster filter whenever the active family changes (pill switcher / query param).
if st.session_state.get("_fam_filter_active_family") != family_id:
    st.session_state["_fam_filter_active_family"] = family_id
    st.session_state["_fam_sel_clusters"] = []

# ── Sidebar filter ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### Filters")
    _cluster_scope = [
        (r["tagline"], r["cluster_id"]) for r in clusters.sort("tagline").to_dicts()
    ]
    selected_clusters: list[str] = render_chip_multiselect(
        "Cluster",
        "_fam_sel_clusters",
        _cluster_scope,
        placeholder="Add cluster…",
        search_key="family_cluster_sb",
    )

cluster_ids_filter = tuple(selected_clusters) if selected_clusters else None

pat_df = load_family_org_leaderboard(family_id, "patent", 50, cluster_ids=cluster_ids_filter)
res_df = load_family_org_leaderboard(family_id, "paper", 50, cluster_ids=cluster_ids_filter)

_clusters_filtered = (
    clusters.filter(pl.col("cluster_id").is_in(selected_clusters))
    if selected_clusters else clusters
)

# ── Family pill switcher — single line, max size ──────────────────────────────
_pills_html = ""
for _fid, _flbl in _HEADLINE_FAMILIES.items():
    _fc = FAMILY_COLORS.get(_fid, "#888888")
    if _fid == family_id:
        _pills_html += (
            f"<a href='/Family?family={_fid}' target='_self' class='fpill fpill-on'"
            f" style='background:{_fc};color:#ffffff;border-color:{_fc};'>{_flbl}</a>"
        )
    else:
        _pills_html += (
            f"<a href='/Family?family={_fid}' target='_self' class='fpill fpill-off'"
            f" style='color:{_fc};border-color:{_fc};'>{_flbl}</a>"
        )

st.markdown(
    "<style>"
    ".fpill-row { display:flex; flex-wrap:nowrap; gap:10px; margin-bottom:1rem; width:100%; }"
    ".fpill { flex:1 1 0; text-align:center; font-size:19px; font-weight:600; white-space:nowrap;"
    "  padding:16px 20px; border-radius:10px; border:1.5px solid;"
    "  text-decoration:none !important; transition:opacity .15s; }"
    ".fpill-on  { font-weight:700; }"
    ".fpill-off { background:#ffffff; opacity:0.6; }"
    ".fpill-off:hover { opacity:1; }"
    "</style>"
    f"<div class='fpill-row'>{_pills_html}</div>"
    f"<p style='color:#888888;font-size:15px;margin-top:0;margin-bottom:1.4rem;'>"
    f"{family_desc}</p>",
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
            f"<div class='card card--metric' style='margin-bottom:1rem;--accent:{family_color};'>"
            f"<div class='card-stat' style='font-family:{_FONT};font-size:28px;"
            f"font-weight:800;line-height:1;'>{value}</div>"
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
                config={"displayModeBar": False, "displaylogo": False},
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
                config={"displayModeBar": False, "displaylogo": False},
                key="bar_paper",
            )
    else:
        st.caption("No researcher data for this family.")

# ── Velocity: research & patenting over time ───────────────────────────────────
vel_df = load_family_velocity(family_id, cluster_ids=cluster_ids_filter)
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
    _vel_scope_note = (
        f" (filtered to {len(selected_clusters)} selected clusters)" if selected_clusters else ""
    )

    st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-family:{_FONT};font-size:14px;font-weight:700;"
        f"color:#111111;'>Research &amp; patenting over time</div>"
        f"<div style='font-size:12px;color:#888888;margin-bottom:8px;'>"
        f"Annual research papers (by publication year) and granted US patents "
        f"(by filing year) in {family_name}{_vel_scope_note}. "
        f"The shaded years are still moving "
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
                   showline=True, linecolor="#e6e6e6", tickfont=dict(size=11),
                   showspikes=False),
        yaxis=dict(gridcolor="#f0f0f0", zeroline=False, rangemode="tozero",
                   tickfont=dict(size=11), showspikes=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=11), title=None),
        hovermode="x unified",
        dragmode=False,
    )
    st.plotly_chart(
        fig_vel, use_container_width=True,
        config={"displayModeBar": False, "displaylogo": False}, key="velocity_chart",
    )

# ── Cluster breakdown table ────────────────────────────────────────────────────
if len(_clusters_filtered) > 0:
    n_shown = len(_clusters_filtered)
    n_total = len(clusters)
    count_label = f"{n_shown} of {n_total} clusters" if selected_clusters else f"{n_total} clusters"

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
