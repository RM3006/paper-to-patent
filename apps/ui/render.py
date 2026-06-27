"""Semantic color constants for the UI. Chrome colors live in app.py CSS."""
from __future__ import annotations

FAMILY_COLORS: dict[str, str] = {
    "euv":          "#7c3aed",  # violet — EUV light sits just below visible violet
    "si_photonics": "#0ea5e9",  # sky blue — light propagating through glass and silicon
    "lasers":       "#f97316",  # orange — coherent light, energy
    "neuromorphic": "#ec4899",  # fuchsia — neural/biological-digital bridge
    "in_memory":    "#10b981",  # emerald — storage, data, growth
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


def hhi_color(t: float) -> str:
    """Interpolate #22c55e (diffuse, t=0) → #ef4444 (concentrated, t=1)."""
    t = max(0.0, min(1.0, t))
    r = int(34  + (239 - 34)  * t)
    g = int(197 + (68  - 197) * t)
    b = int(94  + (68  - 94)  * t)
    return f"#{r:02x}{g:02x}{b:02x}"
