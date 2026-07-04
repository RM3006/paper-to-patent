"""
Organisation Profile — Surface 3.

Two-sided ledger: patent output (IP) on the left, research output (papers) on the right.
The NPL citation bridge sits between them, showing which science feeds into this org's
patents and which orgs build on its research.

Entry: single searchable dropdown on this page; defaults to TSMC.
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
from render import FAMILY_COLORS, render_nav, render_tour_banner
from streamlit_searchbox import st_searchbox

_SEARCHBOX_STYLE = {"searchbox": {"option": {"highlightColor": "#f0f0f0"}}}

from data import (
    search_orgs_ilike,
    load_dataset_totals,
    load_org_filing_years,
    load_org_flagship_paper,
    load_org_flagship_patent,
    load_org_influence,
    load_org_intake,
    load_org_output_by_family,
    load_org_paper_output_by_family,
    load_org_paper_years,
    load_org_profile,
    load_org_top_patent_clusters,
    load_org_top_research_clusters,
)

st.set_page_config(
    page_title="Organisation Profile — The Chips Behind AI",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_FONT = '"Space Grotesk", -apple-system, system-ui, sans-serif'

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&display=swap');
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
/* Remove Plotly crosshair cursor and spike line overlay */
.js-plotly-plot .plotly .cursor-crosshair { cursor: default !important; }
.js-plotly-plot .cartesianlayer .spikeline { display: none !important; }
</style>
""", unsafe_allow_html=True)

render_nav("Organisation Profile")
render_tour_banner(3)


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _bar_chart(
    names: list[str],
    counts: list[int],
    color: str,
    title: str,
    height: int = 200,
) -> go.Figure:
    truncated = [n[:28] + "…" if len(n) > 28 else n for n in names]
    f = go.Figure(go.Bar(
        x=counts, y=truncated, orientation="h",
        marker_color=color, marker_opacity=0.85,
        text=[f"{v:,}" for v in counts],
        textposition="outside",
        cliponaxis=False,
        textfont=dict(size=11, color="#111111"),
    ))
    f.update_layout(
        title=dict(text=title, font=dict(size=11, color="#888888"), x=0),
        height=height,
        margin=dict(l=0, r=60, t=28, b=5),
        plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
        font=dict(size=11, color="#111111"),
        xaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, autorange="reversed"),
        showlegend=False,
    )
    return f


def _spacer() -> None:
    st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)


def _cluster_list(clusters: list[dict], min_rows: int = 5) -> None:
    """Render cluster rows: white background, grey border, family-color text, fixed row height.

    Always renders min_rows rows — real rows first, then invisible spacers — so both
    columns stay vertically aligned regardless of how many clusters each side has.
    """
    for row in clusters:
        pct = (row["share"] or 0) * 100
        fam_color = FAMILY_COLORS.get(row.get("family_id") or "", "#888888")
        st.markdown(
            f"<div class='card card--row' style='--accent:{fam_color};'>"
            f"<div class='card-stat' style='font-size:12px;font-weight:600;"
            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>"
            f"{row['tagline']}</div>"
            f"<div style='font-size:11px;color:#888888;margin-top:2px;'>"
            f"{row['doc_count']:,} · {pct:.1f}% cluster share"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    for _ in range(max(0, min_rows - len(clusters))):
        st.markdown(
            "<div style='height:48px;box-sizing:border-box;margin-bottom:4px;'></div>",
            unsafe_allow_html=True,
        )


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    "<p style='color:#888888;margin-top:0;margin-bottom:1rem;font-size:15px;'>"
    "Search any organisation in the dataset — academic, corporate, or government. "
    "The ledger shows what they research and what they patent."
    "</p>",
    unsafe_allow_html=True,
)

# ── Pre-selection ─────────────────────────────────────────────────────────────
_preselected: str | None = st.session_state.get("selected_org_id")

# ── ILIKE combobox ────────────────────────────────────────────────────────────
chosen_id: str | None = st_searchbox(
    search_orgs_ilike,
    placeholder="Search all organisations... (type to find any)",
    key="org_searchbox",
    style_overrides=_SEARCHBOX_STYLE,
    default_options=search_orgs_ilike(""),
)

selected_org_id: str | None = chosen_id or _preselected or "org_tsmc"
if chosen_id is not None:
    st.session_state.selected_org_id = chosen_id

# ── Load profile ──────────────────────────────────────────────────────────────
profile_df = load_org_profile(selected_org_id)
if len(profile_df) == 0:
    st.error(f"Organisation '{selected_org_id}' not found.")
    st.stop()

profile    = profile_df.row(0, named=True)
org_name   = profile["canonical_name"]
match_meth = profile["primary_match_method"]
confidence = profile["primary_confidence"]

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Loading…"):
    output_by_family = load_org_output_by_family(selected_org_id)
    paper_by_family  = load_org_paper_output_by_family(selected_org_id)
    top_pat_clusters = load_org_top_patent_clusters(selected_org_id)
    top_res_clusters = load_org_top_research_clusters(selected_org_id)
    filing_years     = load_org_filing_years(selected_org_id)
    paper_years      = load_org_paper_years(selected_org_id)
    intake           = load_org_intake(selected_org_id)
    influence        = load_org_influence(selected_org_id)
    flagship_paper   = load_org_flagship_paper(selected_org_id)
    flagship_patent  = load_org_flagship_patent(selected_org_id)
    dataset_totals   = load_dataset_totals()

n_patents_total  = int(output_by_family["n_patents"].sum()) if len(output_by_family) > 0 else 0
n_papers_total   = int(paper_by_family["n_papers"].sum())  if len(paper_by_family)  > 0 else 0
has_patents      = n_patents_total > 0
has_papers       = n_papers_total > 0

total_patents_ds = dataset_totals["total_patents"]
total_papers_ds  = dataset_totals["total_papers"]
pct_patents = (n_patents_total / total_patents_ds * 100) if total_patents_ds > 0 else 0.0
pct_papers  = (n_papers_total  / total_papers_ds  * 100) if total_papers_ds  > 0 else 0.0

# ── Dominant family color ─────────────────────────────────────────────────────
_family_counts: dict[str, int] = {}
for r in output_by_family.to_dicts():
    _family_counts[r["family_id"]] = _family_counts.get(r["family_id"], 0) + int(r["n_patents"])
for r in paper_by_family.to_dicts():
    _family_counts[r["family_id"]] = _family_counts.get(r["family_id"], 0) + int(r["n_papers"])

dominant_family = max(_family_counts, key=_family_counts.get) if _family_counts else "noise"
org_color = FAMILY_COLORS.get(dominant_family, "#888888")

# ── Role descriptor ───────────────────────────────────────────────────────────
if n_papers_total == 0 and n_patents_total > 0:
    role_label = "Primarily an IP holder"
elif n_patents_total == 0 and n_papers_total > 0:
    role_label = "Primarily a research institution"
else:
    ratio = n_patents_total / max(n_papers_total + n_patents_total, 1)
    if ratio >= 0.7:
        role_label = "Primarily an IP holder"
    elif ratio <= 0.3:
        role_label = "Primarily a research institution"
    else:
        role_label = "Both researcher and IP holder"

# ── Org identity header ───────────────────────────────────────────────────────
st.markdown(
    f"<div style='margin-top:1rem;margin-bottom:1.2rem;'>"
    f"<div style='font-family:{_FONT};font-size:28px;font-weight:800;"
    f"color:#111111;line-height:1.2;margin-bottom:4px;'>{org_name}</div>"
    f"<div style='font-size:12px;color:#888888;'>{role_label}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# ── 4 metric cards ─────────────────────────────────────────────────────────────
_om1, _om2, _om3, _om4 = st.columns(4)
for _col, _val, _lbl in [
    (_om1, f"{n_patents_total:,}", "US patents"),
    (_om2, f"{pct_patents:.2f}%",  "of all patents"),
    (_om3, f"{n_papers_total:,}",  "research papers"),
    (_om4, f"{pct_papers:.2f}%",   "of all papers"),
]:
    with _col:
        st.markdown(
            f"<div class='card card--metric' style='margin-bottom:1rem;'>"
            f"<div class='card-stat' style='font-family:{_FONT};font-size:28px;"
            f"font-weight:800;line-height:1;'>{_val}</div>"
            f"<div style='font-size:12px;color:#888888;margin-top:6px;"
            f"white-space:nowrap;'>{_lbl}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
st.markdown("<div style='margin-bottom:3rem;'></div>", unsafe_allow_html=True)

# ── Two-sided ledger — Patent left, Research right ────────────────────────────
# Shared chart height so both family bar charts are always the same size regardless of bar count.
_n_pat_fam = len(output_by_family) if has_patents else 0
_n_res_fam = len(paper_by_family) if has_papers else 0
_family_chart_h = max(160, 40 * max(_n_pat_fam, _n_res_fam) + 40)

col_patent, col_research = st.columns(2, gap="large")

# ── PATENT SIDE ───────────────────────────────────────────────────────────────
with col_patent:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:#555555;"
        f"padding-bottom:4px;margin-bottom:0.75rem;"
        f"border-bottom:1px solid #555555;'>Patent output</div>",
        unsafe_allow_html=True,
    )

    if not has_patents:
        st.caption("No resolved US patents found for this organisation.")
    else:
        # Patents by family — descending by count
        fam_ids    = output_by_family["family_id"].to_list()
        fam_names  = output_by_family["family_name"].to_list()
        n_pats     = [int(v) for v in output_by_family["n_patents"].to_list()]
        bar_colors = [FAMILY_COLORS.get(fid, "#888888") for fid in fam_ids]

        pairs = sorted(zip(n_pats, fam_names, bar_colors, strict=False), reverse=True)
        pv, pn, pc = map(list, zip(*pairs, strict=False))

        fig_fam = go.Figure(go.Bar(
            x=pv, y=pn, orientation="h",
            marker_color=pc,
            text=[f"{v:,}" for v in pv],
            textposition="outside", cliponaxis=False,
        ))
        fig_fam.update_layout(
            title=dict(text="US patents by family", font=dict(size=11, color="#888888"), x=0),
            height=_family_chart_h,
            margin=dict(l=0, r=60, t=28, b=5),
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            font=dict(size=11, color="#111111"),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, autorange="reversed"),
            showlegend=False,
        )
        st.plotly_chart(fig_fam, use_container_width=True,
                        config={"displayModeBar": False, "displaylogo": False},
                        key="org_pat_family")

        if len(top_pat_clusters) > 0:
            _spacer()
            st.markdown(
                "<div style='font-size:11px;color:#888888;"
                "margin-bottom:8px;'>Top patent clusters</div>",
                unsafe_allow_html=True,
            )
            _cluster_list(top_pat_clusters.to_dicts())

        if len(filing_years) > 0:
            _spacer()
            yrs = filing_years["year"].to_list()
            nps = [int(v) for v in filing_years["n_patents"].to_list()]
            fig_fy = go.Figure(go.Bar(
                x=yrs, y=nps,
                marker_color="#555555",
                text=[str(v) for v in nps], textposition="outside", cliponaxis=False,
            ))
            fig_fy.update_layout(
                title=dict(text="US patent filings per year", font=dict(size=11, color="#888888"), x=0),
                height=170,
                margin=dict(l=0, r=10, t=28, b=5),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                font=dict(size=11, color="#111111"),
                xaxis=dict(showgrid=False, zeroline=False, dtick=2),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                showlegend=False,
            )
            st.plotly_chart(fig_fy, use_container_width=True,
                            config={"displayModeBar": False, "displaylogo": False},
                            key="org_pat_years")
            st.markdown(
                "<span style='font-size:10px;color:#888888;'>"
                "Counts after 2019 are understated — recent filings take 2–4 years to be granted."
                "</span>",
                unsafe_allow_html=True,
            )

# ── RESEARCH SIDE ─────────────────────────────────────────────────────────────
with col_research:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:#555555;"
        f"padding-bottom:4px;margin-bottom:0.75rem;"
        f"border-bottom:1px solid #555555;'>Research output</div>",
        unsafe_allow_html=True,
    )

    if not has_papers:
        st.caption("No resolved research papers found for this organisation.")
    else:
        # Papers by family — descending by count
        pf_ids    = paper_by_family["family_id"].to_list()
        pf_names  = paper_by_family["family_name"].to_list()
        pf_counts = [int(v) for v in paper_by_family["n_papers"].to_list()]
        pf_colors = [FAMILY_COLORS.get(fid, "#888888") for fid in pf_ids]

        pairs = sorted(zip(pf_counts, pf_names, pf_colors, strict=False), reverse=True)
        pv, pn, pc = map(list, zip(*pairs, strict=False))

        fig_pf = go.Figure(go.Bar(
            x=pv, y=pn, orientation="h",
            marker_color=pc,
            text=[f"{v:,}" for v in pv],
            textposition="outside", cliponaxis=False,
        ))
        fig_pf.update_layout(
            title=dict(text="Research papers by family", font=dict(size=11, color="#888888"), x=0),
            height=_family_chart_h,
            margin=dict(l=0, r=60, t=28, b=5),
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            font=dict(size=11, color="#111111"),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, autorange="reversed"),
            showlegend=False,
        )
        st.plotly_chart(fig_pf, use_container_width=True,
                        config={"displayModeBar": False, "displaylogo": False},
                        key="org_res_family")

        if len(top_res_clusters) > 0:
            _spacer()
            st.markdown(
                "<div style='font-size:11px;color:#888888;"
                "margin-bottom:8px;'>Top research clusters</div>",
                unsafe_allow_html=True,
            )
            _cluster_list(top_res_clusters.to_dicts())

        if len(paper_years) > 0:
            _spacer()
            yrs = paper_years["year"].to_list()
            nps = paper_years["n_papers"].to_list()
            fig_py = go.Figure(go.Bar(
                x=yrs, y=nps,
                marker_color="#aaaaaa",
                text=[str(v) for v in nps], textposition="outside", cliponaxis=False,
            ))
            fig_py.update_layout(
                title=dict(text="Papers per year", font=dict(size=11, color="#888888"), x=0),
                height=170,
                margin=dict(l=0, r=10, t=28, b=5),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                font=dict(size=11, color="#111111"),
                xaxis=dict(showgrid=False, zeroline=False, dtick=2),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                showlegend=False,
            )
            st.plotly_chart(fig_py, use_container_width=True,
                            config={"displayModeBar": False, "displaylogo": False},
                            key="org_res_years")

# ── Flagship documents — single shared zone ───────────────────────────────────
if len(flagship_patent) > 0 or len(flagship_paper) > 0:
    st.markdown("<div style='height:4rem'></div>", unsafe_allow_html=True)

    patent_html = ""
    if len(flagship_patent) > 0:
        fpt = flagship_patent.row(0, named=True)
        filing_yr = fpt["filing_date"].year if fpt["filing_date"] else "—"
        patent_html = (
            f"<div style='flex:1;min-width:0;display:flex;gap:16px;align-items:flex-start;'>"
            f"<div style='flex-shrink:0;text-align:center;padding-top:2px;'>"
            f"<div style='font-family:{_FONT};font-size:52px;font-weight:800;"
            f"color:#111111;line-height:1;'>{fpt['n_papers_cited']:,}</div>"
            f"<div style='font-size:9px;color:#111111;text-transform:uppercase;"
            f"letter-spacing:.08em;margin-top:4px;'>papers cited</div>"
            f"</div>"
            f"<div style='flex:1;min-width:0;padding-left:16px;border-left:1px solid #e6e6e6;'>"
            f"<div style='font-size:9px;font-weight:700;letter-spacing:.1em;"
            f"text-transform:uppercase;color:#aaaaaa;margin-bottom:8px;'>Most NPL-citing patent</div>"
            f"<div style='font-size:14px;font-weight:700;color:#111111;"
            f"line-height:1.45;margin-bottom:10px;'>{fpt['title']}</div>"
            f"<div style='font-size:11px;color:#888888;'>"
            f"Filed {filing_yr} &nbsp;&middot;&nbsp; US{fpt['patent_id']}</div>"
            f"</div>"
            f"</div>"
        )

    paper_html = ""
    if len(flagship_paper) > 0:
        fp = flagship_paper.row(0, named=True)
        pub_yr = fp["publication_date"].year if fp["publication_date"] else "—"
        abstract = (fp["abstract"] or "")[:280]
        if len(fp["abstract"] or "") > 280:
            abstract += "…"
        paper_html = (
            f"<div style='flex:1;min-width:0;display:flex;gap:16px;align-items:flex-start;'>"
            f"<div style='flex-shrink:0;text-align:center;padding-top:2px;'>"
            f"<div style='font-family:{_FONT};font-size:52px;font-weight:800;"
            f"color:#111111;line-height:1;'>{fp['n_citing_patents']:,}</div>"
            f"<div style='font-size:9px;color:#111111;text-transform:uppercase;"
            f"letter-spacing:.08em;margin-top:4px;'>patents cite this</div>"
            f"</div>"
            f"<div style='flex:1;min-width:0;padding-left:16px;border-left:1px solid #e6e6e6;'>"
            f"<div style='font-size:9px;font-weight:700;letter-spacing:.1em;"
            f"text-transform:uppercase;color:#aaaaaa;margin-bottom:8px;'>Most-cited paper</div>"
            f"<div style='font-size:14px;font-weight:700;color:#111111;"
            f"line-height:1.45;margin-bottom:6px;'>{fp['title']}</div>"
            f"<div style='font-size:11px;color:#888888;margin-bottom:10px;'>"
            f"Published {pub_yr}</div>"
            f"<div style='font-size:11px;color:#555555;line-height:1.6;'>"
            f"{abstract}</div>"
            f"</div>"
            f"</div>"
        )

    divider = (
        "<div style='width:1px;background:#e6e6e6;flex-shrink:0;margin:0 2rem;'></div>"
        if patent_html and paper_html else ""
    )

    st.markdown(
        f"<div style='display:flex;align-items:flex-start;'>"
        + patent_html + divider + paper_html
        + "</div>",
        unsafe_allow_html=True,
    )

# ── Citation bridge ───────────────────────────────────────────────────────────
has_intake    = len(intake)    > 0
has_influence = len(influence) > 0

if has_intake or has_influence:
    st.markdown("<div style='margin-top:4rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='text-align:center;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:#888888;margin-bottom:4px;'>"
        f"The citation bridge — via NPL links</div>"
        f"<div style='font-size:12px;color:#888888;margin-bottom:1.5rem;'>"
        f"Who feeds this org's patents with research, and whose patents build on its work."
        f"</div></div>",
        unsafe_allow_html=True,
    )

    col_intake, col_influence = st.columns(2, gap="large")

    with col_intake:
        if has_intake:
            intake_rows = intake.to_dicts()
            i_names  = [r["paper_org_name"] for r in intake_rows]
            i_counts = [int(r["n_papers_cited"]) for r in intake_rows]
            i_ids    = [r["paper_org_id"] for r in intake_rows]
            # descending: largest at top
            pairs_i = sorted(zip(i_counts, i_names, i_ids, strict=False), reverse=True)
            iv, inn, iid = map(list, zip(*pairs_i, strict=False))
            truncated_i = [n[:32] + "…" if len(n) > 32 else n for n in inn]
            hover_i = [
                f"{org_name}'s patents cited <b>{c:,}</b> paper{'s' if c != 1 else ''} "
                f"published by <b>{n}</b>"
                for c, n in zip(iv, inn, strict=False)
            ]
            fig_i = go.Figure(go.Bar(
                x=iv, y=iid, orientation="h",
                marker_color="#aaaaaa", marker_opacity=0.85,
                text=[f"{v:,}" for v in iv],
                textposition="outside", cliponaxis=False,
                textfont=dict(size=11, color="#111111"),
                customdata=hover_i,
                hovertemplate="%{customdata}<extra></extra>",
            ))
            fig_i.update_layout(
                title=dict(
                    text="Research it draws on (papers cited in its patents)",
                    font=dict(size=11, color="#888888"), x=0,
                ),
                height=max(180, 32 * len(iv) + 40),
                margin=dict(l=0, r=60, t=28, b=5),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                font=dict(size=11, color="#111111"),
                xaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False, showticklabels=False, showspikes=False),
                yaxis=dict(tickmode="array", tickvals=iid, ticktext=truncated_i,
                           showgrid=False, zeroline=False, autorange="reversed", showspikes=False),
                hovermode="y",
                dragmode=False,
                showlegend=False,
                hoverlabel=dict(bgcolor="#ffffff", font_size=12, font_color="#111111"),
            )
            st.plotly_chart(fig_i, use_container_width=True,
                            config={"displayModeBar": False, "displaylogo": False},
                            key="org_intake")
        else:
            st.caption("No NPL-linked intake data found.")

    with col_influence:
        if has_influence:
            inf_rows = influence.to_dicts()
            inf_names  = [r["patenter_name"] for r in inf_rows]
            inf_counts = [int(r["n_patents"]) for r in inf_rows]
            inf_ids    = [r["patenter_org_id"] for r in inf_rows]
            # descending: largest at top
            pairs_inf = sorted(zip(inf_counts, inf_names, inf_ids, strict=False), reverse=True)
            infv, infn, infid = map(list, zip(*pairs_inf, strict=False))
            truncated_inf = [n[:32] + "…" if len(n) > 32 else n for n in infn]
            hover_inf = [
                f"<b>{n}</b> filed <b>{c:,}</b> patent{'s' if c != 1 else ''} "
                f"citing papers published by <b>{org_name}</b>"
                for c, n in zip(infv, infn, strict=False)
            ]
            fig_inf = go.Figure(go.Bar(
                x=infv, y=infid, orientation="h",
                marker_color="#555555", marker_opacity=0.85,
                text=[f"{v:,}" for v in infv],
                textposition="outside", cliponaxis=False,
                textfont=dict(size=11, color="#111111"),
                customdata=hover_inf,
                hovertemplate="%{customdata}<extra></extra>",
            ))
            fig_inf.update_layout(
                title=dict(
                    text="Who patents this org's research (patents citing its papers)",
                    font=dict(size=11, color="#888888"), x=0,
                ),
                height=max(180, 32 * len(infv) + 40),
                margin=dict(l=0, r=60, t=28, b=5),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                font=dict(size=11, color="#111111"),
                xaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False, showticklabels=False, showspikes=False),
                yaxis=dict(tickmode="array", tickvals=infid, ticktext=truncated_inf,
                           showgrid=False, zeroline=False, autorange="reversed", showspikes=False),
                hovermode="y",
                dragmode=False,
                showlegend=False,
                hoverlabel=dict(bgcolor="#ffffff", font_size=12, font_color="#111111"),
            )
            st.plotly_chart(fig_inf, use_container_width=True,
                            config={"displayModeBar": False, "displaylogo": False},
                            key="org_influence")
        else:
            st.caption("No NPL-linked influence data found.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(
    "<span style='font-size:11px;color:#888888;'>"
    "<strong>Data quality:</strong> "
    "Org matches use the crosswalk (seed → ROR → fuzzy). "
    "Intake and influence panels are based on NPL citation links only "
    "(high/medium-confidence links). "
    "US patents only (PatentsView / USPTO). "
    "Papers from OpenAlex (2012–2025). "
    "Percentage shares are relative to the total across all five technology families "
    "(resolved documents only; unresolved orgs excluded)."
    "</span>",
    unsafe_allow_html=True,
)
