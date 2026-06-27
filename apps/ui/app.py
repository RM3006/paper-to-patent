"""
The Chips Behind AI — front door (Surface 1).

Five technology family scorecard tiles + patent-share and citation-lag comparison charts.
A guided tour (5 stops) narrates the key contrasts; tour state lives in st.session_state.
Source mart: mart_family.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
from render import FAMILY_COLORS
from tour import TOUR_STEPS, TourStep, is_first_step, is_last_step, progress_label

from data import load_family_scorecard

st.set_page_config(
    page_title="The Chips Behind AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="auto",
)

# ── CSS ─────────────────────────────────────────────────────────────────────────
_CSS = """
<style>
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
  [data-testid="stMetricDelta"] { display: none; }

  /* Tour narration card — warm tint marks it as tutorial chrome. */
  .st-key-tour_card {
    background: #fdf6e3;
    border: 1px solid #ecdfb8;
    border-radius: 8px;
    padding: 4px 20px 18px;
    margin-bottom: 1rem;
  }

  /* Tour nav row — flex right-aligned, buttons become warm-brown text links. */
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


# ── Tour helpers ────────────────────────────────────────────────────────────────
def _start_tour() -> None:
    st.session_state.tour_step = 0
    st.rerun()


def _render_tour_button() -> None:
    if st.session_state.get("tour_step") is None:
        if st.button("Take the tour →", key="tour_start", type="primary"):
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
            f"<div style='font-weight:700;font-size:1rem;color:#111111;"
            f"margin-bottom:6px;margin-top:8px;'>{step.title}</div>"
            f"<div style='color:#111111;font-size:0.9rem;line-height:1.6;'>"
            f"{step.narration}</div>",
            unsafe_allow_html=True,
        )


# ── Scorecard tile ──────────────────────────────────────────────────────────────
def _tile(row: dict, *, highlighted: bool = False) -> str:  # type: ignore[type-arg]
    color = FAMILY_COLORS.get(row["family_id"], "#888888")
    pct = (row["patent_share"] or 0.0) * 100
    lag = row["median_lag_years_weighted"]
    lag_str = f"{lag:.2f} yr" if lag is not None else "—"
    top_a = row["top_assignee_name"] or "—"
    top_r = row["top_researcher_name"] or "—"
    bar_w = min(pct, 100)

    if highlighted:
        outer = (
            f"border:2px solid {color};border-left:5px solid {color};"
            f"box-shadow:0 0 0 3px {color}33;border-radius:4px;padding:15px;"
            f"min-height:210px;"
        )
    else:
        outer = (
            f"border:1px solid #e6e6e6;border-left:4px solid {color};"
            f"border-radius:4px;padding:16px;min-height:210px;"
        )

    return (
        f'<div style="{outer}">'
        f'<div style="font-size:10px;font-weight:700;letter-spacing:.07em;'
        f'text-transform:uppercase;color:#888888;margin-bottom:10px;">'
        f'{row["family_name"]}</div>'
        f'<div style="display:flex;gap:20px;margin-bottom:10px;">'
        f'<div>'
        f'<div style="font-size:22px;font-weight:700;color:#111111;line-height:1.1;">'
        f'{row["n_papers"]:,}</div>'
        f'<div style="font-size:10px;color:#888888;">papers</div>'
        f'</div>'
        f'<div>'
        f'<div style="font-size:22px;font-weight:700;color:#111111;line-height:1.1;">'
        f'{row["n_patents"]:,}</div>'
        f'<div style="font-size:10px;color:#888888;">US patents</div>'
        f'</div>'
        f'</div>'
        f'<div style="background:#e6e6e6;border-radius:2px;height:4px;margin-bottom:5px;">'
        f'<div style="background:{color};width:{bar_w:.1f}%;height:4px;border-radius:2px;">'
        f'</div></div>'
        f'<div style="font-size:11px;color:#555555;margin-bottom:8px;">'
        f'{pct:.0f}% patent share</div>'
        f'<div style="font-size:11px;color:#555555;margin-bottom:4px;">'
        f'⏱ {lag_str} median lag</div>'
        f'<div style="font-size:11px;color:#888888;">'
        f'Patenter: <span style="color:#111111;font-weight:500;">{top_a}</span></div>'
        f'<div style="font-size:11px;color:#888888;">'
        f'Researcher: <span style="color:#111111;font-weight:500;">{top_r}</span></div>'
        f'</div>'
    )


# ── Main ────────────────────────────────────────────────────────────────────────
def main() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Header ──────────────────────────────────────────────────────────────────
    col_title, col_tour = st.columns([5, 1], vertical_alignment="center")
    with col_title:
        st.markdown("## The Chips Behind AI")
        st.markdown(
            "<p style='color:#888888;margin-top:-0.4rem;margin-bottom:0.8rem;font-size:15px;'>"
            "Tracing global semiconductor research papers to US patents "
            "across 5 technology families."
            "</p>",
            unsafe_allow_html=True,
        )
    with col_tour:
        _render_tour_button()

    # ── Tour banner (shown when active) ─────────────────────────────────────────
    tour_step_idx = st.session_state.get("tour_step")
    highlighted_family: str | None = None
    if tour_step_idx is not None:
        step = TOUR_STEPS[tour_step_idx]
        _render_tour_banner(step, tour_step_idx)
        highlighted_family = step.highlighted_family

    # ── Load ────────────────────────────────────────────────────────────────────
    scorecard = load_family_scorecard()
    rows = scorecard.filter(scorecard["family_id"] != "adjacent").to_dicts()

    # ── Scorecard tiles ──────────────────────────────────────────────────────────
    tile_cols = st.columns(5)
    for i, row in enumerate(rows):
        with tile_cols[i]:
            is_hl = highlighted_family == row["family_id"]
            st.markdown(_tile(row, highlighted=is_hl), unsafe_allow_html=True)
            if st.button(
                "Explore →",
                key=f"explore_{row['family_id']}",
                use_container_width=True,
            ):
                st.session_state.selected_family = row["family_id"]
                st.switch_page("pages/2_Family.py")

    # ── Key insight ──────────────────────────────────────────────────────────────
    st.markdown("")
    row_euv = next((r for r in rows if r["family_id"] == "euv"), None)
    row_sip = next((r for r in rows if r["family_id"] == "si_photonics"), None)
    if row_euv and row_sip:
        euv_pct = (row_euv["patent_share"] or 0) * 100
        sip_pct = (row_sip["patent_share"] or 0) * 100
        insight = (
            f"**EUV Lithography** has {euv_pct:.0f}% patent share — more IP activity than "
            f"paper activity. "
            f"**Silicon Photonics** hosts {row_sip['n_papers']:,} papers but only "
            f"{sip_pct:.0f}% reach a US patent. "
            f"In-Memory and Neuromorphic computing show the fastest translation to IP: "
            f"under 3 years from publication to patent filing."
        )
        st.info(insight)

    # ── Comparison charts ─────────────────────────────────────────────────────────
    st.markdown("### Family comparison")
    c_share, c_lag = st.columns(2)

    family_ids = [r["family_id"] for r in rows]
    bar_colors = [FAMILY_COLORS.get(fid, "#888888") for fid in family_ids]

    share_vals = [(r["patent_share"] or 0.0) * 100 for r in rows]
    share_data = sorted(
        zip(share_vals, [r["family_name"] for r in rows], bar_colors, strict=False)
    )
    sv, sn, sc = map(list, zip(*share_data, strict=False))

    with c_share:
        st.markdown("**Patent share** *(patents as % of total family activity)*")
        fig_share = go.Figure(go.Bar(
            x=sv,
            y=sn,
            orientation="h",
            marker_color=sc,
            text=[f"{v:.0f}%" for v in sv],
            textposition="outside",
            cliponaxis=False,
        ))
        fig_share.update_layout(
            height=225,
            margin=dict(l=0, r=55, t=5, b=5),
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            font=dict(size=12, color="#111111"),
            xaxis=dict(showgrid=True, gridcolor="#e6e6e6", zeroline=False, range=[0, 65]),
            yaxis=dict(showgrid=False),
            showlegend=False,
        )
        st.plotly_chart(fig_share, use_container_width=True, config={"displayModeBar": False})

    lag_rows = [r for r in rows if r["median_lag_years_weighted"] is not None]
    lag_data = sorted(zip(
        [r["median_lag_years_weighted"] for r in lag_rows],
        [r["family_name"] for r in lag_rows],
        [FAMILY_COLORS.get(r["family_id"], "#888888") for r in lag_rows],
        strict=False,
    ))
    lv, ln, lc = map(list, zip(*lag_data, strict=False))

    with c_lag:
        lag_title = (
            "**Median citation lag** "
            "*(paper pub → patent filing, via NPL links, US patents only)*"
        )
        st.markdown(lag_title)
        fig_lag = go.Figure(go.Bar(
            x=lv,
            y=ln,
            orientation="h",
            marker_color=lc,
            text=[f"{v:.2f} yr" for v in lv],
            textposition="outside",
            cliponaxis=False,
        ))
        fig_lag.update_layout(
            height=225,
            margin=dict(l=0, r=70, t=5, b=5),
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            font=dict(size=12, color="#111111"),
            xaxis=dict(showgrid=True, gridcolor="#e6e6e6", zeroline=False, range=[0, 4.6]),
            yaxis=dict(showgrid=False),
            showlegend=False,
        )
        st.plotly_chart(fig_lag, use_container_width=True, config={"displayModeBar": False})

    # ── Footer caveat ─────────────────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<span style='font-size:11px;color:#888888;'>"
        "<strong>Scope:</strong> US patents only (PatentsView / USPTO). "
        "Papers from OpenAlex (2012–2025, English, in-scope topics). "
        "Citation links are non-patent-literature (NPL) references from USPTO filings. "
        "Lag = paper publication date → citing patent filing date; never grant date. "
        "Filing counts after 2019 understate activity due to grant-processing delay. "
        "This is not causal inference — NPL citations record reference, not derivation."
        "</span>",
        unsafe_allow_html=True,
    )


main()
