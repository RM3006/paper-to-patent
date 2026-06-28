"""
Organisation Profile — Surface 3.

Two-sided ledger: research output (papers) on the left, patent output (IP) on the right.
The NPL citation bridge sits between them, showing which science feeds into this org's
patents and which orgs build on its research.

Entry: single searchable dropdown on this page, or featured org chips.
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
from render import (
    FAMILY_COLORS,
    confidence_badge,
    method_badge,
)
from streamlit_searchbox import st_searchbox

_SEARCHBOX_STYLE = {"searchbox": {"option": {"highlightColor": "#f0f0f0"}}}

from data import (
    search_orgs_ilike,
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
    page_title="Org Profile — The Chips Behind AI",
    page_icon="🏢",
    layout="wide",
)

_FONT = '"Space Grotesk", -apple-system, system-ui, sans-serif'

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&display=swap');
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
</style>
""", unsafe_allow_html=True)

# Featured orgs shown as chips on the empty state
_FEATURED: list[tuple[str, str]] = [
    ("org_asml",                       "ASML"),
    ("org_tsmc",                       "TSMC"),
    ("org_imec",                       "IMEC"),
    ("org_ibm",                        "IBM"),
    ("org_oa_chinese_academy_of_sciences", "Chinese Academy of Sciences"),
]


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
    truncated = [n[:26] + "…" if len(n) > 26 else n for n in names]
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


def _cluster_list(clusters: list[dict], color: str) -> None:
    for row in clusters:
        pct = (row["share"] or 0) * 100
        st.markdown(
            f"<div style='padding:7px 0;border-bottom:1px solid #f0f0f0;'>"
            f"<div style='font-size:12px;color:#111111;font-weight:500;'>"
            f"{row['tagline']}</div>"
            f"<div style='font-size:11px;color:#888888;'>"
            f"{row['doc_count']:,} · {pct:.1f}% cluster share"
            f"</div></div>",
            unsafe_allow_html=True,
        )


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## Organisation Profile")
st.markdown(
    "<p style='color:#888888;margin-top:-0.4rem;margin-bottom:1rem;font-size:15px;'>"
    "Search any organisation in the dataset — academic, corporate, or government. "
    "The ledger shows what they research and what they patent."
    "</p>",
    unsafe_allow_html=True,
)

# ── Pre-selection from chip click ─────────────────────────────────────────────
_preselected: str | None = st.session_state.get("selected_org_id")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("#### Organisation Profile")
    st.divider()
    if _preselected:
        if st.button("Clear selection", key="org_clear", type="secondary"):
            st.session_state.selected_org_id = None
            st.session_state["org_searchbox"] = None
            st.rerun()
        st.divider()
    st.page_link("app.py",            label="← Overview")
    st.page_link("pages/1_Map.py",    label="Technology map")
    st.page_link("pages/2_Family.py", label="Family detail")
    st.page_link("pages/4_Trace.py",  label="Trace an idea")

# ── ILIKE combobox — true server-side substring filtering ─────────────────────
chosen_id: str | None = st_searchbox(
    search_orgs_ilike,
    placeholder="Search by organisation name…",
    key="org_searchbox",
    style_overrides=_SEARCHBOX_STYLE,
    default_options=search_orgs_ilike(""),
)

selected_org_id: str | None = chosen_id or _preselected
if chosen_id is not None:
    st.session_state.selected_org_id = chosen_id

# ── Empty state — featured org chips ─────────────────────────────────────────
if not selected_org_id:
    st.markdown(
        "<div style='font-size:12px;color:#888888;margin-bottom:10px;'>"
        "Or explore a featured organisation:</div>",
        unsafe_allow_html=True,
    )
    chip_cols = st.columns(len(_FEATURED), gap="small")
    for i, (oid, label) in enumerate(_FEATURED):
        with chip_cols[i]:
            if st.button(label, key=f"featured_{i}", type="secondary"):
                st.session_state.selected_org_id = oid
                st.session_state["org_searchbox"] = None
                st.rerun()
    st.stop()

if not selected_org_id:
    st.stop()

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
with st.spinner("Loading …"):
    output_by_family    = load_org_output_by_family(selected_org_id)        # patents by family
    paper_by_family     = load_org_paper_output_by_family(selected_org_id)  # papers by family
    top_pat_clusters    = load_org_top_patent_clusters(selected_org_id)
    top_res_clusters    = load_org_top_research_clusters(selected_org_id)
    filing_years        = load_org_filing_years(selected_org_id)
    paper_years         = load_org_paper_years(selected_org_id)
    intake              = load_org_intake(selected_org_id)
    influence           = load_org_influence(selected_org_id)
    flagship_paper      = load_org_flagship_paper(selected_org_id)
    flagship_patent     = load_org_flagship_patent(selected_org_id)

n_patents_total = int(output_by_family["n_patents"].sum()) if len(output_by_family) > 0 else 0
n_papers_total  = int(paper_by_family["n_papers"].sum())  if len(paper_by_family)  > 0 else 0
has_patents     = n_patents_total > 0
has_papers      = n_papers_total > 0

# ── Dominant family color (most activity overall) ─────────────────────────────
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
    balance_pct = 100
elif n_patents_total == 0 and n_papers_total > 0:
    role_label = "Primarily a research institution"
    balance_pct = 0
else:
    ratio = n_patents_total / max(n_papers_total + n_patents_total, 1)
    balance_pct = int(ratio * 100)
    if ratio >= 0.7:
        role_label = "Primarily an IP holder"
    elif ratio <= 0.3:
        role_label = "Primarily a research institution"
    else:
        role_label = "Both researcher and IP holder"

# ── Org card ──────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='border:1px solid #e6e6e6;border-radius:10px;"
    f"padding:20px 24px;margin-bottom:1.5rem;background:#ffffff;'>"
    f"<div style='display:flex;align-items:flex-start;justify-content:space-between;"
    f"gap:24px;flex-wrap:wrap;'>"
    # Left: name + badges
    f"<div>"
    f"<div style='font-family:{_FONT};font-size:22px;font-weight:800;"
    f"color:#111111;margin-bottom:8px;'>{org_name}</div>"
    f"<div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap;'>"
    f"{method_badge(match_meth)} {confidence_badge(confidence)}"
    f"<span style='font-size:11px;color:#888888;'>match method · confidence</span>"
    f"</div></div>"
    # Right: paper + patent counts
    f"<div style='display:flex;gap:24px;align-items:center;'>"
    f"<div style='text-align:center;'>"
    f"<div style='font-family:{_FONT};font-size:22px;font-weight:700;"
    f"color:{_hex_rgba(org_color, 0.55)};'>{n_papers_total:,}</div>"
    f"<div style='font-size:10px;color:#888888;'>research papers</div></div>"
    f"<div style='text-align:center;'>"
    f"<div style='font-family:{_FONT};font-size:22px;font-weight:700;"
    f"color:{org_color};'>{n_patents_total:,}</div>"
    f"<div style='font-size:10px;color:#888888;'>US patents</div></div>"
    f"</div></div>"
    # Balance bar
    f"<div style='margin-top:14px;'>"
    f"<div style='display:flex;justify-content:space-between;"
    f"font-size:10px;color:#aaaaaa;margin-bottom:4px;'>"
    f"<span>Research</span><span>IP</span></div>"
    f"<div style='background:#f0f0f0;border-radius:4px;height:6px;width:100%;'>"
    f"<div style='background:{org_color};height:6px;border-radius:4px;"
    f"width:{balance_pct}%;'></div></div>"
    f"<div style='font-size:11px;color:#555555;margin-top:6px;'>{role_label}</div>"
    f"</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# ── Two-sided ledger ──────────────────────────────────────────────────────────
col_research, col_patent = st.columns(2, gap="large")

# ── RESEARCH SIDE ─────────────────────────────────────────────────────────────
with col_research:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:{_hex_rgba(org_color, 0.6)};"
        f"margin-bottom:0.75rem;'>Research output</div>",
        unsafe_allow_html=True,
    )

    if not has_papers:
        st.caption("No resolved research papers found for this organisation.")
    else:
        # Papers by family
        pf_ids    = paper_by_family["family_id"].to_list()
        pf_names  = paper_by_family["family_name"].to_list()
        pf_counts = [int(v) for v in paper_by_family["n_papers"].to_list()]
        pf_colors = [FAMILY_COLORS.get(fid, "#888888") for fid in pf_ids]

        pairs = sorted(zip(pf_counts, pf_names, pf_colors, strict=False))
        pv, pn, pc = map(list, zip(*pairs, strict=False))

        fig_pf = go.Figure(go.Bar(
            x=pv, y=pn, orientation="h",
            marker_color=pc,
            text=[f"{v:,}" for v in pv],
            textposition="outside", cliponaxis=False,
        ))
        fig_pf.update_layout(
            title=dict(text="Research papers by family", font=dict(size=11, color="#888888"), x=0),
            height=max(160, 40 * len(pairs) + 40),
            margin=dict(l=0, r=60, t=28, b=5),
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            font=dict(size=11, color="#111111"),
            xaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, autorange="reversed"),
            showlegend=False,
        )
        st.plotly_chart(fig_pf, use_container_width=True, config={"displayModeBar": False})

        # Top research clusters
        if len(top_res_clusters) > 0:
            st.markdown(
                "<div style='font-size:11px;font-weight:600;color:#555555;"
                "margin:0.5rem 0 4px;'>Top research clusters</div>",
                unsafe_allow_html=True,
            )
            _cluster_list(top_res_clusters.to_dicts(), _hex_rgba(org_color, 0.55))

        # Papers over time
        if len(paper_years) > 0:
            yrs = paper_years["year"].to_list()
            nps = paper_years["n_papers"].to_list()
            fig_py = go.Figure(go.Bar(
                x=yrs, y=nps,
                marker_color=_hex_rgba(org_color, 0.45),
                text=[str(v) for v in nps], textposition="outside", cliponaxis=False,
            ))
            fig_py.update_layout(
                title=dict(text="Papers per year", font=dict(size=11, color="#888888"), x=0),
                height=170,
                margin=dict(l=0, r=10, t=28, b=5),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                font=dict(size=11, color="#111111"),
                xaxis=dict(showgrid=False, zeroline=False, dtick=2),
                yaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False),
                showlegend=False,
            )
            st.plotly_chart(fig_py, use_container_width=True, config={"displayModeBar": False})

        # Flagship paper
        if len(flagship_paper) > 0:
            fp = flagship_paper.row(0, named=True)
            pub_yr = fp["publication_date"].year if fp["publication_date"] else "—"
            abstract = (fp["abstract"] or "")[:220]
            if len(fp["abstract"] or "") > 220:
                abstract += "…"
            st.markdown(
                f"<div style='border:1px solid #e6e6e6;"
                f"border-left:4px solid {_hex_rgba(org_color, 0.45)};"
                f"border-radius:6px;padding:12px 14px;margin-top:0.5rem;'>"
                f"<div style='font-size:9px;font-weight:700;letter-spacing:.07em;"
                f"text-transform:uppercase;color:#888888;margin-bottom:4px;'>"
                f"Most-cited paper · {fp['n_citing_patents']:,} patents cite this</div>"
                f"<div style='font-size:12px;font-weight:600;color:#111111;"
                f"line-height:1.4;margin-bottom:4px;'>{fp['title']}</div>"
                f"<div style='font-size:11px;color:#888888;margin-bottom:6px;'>"
                f"Published {pub_yr}</div>"
                f"<div style='font-size:11px;color:#555555;line-height:1.5;'>"
                f"{abstract}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

# ── PATENT SIDE ───────────────────────────────────────────────────────────────
with col_patent:
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:{org_color};"
        f"margin-bottom:0.75rem;'>Patent output</div>",
        unsafe_allow_html=True,
    )

    if not has_patents:
        st.caption("No resolved US patents found for this organisation.")
    else:
        # Patents by family
        fam_ids   = output_by_family["family_id"].to_list()
        fam_names = output_by_family["family_name"].to_list()
        n_pats    = [int(v) for v in output_by_family["n_patents"].to_list()]
        bar_colors = [FAMILY_COLORS.get(fid, "#888888") for fid in fam_ids]

        pairs = sorted(zip(n_pats, fam_names, bar_colors, strict=False))
        pv, pn, pc = map(list, zip(*pairs, strict=False))

        fig_fam = go.Figure(go.Bar(
            x=pv, y=pn, orientation="h",
            marker_color=pc,
            text=[f"{v:,}" for v in pv],
            textposition="outside", cliponaxis=False,
        ))
        fig_fam.update_layout(
            title=dict(text="US patents by family", font=dict(size=11, color="#888888"), x=0),
            height=max(160, 40 * len(pairs) + 40),
            margin=dict(l=0, r=60, t=28, b=5),
            plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
            font=dict(size=11, color="#111111"),
            xaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, autorange="reversed"),
            showlegend=False,
        )
        st.plotly_chart(fig_fam, use_container_width=True, config={"displayModeBar": False})

        # Top patent clusters
        if len(top_pat_clusters) > 0:
            st.markdown(
                "<div style='font-size:11px;font-weight:600;color:#555555;"
                "margin:0.5rem 0 4px;'>Top patent clusters</div>",
                unsafe_allow_html=True,
            )
            _cluster_list(top_pat_clusters.to_dicts(), org_color)

        # Filing years
        if len(filing_years) > 0:
            yrs = filing_years["year"].to_list()
            nps = [int(v) for v in filing_years["n_patents"].to_list()]
            fig_fy = go.Figure(go.Bar(
                x=yrs, y=nps,
                marker_color=org_color,
                text=[str(v) for v in nps], textposition="outside", cliponaxis=False,
            ))
            fig_fy.update_layout(
                title=dict(text="US patent filings per year", font=dict(size=11, color="#888888"), x=0),
                height=170,
                margin=dict(l=0, r=10, t=28, b=5),
                plot_bgcolor="#ffffff", paper_bgcolor="#ffffff",
                font=dict(size=11, color="#111111"),
                xaxis=dict(showgrid=False, zeroline=False, dtick=2),
                yaxis=dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False),
                showlegend=False,
            )
            st.plotly_chart(fig_fy, use_container_width=True, config={"displayModeBar": False})
            st.markdown(
                "<span style='font-size:10px;color:#888888;'>"
                "Counts after 2019 are understated — recent filings take 2–4 years to be granted."
                "</span>",
                unsafe_allow_html=True,
            )

        # Flagship patent
        if len(flagship_patent) > 0:
            fpt = flagship_patent.row(0, named=True)
            filing_yr = fpt["filing_date"].year if fpt["filing_date"] else "—"
            st.markdown(
                f"<div style='border:1px solid #e6e6e6;"
                f"border-left:4px solid {org_color};"
                f"border-radius:6px;padding:12px 14px;margin-top:0.5rem;'>"
                f"<div style='font-size:9px;font-weight:700;letter-spacing:.07em;"
                f"text-transform:uppercase;color:#888888;margin-bottom:4px;'>"
                f"Most NPL-citing patent · cites {fpt['n_papers_cited']:,} papers</div>"
                f"<div style='font-size:12px;font-weight:600;color:#111111;"
                f"line-height:1.4;margin-bottom:4px;'>{fpt['title']}</div>"
                f"<div style='font-size:11px;color:#888888;'>"
                f"Filed {filing_yr} · US{fpt['patent_id']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

# ── Citation bridge ───────────────────────────────────────────────────────────
has_intake    = len(intake)    > 0
has_influence = len(influence) > 0

if has_intake or has_influence:
    st.markdown("<div style='margin-top:2rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:#888888;margin-bottom:4px;'>"
        f"The citation bridge — via NPL links</div>"
        f"<div style='font-size:12px;color:#888888;margin-bottom:1rem;'>"
        f"Who feeds this org's patents with research, and whose patents build on its work."
        f"</div>",
        unsafe_allow_html=True,
    )

    col_intake, col_bridge, col_influence = st.columns([5, 1, 5], gap="small")

    with col_intake:
        if has_intake:
            intake_rows = intake.to_dicts()
            i_names  = [r["paper_org_name"] for r in intake_rows]
            i_counts = [int(r["n_papers_cited"]) for r in intake_rows]
            i_ids    = [r["paper_org_id"] for r in intake_rows]
            pairs_i = sorted(zip(i_counts, i_names, i_ids, strict=False))
            iv, inn, iid = map(list, zip(*pairs_i, strict=False))
            colors_i = [
                _hex_rgba(org_color, 0.45) if x != selected_org_id else "#cccccc"
                for x in iid
            ]
            fig_i = _bar_chart(
                inn, iv, colors_i,  # type: ignore[arg-type]
                "Research it draws on (papers cited in its patents)",
                height=max(180, 32 * len(iv) + 40),
            )
            fig_i.update_traces(marker_color=colors_i)
            st.plotly_chart(fig_i, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No NPL-linked intake data found.")

    with col_bridge:
        st.markdown(
            f"<div style='display:flex;flex-direction:column;"
            f"align-items:center;justify-content:center;height:100%;'>"
            f"<div style='font-size:20px;color:{org_color};'>→</div>"
            f"<div style='font-size:9px;font-weight:700;letter-spacing:.06em;"
            f"text-transform:uppercase;color:#aaaaaa;text-align:center;"
            f"writing-mode:vertical-lr;margin:8px 0;'>{org_name[:16]}</div>"
            f"<div style='font-size:20px;color:{org_color};'>→</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with col_influence:
        if has_influence:
            inf_rows = influence.to_dicts()
            inf_names  = [r["patenter_name"] for r in inf_rows]
            inf_counts = [int(r["n_patents"]) for r in inf_rows]
            pairs_inf = sorted(zip(inf_counts, inf_names, strict=False))
            infv, infn = map(list, zip(*pairs_inf, strict=False))
            fig_inf = _bar_chart(
                infn, infv, org_color,
                "Who patents this org's research (patents citing its papers)",
                height=max(180, 32 * len(infv) + 40),
            )
            st.plotly_chart(fig_inf, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No NPL-linked influence data found.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(
    "<span style='font-size:11px;color:#888888;'>"
    "<strong>Data quality:</strong> "
    "Org matches use the crosswalk (seed → ROR → fuzzy). "
    "Confidence badge reflects the match tier. "
    "Intake and influence panels are based on NPL citation links only "
    "(high/medium-confidence links). "
    "US patents only (PatentsView / USPTO). "
    "Papers from OpenAlex (2012–2025). "
    "Balance bar counts resolved documents only (unresolved orgs excluded)."
    "</span>",
    unsafe_allow_html=True,
)
