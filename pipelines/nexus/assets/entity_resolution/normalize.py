"""Organisation name normalisation for entity resolution.

normalize_org_name() is the single shared function used by every ER layer
(Layer 1 staging, Layer 2 seed crosswalk, Layer 3 fuzzy bridge) so that
all comparisons are made on identically pre-processed strings.

Normalisation steps (in order):
  1. Expand dotted legal abbreviations  ("N.V." → "nv", "L.T.D." → "ltd")
  2. NFKD unicode → ASCII approximation (strips accents; CJK falls back to "")
  3. Lowercase
  4. Remove punctuation (replace with spaces)
  5. Split → tokens
  6. Strip legal-entity suffix tokens from the right (keep ≥ 1 token)
  7. Rejoin with single spaces
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# Dotted-abbreviation expansions — applied before punct stripping so that
# "N.V." collapses to "nv" (which is in _LEGAL_SUFFIXES) rather than "n v".
# Each tuple is (pattern, replacement); patterns are word-boundary anchored,
# case-insensitive, applied left-to-right on the lowercased name.
# ---------------------------------------------------------------------------

_DOTTED_EXPANSIONS: list[tuple[str, str]] = [
    (r"\bn\.v\.?", "nv"),
    (r"\bb\.v\.?", "bv"),
    (r"\bp\.l\.c\.?", "plc"),
    (r"\bl\.l\.c\.?", "llc"),
    (r"\bl\.t\.d\.?", "ltd"),
    (r"\bi\.n\.c\.?", "inc"),
    (r"\bc\.o\.?(?=\s|$)", "co"),  # lookahead: "Co." but not "Corp"
    (r"\ba\.g\.?(?=\s|$)", "ag"),
    (r"\bg\.m\.b\.h\.?", "gmbh"),
    (r"\bs\.r\.l\.?", "srl"),   # Italian S.r.l. (Società a responsabilità limitata)
    (r"\bs\.a\.s\.?", "sas"),
    (r"\bs\.a\.?(?=\s|$)", "sa"),
    (r"\bp\.t\.e\.?", "pte"),
    (r"\bp\.t\.y\.?", "pty"),
]

# ---------------------------------------------------------------------------
# Legal-entity suffix tokens — stripped from the right of the token list.
# Only the tokens that survive dotted-expansion + punct-removal land here.
# ---------------------------------------------------------------------------

_LEGAL_SUFFIXES: frozenset[str] = frozenset(
    {
        # English forms
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "ltd",
        "limited",
        "llc",
        "co",
        "company",
        "companies",
        "plc",
        "lp",
        "llp",
        "pte",
        "pty",
        # European forms (post-dotted-expansion)
        "nv",
        "bv",
        "ag",
        "gmbh",
        "sa",
        "sas",
        "se",
        # Japanese forms
        "kk",       # Kabushiki Kaisha (abbreviated)
        "kabushiki",
        "kaisha",
        "srl",
        # Generic descriptors that never disambiguate
        # Generic descriptors that never disambiguate
        "holding",
        "holdings",
        "group",
    }
)


def normalize_org_name(name: str) -> str:
    """Return a canonical form of an organisation name for fuzzy comparison.

    Applies dotted-expansion → ASCII → lowercase → no-punct → suffix-strip.
    Returns "" for empty or whitespace-only input; never raises.
    """
    if not name or not name.strip():
        return ""

    # Step 1 — expand dotted legal abbreviations (case-insensitive)
    result = name.lower()
    for pattern, replacement in _DOTTED_EXPANSIONS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # Step 2 — NFKD decomposition → drop non-ASCII bytes (accents etc.)
    nfkd = unicodedata.normalize("NFKD", result)
    result = nfkd.encode("ascii", errors="ignore").decode("ascii")

    # Step 3 — lowercase (again after ASCII; NFKD may expose uppercase forms)
    result = result.lower()

    # Step 4 — replace punctuation and underscores with spaces
    result = re.sub(r"[^\w\s]", " ", result)
    result = result.replace("_", " ")

    # Step 5 — tokenise
    tokens = result.split()
    if not tokens:
        return ""

    # Step 6 — strip legal suffix tokens from right; always keep ≥ 1 token
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()

    return " ".join(tokens)
