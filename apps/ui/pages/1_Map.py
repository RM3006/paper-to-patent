"""
Technology Map — Surface 4.

UMAP scattergl of all ~196k papers and patents.
Controls: color by family/doc-type, paper/patent toggle,
          year range slider, family multiselect filter.
Click any point to see the cluster mini-card (tagline, summary, gap metrics).

Source: fact_document_cluster + dim_technology_cluster + seed_cluster_family
        + dim_paper (year) + dim_patent (year) + mart_gap (mini-card).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from render import FAMILY_COLORS, PAPER_COLOR, PATENT_COLOR

from data import load_cluster_card, load_umap_points

st.set_page_config(
    page_title="Technology Map — The Chips Behind AI",
    page_icon="🗺️",
    layout="wide",
)

st.markdown("""
<style>
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── Constants ────────────────────────────────────────────────────────────────────
FAMILY_ORDER = [
    "euv", "si_photonics", "lasers", "neuromorphic", "in_memory", "adjacent", "noise",
]
FAMILY_LABELS: dict[str, str] = {
    "euv":          "EUV Lithography",
    "si_photonics": "Silicon Photonics & Optical I/O",
    "lasers":       "Lasers & Light Sources",
    "neuromorphic": "Neuromorphic / Brain-inspired",
    "in_memory":    "In-Memory & Emerging Memory",
    "adjacent":     "Adjacent",
    "noise":        "Frontier / Unclustered",
}

# ── Load data ─────────────────────────────────────────────────────────────────────
with st.spinner("Loading technology map…"):
    df = load_umap_points()

year_min = int(df["year"].min() or 2012)
year_max = int(df["year"].max() or 2025)

# ── Header ────────────────────────────────────────────────────────────────────────
st.markdown("## Technology Map")
st.markdown(
    "<p style='color:#888888;margin-top:-0.4rem;margin-bottom:0.8rem;font-size:15px;'>"
    "Each dot is a research paper or US patent. Position reflects semantic similarity "
    "(UMAP over sentence-transformer embeddings). Click any dot to see the cluster card."
    "</p>",
    unsafe_allow_html=True,
)

# ── Sidebar filters ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<div style='font-weight:700;color:#111111;font-size:0.95rem;"
        "margin-bottom:6px;'>Families</div>",
        unsafe_allow_html=True,
    )
    selected_families = st.multiselect(
        "Families",
        options=FAMILY_ORDER,
        default=FAMILY_ORDER,
        format_func=lambda k: FAMILY_LABELS[k],
        label_visibility="collapsed",
        key="map_families",
    )
    if not selected_families:
        selected_families = FAMILY_ORDER

    st.divider()
    st.page_link("app.py", label="← Overview")

# ── Control bar ───────────────────────────────────────────────────────────────────
c_mode, c_docs, c_yr = st.columns([2, 3, 4])
with c_mode:
    color_by = st.radio(
        "Color by",
        ["Technology family", "Document type"],
        horizontal=True,
        key="map_color_by",
    )
with c_docs:
    show_docs = st.radio(
        "Show",
        ["Papers + Patents", "Papers only", "Patents only"],
        horizontal=True,
        key="map_show_docs",
    )
with c_yr:
    year_range = st.slider(
        "Year range",
        min_value=year_min,
        max_value=year_max,
        value=(year_min, year_max),
        step=1,
        key="map_year_range",
    )

# ── Filter ────────────────────────────────────────────────────────────────────────
if show_docs == "Papers only":
    df = df.filter(pl.col("doc_type") == "paper")
elif show_docs == "Patents only":
    df = df.filter(pl.col("doc_type") == "patent")

df = df.filter(
    (pl.col("year") >= year_range[0]) & (pl.col("year") <= year_range[1])
)

if set(selected_families) != set(FAMILY_ORDER):
    df = df.filter(pl.col("family_id").is_in(selected_families))

# ── Build figure ──────────────────────────────────────────────────────────────────
fig = go.Figure()

if color_by == "Technology family":
    for fid in FAMILY_ORDER:
        if fid not in selected_families:
            continue
        sub = df.filter(pl.col("family_id") == fid)
        if len(sub) == 0:
            continue
        color = FAMILY_COLORS.get(fid, "#d1d5db")
        hover = [
            f"{tag} · {dt}"
            for tag, dt in zip(
                sub["tagline"].to_list(), sub["doc_type"].to_list(), strict=False
            )
        ]
        fig.add_trace(go.Scattergl(
            x=sub["umap_x"].to_list(),
            y=sub["umap_y"].to_list(),
            mode="markers",
            name=FAMILY_LABELS.get(fid, fid),
            marker=dict(color=color, size=2, opacity=0.45),
            text=hover,
            customdata=sub["cluster_id"].to_list(),
            hovertemplate="%{text}<extra></extra>",
        ))
else:
    for doc_type, label, color in [
        ("paper",  "Research paper", PAPER_COLOR),
        ("patent", "US patent",      PATENT_COLOR),
    ]:
        sub = df.filter(pl.col("doc_type") == doc_type)
        if len(sub) == 0:
            continue
        fig.add_trace(go.Scattergl(
            x=sub["umap_x"].to_list(),
            y=sub["umap_y"].to_list(),
            mode="markers",
            name=label,
            marker=dict(color=color, size=2, opacity=0.45),
            text=sub["tagline"].to_list(),
            customdata=sub["cluster_id"].to_list(),
            hovertemplate="%{text}<extra></extra>",
        ))

fig.update_layout(
    height=640,
    clickmode="event+select",
    plot_bgcolor="#ffffff",
    paper_bgcolor="#ffffff",
    font=dict(size=12, color="#111111"),
    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
    legend=dict(
        bordercolor="#e6e6e6",
        borderwidth=1,
        itemsizing="constant",
        font=dict(size=11),
        title=None,
    ),
    margin=dict(l=10, r=200, t=10, b=10),
    hovermode="closest",
    dragmode="select",
)

# ── Chart + click handler ─────────────────────────────────────────────────────────
event = st.plotly_chart(
    fig,
    use_container_width=True,
    on_select="rerun",
    selection_mode=("points",),
    config={"displayModeBar": True, "displaylogo": False,
            "modeBarButtonsToRemove": ["zoom2d", "pan2d", "zoomIn2d", "zoomOut2d",
                                        "autoScale2d", "resetScale2d", "toImage"]},
    key="umap_chart",
)

# ── Cluster mini-card ─────────────────────────────────────────────────────────────
selected_cluster_id: str | None = None
if event and event.selection and event.selection.points:
    pt = event.selection.points[0]
    cdata = pt.get("customdata")
    if isinstance(cdata, str):
        selected_cluster_id = cdata
    elif isinstance(cdata, list) and len(cdata) > 0:
        selected_cluster_id = str(cdata[0])

if selected_cluster_id:
    card_df = load_cluster_card(selected_cluster_id)
    if len(card_df) > 0:
        crow = card_df.row(0, named=True)
        family_id = crow["family_id"] or "noise"
        family_color = FAMILY_COLORS.get(family_id, "#888888")
        family_label = FAMILY_LABELS.get(family_id, "Frontier / Unclustered")

        n_papers  = crow["n_papers"]  or 0
        n_patents = crow["n_patents"] or 0
        lag       = crow["npl_median_lag_years"]
        lag_str   = f"{lag:.2f} yr" if (lag is not None and crow["npl_reportable"]) else "—"

        # top_terms is a VARCHAR[] array — Polars delivers it as a Python list
        raw_terms = crow["top_terms"]
        terms = list(raw_terms[:6]) if isinstance(raw_terms, list) and raw_terms else []
        terms_html = " ".join(
            f"<span style='background:#f0f0f0;border-radius:3px;"
            f"padding:2px 7px;font-size:11px;color:#444444;'>{t}</span>"
            for t in terms
        )

        summary = (crow["summary_friendly"] or "")[:300]
        if len(crow["summary_friendly"] or "") > 300:
            summary += "…"

        st.markdown(
            f"<div style='border:1px solid {family_color}55;"
            f"border-left:4px solid {family_color};"
            f"border-radius:6px;padding:16px 20px;margin-top:0.6rem;'>"
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:flex-start;margin-bottom:8px;'>"
            f"<div>"
            f"<span style='font-size:10px;font-weight:700;letter-spacing:.07em;"
            f"text-transform:uppercase;color:#888888;'>{family_label}</span>"
            f"<div style='font-size:16px;font-weight:700;color:#111111;margin-top:2px;'>"
            f"{crow['tagline']}</div>"
            f"</div>"
            f"<span style='font-size:11px;color:#888888;'>cluster {selected_cluster_id}</span>"
            f"</div>"
            f"<div style='font-size:12px;color:#444444;line-height:1.6;margin-bottom:10px;'>"
            f"{summary}</div>"
            f"<div style='display:flex;gap:24px;margin-bottom:10px;'>"
            f"<div><span style='font-size:18px;font-weight:700;color:#111111;'>"
            f"{n_papers:,}</span> "
            f"<span style='font-size:11px;color:#888888;'>papers</span></div>"
            f"<div><span style='font-size:18px;font-weight:700;color:#111111;'>"
            f"{n_patents:,}</span> "
            f"<span style='font-size:11px;color:#888888;'>US patents</span></div>"
            f"<div><span style='font-size:18px;font-weight:700;color:#111111;'>"
            f"{lag_str}</span> "
            f"<span style='font-size:11px;color:#888888;'>median lag</span></div>"
            f"</div>"
            + (f"<div style='margin-top:4px;'>{terms_html}</div>" if terms else "")
            + "</div>",
            unsafe_allow_html=True,
        )

        if crow["family_id"]:
            if st.button(
                f"Explore {family_label} →",
                key="map_explore_family",
                type="primary",
            ):
                st.session_state.selected_family = crow["family_id"]
                st.switch_page("pages/2_Family.py")

# ── Footer ────────────────────────────────────────────────────────────────────────
n_shown = len(df)
yr_note = (
    f" · {year_range[0]}–{year_range[1]}"
    if (year_range[0] != year_min or year_range[1] != year_max)
    else ""
)
st.markdown(
    f"<span style='font-size:11px;color:#888888;'>"
    f"Showing {n_shown:,} documents{yr_note}. "
    f"Grey = Frontier / Unclustered — research at the intersection of multiple families. "
    f"US patents only (PatentsView). Click any dot to see the cluster card."
    f"</span>",
    unsafe_allow_html=True,
)
