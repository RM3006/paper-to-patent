"""
Part 0 — OpenAlex Scope Count (Task 5)
========================================
Queries the OpenAlex /works and /topics endpoints to:
  1. Verify the canonical topic IDs for our scope topic names.
  2. Count papers in scope (topics + year window 2012–2024).

No data is downloaded — only meta.count is read per topic.
Update ROADMAP.md scope table if any topic ID has changed.

Run:  uv run python notebooks/part0_openalex_count.py
Requires: OPENALEX_MAILTO in environment or .env.local
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env.local"

# Load .env.local if it exists
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

MAILTO = os.environ.get("OPENALEX_MAILTO", "")
if not MAILTO:
    print("[ERROR] OPENALEX_MAILTO not set. Add it to .env.local or the environment.")
    sys.exit(1)

BASE_URL = "https://api.openalex.org"
HEADERS = {"User-Agent": f"paper-to-patent/0.1 (mailto:{MAILTO})"}

PUB_YEAR_START = 2012
PUB_YEAR_END = 2024

# Scope topic names to verify (from ROADMAP Part 0)
SCOPE_TOPIC_NAMES: list[str] = [
    "Extreme Ultraviolet Lithography",
    "EUV photomask / pellicle",
    "Plasma-based EUV light source",
    "Silicon Photonics",
    "Optical Interconnects",
    "Photonic Integrated Circuits",
    "Neuromorphic Computing",
    "Memristors",
    "In-Memory Computing",
    "Spiking Neural Networks",
]

# Kill criterion
MIN_PAPERS = 10_000


def search_topics(name: str, client: httpx.Client) -> list[dict[str, object]]:
    resp = client.get(
        f"{BASE_URL}/topics",
        params={"search": name, "per-page": "5"},
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])  # type: ignore[no-any-return]


def count_works_for_topics(topic_ids: list[str], client: httpx.Client) -> int:
    filter_str = (
        f"primary_topic.id:{'|'.join(topic_ids)},"
        f"publication_year:{PUB_YEAR_START}-{PUB_YEAR_END},"
        "language:en,"
        "has_abstract:true"
    )
    resp = client.get(
        f"{BASE_URL}/works",
        params={"filter": filter_str, "per-page": "1"},
        headers=HEADERS,
    )
    resp.raise_for_status()
    return resp.json()["meta"]["count"]  # type: ignore[no-any-return]


def run_count() -> None:
    print("=" * 60)
    print("Part 0 — OpenAlex Scope Count")
    print("=" * 60)

    confirmed_ids: list[str] = []
    print("\n[1/2] Verifying topic IDs...")

    with httpx.Client(timeout=30) as client:
        for name in SCOPE_TOPIC_NAMES:
            results = search_topics(name, client)
            if not results:
                print(f"  [WARN] No topic found for: '{name}'")
                continue
            top = results[0]
            topic_id: str = str(top.get("id", ""))
            topic_display: str = str(top.get("display_name", ""))
            works_count: int = int(top.get("works_count", 0))
            print(f"  '{name}' -> '{topic_display}' ({topic_id}, {works_count:,} works)")
            confirmed_ids.append(topic_id.replace("https://openalex.org/", ""))

        print(f"\n  Confirmed {len(confirmed_ids)} topic IDs.")
        print("  -> Update ROADMAP.md scope table if any display name differs from expected.\n")

        # ------------------------------------------------------------------
        # Count works across all confirmed topic IDs in the year window
        # ------------------------------------------------------------------
        print("[2/2] Counting works in scope (all topics combined)...")

        if not confirmed_ids:
            print("[ERROR] No topic IDs confirmed — cannot count works.")
            sys.exit(1)

        total = count_works_for_topics(confirmed_ids, client)
        print(f"  Total works (all topics, {PUB_YEAR_START}–{PUB_YEAR_END}, en, has_abstract): {total:,}")

        print("\n" + "=" * 60)
        print("KILL CRITERION CHECK")
        print("=" * 60)
        passed = total >= MIN_PAPERS
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] OpenAlex papers >= {MIN_PAPERS:,} (got {total:,})")

        if not passed:
            print("\n  -> Scope too narrow. Consider widening topic list or year window.")
        else:
            print("\n  -> Good. Proceed to R2 credential check (SETUP.md C2).")


if __name__ == "__main__":
    run_count()
