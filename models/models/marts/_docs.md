{% docs __overview__ %}
# Paper → Patent — "The Chips Behind AI"

This atlas traces science-adjacent microchip hardware — EUV lithography,
silicon photonics, neuromorphic computing, and in-memory/emerging memory —
from research paper to US patent. It brings together two independent
populations of documents:

- **Papers**: global scientific literature on these technologies.
- **Patents**: US-granted patents in the same technology space.

The two are connected in three ways:

1. **Direct citation links** — a patent that cites a specific paper as prior
   art (a "non-patent-literature" reference). This is the strongest evidence
   of a documented link between a specific piece of research and a specific
   patent, and it carries a **citation lag**: the time between the paper's
   publication and the citing patent's filing. This is a lag, not a "lead
   time" — a patent can cite a paper for many reasons, and the interval says
   nothing about whether that research caused the invention.
2. **Organisation identity** — papers and patents are each attributed to
   organisations (universities, companies, research labs). The same
   organisation appearing in both populations is resolved to one identity, so
   "how much does this organisation publish vs. patent" is a real comparison
   rather than two disconnected name strings.
3. **Technology clusters** — every paper and patent is placed into one of a
   few hundred clusters of closely related work, based on the similarity of
   its text. Each cluster gets a short, plain-English name and description.
   Clusters roll up further into a handful of headline technology families
   (EUV Lithography, Silicon Photonics, Lasers, Neuromorphic Computing,
   In-Memory & Emerging Memory).

**Two important caveats baked into every number in this atlas:**

- **The patent side is US-only.** Every patent count, share, and concentration
  measure here describes US patenting activity specifically — never global
  patent filings. A technology can be researched heavily worldwide and show
  up as "US-patent-light" here simply because the patenting happened
  elsewhere.
- **Not every link is equally certain.** Every organisation match and every
  paper↔patent link carries two things: how it was matched, and how
  confident that match is (high, medium, or low). A hard citation link and a
  soft "these two orgs are probably the same" guess are never presented as
  if they were the same kind of evidence.

**Where to start**: the organisation entity is the thing both papers and
patents resolve to — open it and follow the connections outward. The
technology-cluster entity is the thing every document is assigned to, and is
the natural way to browse "what's happening in EUV lithography" or "who's
active in neuromorphic computing."
{% enddocs %}

{% docs org_id %}
Canonical identifier for one organisation (e.g. a specific university,
company, or lab), spanning both the paper-side and patent-side populations.
The same real-world organisation can appear under different names or IDs in
each population; this identifier resolves them to one entity so a company's
publishing activity and patenting activity can be compared directly, rather
than joined on a raw name string that would miss spelling variants,
subsidiaries, and renamed institutions.
{% enddocs %}

{% docs match_method %}
How this match or link was established — ranging from an exact shared
identifier (most certain) through a curated lookup, an automated fuzzy name
match, to a resolved citation. Always shown alongside a confidence tier, so
a reader can judge how much weight a given match deserves. Matches too
uncertain to trust outright are never included silently — they're either
resolved by a human reviewer or left out.
{% enddocs %}

{% docs confidence %}
How much trust to place in this match or link — high, medium, or low.
Shown alongside match_method so a hard, direct link (e.g. a patent explicitly
citing a specific paper) is never presented the same way as a soft,
inferred one (e.g. two organisations that merely look similar by name).
{% enddocs %}

{% docs cluster_id %}
The technology cluster this document belongs to — a group of papers and
patents whose text is closely related, given a short human-readable name
and description. Includes a "noise" cluster for documents too dissimilar
from everything else to group meaningfully. Empty until the clustering step
of the pipeline has been run for the current corpus.
{% enddocs %}

{% docs work_id %}
Identifier for one paper in the global scientific literature — the anchor
for every paper-side fact and link in this atlas.
{% enddocs %}

{% docs patent_id %}
Identifier for one US patent — the anchor for every patent-side fact and
link in this atlas.
{% enddocs %}

{% docs filing_date %}
The date this patent's application was filed. This, not the later grant
date, is the anchor for every patent-side time comparison in this atlas:
filing reflects when the invention was actually put forward, while grant
date is delayed by however long the patent office took to review it — a
delay that has nothing to do with the underlying research or invention
timeline.
{% enddocs %}

{% docs publication_date %}
The date this paper was published — the anchor for every paper-side time
comparison in this atlas.
{% enddocs %}

{% docs citation_lag %}
The time between a paper's publication and the filing of a patent that
cites it as prior art. Called a citation lag, deliberately not "lead time"
or "time to market": a citation records that a patent examiner or applicant
pointed to this paper, not that the paper caused or enabled the invention.
Grant date is never used for this measurement, since it reflects patent-office
processing time rather than anything about the research or invention.
{% enddocs %}
