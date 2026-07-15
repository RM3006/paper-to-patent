# pyright: basic
"""
The Chips Behind AI — front door (Surface 1).

Five technology family rows (horizontal, full-width) each showing patent share,
paper / patent volumes, top patenters, top researchers, and a family-colored
Explore button. A guided tour (5 stops) narrates the key contrasts.
Source marts: mart_family, mart_competitive, seed_cluster_family.
"""

from __future__ import annotations

import streamlit as st

from data import load_family_scorecard, load_family_top_orgs, load_unattributed_counts
from render import FAMILY_COLORS, embed_url, render_nav, render_tour_banner

st.set_page_config(
    page_title="The Chips Behind AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_FONT = '"Space Grotesk", -apple-system, system-ui, sans-serif'

# Document-level family IDs, in family_sort_order (mart_family.family_sort_order).
_FAMILY_IDS = ["euv", "lasers", "si_photonics", "neuromorphic", "in_memory"]

_FAMILY_DESC: dict[str, str] = {
    "euv": (
        "Extreme-UV optics that print transistors smaller than a virus: "
        "the bottleneck of the entire chip industry."
    ),
    "lasers": (
        "On-chip lasers that generate the light signals for high-speed "
        "optical data transmission."
    ),
    "si_photonics": (
        "Silicon waveguides and modulators that route light-encoded data "
        "across a chip, cutting latency and power inside AI data centres."
    ),
    "neuromorphic": (
        "Chips that compute the way neurons do: spiking, event-driven "
        "circuits trading raw clock speed for energy efficiency."
    ),
    "in_memory": (
        "Memory that computes where data lives: resistive and phase-change "
        "cells that skip the slow trip to a separate processor."
    ),
}

# ── CSS — shared chrome ───────────────────────────────────────────────────────────
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&display=swap');

.stApp { background: #ffffff; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
hr { border-color: #e6e6e6 !important; }

[data-testid="stDecoration"] { display: none; }
[data-testid="stHeader"]     { background: transparent; }

[data-testid="stSidebarNav"] a span,
[data-testid="stSidebarNav"] a p  { color: #111111 !important; }
[data-testid="stSidebarNav"] a:hover { background: #f5f5f5; }

/* .card / .card-tag / .card-stat / .family-explore come from render.py's
   render_nav(), shared by every page. */

/* Family row: same .card shell, fixed-height flex layout, accent threaded via --accent
   (set inline per family) instead of repeating the family color across every child.
   Selector is ".card.card--family" (not just ".card--family") so these properties
   always beat .card's, regardless of which <style> block happens to load last --
   .card comes from render.py's render_nav(), .card--family from here; their relative
   order is not something this file controls. */
.card.card--family {
    height: 144px;
    box-sizing: border-box;
    padding: 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    border-color: var(--accent-border, #e6e6e6);
}
.card.card--family.is-highlighted {
    box-shadow: 0 0 0 4px var(--accent-glow, transparent);
}
.card--family .card-title    { color: var(--accent); }
.card--family .card-tile-pct { background: #ffffff; }
/* .card-stat and .family-explore already resolve var(--accent) generically (render.py). */

[data-testid="stVerticalBlockBorderWrapper"] {
    background: #ffffff;
    border: 1px solid #e6e6e6 !important;
    border-radius: 10px;
    box-shadow: none;
}

[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e6e6e6;
}

/* Default button: borderless nav link. */
[data-testid="stButton"] button {
    justify-content: flex-start;
    border: none;
    font-weight: 600;
    color: #111111;
    background: transparent;
    padding: 0;
}
[data-testid="stButton"] button:hover {
    color: #000000;
    text-decoration: underline;
    background: transparent;
}

/* Primary: solid ink (overridden per family for Explore buttons). */
[data-testid="stButton"] button[kind="primary"] {
    justify-content: center;
    padding: 0.5rem 1.4rem;
    border: 1px solid #111111;
    border-radius: 8px;
    font-weight: 700;
    color: #ffffff;
    background: #111111;
    text-decoration: none;
}
[data-testid="stButton"] button[kind="primary"]:hover {
    color: #ffffff;
    background: #333333;
    border-color: #333333;
    text-decoration: none;
}

/* Secondary: outlined. */
[data-testid="stButton"] button[kind="secondary"] {
    justify-content: center;
    padding: 0.5rem 1.4rem;
    border: 1px solid #111111;
    border-radius: 8px;
    font-weight: 700;
    color: #111111;
    background: #ffffff;
    text-decoration: none;
}
[data-testid="stButton"] button[kind="secondary"]:hover {
    background: #f5f5f5;
    text-decoration: none;
}

</style>
"""


def _html_family_card(
    row: dict,
    top_orgs: dict[str, list[str]],
    highlighted: bool,
) -> str:
    """Self-contained HTML card for one technology family."""
    fid = row["family_id"]
    color = FAMILY_COLORS.get(fid, "#888888")
    pct = (row["patent_share"] or 0.0) * 100
    lag = row["median_lag_years_weighted"]
    lag_str = f"{lag:.1f} yr" if lag is not None else "—"
    n_links = row["total_npl_links"] or 0
    lag_tooltip = (
        f"Based on {n_links:,} NPL-linked citations"
        if lag is not None
        else "Fewer than 20 NPL-linked citations, not reportable"
    )
    card_cls = "card card--family is-highlighted" if highlighted else "card card--family"
    accent_vars = f"--accent:{color};--accent-border:{color}55;--accent-glow:{color}44;"

    pat_html = _org_rows(top_orgs.get("patent", []), color)
    res_html = _org_rows(top_orgs.get("paper", []), color)
    desc = _FAMILY_DESC.get(fid, "")

    return (
        f"<div class='{card_cls}' style='{accent_vars}'>"
        f"<div style='flex:0 0 400px;display:flex;flex-direction:column;"
        f"justify-content:center;'>"
        f"<div class='card-title' style='font-family:{_FONT};font-size:16px;font-weight:700;"
        f"letter-spacing:.07em;text-transform:uppercase;margin-bottom:6px;'>{row['family_name']}</div>"
        f"<div style='font-size:13px;color:#555555;line-height:1.5;'>{desc}</div>"
        f"</div>"
        f"<div style='flex-shrink:0;display:grid;"
        f"grid-template-columns:104px 104px;grid-template-rows:48px 48px;gap:8px;'>"
        f"<div class='card-tile-pct' style='border-radius:10px;"
        f"display:flex;flex-direction:column;align-items:center;justify-content:center;'>"
        f"<div style='font-family:{_FONT};font-size:18px;font-weight:800;"
        f"color:{color};line-height:1;'>{pct:.0f}%</div>"
        f"<div style='font-size:12px;color:#707070;margin-top:3px;"
        f"white-space:nowrap;'>patent share</div>"
        f"</div>"
        f"<div style='display:flex;flex-direction:column;"
        f"align-items:center;justify-content:center;'>"
        f"<div class='card-stat' style='font-family:{_FONT};font-size:18px;font-weight:700;"
        f"line-height:1;'>{row['n_patents']:,}</div>"
        f"<div style='font-size:12px;color:#707070;margin-top:3px;white-space:nowrap;'>"
        f"granted US patents</div>"
        f"</div>"
        f"<div title='{lag_tooltip}' style='display:flex;flex-direction:column;"
        f"align-items:center;justify-content:center;'>"
        f"<div class='card-stat' style='font-family:{_FONT};font-size:18px;font-weight:700;"
        f"line-height:1;'>{lag_str}</div>"
        f"<div style='font-size:12px;color:#707070;margin-top:3px;white-space:nowrap;'>"
        f"citation lag</div>"
        f"</div>"
        f"<div style='display:flex;flex-direction:column;"
        f"align-items:center;justify-content:center;'>"
        f"<div class='card-stat' style='font-family:{_FONT};font-size:18px;font-weight:700;"
        f"line-height:1;'>{row['n_papers']:,}</div>"
        f"<div style='font-size:12px;color:#707070;margin-top:3px;white-space:nowrap;'>papers</div>"
        f"</div>"
        f"</div>"
        f"<div style='flex-shrink:0;display:flex;gap:24px;align-self:stretch;'>"
        f"<div style='width:188px;min-width:0;overflow:hidden;"
        f"display:flex;flex-direction:column;justify-content:space-between;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
        f"text-transform:uppercase;color:#707070;'>Top patenters</div>"
        f"{pat_html}</div>"
        f"<div style='width:188px;min-width:0;overflow:hidden;"
        f"display:flex;flex-direction:column;justify-content:space-between;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
        f"text-transform:uppercase;color:#707070;'>Top researchers</div>"
        f"{res_html}</div>"
        f"</div>"
        f"<div style='flex:0 0 auto;display:flex;align-items:center;padding:0 32px 0 16px;'>"
        f"<a href='{embed_url(f'/Family?family={fid}')}' target='_self'"
        f" class='family-explore'>Explore family →</a>"
        f"</div>"
        f"</div>"
    )


# ── Org ranked list (top 3) ───────────────────────────────────────────────────────
def _org_rows(names: list[str], color: str) -> str:
    if not names:
        return "<div style='font-size:12px;color:#aaaaaa;'>—</div>"
    return "".join(
        f'<div style="margin-bottom:4px;font-size:13px;color:#555555;line-height:1.3;'
        f'overflow:hidden;white-space:nowrap;text-overflow:ellipsis;">'
        f'{name[:30] + "…" if len(name) > 30 else name}</div>'
        for name in names
    )


# ── Main ──────────────────────────────────────────────────────────────────────────
def main() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    render_nav("Overview")
    render_tour_banner(0)

    scorecard = load_family_scorecard()
    rows = scorecard.sort("patent_share", descending=True, nulls_last=True).to_dicts()

    top_map: dict[str, dict[str, list[str]]] = {}
    for r in load_family_top_orgs().to_dicts():
        top_map.setdefault(r["family_id"], {"patent": [], "paper": []})[r["side"]].append(
            r["canonical_name"]
        )

    st.markdown(
        "<div style='font-size:14px;color:#555555;line-height:1.65;margin-bottom:1.4rem;'>"
        "These are the 5 technology families powering the next generation of AI hardware: "
        "from the extreme-ultraviolet optics that print the world's smallest transistors to the "
        "brain-inspired chips that process data the way neurons do. "
        "Each row shows what share of all US patenting activity in this space the family "
        "represents, who holds that IP, and how fast ideas travel: "
        "the <strong>citation lag</strong> is the gap between a paper's publication date "
        "and the filing date of a US patent that cites it."
        "</div>",
        unsafe_allow_html=True,
    )

    for row in rows:
        top_orgs = top_map.get(row["family_id"], {"patent": [], "paper": []})
        st.markdown(
            _html_family_card(row, top_orgs, False),
            unsafe_allow_html=True,
        )

    unattributed = load_unattributed_counts()
    st.markdown(
        "<div style='border-top:1px solid #e6e6e6;margin-top:2rem;padding-top:1rem;"
        "font-size:11px;color:#707070;line-height:1.6;'>"
        "<strong>Scope:</strong> Granted US patents only (PatentsView / USPTO, filing dates "
        "2014–2025). US filings are roughly 1 in 6 (~16%) of the world's patent applications "
        "(WIPO, World Intellectual Property Indicators 2025). Treat concentration and "
        "IP-capture figures here as a US-filing view, not a global one. "
        "In-scope research papers from OpenAlex (2012–2025, English, matched to EUV, silicon "
        "photonics, lasers, neuromorphic, and in-memory compute topics). "
        f"{unattributed['unattributed_patents']:,} granted US patents and "
        f"{unattributed['unattributed_papers']:,} research papers are in scope but aren't shown "
        "in any family card above. Their primary classification falls outside the five family "
        "definitions (patents that entered scope via a secondary CPC code) or, for papers, an "
        "unresolved neuromorphic/in-memory keyword split. They remain part of the full corpus; "
        "we don't guess which family they belong to. "
        "Citation links are non-patent-literature (NPL) references from USPTO filings: the "
        "gold-standard Marx &amp; Fuegi &lsquo;Reliance on Science&rsquo; dataset where it "
        "covers a patent, and our own DOI + fuzzy-title matcher (recall measured against that "
        "gold set) for recent grants beyond its vintage; link counts are a lower bound. "
        "Lag = paper publication date → citing patent filing date; never grant date. "
        "Patent counts after 2019 understate activity due to grant-processing delay. "
        "This is not causal inference; NPL citations record reference, not derivation."
        "</div>",
        unsafe_allow_html=True,
    )


main()
