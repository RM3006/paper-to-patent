"""
The Chips Behind AI — front door (Surface 1).

Five technology family rows (horizontal, full-width) each showing patent share,
paper / patent volumes, top patenters, top researchers, and a family-colored
Explore button. A guided tour (5 stops) narrates the key contrasts.
Source marts: mart_family, mart_competitive, seed_cluster_family.
"""

from __future__ import annotations

import streamlit as st
from render import FAMILY_COLORS, render_nav, render_tour_banner

from data import load_family_scorecard, load_family_top_orgs

st.set_page_config(
    page_title="The Chips Behind AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_FONT = '"Space Grotesk", -apple-system, system-ui, sans-serif'

# Family IDs in display order (excludes adjacent / noise).
_FAMILY_IDS = ["euv", "si_photonics", "lasers", "neuromorphic", "in_memory"]

_FAMILY_DESC: dict[str, str] = {
    "euv": "Extreme-UV optics that print transistors smaller than a virus — the bottleneck of the entire chip industry.",
    "si_photonics": "Moving data as light pulses through silicon, replacing copper wires to cut latency and power inside AI servers.",
    "lasers": "Coherent light sources integrated at chip scale, enabling the transceivers that hold data-centre networks together.",
    "neuromorphic": "Brain-inspired chips that process data the way neurons fire, trading raw clock speed for dramatic energy efficiency.",
    "in_memory": "Processing data where it is stored so the chip never has to fetch it across slow memory buses.",
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

.card {
    background: #ffffff;
    border: 1px solid #e6e6e6;
    border-radius: 10px;
    padding: 20px 22px;
    margin-bottom: 4px;
}

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

.family-explore {
    font-size: 14px;
    font-weight: 600;
    text-decoration: underline;
    text-underline-offset: 3px;
    transition: opacity 0.18s ease;
    white-space: nowrap;
}
.family-explore:hover { opacity: 0.55; }

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
    padding: 0.5rem 1.3rem;
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
    padding: 0.5rem 1.3rem;
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
    glow = f"box-shadow:0 0 0 4px {color}44;" if highlighted else ""

    pat_html = _org_rows(top_orgs.get("patent", []), color)
    res_html = _org_rows(top_orgs.get("paper", []), color)
    desc = _FAMILY_DESC.get(fid, "")

    return (
        f"<div style='height:144px;box-sizing:border-box;border:1px solid #e6e6e6;"
        f"border-radius:10px;padding:16px;display:flex;align-items:center;"
        f"justify-content:space-between;"
        f"background:#ffffff;margin-bottom:0.75rem;{glow}'>"
        f"<div style='flex:0 0 400px;display:flex;flex-direction:column;"
        f"justify-content:center;'>"
        f"<div style='font-family:{_FONT};font-size:16px;font-weight:700;"
        f"letter-spacing:.07em;text-transform:uppercase;color:{color};"
        f"margin-bottom:6px;'>{row['family_name']}</div>"
        f"<div style='font-size:12px;color:#888888;line-height:1.5;'>{desc}</div>"
        f"</div>"
        f"<div style='flex-shrink:0;display:grid;"
        f"grid-template-columns:104px 104px;grid-template-rows:48px 48px;gap:8px;'>"
        f"<div style='background:{color};border-radius:10px;"
        f"display:flex;flex-direction:column;align-items:center;justify-content:center;'>"
        f"<div style='font-family:{_FONT};font-size:18px;font-weight:800;"
        f"color:#ffffff;line-height:1;'>{pct:.0f}%</div>"
        f"<div style='font-size:9px;color:rgba(255,255,255,0.75);margin-top:3px;white-space:nowrap;'>patent share</div>"
        f"</div>"
        f"<div style='display:flex;flex-direction:column;align-items:center;justify-content:center;'>"
        f"<div style='font-family:{_FONT};font-size:18px;font-weight:700;"
        f"color:{color};line-height:1;'>{row['n_patents']:,}</div>"
        f"<div style='font-size:9px;color:#888888;margin-top:3px;white-space:nowrap;'>granted US patents</div>"
        f"</div>"
        f"<div style='display:flex;flex-direction:column;align-items:center;justify-content:center;'>"
        f"<div style='font-family:{_FONT};font-size:18px;font-weight:700;"
        f"color:{color};line-height:1;'>{lag_str}</div>"
        f"<div style='font-size:9px;color:#888888;margin-top:3px;white-space:nowrap;'>citation lag</div>"
        f"</div>"
        f"<div style='display:flex;flex-direction:column;align-items:center;justify-content:center;'>"
        f"<div style='font-family:{_FONT};font-size:18px;font-weight:700;"
        f"color:{color};line-height:1;'>{row['n_papers']:,}</div>"
        f"<div style='font-size:9px;color:#888888;margin-top:3px;white-space:nowrap;'>papers</div>"
        f"</div>"
        f"</div>"
        f"<div style='flex-shrink:0;display:flex;gap:24px;align-self:stretch;'>"
        f"<div style='width:188px;min-width:0;overflow:hidden;"
        f"display:flex;flex-direction:column;justify-content:space-between;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
        f"text-transform:uppercase;color:#888888;'>Top patenters</div>"
        f"{pat_html}</div>"
        f"<div style='width:188px;min-width:0;overflow:hidden;"
        f"display:flex;flex-direction:column;justify-content:space-between;'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
        f"text-transform:uppercase;color:#888888;'>Top researchers</div>"
        f"{res_html}</div>"
        f"</div>"
        f"<div style='flex:0 0 auto;display:flex;align-items:center;padding:0 32px 0 16px;'>"
        f"<a href='/Family?family={fid}' target='_self'"
        f" class='family-explore' style='color:{color};'>Explore family →</a>"
        f"</div>"
        f"</div>"
    )


# ── Org ranked list (top 3) ───────────────────────────────────────────────────────
def _org_rows(names: list[str], color: str) -> str:
    if not names:
        return "<div style='font-size:12px;color:#aaaaaa;'>—</div>"
    return "".join(
        f'<div style="margin-bottom:4px;font-size:12.5px;color:#111111;line-height:1.3;'
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
    rows = (
        scorecard.filter(scorecard["family_id"] != "adjacent")
        .sort("patent_share", descending=True, nulls_last=True)
        .to_dicts()
    )

    top_map: dict[str, dict[str, list[str]]] = {}
    for r in load_family_top_orgs().to_dicts():
        top_map.setdefault(r["family_id"], {"patent": [], "paper": []})[r["side"]].append(
            r["canonical_name"]
        )

    st.markdown(
        "<div style='font-size:14px;color:#555555;line-height:1.65;margin-bottom:1.4rem;'>"
        "These are the 5 main technology families powering the next generation of AI hardware — "
        "from the extreme-ultraviolet optics that print the world's smallest transistors to the "
        "brain-inspired chips that process data the way neurons do. "
        "Each row shows how much of the global research has been captured as US patents, "
        "who holds that IP, and how fast ideas travel: "
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

    st.markdown(
        "<div style='border-top:1px solid #e6e6e6;margin-top:2rem;padding-top:1rem;"
        "font-size:11px;color:#aaaaaa;line-height:1.6;'>"
        "<strong>Scope:</strong> Granted US patents only (PatentsView / USPTO, filing dates 2014–2025). "
        "In-scope research papers from OpenAlex (2012–2025, English, matched to EUV, silicon photonics, lasers, neuromorphic, and in-memory compute topics). "
        "Citation links are non-patent-literature (NPL) references from USPTO filings. "
        "Lag = paper publication date → citing patent filing date; never grant date. "
        "Patent counts after 2019 understate activity due to grant-processing delay. "
        "This is not causal inference — NPL citations record reference, not derivation."
        "</div>",
        unsafe_allow_html=True,
    )


main()
