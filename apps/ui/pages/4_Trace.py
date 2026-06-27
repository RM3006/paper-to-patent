"""
Trace an Idea — Surface 5.

Semi-static narrative: pick one curated paper and follow its journey into
US patents that cited it via NPL (non-patent literature) references.

Shows: paper card → citing patents (deduplicated, one row per patent) →
       family-level citation-lag closing stat.

Anchors are validated against fact_npl_link (≥ 8 citing patents).
Source: dim_paper, fact_npl_link, dim_patent, fact_patent_filing,
        dim_organization, mart_family.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import streamlit as st
from render import FAMILY_COLORS, PAPER_COLOR, PATENT_COLOR, confidence_badge

from data import load_trace_family_stat, load_trace_links, load_trace_paper

st.set_page_config(
    page_title="Trace an Idea — The Chips Behind AI",
    page_icon="🔬",
    layout="wide",
)

st.markdown(
    """
<style>
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
</style>
""",
    unsafe_allow_html=True,
)

# ── Curated anchors ───────────────────────────────────────────────────────────
# Validated: each has ≥ 8 distinct citing patents in fact_npl_link.
_ANCHORS: list[dict[str, str]] = [
    {
        "label": "IBM TrueNorth — A million spiking-neuron integrated circuit (2014)",
        "work_id": "W2138913040",
        "family_id": "neuromorphic",
    },
    {
        "label": "EUV photoresist — Super high sensitivity via photo-sensitized "
        "amplification (2013)",
        "work_id": "W2094311390",
        "family_id": "euv",
    },
]

FAMILY_LABELS: dict[str, str] = {
    "euv": "EUV Lithography",
    "si_photonics": "Silicon Photonics & Optical I/O",
    "lasers": "Lasers & Light Sources",
    "neuromorphic": "Neuromorphic / Brain-inspired",
    "in_memory": "In-Memory & Emerging Memory",
}

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## Trace an Idea")
st.markdown(
    "<p style='color:#888888;margin-top:-0.4rem;margin-bottom:1.2rem;font-size:15px;'>"
    "Pick a research paper and follow it into the US patents that cited it. "
    "The time between publication and filing is the <strong>citation lag</strong> — "
    "not R&amp;D-to-market time, which the data cannot support."
    "</p>",
    unsafe_allow_html=True,
)

# ── Anchor picker ─────────────────────────────────────────────────────────────
anchor_labels = [a["label"] for a in _ANCHORS]
choice = st.radio(
    "Select a paper to trace:",
    options=anchor_labels,
    key="trace_anchor",
    label_visibility="visible",
)
anchor = next(a for a in _ANCHORS if a["label"] == choice)
work_id = anchor["work_id"]
family_id = anchor["family_id"]
family_color = FAMILY_COLORS.get(family_id, "#888888")
family_label = FAMILY_LABELS.get(family_id, family_id)

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Loading…"):
    paper_df = load_trace_paper(work_id)
    links_df = load_trace_links(work_id)
    family_df = load_trace_family_stat(family_id)

if len(paper_df) == 0:
    st.error("Paper data not found. The warehouse may need a rebuild.")
    st.stop()

paper = paper_df.row(0, named=True)
n_citing = len(links_df)

# ── Layout: paper card | citing patents ──────────────────────────────────────
col_paper, col_patents = st.columns([4, 6], gap="large")

with col_paper:
    # Paper metadata card
    abstract_raw = paper.get("abstract") or ""
    abstract_snippet = abstract_raw[:350] + ("…" if len(abstract_raw) > 350 else "")
    pub_year = str(paper.get("publication_date") or "")[:4]
    org_name = paper.get("org_name") or "Multiple institutions"
    topic = paper.get("primary_topic_name") or ""

    st.markdown(
        f"<div style='border-left:4px solid {PAPER_COLOR};"
        f"border:1px solid {PAPER_COLOR}44;"
        f"border-radius:6px;padding:16px 18px;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
        f"text-transform:uppercase;color:{PAPER_COLOR};margin-bottom:6px;'>"
        f"Research Paper · {pub_year}</div>"
        f"<div style='font-size:15px;font-weight:700;color:#111111;"
        f"line-height:1.45;margin-bottom:8px;'>{paper['title']}</div>"
        f"<div style='font-size:12px;color:#555555;margin-bottom:10px;'>"
        f"{org_name}"
        + (f"<span style='color:#aaaaaa;margin-left:8px;'>· {topic}</span>" if topic else "")
        + "</div>"
        f"<div style='font-size:12px;color:#444444;line-height:1.6;'>"
        f"{abstract_snippet}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # Family tag + total patent count
    st.markdown(
        f"<div style='background:{family_color}11;border:1px solid {family_color}44;"
        f"border-radius:6px;padding:12px 16px;margin-top:4px;'>"
        f"<span style='font-size:10px;font-weight:700;letter-spacing:.07em;"
        f"text-transform:uppercase;color:{family_color};'>{family_label}</span>"
        f"<div style='font-size:24px;font-weight:700;color:#111111;margin-top:4px;'>"
        f"{n_citing} <span style='font-size:13px;font-weight:400;color:#888888;'>"
        f"US patents shown citing this paper</span></div>"
        f"<div style='font-size:11px;color:#888888;margin-top:2px;'>"
        f"via NPL citation match · top 6 by citation lag</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

with col_patents:
    if n_citing == 0:
        st.info("No citing patents found in the current NPL link set.")
    else:
        # Compute max lag for proportional bar widths
        lags = [
            r["citation_lag_years"]
            for r in links_df.to_dicts()
            if r["citation_lag_years"] is not None
        ]
        max_lag = max(lags) if lags else 1.0

        st.markdown(
            "<div style='font-size:13px;font-weight:700;color:#111111;"
            "margin-bottom:10px;'>Citing US Patents — earliest first</div>",
            unsafe_allow_html=True,
        )

        for row in links_df.to_dicts():
            lag = row["citation_lag_years"]
            lag_str = f"{lag:.1f} yr" if lag is not None else "—"
            bar_pct = int((lag / max_lag) * 100) if lag is not None else 0
            patent_title = (row["patent_title"] or "Untitled")[:70]
            if len(row["patent_title"] or "") > 70:
                patent_title += "…"
            filing_year = str(row.get("filing_date") or "")[:4]
            assignee = row.get("assignee") or "Unresolved"
            conf_html = confidence_badge(row["confidence"])

            st.markdown(
                f"<div style='border-left:4px solid {PATENT_COLOR};"
                f"border:1px solid {PATENT_COLOR}44;"
                f"border-radius:6px;padding:12px 16px;margin-bottom:8px;'>"
                f"<div style='font-size:13px;font-weight:600;color:#111111;"
                f"margin-bottom:4px;line-height:1.4;'>{patent_title}</div>"
                f"<div style='font-size:12px;color:#555555;margin-bottom:8px;'>"
                f"{assignee} · Filed {filing_year} · Patent {row['patent_id']}"
                f"&nbsp;&nbsp;{conf_html}</div>"
                f"<div style='display:flex;align-items:center;gap:8px;'>"
                f"<div style='background:{PATENT_COLOR};height:6px;"
                f"border-radius:3px;width:{bar_pct}%;max-width:200px;'></div>"
                f"<span style='font-size:12px;font-weight:700;color:{PATENT_COLOR};'>"
                f"{lag_str} lag</span>"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

# ── Closing stat ──────────────────────────────────────────────────────────────
st.divider()

if len(family_df) > 0:
    frow = family_df.row(0, named=True)
    fam_name = frow["family_name"]
    med_lag = frow["median_lag_years_weighted"]
    n_links = frow["total_npl_links"]
    n_papers = frow["n_papers"]
    n_patents = frow["n_patents"]

    lag_display = f"{med_lag:.1f}" if med_lag is not None else "—"
    st.markdown(
        f"<div style='background:{family_color}0d;border:1px solid {family_color}33;"
        f"border-radius:8px;padding:20px 24px;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
        f"text-transform:uppercase;color:{family_color};margin-bottom:6px;'>"
        f"Across {fam_name}</div>"
        f"<div style='font-size:28px;font-weight:700;color:#111111;'>"
        f"{lag_display} <span style='font-size:14px;font-weight:400;color:#888888;'>"
        f"years median citation lag (publication → filing)</span></div>"
        f"<div style='font-size:12px;color:#888888;margin-top:6px;'>"
        f"Based on {n_links:,} NPL-matched paper→patent links · "
        f"{n_papers:,} papers · {n_patents:,} US patents in scope"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ── Methodology note ──────────────────────────────────────────────────────────
st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
st.caption(
    "**Citation lag** is the interval between a paper's publication date and a patent's "
    "filing date, measured only where a verified NPL reference link exists. "
    "It is not R&D-to-market time and does not imply causation. "
    "Confidence reflects the NPL matching method: DOI-exact match = high; "
    "fuzzy title match = medium. "
    "Patents are US-only (PatentsView). "
    "Showing top 6 citing patents by citation lag; the paper may have more."
)

st.divider()
st.page_link("app.py", label="← Overview")
