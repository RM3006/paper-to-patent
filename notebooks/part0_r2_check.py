"""
Part 0 — R2 Credential Check (Task 6)
======================================
Verifies DuckDB can read/write a Parquet file from Cloudflare R2.
Reads credentials from .env.local in the project root.

Run:  uv run python notebooks/part0_r2_check.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb
import polars as pl

ROOT = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env.local"

# Load .env.local
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
KEY_ID = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY_ID", "")
SECRET = os.environ.get("CLOUDFLARE_R2_SECRET_ACCESS_KEY", "")
BUCKET = "p2p-lake"
TEST_KEY = "test/r2_check.parquet"

if not all([ACCOUNT_ID, KEY_ID, SECRET]):
    print("[ERROR] R2 credentials missing from .env.local")
    sys.exit(1)

print("=" * 60)
print("Part 0 -- R2 Credential Check")
print("=" * 60)
print(f"  Account ID : {ACCOUNT_ID[:8]}...")
print(f"  Key ID     : {KEY_ID[:8]}...")
print(f"  Bucket     : {BUCKET}")
print(f"  Test path  : r2://{BUCKET}/{TEST_KEY}")

con = duckdb.connect()

# Configure the R2 secret
con.execute(f"""
    CREATE OR REPLACE SECRET r2 (
        TYPE r2,
        ACCOUNT_ID '{ACCOUNT_ID}',
        KEY_ID '{KEY_ID}',
        SECRET '{SECRET}'
    )
""")
print("\n[1/3] R2 secret configured in DuckDB.")

# Write a tiny test Parquet to R2
print(f"\n[2/3] Writing test Parquet to r2://{BUCKET}/{TEST_KEY} ...")
try:
    con.execute(f"""
        COPY (SELECT 42 AS answer, 'p2p-lake r2 check' AS message)
        TO 'r2://{BUCKET}/{TEST_KEY}'
        (FORMAT PARQUET)
    """)
    print("    Write: OK")
except Exception as e:
    print(f"    Write FAILED: {e}")
    if "NoSuchBucket" in str(e) or "does not exist" in str(e).lower():
        print(
            "\n  --> Bucket 'p2p-lake' does not exist yet."
            "\n      Create it via the Cloudflare dashboard:"
            "\n      R2 -> Create bucket -> name: p2p-lake -> location: auto"
            "\n      Then re-run this script."
        )
    sys.exit(1)

# Read it back
print(f"\n[3/3] Reading test Parquet from r2://{BUCKET}/{TEST_KEY} ...")
try:
    result = con.execute(
        f"SELECT * FROM read_parquet('r2://{BUCKET}/{TEST_KEY}')"
    ).fetchone()
    print(f"    Read: OK — {result}")
except Exception as e:
    print(f"    Read FAILED: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("R2 CREDENTIAL CHECK: PASS")
print("=" * 60)
print("DuckDB can write and read Parquet from R2.")
print("Part 0 exit criteria complete. Proceed to Part 1.")

con.close()
