# P2-01 closure: why the maintenance case is simulated, not observed

Blueprint item P2-01 asked for a real institutional maintenance and redundancy
deployment case: a network with reference sensors, failure logs and maintenance
reasons, distinguishing battery, ice, flood, low-flow and planned-removal
outages, and reporting how many wrong decisions each management action avoids and
at what cost. The acceptance bar was explicit: *"效果观察"* — observed effects,
with the repaired scenario simulation allowed only to design, never to replace,
the observation.

## What was done instead of asserting infeasibility

We tried to recover observed outage causes from the provider that publishes the
richest per-day metadata in this panel. `results/wrr_submission_ready/amendments/outage_causes/`
classifies **every** missing day of the USGS part of the real incomplete-year
population — 200 stations, 1,361 station-years, 2,921 interior gaps, 68,180
missing days — against USGS's own daily-value qualifier codes, retrieved through
three separate NWIS endpoints (709 raw responses, SHA-256 in
`raw_cache/manifest.csv`).

Findings:

- **No cause-naming qualifier occurs once.** Maintenance, equipment, ice,
  seasonal, discontinued, flood and dry codes: 0 records in 832,983. The
  codes that do occur describe the *present* values (`A` approved, `P`
  provisional, `R` revised, `e` estimated, grade `[4]` incomplete or partial
  aggregate). A missing day simply has no row, so the archive records *that* a
  value is absent, never *why*.
- **What is measurable is the split between provider silence and archive-side
  loss** (network-clustered intervals): 94.9% [88.7, 98.2] of missing days are
  days the provider published no record for at all; 4.8% [1.6, 11.1] were
  published only under a different statistic of the same parameter (daily
  maximum, minimum or median); 0.28% [0.003, 0.70] were published for the target
  statistic and dropped by the archive. Long gaps are almost pure provider
  silence (99% of 30–89-day gaps, 96% of gaps of 90 days or more).
- **The cause-conditional admission rule is a no-op.** "Exclude planned
  maintenance, keep equipment failures" changes the admission of 0 of 1,361
  station-years, because neither cause is ever documented.
- **A genuinely actionable by-product:** 8 gaps in 5 station-years (all
  2024–2025) are days USGS now publishes the target daily mean for — the archive
  snapshot and the live service disagree, so re-ingestion recovers them; and
  3,269 further days are recoverable by widening the statistic filter.

## Consequence for the paper

The maintenance-calendar counterfactual stays **exploratory and is barred from
the abstract and conclusions**; the manuscript says in one sentence why an
observed replacement is impossible on this archive. No claim about autumn
servicing, redundancy investment or regulatory substitution is made.

## What would close P2-01 properly

A provider that publishes gap reasons (none of the eleven here does); USGS
site-file free-text remarks read by hand for the long-gap stations (station
level, undated); district maintenance and calibration logs (not public, data
request); or the instantaneous-value service's richer remark vocabulary, which
was out of scope here and is the most promising next retrieval. Absent one of
those, the honest framing is the one the paper now uses: screen on what the
absence does to the endpoint, not on a presumed cause.
