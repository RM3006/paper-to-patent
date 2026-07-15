# pyright: basic
"""Tests for render.py's navigation tab strip and shared text helpers.

Regression cover for the embedded-iframe nesting bug: the tabs were plain
<a href> anchors, so each click was a browser navigation that rebooted the app.
Inside an embedding iframe Community Cloud re-framed that reboot, leaving one
nested, still-running copy of the app per click -- stacked "Built with
Streamlit" badges and 404s on /<page>/_stcore/*. They are st.page_link now,
which swaps the page inside the running app instead.
"""

from __future__ import annotations

import pathlib

import render

_UI_ROOT = pathlib.Path(render.__file__).parent


def test_nav_tab_targets_resolve_to_real_files() -> None:
    """st.page_link resolves targets relative to the entrypoint, at runtime.

    A renamed or moved page therefore breaks navigation only when a user clicks
    the tab -- no import fails, no type checker complains. This is the guard.
    """
    for label, target in render.NAV_TABS:
        assert (_UI_ROOT / target).is_file(), f"tab {label!r} -> missing {target}"


def test_nav_tabs_cover_every_page() -> None:
    """Every page script is reachable from the strip; the strip is the only nav.

    config.toml sets showSidebarNavigation=false, so a page absent from NAV_TABS
    has no way in at all.
    """
    linked = {t for _, t in render.NAV_TABS}
    on_disk = {f"pages/{p.name}" for p in (_UI_ROOT / "pages").glob("*.py")}
    assert on_disk - linked == set(), f"pages with no tab: {on_disk - linked}"
    assert "app.py" in linked


def test_chip_keys_are_unique_and_css_safe() -> None:
    """Each tab's key becomes a CSS hook (.st-key-<key>) targeting the active tab.

    A collision would underline two tabs at once; a space would break the selector.
    """
    keys = [render._chip_key(label) for label, _ in render.NAV_TABS]
    assert len(keys) == len(set(keys))
    for key in keys:
        assert key.replace("_", "").isalnum(), f"{key!r} is not a valid CSS class"


# The real dim_paper.abstract of W2802367674, the Trace page's default paper.
# A blind abstract_raw[:320] landed mid-acronym here -- "(ReRAM)" rendered as
# "(ReRA…" -- which is what made an intentional preview read as a broken one.
_RERAM_ABSTRACT = (
    "As data movement operations and power-budget become key bottlenecks in the design "
    "of computing systems, the interest in unconventional approaches such as "
    "processing-in-memory (PIM), machine learning (ML), and especially neural network "
    "(NN)-based accelerators has grown significantly. Resistive random access memory "
    "(ReRAM) is a promising technology for efficiently architecting PIM- and NN-based "
    "accelerators."
)


def test_truncate_at_word_leaves_short_text_alone() -> None:
    """Text within the limit is returned verbatim and flagged as not truncated."""
    assert render.truncate_at_word("short abstract", 320) == ("short abstract", False)


def test_truncate_at_word_treats_exact_length_as_untruncated() -> None:
    """len(text) == limit is a complete text -- an ellipsis there would lie."""
    assert render.truncate_at_word("abcde", 5) == ("abcde", False)


def test_truncate_at_word_does_not_split_the_reram_acronym() -> None:
    """The reported bug: the 320-char cut fell inside "ReRAM", yielding "ReRA…"."""
    snippet, truncated = render.truncate_at_word(_RERAM_ABSTRACT, 320)
    assert truncated
    assert not snippet.endswith("(ReRA")
    assert snippet.endswith("Resistive random access memory")
    assert len(snippet) <= 320
    # The cut landed on a real boundary, so the next source char is the space
    # that followed the last kept word -- proof no word was severed.
    assert _RERAM_ABSTRACT.startswith(snippet)
    assert _RERAM_ABSTRACT[len(snippet)] == " "


def test_truncate_at_word_keeps_last_word_when_cut_lands_on_a_space() -> None:
    """A limit falling exactly on a space must not drop the word before it."""
    assert render.truncate_at_word("alpha beta gamma", 10) == ("alpha beta", True)


def test_truncate_at_word_hard_cuts_a_spaceless_run() -> None:
    """No boundary to back up to -- backing up anyway would show nothing."""
    assert render.truncate_at_word("a" * 40, 10) == ("a" * 10, True)
