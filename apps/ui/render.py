"""Semantic color constants for the UI. Chrome colors live in app.py CSS."""
from __future__ import annotations

FAMILY_COLORS: dict[str, str] = {
    "euv":          "#3a4a6b",  # deep navy — editorial "cool technical" palette
    "si_photonics": "#5a8fa8",  # steel blue
    "lasers":       "#c1666b",  # dusty rose
    "neuromorphic": "#7a6c91",  # slate purple
    "in_memory":    "#6a9c89",  # sage green
    "adjacent":     "#94a3b8",  # slate — muted, not headline
    "noise":        "#d1d5db",  # light grey — frontier / unclustered
}

PAPER_COLOR = "#3b82f6"    # blue  — academic
PATENT_COLOR = "#f59e0b"   # amber — IP / industrial
NOISE_COLOR = "#d1d5db"    # light grey

CONFIDENCE_HIGH = "#22c55e"    # green
CONFIDENCE_MEDIUM = "#94a3b8"  # slate
CONFIDENCE_LOW = "#ef4444"     # red


def confidence_color(level: str) -> str:
    """Map 'high' / 'medium' / 'low' to the confidence color constants."""
    return {
        "high":   CONFIDENCE_HIGH,
        "medium": CONFIDENCE_MEDIUM,
        "low":    CONFIDENCE_LOW,
    }.get(level, CONFIDENCE_MEDIUM)


_METHOD_BADGE: dict[str, tuple[str, str]] = {
    "seed_crosswalk": ("Seed list",      "#6366f1"),
    "ror":            ("Verified ROR",   "#22c55e"),
    "native_id":      ("Verified",       "#22c55e"),
    "ror_bridge":     ("ROR bridge",     "#0ea5e9"),
    "fuzzy_high":     ("Fuzzy match",    "#f97316"),
    "fuzzy_review":   ("Fuzzy reviewed", "#f97316"),
    "npl_citation":   ("NPL citation",   "#ec4899"),
}


def method_badge(method: str) -> str:
    """Inline HTML badge for a match_method value."""
    label, color = _METHOD_BADGE.get(method, (method.replace("_", " "), "#888888"))
    return (
        f"<span style='background:{color}22;color:{color};"
        f"border:1px solid {color}66;border-radius:4px;"
        f"padding:2px 8px;font-size:11px;font-weight:600;'>{label}</span>"
    )


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
