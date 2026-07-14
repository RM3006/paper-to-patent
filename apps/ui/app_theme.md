# UI Color Theme — `apps/ui/app.py`

The visual language is split into two non-overlapping layers: **editorial chrome** (structure, layout, typography) stays strictly monochrome; **semantic colors** are applied only to data values and are imported from `render.py`.

---

## Layer 1 — Editorial Chrome (monochrome)

These four values carry every structural element: backgrounds, borders, dividers, labels, body text, and interactive controls.

| Role | HEX | RGB |
|---|---|---|
| Canvas / card / sidebar background | `#ffffff` | `rgb(255, 255, 255)` |
| Borders, dividers, progress-bar track, dropdown frame, list rules | `#e6e6e6` | `rgb(230, 230, 230)` |
| Muted labels, captions, metric labels, tab text (inactive), secondary text | `#888888` | `rgb(136, 136, 136)` |
| Primary ink — headings, body text, metric values, active tab underline, primary button fill | `#111111` | `rgb(17, 17, 17)` |

### Derived / one-off chrome shades

| Role | HEX | RGB |
|---|---|---|
| Family-group pill background; primary button hover state | `#333333` | `rgb(51, 51, 51)` |
| Secondary button hover background (very light tint over white) | `#f5f5f5` | `rgb(245, 245, 245)` |
| Cluster-detail legend text / secondary label (slightly softer than `#888888`) | `#555555` | `rgb(85, 85, 85)` |
| Button hover shorthand (equivalent to `#111111`) | `#000` | `rgb(0, 0, 0)` |
| Selection-ring fill in technology map scatter (fully transparent) | `rgba(0,0,0,0)` | transparent |
| Selection-ring stroke in technology map scatter | `#000000` | `rgb(0, 0, 0)` |

---

## Layer 2 — Tour Chrome (warm tint)

The guided-tour card uses a warm palette to visually distinguish tutorial chrome from the neutral chrome above. No other element uses these colors.

| Role | HEX | RGB |
|---|---|---|
| Tour card background | `#fdf6e3` | `rgb(253, 246, 227)` |
| Tour card border | `#ecdfb8` | `rgb(236, 223, 184)` |
| Tour nav button text (Back / Next / Finish / Exit) | `#8a6d1f` | `rgb(138, 109, 31)` |
| Tour nav button text — hover state | `#a3821f` | `rgb(163, 130, 31)` |

---

## Layer 3 — Semantic Colors (defined in `render.py`)

These are **not** defined in `app.py`; they are imported from `render.py` and used only on data values — never on chrome elements.

### Technology families

Two grains coexist in `FAMILY_COLORS`/`FAMILY_LABELS` (revised 2026-07-13). The 5-way
**document-level family** (each paper/patent's own direct family) is used on the Overview
scorecard, Family Deepdive, and Organisation Profile. The 3-way **cluster-label family**
(a cluster's majority-vote display label, `seed_cluster_family`) is used only on the
Technology Landscape map, plus a muted "mixed" slot for clusters with no clear majority —
see `seed_cluster_family.sql` for why clusters stay 3-way while documents are 5-way.

**Document-level family (5-way):**

| Family | `FAMILY_COLORS` key | HEX | RGB | Rationale |
|---|---|---|---|---|
| EUV Lithography | `"euv"` | `#3a4a6b` | `rgb(58, 74, 107)` | Deep navy — cool, technical, industrial |
| Lasers | `"lasers"` | `#c1666b` | `rgb(193, 102, 107)` | Dusty rose — coherent light, warm without danger-red |
| Silicon Photonics | `"si_photonics"` | `#5a8fa8` | `rgb(90, 143, 168)` | Steel blue — light through glass and silicon |
| Neuromorphic | `"neuromorphic"` | `#7a6c91` | `rgb(122, 108, 145)` | Slate purple — neural/biological-digital bridge |
| In-Memory Compute | `"in_memory"` | `#6a9c89` | `rgb(106, 156, 137)` | Sage green — storage, data, growth |

**Cluster-label family (3-way, Technology Landscape map only):**

| Family | `FAMILY_COLORS` key | HEX | RGB | Rationale |
|---|---|---|---|---|
| Silicon Photonics & Lasers | `"silicon_photonics"` | `#8e7a8a` | `rgb(142, 122, 138)` | Blend of Silicon Photonics `#5a8fa8` + Lasers `#c1666b` |
| Neuromorphic & In-Memory Compute | `"neuromorphic_in_memory"` | `#72848d` | `rgb(114, 132, 141)` | Blend of Neuromorphic `#7a6c91` + In-Memory `#6a9c89` |
| Mixed | `"mixed"` | `#8f8f8f` | `rgb(143, 143, 143)` | Neutral grey (zero saturation) — reads as "no dominant family," distinct from the 3 hued colors |
| Frontier / Unclustered | `"noise"` | `#d1d5db` | `rgb(209, 213, 219)` | Light grey — unclustered / frontier documents |

Constant: `render.FAMILY_COLORS: dict[str, str]`.

### Document type

Used whenever papers and patents are shown together (UMAP scatter toggle, velocity trend lines, org-profile output/intake split).

| Document type | Constant | HEX | RGB |
|---|---|---|---|
| Research paper | `render.PAPER_COLOR` | `#3b82f6` | `rgb(59, 130, 246)` |
| US patent | `render.PATENT_COLOR` | `#f59e0b` | `rgb(245, 158, 11)` |

### Confidence / link quality

Used in org-profile confidence badges and NPL link provenance chips.

| Level | Constant | HEX | RGB |
|---|---|---|---|
| High (DOI match / ROR / seed) | `render.CONFIDENCE_HIGH` | `#22c55e` | `rgb(34, 197, 94)` |
| Medium (fuzzy title / fuzzy org) | `render.CONFIDENCE_MEDIUM` | `#94a3b8` | `rgb(148, 163, 184)` |
| Low / unresolved | `render.CONFIDENCE_LOW` | `#ef4444` | `rgb(239, 68, 68)` |

Helper: `render.confidence_color(level: str) -> str` maps `"high"` / `"medium"` / `"low"` to the above.

### HHI concentration scale

Used in the family-detail asymmetry panel and cluster-detail HHI badge. Continuous interpolation from diffuse (green) to concentrated (red).

| Anchor | HEX | Meaning |
|---|---|---|
| `t = 0` (diffuse, many assignees) | `#22c55e` | Open, competitive market |
| `t = 1` (concentrated, few assignees) | `#ef4444` | Dominant assignee(s) |

Helper: `render.hhi_color(t: float) -> str` where `t` is the HHI value in [0, 1].

### Noise / unclustered bucket

| Role | Constant | HEX | RGB |
|---|---|---|---|
| Frontier / Unclustered dots in technology map | `render.NOISE_COLOR` | `#d1d5db` | `rgb(209, 213, 219)` |

---

## Design Rules (from module docstring)

- **Chrome never takes a semantic hue.** Borders, backgrounds, labels, and controls are always from Layer 1/2.
- **Data values never take a chrome hue.** Family, document-type, confidence, and HHI colors are always from Layer 3.
- **Family colors are the dominant categorical signal.** When a chart can be coloured by family or by document type, family takes precedence unless the view explicitly contrasts paper vs patent.
- **HHI and confidence share green/red anchors intentionally** — green = good signal / open market; red = weak signal / concentrated. Never used simultaneously in the same panel.
