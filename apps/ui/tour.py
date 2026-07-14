# pyright: basic
"""Guided tour definition — "The Chips Behind AI".

Five stops, one per page, in nav order: Overview, Family Deepdive, Technology
Landscape, Organisation Profile, Trace a Paper. Each step narrates the key
insight of its page and carries the page_file path used by render_tour_banner()
for navigation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TourStep:
    title: str
    narration: str
    page_file: str  # path passed to st.switch_page()


TOUR_STEPS: list[TourStep] = [
    TourStep(
        title="Five technology families powering AI hardware",
        narration=(
            "Each row is one technology family, from extreme-UV lithography that prints "
            "transistors smaller than a virus, to in-memory computing that eliminates "
            "the speed bottleneck between processor and memory. "
            "The <strong>patent share</strong> tells you what fraction of all US patenting "
            "activity in scope this family represents. "
            "The <strong>citation lag</strong> is the gap between a paper's publication date "
            "and the filing date of a US patent that references it: a traceable number "
            "extracted from real USPTO non-patent-literature citations, not an estimate."
        ),
        page_file="app.py",
    ),
    TourStep(
        title="Inside a technology family",
        narration=(
            "Use the pills at the top to switch between the five technology families. "
            "The metrics strip shows patent share, citation lag, granted US patents, "
            "and research papers. "
            "The leaderboards rank who files the most patents and publishes the most papers. "
            "The velocity chart shows how filing activity has shifted year by year. "
            "At the bottom, the cluster table breaks the family into its sub-topics, each "
            "with its own HHI (a concentration index measuring how few organisations "
            "dominate that cluster's patents)."
        ),
        page_file="pages/1_Family.py",
    ),
    TourStep(
        title="Every cluster at a glance",
        narration=(
            "Each dot is a technology cluster: a coherent group of papers and patents "
            "identified by semantic similarity. "
            "Position encodes the balance between research volume (Y axis) "
            "and patent capture (X axis), both on a log scale. "
            "Dots high and left are prolific research areas with little IP capture; "
            "dots low and right are industrialised niches. "
            "<strong>Click any dot</strong> to open its detail card: plain English summary, "
            "citation lag, top patenters, and top researchers."
        ),
        page_file="pages/2_Map.py",
    ),
    TourStep(
        title="Who owns the IP?",
        narration=(
            "Search any organisation (company, university, or research institute) "
            "and see its two-sided ledger: patents filed on the left, papers published on "
            "the right. The bar charts break activity down by technology family, "
            "so you can see where an organisation concentrates its effort. "
            "The NPL bridge shows which research feeds into its patents and "
            "which organisations build on its science."
        ),
        page_file="pages/3_Org.py",
    ),
    TourStep(
        title="From paper to patent: a traceable link",
        narration=(
            "Every link here is a real non-patent-literature citation extracted from a "
            "USPTO filing, not a model prediction. "
            "Search a paper and the timeline shows every US patent that cited it, "
            "positioned at its filing date. "
            "The gap between the paper's publication date and the earliest citing patent "
            "is the citation lag you have seen on every other page. "
            "This is where it comes from."
        ),
        page_file="pages/4_Trace.py",
    ),
]


def is_first_step(idx: int) -> bool:
    return idx == 0


def is_last_step(idx: int) -> bool:
    return idx == len(TOUR_STEPS) - 1


def progress_label(idx: int) -> str:
    return f"Step {idx + 1} of {len(TOUR_STEPS)}"
