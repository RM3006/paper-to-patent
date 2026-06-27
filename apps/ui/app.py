"""
The Chips Behind AI — front door (Surface 1).

Five technology family rows (horizontal, full-width) each showing patent share,
paper / patent volumes, top patenters, top researchers, and a family-colored
Explore button. A guided tour (5 stops) narrates the key contrasts.
Source marts: mart_family, mart_competitive, seed_cluster_family.
"""

from __future__ import annotations

import streamlit as st
from render import FAMILY_COLORS
from tour import TOUR_STEPS, TourStep, is_first_step, is_last_step, progress_label

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

# ── CSS — shared chrome ───────────────────────────────────────────────────────────
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700;800&display=swap');

.stApp { background: #ffffff; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; }
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

/* Tour card. */
.st-key-tour_card {
    background: #fdf6e3;
    border: 1px solid #ecdfb8;
    border-radius: 10px;
    padding: 4px 22px 18px;
    margin-bottom: 1.2rem;
}

/* Tour nav. */
.st-key-tour_nav {
    display: flex;
    flex-direction: row;
    justify-content: flex-end;
    align-items: center;
    gap: 0.5rem;
    margin-top: 10px;
}
.st-key-tour_nav [data-testid="stButton"] button,
.st-key-tour_nav [data-testid="stButton"] button[kind="primary"],
.st-key-tour_nav [data-testid="stButton"] button[kind="secondary"] {
    padding: 0.1rem 0.3rem;
    font-size: 0.82rem;
    font-weight: 600;
    border: none;
    border-radius: 0;
    text-decoration: underline;
    color: #8a6d1f;
    background: transparent;
}
.st-key-tour_nav [data-testid="stButton"] button:hover,
.st-key-tour_nav [data-testid="stButton"] button[kind="primary"]:hover,
.st-key-tour_nav [data-testid="stButton"] button[kind="secondary"]:hover {
    color: #a3821f;
    background: transparent;
    text-decoration: underline;
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
    bar_w = min(pct, 100)
    lag = row["median_lag_years_weighted"]
    lag_str = f"{lag:.1f} yr" if lag is not None else "—"
    glow = f"box-shadow:0 0 0 4px {color}44;" if highlighted else ""

    pat_html = _org_rows(top_orgs.get("patent", []), color)
    res_html = _org_rows(top_orgs.get("paper", []), color)

    # Heroicons-style arrow-right: single <path> so shaft and arrowhead are one
    # continuous stroke — no disconnected parts.
    # viewBox 24×24, rendered at 88×88px ≈ 80% of the ~110px card height.
    # stroke-width="2" → effective ~7px at render size: thick and clean.
    arrow = (
        f"<svg viewBox='0 0 24 24' width='88' height='88' fill='none' "
        f"xmlns='http://www.w3.org/2000/svg'>"
        f"<path d='M4 12 H20 M10 2 L20 12 L10 22' "
        f"stroke='{color}' stroke-width='2' "
        f"stroke-linecap='round' stroke-linejoin='round'/>"
        f"</svg>"
    )

    col = "padding-right:16px;"
    return (
        f"<div style='border:1px solid #e6e6e6;border-radius:10px;"
        f"padding:1rem 1.25rem;display:flex;align-items:center;"
        f"background:#ffffff;margin-bottom:0.75rem;{glow}'>"
        # ── Family name + lag ─────────────────────────────────────────────────
        f"<div style='flex:2.2;min-width:0;{col}'>"
        f"<div style='font-family:{_FONT};font-size:12px;font-weight:700;"
        f"letter-spacing:.07em;text-transform:uppercase;color:{color};"
        f"margin-bottom:5px;'>{row['family_name']}</div>"
        f"<div style='font-size:12px;color:#888888;'>{lag_str} median citation lag</div>"
        f"</div>"
        # ── Patent share % ────────────────────────────────────────────────────
        f"<div style='flex:1.4;{col}'>"
        f"<div style='font-family:{_FONT};font-size:32px;font-weight:800;"
        f"color:{color};line-height:1;'>{pct:.0f}%</div>"
        f"<div style='font-size:11px;color:#888888;margin-top:2px;'>patent share</div>"
        f"<div style='background:#e6e6e6;border-radius:2px;height:3px;margin-top:7px;'>"
        f"<div style='background:{color};width:{bar_w:.1f}%;height:3px;border-radius:2px;'>"
        f"</div></div></div>"
        # ── Paper / patent counts ─────────────────────────────────────────────
        f"<div style='flex:1.4;{col}'>"
        f"<div style='margin-bottom:8px;'>"
        f"<div style='font-family:{_FONT};font-size:20px;font-weight:700;"
        f"color:#111111;line-height:1;'>{row['n_papers']:,}</div>"
        f"<div style='font-size:10px;color:#888888;margin-top:2px;'>papers</div></div>"
        f"<div style='font-family:{_FONT};font-size:20px;font-weight:700;"
        f"color:#111111;line-height:1;'>{row['n_patents']:,}</div>"
        f"<div style='font-size:10px;color:#888888;margin-top:2px;'>US patents</div>"
        f"</div>"
        # ── Top patenters ─────────────────────────────────────────────────────
        f"<div style='flex:2.4;{col}'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
        f"text-transform:uppercase;color:#888888;margin-bottom:7px;'>Top patenters</div>"
        f"{pat_html}</div>"
        # ── Top researchers ───────────────────────────────────────────────────
        f"<div style='flex:2.2;{col}'>"
        f"<div style='font-size:10px;font-weight:700;letter-spacing:.07em;"
        f"text-transform:uppercase;color:#888888;margin-bottom:7px;'>Top researchers</div>"
        f"{res_html}</div>"
        # ── Arrow — thick SVG right arrow in family color ────────────────────
        f"<div style='flex:1.8;display:flex;align-items:center;justify-content:center;'>"
        f"<a href='/Family?family={fid}' target='_self'"
        f" style='display:flex;align-items:center;text-decoration:none;'>"
        f"{arrow}</a>"
        f"</div>"
        f"</div>"
    )


# ── Tour helpers ──────────────────────────────────────────────────────────────────
def _start_tour() -> None:
    st.session_state.tour_step = 0
    st.rerun()


def _render_tour_button() -> None:
    if st.session_state.get("tour_step") is None:
        if st.button("Take the 90-second tour", key="tour_start", type="primary"):
            _start_tour()


def _render_tour_banner(step: TourStep, idx: int) -> None:
    with st.container(key="tour_card"):
        col_label, col_nav = st.columns([3, 1], vertical_alignment="center")
        with col_label:
            st.markdown(
                f"<span style='color:#888888;font-size:0.72rem;font-weight:700;"
                f"text-transform:uppercase;letter-spacing:0.1em;'>"
                f"Guided tour · {progress_label(idx)}</span>",
                unsafe_allow_html=True,
            )
        with col_nav, st.container(key="tour_nav"):
            if not is_first_step(idx):
                if st.button("← Back", key="tour_back", type="secondary"):
                    st.session_state.tour_step = idx - 1
                    st.rerun()
            finish_label = "Finish →" if is_last_step(idx) else "Next →"
            if st.button(finish_label, key="tour_next", type="primary"):
                if is_last_step(idx):
                    st.session_state.tour_step = None
                else:
                    st.session_state.tour_step = idx + 1
                st.rerun()
            if st.button("Exit tour", key="tour_exit", type="secondary"):
                st.session_state.tour_step = None
                st.rerun()

        st.markdown(
            f"<div style='font-family:{_FONT};font-weight:700;font-size:1rem;"
            f"color:#111111;margin-bottom:6px;margin-top:10px;'>{step.title}</div>"
            f"<div style='color:#111111;font-size:0.9rem;line-height:1.6;'>"
            f"{step.narration}</div>",
            unsafe_allow_html=True,
        )


# ── Org ranked list (top 3) ───────────────────────────────────────────────────────
def _org_rows(names: list[str], color: str) -> str:
    if not names:
        return "<div style='font-size:12px;color:#aaaaaa;'>—</div>"
    return "".join(
        f'<div style="display:flex;gap:6px;align-items:baseline;margin-bottom:4px;">'
        f'<span style="font-family:{_FONT};font-size:10px;font-weight:700;'
        f'color:{color};min-width:12px;">{i}</span>'
        f'<span style="font-size:12.5px;color:#111111;line-height:1.3;">'
        f"{name[:28]}</span></div>"
        for i, name in enumerate(names, start=1)
    )


# ── Main ──────────────────────────────────────────────────────────────────────────
def main() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Hero header ──────────────────────────────────────────────────────────────
    col_title, col_tour = st.columns([5, 2], vertical_alignment="center")
    with col_title:
        st.markdown(
            f"<div style='font-family:{_FONT};font-size:72px;font-weight:bold;"
            "color:#111111;letter-spacing:-0.02em;line-height:1.05;'>"
            "The Chips Behind AI</div>"
            "<div style='color:#888888;font-size:0.9rem;'>"
            "Tracing global semiconductor research papers to US patents "
            "across 5 technology families."
            "</div>",
            unsafe_allow_html=True,
        )
    with col_tour:
        _render_tour_button()

    st.markdown(
        "<div style='border-bottom:1px solid #e6e6e6;margin-bottom:1.1rem;'></div>",
        unsafe_allow_html=True,
    )

    # ── Tour banner ──────────────────────────────────────────────────────────────
    tour_step_idx = st.session_state.get("tour_step")
    highlighted_family: str | None = None
    if tour_step_idx is not None:
        step = TOUR_STEPS[tour_step_idx]
        _render_tour_banner(step, tour_step_idx)
        highlighted_family = step.highlighted_family

    # ── Load ─────────────────────────────────────────────────────────────────────
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

    # ── Short description ─────────────────────────────────────────────────────────
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

    # ── Family rows — pure HTML cards so inline styles cannot be overridden ───────
    for row in rows:
        top_orgs = top_map.get(row["family_id"], {"patent": [], "paper": []})
        st.markdown(
            _html_family_card(row, top_orgs, highlighted_family == row["family_id"]),
            unsafe_allow_html=True,
        )

    # ── Footer caveat ─────────────────────────────────────────────────────────────
    st.markdown(
        "<div style='border-top:1px solid #e6e6e6;margin-top:2rem;padding-top:1rem;'></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "**Scope:** US patents only (PatentsView / USPTO). "
        "Papers from OpenAlex (2012–2025, English, in-scope topics). "
        "Citation links are non-patent-literature (NPL) references from USPTO filings. "
        "Lag = paper publication date → citing patent filing date; never grant date. "
        "Filing counts after 2019 understate activity due to grant-processing delay. "
        "This is not causal inference — NPL citations record reference, not derivation."
    )


main()
