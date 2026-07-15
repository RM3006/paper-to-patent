# pyright: basic
"""Semantic color constants for the UI. Chrome colors live in app.py CSS."""
from __future__ import annotations

from collections.abc import Callable

import streamlit as st
from streamlit_searchbox import StyleOverrides, st_searchbox

_FILTER_SEARCHBOX_STYLE: StyleOverrides = {"searchbox": {"option": {"highlightColor": "#f0f0f0"}}}

FAMILY_COLORS: dict[str, str] = {
    # 5-way document-level family (each paper/patent's own direct family --
    # Overview, Family Deepdive, Organisation Profile).
    "euv":          "#3a4a6b",  # deep navy — editorial "cool technical" palette
    "lasers":       "#c1666b",  # dusty rose — coherent light, warm without danger-red
    "si_photonics": "#5a8fa8",  # steel blue — light through glass and silicon
    "neuromorphic": "#7a6c91",  # slate purple — neural/biological-digital bridge
    "in_memory":    "#6a9c89",  # sage green — storage, data, growth
    # 3-way cluster-label family (Technology Landscape map only -- a cluster's
    # majority-vote display label; see seed_cluster_family.sql for why clusters
    # stay 3-way while documents are 5-way).
    "silicon_photonics":      "#8e7a8a",  # blend of si_photonics #5a8fa8 + lasers #c1666b
    "neuromorphic_in_memory": "#72848d",  # blend of neuromorphic #7a6c91 + in_memory #6a9c89
    "mixed":                  "#8f8f8f",  # neutral grey (zero saturation) --
                                           # reads as "no dominant family",
                                           # distinct from the 3 hued colors
    "noise":                  "#d1d5db",  # light grey — frontier / unclustered
}

FAMILY_LABELS: dict[str, str] = {
    # 5-way document-level family.
    "euv":          "EUV Lithography",
    "lasers":       "Lasers",
    "si_photonics": "Silicon Photonics",
    "neuromorphic": "Neuromorphic",
    "in_memory":    "In-Memory Compute",
    "unattributed": "Unattributed",
    # 3-way cluster-label family (Technology Landscape map only).
    "silicon_photonics":      "Silicon Photonics & Lasers",
    "neuromorphic_in_memory": "Neuromorphic & In-Memory Compute",
    "mixed":                  "Mixed",
    "noise":                  "Frontier / Unclustered",
}

PAPER_COLOR = "#3b82f6"    # blue  — academic
PATENT_COLOR = "#f59e0b"   # amber — IP / industrial
NOISE_COLOR = "#d1d5db"    # light grey

CONFIDENCE_HIGH = "#22c55e"    # green
CONFIDENCE_MEDIUM = "#94a3b8"  # slate
CONFIDENCE_LOW = "#ef4444"     # red


def embed_url(path: str) -> str:
    """Build an <a href> that survives being clicked inside an embedding iframe.

    The nav tabs and family pills are plain anchors, so clicking one is a full
    browser navigation: whatever query string the frame was loaded with is lost.
    Losing `embed=true` lands the frame on Community Cloud's non-embed host page,
    which starts a login redirect that cannot complete cross-site -- the frame
    then bounces /Family -> app?redirect_uri= -> login?payload= until the browser
    gives up with ERR_TOO_MANY_REDIRECTS.

    Streamlit reserves `embed` and withholds it from st.query_params, so the app
    cannot read it back to know it is embedded. The iframe therefore passes a
    non-reserved `e=1` alongside it, which st.query_params does expose.
    """
    if st.query_params.get("e") != "1":
        return path
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}embed=true&e=1"


def confidence_color(level: str) -> str:
    """Map 'high' / 'medium' / 'low' to the confidence color constants."""
    return {
        "high":   CONFIDENCE_HIGH,
        "medium": CONFIDENCE_MEDIUM,
        "low":    CONFIDENCE_LOW,
    }.get(level, CONFIDENCE_MEDIUM)


def confidence_badge(level: str) -> str:
    """Inline HTML badge for a confidence level."""
    color = confidence_color(level)
    return (
        f"<span style='background:{color}22;color:{color};"
        f"border:1px solid {color}66;border-radius:4px;"
        f"padding:2px 8px;font-size:11px;font-weight:600;'>{level}</span>"
    )


def hhi_color(t: float) -> str:
    """Interpolate #22c55e (diffuse, t=0) → #ef4444 (concentrated, t=1)."""
    t = max(0.0, min(1.0, t))
    r = int(34  + (239 - 34)  * t)
    g = int(197 + (68  - 197) * t)
    b = int(94  + (68  - 94)  * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def render_tour_banner(page_step: int) -> None:
    """Show the guided tour banner if the active tour step matches this page.

    Call once per page right after render_nav(), passing the zero-based step
    index that belongs to this page. Returns immediately when no tour is active
    or when the active step belongs to a different page.
    """
    from tour import TOUR_STEPS, is_first_step, is_last_step, progress_label

    tour_step = st.session_state.get("tour_step")
    if tour_step != page_step:
        return

    step = TOUR_STEPS[page_step]
    _font = '"Space Grotesk", -apple-system, system-ui, sans-serif'

    st.markdown(
        "<style>"
        ".st-key-tour_card {"
        "  background:#fdf6e3;border:1px solid #ecdfb8;"
        "  border-radius:10px;padding:4px 26px 22px;margin-bottom:1rem;"
        "}"
        ".st-key-tour_nav {"
        "  display:flex;flex-direction:row;justify-content:flex-end;"
        "  align-items:center;gap:0.5rem;margin-top:10px;"
        "}"
        ".st-key-tour_nav [data-testid='stButton'] button,"
        ".st-key-tour_nav [data-testid='stButton'] button[kind='primary'],"
        ".st-key-tour_nav [data-testid='stButton'] button[kind='secondary'] {"
        "  padding:0.1rem 0.3rem;font-size:0.82rem;font-weight:600;"
        "  border:none;border-radius:0;text-decoration:underline;"
        "  color:#8a6d1f;background:transparent;"
        "}"
        ".st-key-tour_nav [data-testid='stButton'] button:hover,"
        ".st-key-tour_nav [data-testid='stButton'] button[kind='primary']:hover,"
        ".st-key-tour_nav [data-testid='stButton'] button[kind='secondary']:hover {"
        "  color:#a3821f;background:transparent;text-decoration:underline;"
        "}"
        ".st-key-tour_card,"
        ".st-key-tour_card > div > [data-testid='stVerticalBlock'] {"
        "  gap:4px !important;"
        "}"
        "</style>",
        unsafe_allow_html=True,
    )

    with st.container(key="tour_card"):
        col_label, col_nav = st.columns([3, 1], vertical_alignment="center")
        with col_label:
            st.markdown(
                f"<div style='color:#888888;font-size:0.72rem;font-weight:700;"
                f"text-transform:uppercase;letter-spacing:0.12em;'>"
                f"Guided tour · {progress_label(page_step)}</div>",
                unsafe_allow_html=True,
            )
        def _end_tour() -> None:
            """Leave the tour and return to whichever page it was started from."""
            st.session_state["tour_step"] = None
            return_page = st.session_state.pop("tour_return_page", "app.py")
            if return_page == TOUR_STEPS[page_step].page_file:
                st.rerun()
            else:
                st.switch_page(return_page)

        with col_nav, st.container(key="tour_nav"):
            if not is_first_step(page_step):
                prev_page = TOUR_STEPS[page_step - 1].page_file
                if st.button("← Back", key="tour_back", type="secondary"):
                    st.session_state["tour_step"] = page_step - 1
                    st.switch_page(prev_page)
            finish_label = "Finish →" if is_last_step(page_step) else "Next →"
            if st.button(finish_label, key="tour_next", type="primary"):
                if is_last_step(page_step):
                    _end_tour()
                else:
                    st.session_state["tour_step"] = page_step + 1
                    st.switch_page(TOUR_STEPS[page_step + 1].page_file)
            if st.button("Exit tour", key="tour_exit", type="secondary"):
                _end_tour()

        st.markdown(
            f"<div style='font-family:{_font};font-weight:700;font-size:1rem;"
            f"color:#111111;margin-bottom:6px;'>{step.title}</div>"
            f"<div style='color:#111111;font-size:0.95rem;line-height:1.55;'>"
            f"{step.narration}</div>",
            unsafe_allow_html=True,
        )


def render_nav(active: str, filter_sidebar: bool = False) -> None:
    """Persistent site header rendered at the top of every page.

    Brand block (wordmark + subtitle + tour CTA) above a full-width tab strip.
    Pass filter_sidebar=True on pages that use st.sidebar for data filters --
    it stays a normal, user-collapsible sidebar instead of being hidden. The
    auto-generated Streamlit page-nav list inside it is always hidden either
    way, since the tab strip below is this app's only navigation.
    """
    _font = '"Space Grotesk", -apple-system, system-ui, sans-serif'

    # Suppress decoration stripe, toolbar colour, auto page nav, and (unless this
    # page uses it for filters) the sidebar itself. Also defines the shared .card
    # family, used on every page. Dynamic per-instance color (family, org...)
    # goes through --accent / --accent-border, set inline on the card root --
    # never baked into the class itself.
    _sidebar_css = (
        ""
        if filter_sidebar
        else (
            "[data-testid='stSidebar'] { display: none !important; }"
            "[data-testid='stSidebarCollapseButton'] { display: none !important; }"
            "[data-testid='stExpandSidebarButton'] { display: none !important; }"
            "[data-testid='collapsedControl'] { display: none !important; }"
            "[data-testid='stSidebarCollapsedControl'] { display: none !important; }"
        )
    )
    st.markdown(
        "<style>"
        "[data-testid='stDecoration'] { display: none !important; }"
        "[data-testid='stHeader'] { background: transparent !important; }"
        "[data-testid='stSidebarNav'] { display: none !important; }"
        f"{_sidebar_css}"
        ".card {"
        "  background:#ffffff;border:1px solid #e6e6e6;border-radius:10px;"
        "  padding:22px 26px;margin-bottom:1rem;"
        "}"
        ".card-tag  { color: var(--accent, #888888); }"
        ".card-stat { color: var(--accent, #111111); }"
        ".family-explore {"
        "  font-size:13px;font-weight:600;text-decoration:underline !important;"
        "  text-underline-offset:3px;transition:opacity 0.18s ease;"
        "  white-space:nowrap;color:var(--accent, #111111) !important;"
        "}"
        ".family-explore:hover { opacity: 0.55; }"
        ".card.card--metric {"
        "  height:90px;padding:18px 8px;text-align:center;display:flex;"
        "  flex-direction:column;align-items:center;justify-content:center;"
        "  border-radius:8px;"
        "}"
        ".card.card--row {"
        "  height:48px;box-sizing:border-box;padding:0 10px;border-radius:6px;"
        "  margin-bottom:4px;display:flex;flex-direction:column;justify-content:center;"
        "}"
        ".card.card--identity {"
        "  border-radius:6px;padding:16px 18px;"
        "  border-color:var(--accent-border, #e6e6e6);"
        "}"
        "</style>",
        unsafe_allow_html=True,
    )

    # ── Brand block: wordmark + subtitle (left) | tour button (right) ─────────
    col_brand, col_cta = st.columns([5, 2], vertical_alignment="center")
    with col_brand:
        st.markdown(
            f"<div style='font-family:{_font};font-size:72px;font-weight:bold;"
            f"color:#111111;letter-spacing:-0.02em;line-height:1.05;'>"
            f"The Chips Behind AI</div>"
            f"<div style='color:#888888;font-size:0.9rem;'>"
            f"Tracing global semiconductor research papers to US patents "
            f"across 5 technology families · papers 2012–2025, patents filed 2014–2025"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col_cta:
        if st.session_state.get("tour_step") is None:
            if st.button("Take the 90-second tour", key=f"_hdr_tour_{active}", type="primary"):
                from tour import TOUR_STEPS

                # TOUR_STEPS is ordered Overview, Family, Map, Org, Trace -- same
                # order as the tab strip below -- so this label lookup stays valid
                # as long as both lists list pages in that order.
                _nav_labels = [
                    "Overview", "Family Deepdive", "Technology Landscape",
                    "Organisation Profile", "Trace a Paper",
                ]
                st.session_state["tour_step"] = 0
                st.session_state["tour_return_page"] = (
                    TOUR_STEPS[_nav_labels.index(active)].page_file
                )
                if active != "Overview":
                    st.switch_page("app.py")
                else:
                    st.rerun()

    # ── Tab strip ──────────────────────────────────────────────────────────────
    _tabs = [
        ("Overview",             "/"),
        ("Family Deepdive",      "/Family"),
        ("Technology Landscape", "/Map"),
        ("Organisation Profile", "/Org"),
        ("Trace a Paper",        "/Trace"),
    ]
    tabs_html = ""
    for label, href in _tabs:
        cls = ' class="chip-active"' if label == active else ""
        tabs_html += f"<a href='{embed_url(href)}' target='_self'{cls}>{label}</a>"

    st.markdown(
        "<style>"
        ".chip-nav {"
        "  display:flex; gap:40px; padding:0;"
        "  border-bottom:1px solid #e6e6e6;"
        "  margin-top:1rem; margin-bottom:1.5rem;"
        "}"
        ".chip-nav a {"
        "  font-size:14px; font-weight:400; color:#888888 !important;"
        "  text-decoration:none !important;"
        "  padding-bottom:6px; margin-bottom:-1px;"
        "  border-bottom:2px solid transparent;"
        "  white-space:nowrap; display:inline-block;"
        "  transition:color .15s, border-color .15s;"
        "}"
        ".chip-nav a:hover { color:#555555 !important; }"
        ".chip-nav a.chip-active {"
        "  font-weight:700; color:#111111 !important;"
        "  border-bottom-color:#111111;"
        "}"
        "</style>"
        f"<div class='chip-nav'>{tabs_html}</div>",
        unsafe_allow_html=True,
    )


def render_chip_multiselect(
    label: str,
    session_key: str,
    options: list[tuple[str, str]],
    *,
    placeholder: str,
    search_key: str,
    on_remove: Callable[[str], None] | None = None,
) -> list[str]:
    """Chip-tag multi-select: an st_searchbox to add a value, one button per chip to remove it.

    `options` is the full (label, value) universe to search over -- matching is
    substring, case-insensitive, over the label. Selections persist in
    st.session_state[session_key] and are returned as that same list of values.
    `on_remove(value)` runs right before the rerun that follows removing a chip,
    e.g. to cascade-drop cluster selections that belonged to a removed family.
    """
    if session_key not in st.session_state:
        st.session_state[session_key] = []

    label_by_value = {val: lbl for lbl, val in options}

    def _search(query: str) -> list[tuple[str, str]]:
        if not query:
            return options
        q = query.lower()
        return [(lbl, val) for lbl, val in options if q in lbl.lower()]

    # st_searchbox only reads `default_options` when its own widget state is freshly
    # (re)initialized -- passing a new `options` list on a later render does NOT
    # refresh what the dropdown shows before the user types a character. When this
    # widget's option universe depends on another filter (e.g. cluster options
    # scoped by the selected family), a changed universe must force a fresh widget
    # generation here, otherwise the dropdown keeps offering stale, out-of-scope
    # options picked up from whatever the universe was on first render.
    _scope_fingerprint = tuple(val for _, val in options)
    _scope_key = f"_{search_key}_scope_fp"
    if st.session_state.get(_scope_key) != _scope_fingerprint:
        st.session_state[_scope_key] = _scope_fingerprint
        st.session_state.pop(search_key, None)
        st.session_state.pop(f"_{search_key}_seen_gen", None)

    st.caption(label)
    picked = st_searchbox(
        _search,
        placeholder=placeholder,
        key=search_key,
        clear_on_submit=True,
        style_overrides=_FILTER_SEARCHBOX_STYLE,
        default_options=options[:20],
    )

    # st_searchbox keeps returning the same submitted value on every rerun after a
    # pick -- clear_on_submit only resets the visible text box, not the Python
    # return value. Without a guard, a rerun triggered by something else entirely
    # (e.g. clicking a chip's remove button below) looks identical to a fresh pick
    # and re-appends the value right after it's removed. The library regenerates
    # `key_react` on every genuine new submission, so it's a reliable "did a new
    # pick actually happen" signal, independent of whether the picked value repeats.
    _generation = st.session_state[search_key]["key_react"]
    _seen_key = f"_{search_key}_seen_gen"
    if picked and st.session_state.get(_seen_key) != _generation:
        st.session_state[_seen_key] = _generation
        if picked not in st.session_state[session_key]:
            st.session_state[session_key].append(picked)
            st.rerun()

    selected: list[str] = list(st.session_state[session_key])
    for value in selected:
        short = label_by_value.get(value, value)
        short = short[:30] + "…" if len(short) > 30 else short
        if st.button(
            f"× {short}", key=f"rm_{search_key}_{value}",
            use_container_width=True, type="secondary",
        ):
            st.session_state[session_key].remove(value)
            if on_remove:
                on_remove(value)
            st.rerun()

    return list(st.session_state[session_key])
