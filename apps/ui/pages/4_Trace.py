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

import plotly.graph_objects as go
import streamlit as st
from render import FAMILY_COLORS, confidence_badge

from data import load_trace_family_stat, load_trace_links, load_trace_paper

st.set_page_config(
    page_title="Trace an Idea — The Chips Behind AI",
    page_icon="🔬",
    layout="wide",
)

_FONT = '"Space Grotesk", -apple-system, system-ui, sans-serif'

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&display=swap');
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

# ── Curated anchors (all validated: ≥ 8 citing patents, high/medium confidence) ──
_ANCHORS: list[dict] = [
    {
        "work_id": "W4254672563",
        "family_id": "in_memory",
        "label": "PRIME: Processing-in-Memory for Neural Networks",
        "teaser": "A 2016 architecture that processes neural-network data inside the memory chip itself — cited by 80 US patents.",
        "n_citing": 80,
        "fastest_lag": 0.3,
    },
    {
        "work_id": "W2929378582",
        "family_id": "si_photonics",
        "label": "300-mm Monolithic Silicon Photonics Foundry",
        "teaser": "The foundry-scale integration recipe that brought silicon photonics into standard chip fabs — cited by 63 US patents.",
        "n_citing": 63,
        "fastest_lag": 1.1,
    },
    {
        "work_id": "W2138913040",
        "family_id": "neuromorphic",
        "label": "IBM TrueNorth: A Million Spiking-Neuron Chip",
        "teaser": "IBM's 2014 neuromorphic processor mimicking how the brain fires neurons — cited by 55 US patents.",
        "n_citing": 55,
        "fastest_lag": 0.5,
    },
    {
        "work_id": "W2094311390",
        "family_id": "euv",
        "label": "EUV Photoresist — Super-High Sensitivity via Amplification",
        "teaser": "A photoresist chemistry enabling extreme-UV printing at the atomic scale — cited by 13 US patents.",
        "n_citing": 13,
        "fastest_lag": 2.1,
    },
    {
        "work_id": "W2093314327",
        "family_id": "lasers",
        "label": "High-Power Tunable Si Hybrid External-Cavity Laser",
        "teaser": "A silicon-integrated laser powering the transceivers inside data-centre networks — cited by 9 US patents.",
        "n_citing": 9,
        "fastest_lag": 0.4,
    },
]

_FAMILY_LABELS: dict[str, str] = {
    "euv":          "EUV Lithography",
    "si_photonics": "Silicon Photonics",
    "lasers":       "Lasers & Light Sources",
    "neuromorphic": "Neuromorphic",
    "in_memory":    "In-Memory Compute",
}


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## Trace an Idea")
st.markdown(
    "<p style='color:#888888;margin-top:-0.4rem;margin-bottom:1.4rem;font-size:15px;'>"
    "Pick a research paper and follow it into the US patents that cited it. "
    "The horizontal distance on the timeline is the <strong>citation lag</strong> — "
    "time between publication and when industry filed a patent referencing it."
    "</p>",
    unsafe_allow_html=True,
)

# ── Story card selector ───────────────────────────────────────────────────────
active_idx: int = int(st.session_state.get("trace_anchor_idx", 0))

cols = st.columns(len(_ANCHORS), gap="small")
for i, anchor in enumerate(_ANCHORS):
    color = FAMILY_COLORS.get(anchor["family_id"], "#888888")
    is_active = (i == active_idx)
    border_style = f"border:2px solid {color};" if is_active else "border:1px solid #e6e6e6;"
    bg_style = f"background:{_hex_rgba(color, 0.06)};" if is_active else "background:#ffffff;"

    with cols[i]:
        st.markdown(
            f"<div style='{border_style}{bg_style}border-radius:10px;"
            f"padding:14px 14px 12px;height:130px;box-sizing:border-box;'>"
            f"<div style='font-size:9px;font-weight:700;letter-spacing:.08em;"
            f"text-transform:uppercase;color:{color};margin-bottom:6px;'>"
            f"{_FAMILY_LABELS.get(anchor['family_id'], anchor['family_id'])}</div>"
            f"<div style='font-size:12px;font-weight:600;color:#111111;line-height:1.35;"
            f"margin-bottom:8px;overflow:hidden;display:-webkit-box;"
            f"-webkit-line-clamp:3;-webkit-box-orient:vertical;'>"
            f"{anchor['label']}</div>"
            f"<div style='font-size:11px;color:#888888;'>"
            f"→ {anchor['n_citing']} patents · fastest {anchor['fastest_lag']:.1f} yr"
            f"</div></div>",
            unsafe_allow_html=True,
        )
        if st.button("Select", key=f"trace_btn_{i}", type="secondary" if not is_active else "primary"):
            st.session_state.trace_anchor_idx = i
            st.rerun()

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

anchor = _ANCHORS[active_idx]
work_id = anchor["work_id"]
family_id = anchor["family_id"]
family_color = FAMILY_COLORS.get(family_id, "#888888")
family_label = _FAMILY_LABELS.get(family_id, family_id)
paper_color = _hex_rgba(family_color, 0.45)

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Loading…"):
    paper_df  = load_trace_paper(work_id)
    links_df  = load_trace_links(work_id)
    family_df = load_trace_family_stat(family_id)

if len(paper_df) == 0:
    st.error("Paper data not found. The warehouse may need a rebuild.")
    st.stop()

paper    = paper_df.row(0, named=True)
n_citing = len(links_df)
pub_date = paper.get("publication_date")
pub_year = int(str(pub_date)[:4]) if pub_date else 2014
pub_decimal = pub_year + ((pub_date.month - 1) / 12.0 if pub_date else 0.0)

# ── Paper card + stat row ────────────────────────────────────────────────────
col_paper, col_stat = st.columns([5, 2], gap="large")

with col_paper:
    abstract_raw = paper.get("abstract") or ""
    abstract_snippet = abstract_raw[:320] + ("…" if len(abstract_raw) > 320 else "")
    org_name = paper.get("org_name") or "Multiple institutions"
    topic = paper.get("primary_topic_name") or ""

    st.markdown(
        f"<div style='border:1px solid {family_color}55;"
        f"border-left:4px solid {family_color};"
        f"border-radius:6px;padding:16px 18px;'>"
        f"<div style='font-size:9px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:{family_color};margin-bottom:6px;'>"
        f"Research Paper · {pub_year} · {family_label}</div>"
        f"<div style='font-family:{_FONT};font-size:15px;font-weight:700;color:#111111;"
        f"line-height:1.4;margin-bottom:8px;'>{paper['title']}</div>"
        f"<div style='font-size:12px;color:#555555;margin-bottom:10px;'>"
        f"{org_name}"
        + (f"<span style='color:#aaaaaa;margin-left:8px;'>· {topic}</span>" if topic else "")
        + f"</div>"
        f"<div style='font-size:12px;color:#444444;line-height:1.6;'>{abstract_snippet}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

with col_stat:
    fam_med: float | None = None
    if len(family_df) > 0:
        frow = family_df.row(0, named=True)
        fam_med = frow["median_lag_years_weighted"]

    lags_known = [
        r["citation_lag_years"]
        for r in links_df.to_dicts()
        if r["citation_lag_years"] is not None
    ]
    fastest = min(lags_known) if lags_known else None
    fastest_str = f"{fastest:.1f} yr" if fastest is not None else "—"
    fam_med_str = f"{fam_med:.1f} yr" if fam_med is not None else "—"

    # "Faster / slower than family" verdict
    if fastest is not None and fam_med is not None:
        if fastest < fam_med:
            verdict = f"Fastest patent was <strong>{fam_med - fastest:.1f} yr earlier</strong> than the family median"
        else:
            verdict = f"Fastest patent matched the family median of {fam_med_str}"
    else:
        verdict = ""

    st.markdown(
        f"<div style='background:{_hex_rgba(family_color, 0.06)};"
        f"border:1px solid {family_color}44;border-radius:10px;padding:20px 18px;'>"
        f"<div style='font-size:9px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:{family_color};margin-bottom:14px;'>"
        f"{family_label}</div>"
        f"<div style='font-family:{_FONT};font-size:32px;font-weight:800;"
        f"color:#111111;line-height:1;'>{n_citing}</div>"
        f"<div style='font-size:12px;color:#888888;margin-top:4px;'>"
        f"US patents cited this paper</div>"
        f"<div style='border-top:1px solid {family_color}33;margin:14px 0;'></div>"
        f"<div style='display:flex;justify-content:space-between;margin-bottom:10px;'>"
        f"<div><div style='font-family:{_FONT};font-size:20px;font-weight:700;"
        f"color:{family_color};'>{fastest_str}</div>"
        f"<div style='font-size:10px;color:#888888;'>fastest citation lag</div></div>"
        f"<div><div style='font-family:{_FONT};font-size:20px;font-weight:700;"
        f"color:#aaaaaa;'>{fam_med_str}</div>"
        f"<div style='font-size:10px;color:#888888;'>family median</div></div>"
        f"</div>"
        + (
            f"<div style='font-size:11px;color:#555555;line-height:1.5;'>"
            f"{verdict}</div>"
            if verdict else ""
        )
        + "</div>",
        unsafe_allow_html=True,
    )

# ── Timeline chart ────────────────────────────────────────────────────────────
st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
st.markdown(
    f"<div style='font-family:{_FONT};font-size:14px;font-weight:700;"
    f"color:#111111;margin-bottom:4px;'>The Journey — publication to patent filing</div>"
    f"<div style='font-size:12px;color:#888888;margin-bottom:12px;'>"
    f"Each marker is a US patent that cited this paper, plotted at its filing date. "
    f"The dashed line shows the family median citation lag."
    f"</div>",
    unsafe_allow_html=True,
)

if n_citing == 0:
    st.info("No citing patents found in the current NPL link set.")
else:
    links = links_df.to_dicts()
    # Compute decimal filing years for precise X position
    for row in links:
        fd = row.get("filing_date")
        if fd is not None:
            row["filing_decimal"] = int(str(fd)[:4]) + ((fd.month - 1) / 12.0)
        else:
            row["filing_decimal"] = None

    links_with_date = [r for r in links if r["filing_decimal"] is not None]
    links_no_date   = [r for r in links if r["filing_decimal"] is None]

    # Y positions: each patent gets a row, paper gets a special Y
    n = len(links_with_date)
    # Assign Y: earliest patent at top (Y = n-1 down to 0), paper at Y = n + 0.5
    paper_y = n + 0.3

    y_positions = list(range(n - 1, -1, -1))  # n-1, n-2, ... 0
    y_labels = [
        (r["assignee"] or "Unresolved")[:22]
        for r in links_with_date
    ]

    fig = go.Figure()

    # Connector lines (paper → each patent)
    for i, row in enumerate(links_with_date):
        y_i = y_positions[i]
        fig.add_shape(
            type="line",
            x0=pub_decimal, x1=row["filing_decimal"],
            y0=paper_y, y1=y_i,
            line=dict(color=_hex_rgba(family_color, 0.18), width=1, dash="dot"),
        )

    # Family median reference line
    if fam_med is not None:
        median_x = pub_decimal + fam_med
        fig.add_vline(
            x=median_x,
            line=dict(color=_hex_rgba(family_color, 0.45), width=1.5, dash="dash"),
            annotation_text=f"family median<br>{fam_med:.1f} yr",
            annotation_font=dict(size=10, color=family_color),
            annotation_position="top right",
        )

    # Patent markers
    xs = [r["filing_decimal"] for r in links_with_date]
    ys = y_positions
    hover_texts = []
    for row in links_with_date:
        lag_str = f"{row['citation_lag_years']:.1f} yr" if row["citation_lag_years"] is not None else "—"
        title = (row["patent_title"] or "Untitled")[:60]
        assignee = row["assignee"] or "Unresolved"
        filing_yr = str(row.get("filing_date") or "")[:4]
        hover_texts.append(
            f"<b>{title}</b><br>"
            f"Assignee: {assignee}<br>"
            f"Filed: {filing_yr}<br>"
            f"Lag: {lag_str}<br>"
            f"Patent: US{row['patent_id']}"
        )

    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers+text",
        marker=dict(
            color=family_color,
            size=12,
            symbol="circle",
            line=dict(color="#ffffff", width=1.5),
        ),
        text=[f"  {(r['assignee'] or 'Unresolved')[:18]}" for r in links_with_date],
        textposition="middle right",
        textfont=dict(size=10, color="#555555"),
        hovertext=hover_texts,
        hoverinfo="text",
        name="Citing patents",
    ))

    # Paper origin marker
    fig.add_trace(go.Scatter(
        x=[pub_decimal], y=[paper_y],
        mode="markers+text",
        marker=dict(
            color=paper_color,
            size=18,
            symbol="diamond",
            line=dict(color=family_color, width=2),
        ),
        text=[f"  Paper published {pub_year}"],
        textposition="middle right",
        textfont=dict(size=11, color=family_color, family=_FONT),
        hovertext=[f"<b>{paper['title'][:60]}</b><br>Published {pub_year}"],
        hoverinfo="text",
        name=f"Paper ({pub_year})",
    ))

    all_xs = [pub_decimal] + [r["filing_decimal"] for r in links_with_date if r["filing_decimal"]]
    x_min = min(all_xs) - 0.5
    x_max = max(all_xs) + 1.5

    fig.update_layout(
        height=max(280, n * 38 + 120),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(size=11, color="#111111"),
        margin=dict(l=10, r=180, t=30, b=40),
        xaxis=dict(
            title="Year",
            range=[x_min, x_max],
            showgrid=True, gridcolor="#f0f0f0",
            zeroline=False, showline=True, linecolor="#e6e6e6",
            tickformat="d",
            dtick=1,
        ),
        yaxis=dict(
            showticklabels=False,
            showgrid=False, zeroline=False,
            range=[-0.8, paper_y + 0.7],
        ),
        showlegend=False,
        hovermode="closest",
    )

    # Confidence badges in hover are HTML — use confidence as text note
    for i, row in enumerate(links_with_date):
        conf = row.get("confidence", "medium")
        conf_color = {"high": "#22c55e", "medium": "#94a3b8", "low": "#ef4444"}.get(conf, "#94a3b8")
        y_i = y_positions[i]
        fig.add_annotation(
            x=x_min + 0.05, y=y_i,
            text=f"<span style='color:{conf_color};'>●</span>",
            showarrow=False,
            font=dict(size=8, color=conf_color),
            xanchor="left",
            align="left",
        )

    st.plotly_chart(
        fig, use_container_width=True,
        config={"displayModeBar": False}, key="trace_timeline",
    )

    if links_no_date:
        st.caption(f"{len(links_no_date)} patent(s) not shown — no filing date available.")

# ── Closing stat ──────────────────────────────────────────────────────────────
if len(family_df) > 0:
    frow = family_df.row(0, named=True)
    fam_name = frow["family_name"]
    med_lag = frow["median_lag_years_weighted"]
    n_links = frow["total_npl_links"]
    n_papers = frow["n_papers"]
    n_patents = frow["n_patents"]
    lag_display = f"{med_lag:.1f}" if med_lag is not None else "—"

    st.markdown(
        f"<div style='background:{_hex_rgba(family_color, 0.05)};"
        f"border:1px solid {family_color}33;"
        f"border-radius:10px;padding:20px 24px;margin-top:1.5rem;'>"
        f"<div style='font-size:9px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:{family_color};margin-bottom:6px;'>"
        f"The pattern across {fam_name}</div>"
        f"<div style='font-family:{_FONT};font-size:28px;font-weight:800;color:#111111;'>"
        f"{lag_display}"
        f"<span style='font-size:14px;font-weight:400;color:#888888;margin-left:8px;'>"
        f"years — median citation lag across the family (publication → filing)</span></div>"
        f"<div style='font-size:12px;color:#888888;margin-top:6px;'>"
        f"Based on {n_links:,} NPL-matched paper→patent links · "
        f"{n_papers:,} papers · {n_patents:,} US patents in scope"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ── Methodology caption ───────────────────────────────────────────────────────
st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
st.caption(
    "**Citation lag** is the interval between a paper's publication date and a patent's "
    "filing date, measured only where a verified NPL reference link exists. "
    "It is not R&D-to-market time and does not imply causation. "
    "Confidence (● green = high, ● grey = medium) reflects the NPL matching method: "
    "DOI-exact match = high; fuzzy title match = medium. "
    "Patents are US-only (PatentsView). "
    f"Showing up to 12 citing patents by citation lag; each paper may have more."
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### Trace an Idea")
    st.divider()
    st.page_link("app.py",             label="← Overview")
    st.page_link("pages/1_Map.py",     label="Technology map")
    st.page_link("pages/3_Org.py",     label="Organisation profile")
