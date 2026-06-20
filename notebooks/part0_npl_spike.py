"""
Part 0 NPL Feasibility Spike
=============================
Reads PatentsView bulk TSVs and the Marx & Fuegi gold eval set from local files.
Computes: scope patent count, NPL reference count, and Marx/Fuegi gold pair counts per family.
Checks all kill criteria from ROADMAP Part 0 and prints a pass/fail report.

Required local files (extracted from zip, all gitignored):
  data/raw/g_patent.tsv            -- patent_id, patent_type, patent_date (GRANT date), patent_title
  data/raw/g_cpc_current.tsv       -- patent_id, cpc_group (full code, e.g. "G03F7/20"), cpc_type
  data/raw/g_other_reference.tsv   -- patent_id, other_reference_sequence, other_reference_text
  data/reference/marx_fuegi_pcs.csv -- oaid (OpenAlex ID), patent (us-NUMBER-KIND), confscore, ...

NOTE: g_patent.tsv contains grant date only (patent_date). Filing date lives in g_application.tsv
which is NOT needed for the spike — the date filter is applied properly in Part 2.
patent_id in PatentsView == the US patent grant number (same value as in Marx/Fuegi us-NUMBER-b2).

Run:  uv run python notebooks/part0_npl_spike.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

# ---------------------------------------------------------------------------
# Scope contract (mirrors ROADMAP Part 0 scope table)
# ---------------------------------------------------------------------------

FAMILY_CPC: dict[str, list[str]] = {
    "EUV Lithography": ["G03F7/20", "G03F7/70"],
    "Silicon Photonics": ["G02B6/12", "G02B6/122", "H01S5/0224", "H01S5/10"],
    "Neuromorphic & In-Memory Compute": ["G06N3/049", "G11C11/54", "G11C13/00", "H10N70/00"],
}

ALL_CPC = [code for codes in FAMILY_CPC.values() for code in codes]

KILL_CRITERIA = {
    "min_scope_patents": 5_000,
    "min_npl_refs": 2_000,
    "min_marx_fuegi_total": 300,
    "min_marx_fuegi_per_family": 50,
}

ROOT = Path(__file__).parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_REF = ROOT / "data" / "reference"

PATENT_FILE = DATA_RAW / "g_patent.tsv"
CPC_FILE = DATA_RAW / "g_cpc_current.tsv"
NPL_FILE = DATA_RAW / "g_other_reference.tsv"
MF_FILE = DATA_REF / "marx_fuegi_pcs.csv"


def check_files() -> None:
    missing = [f for f in [PATENT_FILE, CPC_FILE, NPL_FILE, MF_FILE] if not f.exists()]
    if missing:
        print("\n[ERROR] Missing required files:")
        for f in missing:
            print(f"  {f}")
        sys.exit(1)


def cpc_filter_sql(codes: list[str], col: str = "cpc_group") -> str:
    """SQL WHERE clause: match any scope CPC code as a prefix of cpc_group."""
    parts = [f"STARTS_WITH({col}, '{c}')" for c in codes]
    return "(" + " OR ".join(parts) + ")"


def run_spike() -> dict[str, object]:
    print("=" * 60)
    print("Part 0 -- NPL Feasibility Spike")
    print("=" * 60)
    print("NOTE: date filter skipped (g_patent.tsv has grant date only;")
    print("      filing date requires g_application.tsv, added in Part 2).")

    check_files()
    con = duckdb.connect()

    # ------------------------------------------------------------------
    # Step 1: scope patents from CPC filter
    # All TSVs have double-quoted column names -- DuckDB handles by default.
    # ------------------------------------------------------------------
    print("\n[1/4] Building scope patent set from CPC codes...")

    scope_filter = cpc_filter_sql(ALL_CPC)

    con.execute(f"""
        CREATE OR REPLACE TABLE scope_patents AS
        SELECT DISTINCT p.patent_id
        FROM read_csv('{CPC_FILE}', sep='\t', header=True, all_varchar=True) AS cpc
        JOIN read_csv('{PATENT_FILE}', sep='\t', header=True, all_varchar=True) AS p
          ON cpc.patent_id = p.patent_id
        WHERE {scope_filter}
    """)

    n_patents = con.execute("SELECT COUNT(*) FROM scope_patents").fetchone()[0]  # type: ignore[index]
    print(f"    Scope patents (CPC match, no date filter): {n_patents:,}")

    # ------------------------------------------------------------------
    # Step 2: NPL references for scope patents
    # ------------------------------------------------------------------
    print("\n[2/4] Counting NPL references for scope patents...")

    con.execute(f"""
        CREATE OR REPLACE TABLE scope_npl AS
        SELECT npl.patent_id, npl.other_reference_text
        FROM read_csv('{NPL_FILE}', sep='\t', header=True, all_varchar=True) AS npl
        JOIN scope_patents ON npl.patent_id = scope_patents.patent_id
    """)

    n_npl = con.execute("SELECT COUNT(*) FROM scope_npl").fetchone()[0]  # type: ignore[index]
    n_npl_patents = con.execute("SELECT COUNT(DISTINCT patent_id) FROM scope_npl").fetchone()[0]  # type: ignore[index]
    print(f"    NPL reference rows:         {n_npl:,}")
    print(f"    Scope patents with any NPL: {n_npl_patents:,}")

    print("\n    Sample NPL strings:")
    for (text,) in con.execute("SELECT other_reference_text FROM scope_npl LIMIT 5").fetchall():
        print(f"      {str(text)[:120]}")

    # ------------------------------------------------------------------
    # Step 3: Marx & Fuegi gold pairs for scope patents
    # MF patent format: "us-10000000-b2" -> extract "10000000" = patent_id
    # ------------------------------------------------------------------
    print("\n[3/4] Counting Marx & Fuegi gold pairs...")

    try:
        con.execute(f"""
            CREATE OR REPLACE TABLE scope_mf AS
            SELECT
                mf.oaid,
                mf.patent,
                mf.confscore,
                mf.wherefound,
                REGEXP_EXTRACT(mf.patent, '^us-([0-9]+)-', 1) AS patent_number
            FROM read_csv('{MF_FILE}', header=True) AS mf
            JOIN scope_patents sp
              ON REGEXP_EXTRACT(mf.patent, '^us-([0-9]+)-', 1) = CAST(sp.patent_id AS VARCHAR)
        """)

        n_mf_total = con.execute("SELECT COUNT(*) FROM scope_mf").fetchone()[0]  # type: ignore[index]
        n_mf_papers = con.execute("SELECT COUNT(DISTINCT oaid) FROM scope_mf").fetchone()[0]  # type: ignore[index]
        print(f"    MF gold pairs in scope:    {n_mf_total:,}")
        print(f"    Distinct OpenAlex papers:  {n_mf_papers:,}")

    except Exception as e:
        print(f"    [WARN] Marx & Fuegi join failed: {e}")
        n_mf_total = 0
        n_mf_papers = 0

    # ------------------------------------------------------------------
    # Step 4: Per-family breakdown
    # ------------------------------------------------------------------
    print("\n[4/4] Per-family breakdown...")

    family_results: dict[str, dict[str, int]] = {}
    for family, codes in FAMILY_CPC.items():
        fam_filter = cpc_filter_sql(codes)

        n_fam = con.execute(f"""
            SELECT COUNT(DISTINCT p.patent_id)
            FROM read_csv('{CPC_FILE}', sep='\t', header=True, all_varchar=True) AS cpc
            JOIN scope_patents p ON cpc.patent_id = p.patent_id
            WHERE {fam_filter}
        """).fetchone()[0]  # type: ignore[index]

        n_fam_npl = con.execute(f"""
            SELECT COUNT(*)
            FROM scope_npl npl
            JOIN (
                SELECT DISTINCT patent_id
                FROM read_csv('{CPC_FILE}', sep='\t', header=True, all_varchar=True) AS cpc
                WHERE {fam_filter}
            ) fam ON npl.patent_id = fam.patent_id
        """).fetchone()[0]  # type: ignore[index]

        n_fam_mf = 0
        if n_mf_total > 0:
            n_fam_mf = con.execute(f"""
                SELECT COUNT(*)
                FROM scope_mf mf
                JOIN (
                    SELECT DISTINCT CAST(p.patent_id AS VARCHAR) AS pid
                    FROM read_csv('{CPC_FILE}', sep='\t', header=True, all_varchar=True) AS cpc
                    JOIN scope_patents p ON cpc.patent_id = p.patent_id
                    WHERE {fam_filter}
                ) fam ON mf.patent_number = fam.pid
            """).fetchone()[0]  # type: ignore[index]

        family_results[family] = {
            "patents": n_fam,
            "npl_refs": n_fam_npl,
            "mf_pairs": n_fam_mf,
        }
        print(
            f"    {family}:\n"
            f"      patents={n_fam:,}  npl_refs={n_fam_npl:,}  mf_pairs={n_fam_mf:,}"
        )

    # ------------------------------------------------------------------
    # Kill-criteria report
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("KILL CRITERIA CHECK")
    print("=" * 60)

    checks: list[tuple[str, bool, str]] = [
        (
            f"Scope patents >= {KILL_CRITERIA['min_scope_patents']:,}",
            n_patents >= KILL_CRITERIA["min_scope_patents"],
            f"got {n_patents:,}",
        ),
        (
            f"NPL refs >= {KILL_CRITERIA['min_npl_refs']:,}",
            n_npl >= KILL_CRITERIA["min_npl_refs"],
            f"got {n_npl:,}",
        ),
        (
            f"MF gold pairs total >= {KILL_CRITERIA['min_marx_fuegi_total']:,}",
            n_mf_total >= KILL_CRITERIA["min_marx_fuegi_total"],
            f"got {n_mf_total:,}",
        ),
    ]
    for family, fr in family_results.items():
        checks.append((
            f"MF pairs for {family} >= {KILL_CRITERIA['min_marx_fuegi_per_family']}",
            fr["mf_pairs"] >= KILL_CRITERIA["min_marx_fuegi_per_family"],
            f"got {fr['mf_pairs']:,}",
        ))

    all_pass = True
    for label, passed, detail in checks:
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {label} ({detail})")
        if not passed:
            all_pass = False

    print()
    if all_pass:
        print("ALL CRITERIA PASSED -- proceed to R2 credential check.")
    else:
        print("ONE OR MORE CRITERIA FAILED -- see ROADMAP Part 0 Risks.")

    print("\nNote: g_application.tsv needed for Part 2 to apply the 2014-2024 filing-date filter.")

    con.close()
    return {
        "n_patents": n_patents,
        "n_npl": n_npl,
        "n_mf_total": n_mf_total,
        "families": family_results,
    }


if __name__ == "__main__":
    run_spike()
