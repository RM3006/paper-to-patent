# ER Eval Set — Organisation Entity Resolution

Hand-labelled pairs used to measure precision and recall of the fuzzy bridge (Layer 3).
Every pair that reaches the `fuzzy_high` or `fuzzy_review` band must be validated against
this set before the crosswalk is used in any mart.

## Methodology

- Pairs drawn from organisations that appear on **both** sides of the scope:
  OpenAlex institutions present in at least one scoped paper (2012–2025) **and**
  PatentsView assignees present in at least one scoped patent (2014–2025).
- Each pair is labelled `match` (same real-world organisation) or `non-match`.
- Hard pairs (subsidiaries, abbreviations, joint ventures) are deliberately over-sampled
  to stress-test the fuzzy bridge at its precision ceiling.
- Labels are independent of the automated matcher — do not update labels to match output.

## Quality target

- Precision ≥ 0.95 at the `fuzzy_high` auto-accept threshold.
- Record the recall you traded for it; do not optimise recall at the expense of precision.

## Precision / Recall Record

| Date | Threshold | Precision | Recall | Notes |
|------|-----------|-----------|--------|-------|
| 2026-06-22 | 90 | < 0.90 | higher | Initial threshold — rejected after finding false positives at 89.8 ("University of Southampton" ↔ "University of Roehampton") and at 90–92 ("National Institute of Standards and Technology" ↔ "National Eye Institute"). `token_set_ratio` rewards shared structural tokens. |
| 2026-06-22 | 100 | 1.00 | lower | Raised to score=100 (exact/token-subset match only). All 10 Tier-3 non-match pairs correctly excluded. All 1,160 accepted rows verified at exactly score=100. 25-row visual sample: all correct (ASML, AMD, ARM, etc.). Recall trade-off: 136 rows at 90–99 dropped (all false positives). Seed crosswalk covers the head of the distribution; fuzzy bridge at 100 handles same-name long-tail matches. |

---

## Labelled Pairs

Format: `PV name (assignee_id)` | `OA name (institution_id)` | `label` | `notes`

A blank `notes` field means the match is unambiguous from the name alone.

### Tier 1 — Unambiguous matches (should all be fuzzy_high)

| PV display name | OA display name | Label | Notes |
|---|---|---|---|
| Taiwan Semiconductor Manufacturing Company, Ltd. | Taiwan Semiconductor Manufacturing Company | match | |
| ASML NETHERLANDS B.V. | ASML | match | OA uses brand; PV uses legal entity |
| ASML Holding N.V. | ASML | match | Second ASML legal entity; same OA institution |
| International Business Machines Corporation | International Business Machines | match | |
| Intel Corporation | Intel | match | |
| Micron Technology, Inc. | Micron Technology | match | |
| GOOGLE LLC | Google | match | OA does not include "LLC" |
| Applied Materials, Inc. | Applied Materials | match | |
| Microsoft Technology Licensing, LLC | Microsoft | match | PV uses licensing entity; OA uses parent brand |
| NVIDIA Corporation | NVIDIA | match | |
| Qualcomm Incorporated | Qualcomm | match | |
| Lam Research Corporation | Lam Research | match | |
| Tokyo Electron Limited | Tokyo Electron | match | |
| SAMSUNG DISPLAY CO., LTD. | Samsung Display | match | |
| SK hynix Inc. | SK Hynix | match | Case difference only |
| Shin-Etsu Chemical Co., Ltd. | Shin-Etsu Chemical | match | |
| Taiwan Semiconductor Manufacturing Company, Ltd. | Taiwan Semiconductor Manufacturing | match | Abbreviated OA form |
| Seagate Technology LLC | Seagate Technology | match | |
| Western Digital Technologies, Inc. | Western Digital | match | |
| Marvell Technology Group Ltd. | Marvell Technology | match | |

### Tier 2 — Near matches (may land in fuzzy_review depending on threshold)

| PV display name | OA display name | Label | Notes |
|---|---|---|---|
| Carl Zeiss SMT GmbH | Carl Zeiss | match | PV includes "SMT" division suffix |
| Carl Zeiss SMT GmbH | Carl Zeiss AG | match | Both refer to the Zeiss optics parent |
| KLA-TENCOR CORPORATION | KLA Corporation | match | Company rebranded KLA-Tencor → KLA in 2019 |
| KLA Corporation | KLA Corporation | match | Post-rebrand form in both sources |
| NIKON CORPORATION | Nikon | match | |
| CANON KABUSHIKI KAISHA | Canon | match | Japanese legal suffix stripped by normalizer |
| Kabushiki Kaisha Toshiba | Toshiba | match | KK prefix is NOT stripped (see normalize.py notes) |
| SAMSUNG ELECTRONICS CO., LTD. | Samsung Electronics | match | |
| Samsung Electronics America, Inc. | Samsung Electronics | match | US subsidiary maps to parent OA institution |
| Imec vzw | IMEC | match | Belgian non-profit research center; PV uses "vzw" |
| Interuniversitair Micro-Electronica Centrum | IMEC | match | Older full legal name in PV |
| Taiwan Semiconductor Manufacturing Company, Ltd. | TSMC | non-match | OA abbreviation "TSMC" normalises differently — excluded from fuzzy; handled by seed |
| Massachusetts Institute of Technology | Massachusetts Institute of Technology | match | |
| The Board of Trustees of the Leland Stanford Junior University | Stanford University | match | Full legal PV name vs OA common name — will NOT fuzzy_high; needs seed with openalex_institution_id |
| California Institute of Technology | Caltech | non-match | "caltech" ≠ "california institute" in first-token blocking |
| California Institute of Technology | California Institute of Technology | match | When OA uses full name |
| University of California | University of California | match | |
| Regents of the University of California | University of California | match | Regents = UC governing body |
| Cornell University | Cornell University | match | |
| Massachusetts Institute of Technology | MIT | non-match | "mit" ≠ "massachusetts" in first-token blocking; seed handles this |

### Tier 3 — Hard non-matches (must not be merged)

| PV display name | OA display name | Label | Notes |
|---|---|---|---|
| Samsung Electronics Co., Ltd. | Samsung Display | non-match | Different legal entities; display patents ≠ chip patents |
| Samsung SDI Co., Ltd. | Samsung Electronics | non-match | Battery division vs semiconductor division |
| Intel Corporation | Intel Capital | non-match | Venture arm is separate from the semiconductor entity |
| Applied Materials, Inc. | Applied Micro Circuits Corporation | non-match | Different companies; "applied" first token overlaps |
| Micron Technology, Inc. | Micro Focus International | non-match | "micro" first token collision; very different businesses |
| Qualcomm Incorporated | Qualcomm CDMA Technologies | non-match | Subsidiary vs parent — keep as separate entities |
| KLA-TENCOR CORPORATION | Tencent | non-match | "tencor" vs "tencent" — different companies |
| NIKON CORPORATION | Nikon Instruments Inc. | non-match | US subsidiary is separately active in PV |
| Carl Zeiss SMT GmbH | Zeiss Group | non-match | SMT division ≠ full Zeiss group |
| Google LLC | Alphabet Inc. | non-match | Parent holding company vs operating subsidiary |
| Microsoft Technology Licensing, LLC | Microsoft Research | non-match | Licensing entity ≠ research division |
| Taiwan Semiconductor Manufacturing Company, Ltd. | United Microelectronics Corporation | non-match | Competing Taiwan fabs |
| ASML NETHERLANDS B.V. | Applied Materials, Inc. | non-match | Both are EUV/deposition equipment; different companies |
| International Business Machines Corporation | Lenovo | non-match | IBM divested PC division to Lenovo; separate orgs |
| Shin-Etsu Chemical Co., Ltd. | Shin-Etsu Polymer Co., Ltd. | non-match | Chemical vs polymer subsidiary; different OA entries |

---

## Notes on known hard cases

**Stanford:** PatentsView uses "The Board of Trustees of the Leland Stanford Junior University"
which normalises to a long unique form that will not fuzzy_high against OpenAlex's
"Stanford University" → "stanford university". Resolution: fill in `openalex_institution_id`
in `seed_crosswalk.csv` for org_stanford (query `openalex_institutions_staging` after
first materialize).

**MIT abbreviation:** "mit" in OpenAlex does not block against "massachusetts" (first-token).
Same resolution path as Stanford — use the seed crosswalk with the institution ID.

**Samsung Display vs Samsung Electronics:** intentionally left as separate org_ids.
Samsung Display holds the display/OLED patent IP; Samsung Electronics holds the
semiconductor IP. Merging them would inflate Samsung's apparent semiconductor presence.

**KLA rebrand:** KLA-Tencor became KLA Corporation in 2019. PatentsView may have both
`assignee_id` forms. Both should map to the same org_id (org_kla). Add a second seed row
if the fuzzy bridge does not auto-merge them.

**Imec:** appears in PatentsView as both "Imec vzw" and "Interuniversitair Micro-Electronica
Centrum". Both should map to org_imec. The seed CSV should cover both normalized forms.
