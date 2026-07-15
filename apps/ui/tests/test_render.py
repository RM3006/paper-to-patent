# pyright: basic
"""Tests for render.py's embed-aware link builder.

Regression cover for the iframe redirect loop: a nav <a href> that drops the
`embed` flag navigates the frame to the non-embed host page, which then starts a
login redirect that cannot complete cross-site (ERR_TOO_MANY_REDIRECTS).
"""

from __future__ import annotations

import pytest
import streamlit as st

import render


def test_embed_url_passthrough_when_not_embedded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standalone app: links stay bare, so it keeps its normal top-level chrome."""
    monkeypatch.setattr(st, "query_params", {})
    assert render.embed_url("/Family") == "/Family"
    assert render.embed_url("/Family?family=euv") == "/Family?family=euv"


def test_embed_url_appends_flag_when_embedded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st, "query_params", {"e": "1"})
    assert render.embed_url("/Family") == "/Family?embed=true&e=1"


def test_embed_url_merges_into_existing_query(monkeypatch: pytest.MonkeyPatch) -> None:
    """/Family?family=euv already carries a query string -- needs &, not a 2nd ?."""
    monkeypatch.setattr(st, "query_params", {"e": "1"})
    assert render.embed_url("/Family?family=euv") == "/Family?family=euv&embed=true&e=1"


def test_embed_url_ignores_other_sentinel_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only e=1 counts; a stray `e` from some other link must not force embed mode."""
    monkeypatch.setattr(st, "query_params", {"e": "0"})
    assert render.embed_url("/Map") == "/Map"
