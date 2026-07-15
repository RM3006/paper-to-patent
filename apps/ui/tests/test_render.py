# pyright: basic
"""Tests for render.py's navigation tab strip.

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
