"""
Technology Map — Surface 4.

UMAP scattergl of all papers and patents (~196k points).
Color by technology family (default) or by document type.
Source: fact_document_cluster + dim_technology_cluster + seed_cluster_family.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from render import FAMILY_COLORS, PAPER_COLOR, PATENT_COLOR

from data import load_umap_points

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

st.markdown("## Technology Map")
st.markdown(
    "<p style='color:#888888;margin-top:-0.4rem;margin-bottom:1.2rem;font-size:15px;'>"
    "Each dot is a research paper or US patent. Position reflects semantic similarity "
    "(UMAP over sentence-transformer embeddings). Clusters of related work emerge naturally."
    "</p>",
    unsafe_allow_html=True,
)

# ── Controls ────────────────────────────────────────────────────────────────────
c_mode, c_docs, _ = st.columns([2, 3, 3])
with c_mode:
    color_by = st.radio(
        "Color by",
        ["Technology family", "Document type"],
        horizontal=True,
    )
with c_docs:
    show_docs = st.radio(
        "Show",
        ["Papers + Patents", "Papers only", "Patents only"],
        horizontal=True,
    )

# ── Load + filter ───────────────────────────────────────────────────────────────
with st.spinner("Loading technology map…"):
    df = load_umap_points()

if show_docs == "Papers only":
    df = df.filter(pl.col("doc_type") == "paper")
elif show_docs == "Patents only":
    df = df.filter(pl.col("doc_type") == "patent")

# ── Build figure ────────────────────────────────────────────────────────────────
FAMILY_ORDER = [
    "euv", "si_photonics", "lasers", "neuromorphic", "in_memory", "adjacent", "noise",
]
FAMILY_LABELS = {
    "euv":          "EUV Lithography",
    "si_photonics": "Silicon Photonics & Optical I/O",
    "lasers":       "Lasers & Light Sources",
    "neuromorphic": "Neuromorphic / Brain-inspired",
    "in_memory":    "In-Memory & Emerging Memory",
    "adjacent":     "Adjacent",
    "noise":        "Frontier / Unclustered",
}

fig = go.Figure()

if color_by == "Technology family":
    for fid in FAMILY_ORDER:
        sub = df.filter(pl.col("family_id") == fid)
        if len(sub) == 0:
            continue
        color = FAMILY_COLORS.get(fid, "#d1d5db")
        hover = [
            f"{tag} · {dt}"
            for tag, dt in zip(sub["tagline"].to_list(), sub["doc_type"].to_list(), strict=False)
        ]
        fig.add_trace(go.Scattergl(
            x=sub["umap_x"].to_list(),
            y=sub["umap_y"].to_list(),
            mode="markers",
            name=FAMILY_LABELS.get(fid, fid),
            marker=dict(color=color, size=2, opacity=0.45),
            text=hover,
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
            hovertemplate="%{text}<extra></extra>",
        ))

fig.update_layout(
    height=680,
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
)

st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ── Footer ──────────────────────────────────────────────────────────────────────
n_shown = len(df)
st.markdown(
    f"<span style='font-size:11px;color:#888888;'>"
    f"Showing {n_shown:,} documents. "
    f"Grey = Frontier / Unclustered (~33% of papers, ~48% of patents) "
    f"— research at the intersection of multiple named families. "
    f"US patents only (PatentsView)."
    f"</span>",
    unsafe_allow_html=True,
)
