"""Guided tour definition — "The Chips Behind AI" front door.

Five stops narrating the key contrasts in the data. The tour runs entirely on
Surface 1 (the family scorecard). Each step optionally highlights one family tile.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TourStep:
    title: str
    narration: str
    highlighted_family: str | None  # family_id to visually highlight, or None


TOUR_STEPS: list[TourStep] = [
    TourStep(
        title="Five families, one story",
        narration=(
            "AI chip manufacturing rests on these five technology clusters — from the "
            "extreme-UV light that etches circuits at atomic scales to the neuromorphic "
            "processors that mimic the brain. Each tile shows you the balance between "
            "academic research and industrial IP. A high patent share means a few companies "
            "have converted knowledge into ownership."
        ),
        highlighted_family=None,
    ),
    TourStep(
        title="EUV Lithography — industrial lock-in",
        narration=(
            "EUV Lithography has 52% patent share — more patents than papers. This is what "
            "industrial lock-in looks like. ASML holds a near-monopoly on EUV machines; "
            "TSMC and a handful of chipmakers own the process IP. IMEC, the Belgian research "
            "institute, leads the academic side. Concentration at the top of the supply chain "
            "is near-total."
        ),
        highlighted_family="euv",
    ),
    TourStep(
        title="Silicon Photonics — the knowledge gap",
        narration=(
            "Silicon Photonics has 35,000+ papers — 7× more than EUV — but only 6% reach a "
            "US patent. Most knowledge stays academic. Chinese Academy of Sciences leads the "
            "research; GlobalFoundries leads the patents. The 3.6-year median lag (longest of "
            "all five families) reflects slower industrial adoption of a field still maturing "
            "in the lab."
        ),
        highlighted_family="si_photonics",
    ),
    TourStep(
        title="The citation lag — a traceable number",
        narration=(
            "Lag = paper publication date → citing patent filing date, measured through "
            "non-patent-literature citations extracted from USPTO filings. It is a "
            "traceable, specific date — not 'time to market' or causal inference. "
            "In-Memory and Neuromorphic computing are fastest at under 3 years. "
            "Look at the right-hand chart: the spread across families is less than 1 year, "
            "but the ranking is stable."
        ),
        highlighted_family=None,
    ),
    TourStep(
        title="See the full landscape",
        narration=(
            "The Technology Map page plots all 197,000 papers and patents as individual dots, "
            "positioned by semantic similarity. Each cluster emerges from embeddings — no "
            "hand-placed layout. The grey Frontier / Unclustered zone holds 33% of papers "
            "and 48% of patents: research at the intersection of multiple families. "
            "Use the sidebar to navigate there, or click 'Explore →' on any family tile to "
            "drill into its cluster detail."
        ),
        highlighted_family=None,
    ),
]


def is_first_step(idx: int) -> bool:
    return idx == 0


def is_last_step(idx: int) -> bool:
    return idx == len(TOUR_STEPS) - 1


def progress_label(idx: int) -> str:
    return f"Stop {idx + 1} of {len(TOUR_STEPS)}"
