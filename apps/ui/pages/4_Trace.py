# pyright: basic
"""
Trace an Idea — Surface 4.

Pick one curated paper and follow it into the US patents that cited it via NPL
(non-patent-literature) references. Displayed as a horizontal timeline: the paper
anchors the left, citing patents spread right at their filing dates.

Anchors are validated against fact_npl_link (≥ 8 citing patents, high/medium confidence).
Source: dim_paper, fact_npl_link, dim_patent, fact_patent_filing,
        dim_organization, mart_family.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from datetime import timedelta

import plotly.graph_objects as go
import streamlit as st
from streamlit_searchbox import StyleOverrides, st_searchbox

from data import load_trace_family_stat, load_trace_links, load_trace_paper, search_papers_ilike
from render import (
    FAMILY_COLORS,
    FAMILY_LABELS,
    confidence_badge,
    render_nav,
    render_tour_banner,
)

_LINK_SOURCE_LABEL: dict[str, str] = {
    "marx_fuegi":  "Marx & Fuegi (gold, published citation)",
    "doi":         "DOI match",
    "fuzzy_title": "Fuzzy title match",
}

st.set_page_config(
    page_title="Trace a Paper — The Chips Behind AI",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_FONT = '"Space Grotesk", -apple-system, system-ui, sans-serif'

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&display=swap');
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
.js-plotly-plot .plotly .cursor-crosshair { cursor: default !important; }
.js-plotly-plot .cartesianlayer .spikeline { display: none !important; }

/* Insight callout: thinner than Streamlit's default st.info padding, so it reads
   as a quiet caption rather than a competing focal point (matches human-protein-atlas). */
.st-key-atlas_insight [data-testid="stAlertContainer"] {
    padding-top: 0.5rem; padding-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

render_nav("Trace a Paper")
render_tour_banner(4)

_SEARCHBOX_STYLE: StyleOverrides = {"searchbox": {"option": {"highlightColor": "#f0f0f0"}}}


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    "<p style='color:#888888;margin-top:0;margin-bottom:1.4rem;font-size:15px;'>"
    "Pick a research paper and follow it into the US patents that cited it. "
    "The horizontal distance on the timeline is the <strong>citation lag</strong> — "
    "time between publication and when industry filed a patent referencing it."
    "</p>",
    unsafe_allow_html=True,
)

# ── Paper searchbox ───────────────────────────────────────────────────────────
_default_paper_options = search_papers_ilike("")
chosen_id: str | None = st_searchbox(
    search_papers_ilike,
    placeholder="Search papers by title… (type to filter all cited papers)",
    key="trace_searchbox",
    style_overrides=_SEARCHBOX_STYLE,
    default_options=_default_paper_options,
)
# A Survey of ReRAM-Based Architectures for Processing-In-Memory and Neural Networks
_default_work_id = "W2802367674"
work_id: str = chosen_id or _default_work_id

# ── Load paper + links ────────────────────────────────────────────────────────
with st.spinner("Loading…"):
    paper_df = load_trace_paper(work_id)
    links_df = load_trace_links(work_id)

if len(paper_df) == 0:
    st.error("Paper data not found. The warehouse may need a rebuild.")
    st.stop()

paper    = paper_df.row(0, named=True)
n_citing = len(links_df)
pub_date = paper.get("publication_date")
if pub_date is None:
    st.error("Paper is missing a publication date. The warehouse may need a rebuild.")
    st.stop()
assert pub_date is not None  # dim_paper.publication_date is not_null; narrows for pyright
pub_year = int(str(pub_date)[:4]) if pub_date else 2014
pub_decimal = pub_year + ((pub_date.month - 1) / 12.0 if pub_date else 0.0)

family_id    = paper.get("family_id") or ""
family_color = FAMILY_COLORS.get(family_id, "#888888")
family_label = FAMILY_LABELS.get(family_id, family_id or "Research Paper")
paper_color  = _hex_rgba(family_color, 0.45)

# ── Load family stats (needs family_id resolved above) ────────────────────────
family_df = load_trace_family_stat(family_id)

# ── Compute stat card values ──────────────────────────────────────────────────
fam_med: float | None = None
fam_links = 0
if len(family_df) > 0:
    frow = family_df.row(0, named=True)
    fam_med = frow["median_lag_years_weighted"]
    fam_links = frow["total_npl_links"] or 0

lags_known = [
    r["citation_lag_years"]
    for r in links_df.to_dicts()
    if r["citation_lag_years"] is not None
]
fastest = min(lags_known) if lags_known else None
fastest_str = f"{fastest:.1f} yr" if fastest is not None else "—"
fam_med_str = f"{fam_med:.1f} yr" if fam_med is not None else "—"
fam_med_tooltip = (
    f"Based on {fam_links:,} NPL-linked citations"
    if fam_med is not None
    else "Fewer than 20 NPL-linked citations — not reportable"
)

# ── Paper card + stat (single flex row → equal height guaranteed) ─────────────
abstract_raw = paper.get("abstract") or ""
abstract_snippet = abstract_raw[:320] + ("…" if len(abstract_raw) > 320 else "")
org_name = paper.get("org_name") or "Multiple institutions"
topic = paper.get("primary_topic_name") or ""
topic_html = f"<span style='color:#aaaaaa;margin-left:8px;'>· {topic}</span>" if topic else ""

# ── Paper description card (full width) ──────────────────────────────────────
st.markdown(
    f"<div class='card card--identity' "
    f"style='--accent:{family_color};--accent-border:{family_color}55;'>"
    f"<div class='card-tag' style='font-size:9px;font-weight:700;letter-spacing:.08em;"
    f"text-transform:uppercase;margin-bottom:6px;'>"
    f"Research Paper · {pub_year} · {family_label}</div>"
    f"<div style='font-family:{_FONT};font-size:15px;font-weight:700;color:#111111;"
    f"line-height:1.4;margin-bottom:8px;'>{paper['title']}</div>"
    f"<div style='font-size:12px;color:#555555;margin-bottom:10px;'>"
    f"{org_name}{topic_html}</div>"
    f"<div style='font-size:12px;color:#444444;line-height:1.6;'>{abstract_snippet}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# ── Metrics cards (3 columns) ─────────────────────────────────────────────────
_m1, _m2, _m3 = st.columns(3)
for _col, _val, _lbl, _tooltip in [
    (_m1, str(n_citing), "Patents citing this paper", None),
    (_m2, fastest_str,   "Fastest citation lag", None),
    (_m3, fam_med_str,   "Family median lag", fam_med_tooltip),
]:
    with _col:
        _title_attr = f" title='{_tooltip}'" if _tooltip else ""
        st.markdown(
            f"<div{_title_attr} class='card card--metric' "
            f"style='margin-bottom:1.5rem;--accent:{family_color};'>"
            f"<div class='card-stat' style='font-family:{_FONT};font-size:28px;"
            f"font-weight:800;line-height:1;'>{_val}</div>"
            f"<div style='font-size:12px;color:#888888;margin-top:6px;"
            f"white-space:nowrap;'>{_lbl}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

# ── Citation lag lollipop chart ───────────────────────────────────────────────
st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-family:{_FONT};font-size:14px;font-weight:700;"
    f"color:#111111;margin-bottom:4px;'>The Journey — publication to patent filing</div>"
    f"<div style='font-size:12px;color:#888888;margin-bottom:12px;'>"
    f"Each marker is a US patent that cited this paper, plotted by how many years after "
    f"publication it was filed. The dashed line shows the family median citation lag."
    f"</div>",
    unsafe_allow_html=True,
)

if n_citing == 0:
    with st.container(key="atlas_insight"):
        st.info("No citing patents found in the current NPL link set.")
else:
    assert pub_date is not None  # narrowed above; re-asserted for pyright across the branch
    links = links_df.to_dicts()
    links_with_lag = [
        r for r in links
        if r.get("citation_lag_years") is not None and r.get("filing_date") is not None
    ]
    links_no_lag = [r for r in links if r not in links_with_lag]

    n = len(links_with_lag)
    # Sorted ascending by lag from SQL; shortest lag → top of chart
    y_positions = list(range(n - 1, -1, -1))

    # Compute median date for the reference vline
    median_date = (
        pub_date + timedelta(days=fam_med * 365.25)
        if fam_med is not None and pub_date is not None else None
    )
    max_filing_date = max(r["filing_date"] for r in links_with_lag)
    x_min = (pub_date + timedelta(days=-90)).isoformat() if pub_date else None
    rightmost = max(max_filing_date, median_date) if median_date else max_filing_date
    x_max = (rightmost + timedelta(days=270)).isoformat()

    fig = go.Figure()

    # Lollipop stems: horizontal line from pub_date to filing_date
    for i, row in enumerate(links_with_lag):
        assert pub_date is not None  # type-narrowing doesn't cross the loop boundary
        fig.add_shape(
            type="line",
            x0=pub_date.isoformat(), x1=row["filing_date"].isoformat(),
            y0=y_positions[i], y1=y_positions[i],
            line=dict(color=_hex_rgba(family_color, 0.5), width=1.5),
        )

    # Publication anchor: vertical line at pub_date
    assert pub_date is not None  # type-narrowing doesn't cross the loop boundary above
    fig.add_vline(
        x=pub_date.isoformat(),
        line=dict(color=family_color, width=2),
    )
    fig.add_annotation(
        x=pub_date.isoformat(), xref="x",
        y=1, yref="paper",
        text=f"Published {pub_year}",
        showarrow=False,
        xanchor="center", yanchor="bottom",
        font=dict(size=10, color=family_color, family=_FONT),
    )

    # Family median reference line
    if median_date is not None:
        fig.add_vline(
            x=median_date.isoformat(),
            line=dict(color=_hex_rgba(family_color, 0.45), width=1.5, dash="dash"),
            annotation_text=f"family median<br>{fam_med:.1f} yr",
            annotation_font=dict(size=10, color=family_color),
            annotation_position="top right",
        )

    # Build hover texts -- discloses link provenance per the project's confidence
    # pattern (rule: every match carries provenance and confidence, shown in the UI).
    def _hover_text(row: dict) -> str:
        lag_str   = f"{row['citation_lag_years']:.1f} yr"
        title     = (row["patent_title"] or "Untitled")[:60]
        assignee  = row["assignee"] or "Unresolved"
        filed_str = row["filing_date"].strftime("%d/%m/%Y")
        source    = _LINK_SOURCE_LABEL.get(row["link_source"], row["link_source"] or "unknown")
        return (
            f"<b>{title}</b><br>"
            f"Assignee: {assignee}<br>"
            f"Filed: {filed_str}<br>"
            f"Lag: {lag_str}<br>"
            f"Patent: US{row['patent_id']}<br>"
            f"{row['confidence'].title()} confidence — {source}"
        )

    # Solid marker = high confidence, hollow = medium -- the visual encoding for
    # the "hard link vs soft link" distinction the confidence pattern requires.
    high_idx   = [i for i, r in enumerate(links_with_lag) if r["confidence"] == "high"]
    medium_idx = [i for i, r in enumerate(links_with_lag) if r["confidence"] != "high"]

    _high_style = (
        "circle", dict(color="#ffffff", width=1.5), "Citing patents — high confidence",
    )
    _medium_style = (
        "circle-open", dict(color=family_color, width=2), "Citing patents — medium confidence",
    )
    for idxs, (symbol, marker_line, trace_name) in (
        (high_idx, _high_style),
        (medium_idx, _medium_style),
    ):
        if not idxs:
            continue
        rows = [links_with_lag[i] for i in idxs]
        fig.add_trace(go.Scatter(
            x=[r["filing_date"].isoformat() for r in rows],
            y=[y_positions[i] for i in idxs],
            mode="markers+text",
            marker=dict(color=family_color, size=12, symbol=symbol, line=marker_line),
            text=[f"  {(r['assignee'] or 'Unresolved')[:22]}" for r in rows],
            textposition="middle right",
            textfont=dict(size=10, color="#555555"),
            hovertext=[_hover_text(r) for r in rows],
            hoverinfo="text",
            name=trace_name,
        ))

    fig.update_layout(
        height=max(260, n * 36 + 80),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(size=11, color="#111111"),
        margin=dict(l=10, r=200, t=40, b=40),
        xaxis=dict(
            type="date",
            range=[x_min, x_max],
            dtick="M6",
            tickformat="%b %Y",
            showgrid=True, gridcolor="#f0f0f0",
            zeroline=False, showline=True, linecolor="#e6e6e6",
            showspikes=False,
        ),
        yaxis=dict(
            showticklabels=False,
            showgrid=False, zeroline=False,
            range=[-0.8, n - 0.2],
            showspikes=False,
        ),
        showlegend=False,
        hovermode="closest",
        dragmode=False,
    )

    st.plotly_chart(
        fig, use_container_width=True,
        config={"displayModeBar": False, "displaylogo": False}, key="trace_timeline",
    )

    st.markdown(
        f"<div style='font-size:11px;color:#888888;margin-top:-4px;'>"
        f"&#9679; Solid marker = {confidence_badge('high')} link (Marx &amp; Fuegi gold citation "
        f"or DOI match) &nbsp;&nbsp; "
        f"&#9675; Hollow marker = {confidence_badge('medium')} link (fuzzy title match)"
        f"</div>",
        unsafe_allow_html=True,
    )

    if links_no_lag:
        st.caption(f"{len(links_no_lag)} patent(s) not shown — citation lag not available.")

# ── Methodology caption ───────────────────────────────────────────────────────
st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
st.markdown(
    "<span style='font-size:11px;color:#888888;'>"
    "<strong>Citation lag</strong> is the interval between a paper's publication date and a "
    "patent's filing date, measured only where a verified NPL reference link exists. "
    "It is not R&D-to-market time and does not imply causation. "
    "Patents are US-only (PatentsView)."
    "</span>",
    unsafe_allow_html=True,
)

