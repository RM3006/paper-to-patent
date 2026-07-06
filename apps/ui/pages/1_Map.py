# pyright: basic
"""
Technology Landscape — Surface 4.

Bubble chart: each dot = one technology cluster.
X = granted US patents (log), Y = research papers (log).
Colour = technology family. Click any dot to see the cluster detail card.

Source: mart_gap + seed_cluster_family + dim_technology_cluster + mart_competitive
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import plotly.graph_objects as go
import polars as pl
import streamlit as st

from data import load_cluster_bubble, load_cluster_card, load_top_orgs
from render import (
    FAMILY_COLORS,
    FAMILY_LABELS,
    render_chip_multiselect,
    render_nav,
    render_tour_banner,
)

st.set_page_config(
    page_title="Technology Landscape — The Chips Behind AI",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_FONT = '"Space Grotesk", -apple-system, system-ui, sans-serif'

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&display=swap');
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
.st-key-cluster_pat_scroll,
.st-key-cluster_res_scroll {
    border: 1px solid #e6e6e6 !important;
    border-radius: 8px !important;
    box-shadow: none !important;
}
.st-key-cta_to_org button,
.st-key-cta_res_to_org button {
    background-color: #111111 !important;
    color: #ffffff !important;
    border: 1px solid #111111 !important;
    font-weight: 600;
}
.st-key-cta_to_org button:hover,
.st-key-cta_res_to_org button:hover {
    background-color: #333333 !important;
    border-color: #333333 !important;
    color: #ffffff !important;
}
.js-plotly-plot .cartesianlayer .select-outline { display: none !important; }
.js-plotly-plot .cartesianlayer .zoomlayer { display: none !important; }
</style>
""", unsafe_allow_html=True)

render_nav("Technology Landscape", filter_sidebar=True)
render_tour_banner(1)

FAMILY_ORDER = ["euv", "silicon_photonics", "neuromorphic_in_memory", "adjacent", "noise"]

# ── Load ─────────────────────────────────────────────────────────────────────────────
df_all = load_cluster_bubble()


def _drop_clusters_of_family(fid: str) -> None:
    """Cascade: dropping a family chip also drops any of its clusters from the cluster filter."""
    gone = {r["cluster_id"] for r in df_all.filter(pl.col("family_id") == fid).to_dicts()}
    st.session_state["_map_sel_clusters"] = [
        c for c in st.session_state.get("_map_sel_clusters", []) if c not in gone
    ]


# ── Sidebar filters ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### Filters")
    _raw_families = render_chip_multiselect(
        "Technology family",
        "_map_sel_families",
        [(FAMILY_LABELS[fid], fid) for fid in FAMILY_ORDER],
        placeholder="Add family…",
        search_key="map_family_sb",
        on_remove=_drop_clusters_of_family,
    )
    selected_families: list[str] = _raw_families or FAMILY_ORDER

    _cluster_scope = [
        (r["tagline"], r["cluster_id"])
        for r in df_all.filter(pl.col("family_id").is_in(selected_families))
        .sort("tagline").to_dicts()
    ]
    selected_clusters: list[str] = render_chip_multiselect(
        "Cluster",
        "_map_sel_clusters",
        _cluster_scope,
        placeholder="Add cluster…",
        search_key="map_cluster_sb",
    )

# ── Header ───────────────────────────────────────────────────────────────────────────
st.markdown(
    "<p style='color:#888888;margin-top:0;margin-bottom:1.2rem;font-size:15px;'>"
    "Each dot is a technology cluster. Position shows the balance between research output (Y) "
    "and patent capture (X). "
    "<strong>Click any dot</strong> to see the cluster detail card."
    "</p>",
    unsafe_allow_html=True,
)

df = df_all.filter(pl.col("family_id").is_in(selected_families))
if selected_clusters:
    df = df.filter(pl.col("cluster_id").is_in(selected_clusters))

# Detect clusters hidden by the log scale (0 patents or 0 papers can't be plotted on it).
_hidden: list[str] = []
if selected_clusters:
    for _cid in selected_clusters:
        _row = df_all.filter(pl.col("cluster_id") == _cid)
        if len(_row) > 0:
            _r = _row.row(0, named=True)
            _np = _r["n_patents"] or 0
            _npa = _r["n_papers"] or 0
            if _np == 0 or _npa == 0:
                if _np == 0 and _npa == 0:
                    _reason = "0 patents and 0 papers — cannot be plotted on either axis"
                elif _np == 0:
                    _reason = f"0 patents — cannot be plotted on the log X axis ({_npa:,} papers)"
                else:
                    _reason = f"0 papers — cannot be plotted on the log Y axis ({_np:,} patents)"
                _hidden.append(f"{_r['tagline']}: {_reason}")

# ── Build bubble chart ────────────────────────────────────────────────────────────────
fig = go.Figure()

for fid in FAMILY_ORDER:
    if fid not in selected_families:
        continue
    sub = df.filter(pl.col("family_id") == fid)
    if len(sub) == 0:
        continue

    color = FAMILY_COLORS.get(fid, "#d1d5db")
    rows = sub.to_dicts()

    hover_texts: list[str] = []
    for row in rows:
        if row["npl_reportable"] and row["npl_median_lag_years"] is not None:
            lag_str = f"{row['npl_median_lag_years']:.1f} yr"
        elif row["cohort_lag_years"] is not None:
            lag_str = f"~{row['cohort_lag_years']:.1f} yr (cohort estimate)"
        else:
            lag_str = "—"
        hover_texts.append(
            f"<b>{row['tagline']}</b><br>"
            f"Family: {FAMILY_LABELS.get(fid, fid)}<br>"
            f"Papers: {row['n_papers']:,}<br>"
            f"Patents: {row['n_patents']:,}<br>"
            f"Citation lag: {lag_str}"
        )

    fig.add_trace(go.Scatter(
        x=sub["n_patents"].to_list(),
        y=sub["n_papers"].to_list(),
        mode="markers",
        name=FAMILY_LABELS.get(fid, fid),
        marker=dict(color=color, size=8, opacity=0.75, line=dict(color="#ffffff", width=1)),
        customdata=sub["cluster_id"].to_list(),
        hovertext=hover_texts,
        hoverinfo="text",
    ))

fig.update_layout(
    height=750,
    clickmode="event+select",
    plot_bgcolor="#ffffff",
    paper_bgcolor="#ffffff",
    font=dict(size=12, color="#111111"),
    xaxis=dict(title="Granted US patents", type="log", gridcolor="#f0f0f0",
               zeroline=False, showline=True, linecolor="#e6e6e6"),
    yaxis=dict(title="Research papers", type="log", gridcolor="#f0f0f0",
               zeroline=False, showline=True, linecolor="#e6e6e6"),
    legend=dict(
        orientation="h",
        yanchor="bottom", y=1.02,
        xanchor="left", x=0,
        bordercolor="#e6e6e6", borderwidth=1,
        itemsizing="constant",
        font=dict(size=11), title=None,
        itemclick="toggleothers", itemdoubleclick="toggle",
    ),
    margin=dict(l=60, r=20, t=60, b=60),
    hovermode="closest",
)

# ── Chart ─────────────────────────────────────────────────────────────────────────────
event = st.plotly_chart(
    fig,
    use_container_width=True,
    on_select="rerun",
    selection_mode=("points",),
    config={"displayModeBar": False, "displaylogo": False},
    key="bubble_chart",
)

# ── Warning: clusters hidden by log scale ──────────────────────────────────────────────
if _hidden:
    _items_html = "".join(f"<li>{h}. Details below.</li>" for h in _hidden)
    st.markdown(
        f"<div style='border:1px solid #f0c040;border-left:4px solid #f0c040;"
        f"border-radius:6px;padding:10px 14px;margin-bottom:0.75rem;"
        f"background:#fffdf0;font-size:13px;color:#555555;'>"
        f"<strong style='color:#111111;'>Not visible on chart</strong> — "
        f"<ul style='margin:4px 0 0 16px;'>{_items_html}</ul>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ── Cluster detail card ───────────────────────────────────────────────────────────────
selected_cluster_id: str | None = None
if event and event["selection"] and event["selection"]["points"]:
    pt = event["selection"]["points"][0]
    cdata = pt.get("customdata")
    if isinstance(cdata, str):
        selected_cluster_id = cdata
    elif isinstance(cdata, list) and len(cdata) > 0:
        selected_cluster_id = str(cdata[0])
# Sidebar single-cluster selection also drives the detail card (covers 0-patent clusters).
if selected_cluster_id is None and len(selected_clusters) == 1:
    selected_cluster_id = selected_clusters[0]

if selected_cluster_id:
    card_df = load_cluster_card(selected_cluster_id)
    if len(card_df) == 0:
        st.warning(f"No data found for cluster {selected_cluster_id}.")
    else:
        crow = card_df.row(0, named=True)
        family_id    = crow["family_id"] or "noise"
        family_color = FAMILY_COLORS.get(family_id, "#888888")
        family_label = FAMILY_LABELS.get(family_id, "Frontier / Unclustered")

        n_patents      = crow["n_patents"]      or 0
        n_papers       = crow["n_papers"]       or 0
        total_patents  = crow["total_patents"]   or 1
        total_papers   = crow["total_papers"]    or 1
        family_patents = crow["family_patents"]  or 1

        pct_patents_all    = n_patents / total_patents  * 100
        pct_patents_family = n_patents / family_patents * 100
        pct_papers_all     = n_papers  / total_papers   * 100

        lag = crow["npl_median_lag_years"]
        if lag is not None and crow["npl_reportable"]:
            lag_str = f"{lag:.1f} yr"
        elif crow["cohort_lag_years"] is not None:
            lag_str = f"~{crow['cohort_lag_years']:.1f} yr"
        else:
            lag_str = "—"

        summary = (crow["summary_friendly"] or "")

        # ── Header card ──────────────────────────────────────────────────────────────
        st.markdown(
            f"<div class='card' style='margin-top:1rem;display:flex;"
            f"justify-content:space-between;align-items:flex-start;--accent:{family_color};'>"
            f"<div style='flex:1;min-width:0;padding-right:32px;'>"
            f"<div class='card-tag' style='font-size:10px;font-weight:700;letter-spacing:.07em;"
            f"text-transform:uppercase;margin-bottom:6px;'>"
            f"{family_label}</div>"
            f"<div style='font-family:{_FONT};font-size:18px;font-weight:700;"
            f"color:#111111;margin-bottom:2px;'>{crow['tagline']}</div>"
            f"<div style='font-size:11px;color:#aaaaaa;margin-bottom:10px;'>"
            f"{selected_cluster_id}</div>"
            f"<div style='font-size:13px;color:#555555;line-height:1.6;'>{summary}</div>"
            f"</div>"
            f"<a href='/Family?family={family_id}' target='_self'"
            f" class='family-explore' style='flex-shrink:0;'>"
            f"Explore family →</a>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # ── 6 metric cards ────────────────────────────────────────────────────────────
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        _metrics = [
            (m1, f"{pct_patents_all:.1f}%",    "of all patents"),
            (m2, f"{pct_patents_family:.1f}%", "patents in family"),
            (m3, f"{n_patents:,}",             "US patents"),
            (m4, f"{pct_papers_all:.1f}%",     "of all papers"),
            (m5, f"{n_papers:,}",              "papers"),
            (m6, lag_str,                      "citation lag"),
        ]
        for col, value, label in _metrics:
            with col:
                st.markdown(
                    f"<div class='card card--metric' style='--accent:{family_color};'>"
                    f"<div class='card-stat' style='font-family:{_FONT};font-size:28px;"
                    f"font-weight:800;line-height:1;'>{value}</div>"
                    f"<div style='font-size:12px;color:#888888;margin-top:6px;"
                    f"white-space:nowrap;'>{label}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        # ── Top patenters / researchers bar charts ────────────────────────────────────
        st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
        col_pat, col_res = st.columns(2)

        pat_df = load_top_orgs((selected_cluster_id,), "patent", 30)
        res_df = load_top_orgs((selected_cluster_id,), "paper",  30)

        def _bar_chart(df: pl.DataFrame, title: str, color: str) -> go.Figure:
            names   = [n[:28] + "…" if len(n) > 28 else n for n in df["canonical_name"].to_list()]
            counts  = [int(v) for v in df["doc_count"].to_list()]
            org_ids = df["org_id"].to_list()
            chart_height = max(len(df), 3) * 38 + 60
            f = go.Figure(go.Bar(
                orientation="h",
                x=counts,
                y=names,
                customdata=org_ids,
                marker_color=color,
                marker_opacity=0.85,
                text=counts,
                textposition="outside",
                textfont=dict(size=11, color="#111111"),
            ))
            f.update_layout(
                title=dict(text=title, font=dict(size=11, color="#888888",
                           family=_FONT), x=0, pad=dict(b=4)),
                height=chart_height,
                plot_bgcolor="#ffffff",
                paper_bgcolor="#ffffff",
                yaxis=dict(range=[len(counts) - 0.5, -0.5], tickfont=dict(size=11),
                           automargin=True, showgrid=False, zeroline=False,
                           fixedrange=True),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                           range=[0, max(counts) * 1.25], fixedrange=True),
                margin=dict(l=8, r=60, t=36, b=8),
                dragmode=False,
                activeselection=dict(fillcolor="rgba(0,0,0,0)", opacity=0),
            )
            return f

        _scroll_h = 10 * 38 + 60  # visible height = 10 bars
        _pat_ev = None
        _res_ev = None

        with col_pat:
            if len(pat_df) > 0:
                with st.container(height=_scroll_h, key="cluster_pat_scroll"):
                    _pat_ev = st.plotly_chart(
                        _bar_chart(pat_df, "TOP PATENTERS — by granted US patents", family_color),
                        use_container_width=True,
                        config={
                            "displayModeBar": False, "displaylogo": False, "doubleClick": False,
                        },
                        key="bar_patent",
                        on_select="rerun",
                    )
                _pat_sel = _pat_ev and _pat_ev["selection"]
                _pat_pts = _pat_sel["points"] if _pat_sel else []
                if _pat_pts:
                    _pi    = _pat_pts[0].get("point_index", 0)
                    _oid   = pat_df["org_id"].to_list()[_pi]
                    _oname = pat_df["canonical_name"].to_list()[_pi]
                    if st.button(f"→ View {_oname} on Organisation page",
                                 key="cta_to_org", use_container_width=True):
                        st.session_state["selected_org_id"] = _oid
                        st.switch_page("pages/3_Org.py")
            else:
                st.caption("No patenter data for this cluster.")

        with col_res:
            if len(res_df) > 0:
                with st.container(height=_scroll_h, key="cluster_res_scroll"):
                    _res_ev = st.plotly_chart(
                        _bar_chart(res_df, "TOP RESEARCHERS — by papers", family_color),
                        use_container_width=True,
                        config={
                            "displayModeBar": False, "displaylogo": False, "doubleClick": False,
                        },
                        key="bar_paper",
                        on_select="rerun",
                    )
                _res_sel = _res_ev and _res_ev["selection"]
                _res_pts = _res_sel["points"] if _res_sel else []
                if _res_pts:
                    _pi    = _res_pts[0].get("point_index", 0)
                    _oid   = res_df["org_id"].to_list()[_pi]
                    _oname = res_df["canonical_name"].to_list()[_pi]
                    if st.button(f"→ View {_oname} on Organisation page",
                                 key="cta_res_to_org", use_container_width=True):
                        st.session_state["selected_org_id"] = _oid
                        st.switch_page("pages/3_Org.py")
            else:
                st.caption("No researcher data for this cluster.")

# ── Footer ────────────────────────────────────────────────────────────────────────────
_is_filtered = bool(selected_families != FAMILY_ORDER or selected_clusters)
_scope_label = (
    f"Showing {len(df)} of {len(df_all)} clusters (filtered)."
    if _is_filtered
    else f"{len(df)} clusters across 3 technology families."
)
st.markdown(
    f"<span style='font-size:11px;color:#888888;'>"
    f"{_scope_label} "
    f"Lag: NPL-linked median where ≥20 citations; ~ prefix = cohort estimate (soft). "
    f"Granted US patents only (PatentsView). Papers from OpenAlex (2012–2025)."
    f"</span>",
    unsafe_allow_html=True,
)
