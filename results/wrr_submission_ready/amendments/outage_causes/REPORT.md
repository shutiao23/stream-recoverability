# Observed outage causes for the real USGS gaps (blueprint item P2-01)

## What was done

- Retrieved USGS NWIS daily values **with qualification codes** for 200 of 200 USGS stations in the
  real incomplete-year population (`results/v18_closure/e2_archive_deployment/`), covering
  every incomplete calendar year plus the complete years between them.
- Retrieved a second time **without the statistic filter**, so a day whose 00010 daily mean
  was never published can be told apart from a day on which USGS published the same
  parameter under a different daily statistic.
- Retrieved the NWIS **series catalog** (`seriesCatalogOutput=true`) for each station, which
  declares the begin/end coverage of every 00010 daily time series.
- Classified 68,180 missing days inside 2,921 real interior gaps (179 further gaps have no day inside the
  incomplete-year population and are excluded).
- Cached every raw provider response under `raw_cache/` with a SHA-256 in
  `raw_cache/manifest.csv`.
- Search of the provider's own declared coverage needed no cause information at all: the
  peak windows used here were recomputed with the manuscript's own definition and agree
  exactly on 1,361 station-years (max |difference| = 0.0).

## Headline

- **0 of 68,180 missing days and 0 of 2,921 gaps carry any provider-documented cause code.**
- 5.075% of the 68,180 missing days were days USGS *did* publish a 00010 daily value for (any statistic); the archive's hole is on the ingestion or statistic-selection side.
- 0.280% of the 68,180 missing days were days USGS published the *target* statistic, the
  00010 daily mean, and the archive dropped them.
- USGS documents partial data loss per day, as a grade code: 1,004 of 832,983 retrieved records (0.1205%) are graded `[4] Incomplete or Partial Aggregated Record` while the day is present; inside the
  incomplete-year population the count is 815 of 445,442 (0.1830%).

## Coverage: n stations, gaps and missing days

| quantity | value |
|---|---:|
| USGS stations in the incomplete-year population | 200 |
| stations with a daily-value response | 200 |
| stations with a declared 00010 series catalog | 200 |
| incomplete station-years (USGS) | 1,361 |
| gaps in scope (≥ 1 day inside that population) | 2,921 |
| missing days classified | 68,180 |
| provider records retrieved (all statistics, station span) | 832,983 |

## The two shares the parent question asks for, network-clustered

Intervals are a network-clustered bootstrap (2,000 resamples of the network identifier,
2.5th-97.5th percentile), because days and gaps inside one network share a provider,
a climate and an operating practice.

| quantity | n | share | 95% interval |
|---|---:|---:|---:|
| missing days *published then dropped* (any 00010 statistic) | 68,180 | 5.075% | [1.812%, 11.337%] |
| missing days published then dropped (target statistic 00003) | 68,180 | 0.280% | [0.003%, 0.697%] |
| missing days published only under another 00010 statistic | 68,180 | 4.795% | [1.585%, 11.078%] |
| missing days with **no provider record** inside declared coverage | 68,180 | 94.925% | [88.663%, 98.188%] |
| missing days with no provider record outside declared coverage | 68,180 | 0.000% | [0.000%, 0.000%] |
| gaps with at least one provider record | 2,921 | 29.613% | [20.727%, 38.459%] |
| missing days with a cause-naming code | 68,180 | 0.000% | [0.000%, 0.000%] |

00010 daily statistics that carry gaps whose target statistic was never published
(number of gaps, gap-level criterion: no mean record on any day of the gap and at least
half of its days covered by the other statistic):

| statistic description (USGS wording) | gaps |
|---|---:|
| Temperature, water, degrees Celsius (Maximum) | 434 |
| Temperature, water, degrees Celsius (Minimum) | 235 |
| Temperature, water, degrees Celsius (Maximum), Channel WQ | 3 |
| Temperature, water, degrees Celsius (Minimum), Channel WQ | 1 |
| Temperature, water, degrees Celsius (Maximum), TOP | 1 |
| Temperature, water, degrees Celsius (Maximum), TOP, [Top] | 1 |
| Temperature, water, degrees Celsius (Maximum), [Right Bank Pump Stand] | 1 |
| Temperature, water, degrees Celsius (Minimum), [Right Bank Pump Stand] | 1 |

## Cause-naming qualifiers: the count is zero

| token | records observed |
|---|---:|
| `Mnt` | 0 |
| `Eqp` | 0 |
| `Ice` | 0 |
| `Dis` | 0 |
| `Ssn` | 0 |
| `***` | 0 |
| `Rat` | 0 |
| `Fld` | 0 |
| `Dry` | 0 |
| `Bkw` | 0 |

The code cell is compound: `A:[4]` is qualification `A` plus grade `[4]`. Cell shapes returned:
`(blank)`, `A`, `A:R`, `A:e`, `P`.

Every qualification code that *was* returned, with USGS's own definition string from the
response header it came in:

| code | USGS definition (verbatim) | records |
|---|---|---:|
| `A` | Approved for publication -- Processing and review completed. | 822,829 |
| `P` | Provisional data subject to revision. | 502 |
| `R` | Records for these data have been revised. | 398 |
| `e` | Value has been estimated. | 13 |
| `[4]` (grade) | Incomplete or Partial Aggregated Record | 1,004 |
| `(blank)` | empty code cell (the day exists only under a sibling time series) | 9,652 |
| `A:R` | compound cell: qualification plus grade | 398 |
| `A:e` | compound cell: qualification plus grade | 13 |

Zero cause-naming codes in 832,983 retrieved records.
A zero count has no bootstrap interval, so the conservative bound is reported instead:
the rule of three at network level gives an upper 95% bound of
3.896% of missing days (77 networks); the optimistic day-level bound is
0.00440% (68,180 days).

Where USGS documents these codes: the two RDB header blocks
`# Data-value grade codes included in this output:` and
`# Data-value qualification codes included in this output:`, reproduced in full with the
request URLs and per-file SHA-256 in `cause_codebook.md` and `raw_cache/manifest.csv`.
USGS retired the legacy NWIS help page that enumerated the wider remark vocabulary
(https://help.waterdata.usgs.gov/code/qual_cd_query) into a client-rendered Code Dictionary
that now covers parameter codes and observed properties only
(https://waterdata.usgs.gov/blog/wdfn-metadata/), so this study attaches no definition and
no count to tokens it did not observe.

## Observed class mix

| observed class | gaps | share of gaps | missing days in gaps of this class | share of days |
|---|---:|---:|---:|---:|
| `no_provider_record_inside_declared_coverage` | 2,321 | 79.46% | 64,230 | 94.21% |
| `published_other_statistic_for_most_days` | 592 | 20.27% | 3,755 | 5.51% |
| `published_target_statistic_then_dropped` | 6 | 0.21% | 108 | 0.16% |
| `published_target_statistic_for_part_of_gap` | 2 | 0.07% | 87 | 0.13% |

Class definitions:

- `published_target_statistic_then_dropped` — every day of the gap has a USGS 00010 daily
  **mean** record; the hole is entirely an ingestion artefact.
- `published_target_statistic_for_part_of_gap` — at least one day of the gap has a mean
  record and at least one does not.
- `published_other_statistic_for_most_days` — no mean record on any day of the gap, and at
  least half of its days carry the same parameter under another daily statistic (for example
  `Temperature, water, degrees Celsius (Median)`, statistic 00008). The archive's
  statistic filter, not the provider, created the hole.
- `no_provider_record_inside_declared_coverage` — no 00010 record of any statistic, and the
  days fall inside a declared 00010 daily series interval from the series catalog: an
  undocumented interruption inside a series the provider still declares.
- `no_provider_record_outside_declared_coverage` — no records, and the days fall outside
  every declared 00010 daily series interval: the provider declares no daily product then.
  This is *consistent with* seasonal or discontinued operation; it is not a documented cause.
- `no_provider_record_coverage_unknown` — no records and no catalog row to compare against.
- `documented_cause_code` — at least one day carries a cause-naming token. Count:
  0.

## (a) Cause mix by gap length class

Full table in `cause_mix.csv` (gap level and day level, four length classes):

| length class | gaps | no provider record | published then dropped | published, other statistic | documented cause |
|---|---:|---:|---:|---:|---:|
| 1-7 d | 2,317 | 1,729 | 5 | 583 | 0 |
| 8-29 d | 361 | 354 | 1 | 6 | 0 |
| 30-89 d | 143 | 142 | 0 | 1 | 0 |
| 90+ d | 100 | 96 | 2 | 2 | 0 |

## (b) Gaps overlapping the station's climatological peak window

403 of 2,921 gaps (13.80%) hide at least one day of the station's hottest 30-day window. Full table in
`peak_overlap_by_cause.csv`; the gaps in that stratum:

| observed class | gaps in the peak stratum | share | missing days | mean peak-window share hidden |
|---|---:|---:|---:|---:|
| `no_provider_record_inside_declared_coverage` | 333 | 82.63% | 43,255 | 0.2755 |
| `published_other_statistic_for_most_days` | 69 | 17.12% | 2,735 | 0.1048 |
| `published_target_statistic_for_part_of_gap` | 0 | 0.00% | 0 | nan |
| `published_target_statistic_then_dropped` | 1 | 0.25% | 91 | 1.0000 |

No cause dominates the peak stratum because no cause is documented anywhere in it. What can
be said about that stratum is the split between provider silence and archive-side loss, and
it is the same split as everywhere else in the USGS population.

## (c) Admission under a cause-conditional rule

The rule the maintenance discussion implies — planned-maintenance gaps may be excluded,
equipment-failure gaps may not — is evaluated against the 1,361 USGS incomplete
station-years in `admission_counterfactual.json`:

- station-years with a documented maintenance gap: 0
- station-years with a documented equipment gap: 0
- station-years whose admission changes relative to the current default: 0

## (d) What can and cannot be claimed operationally

Can be claimed: a descriptive, provider-documented account of what the archive is missing.
Most missing days are days USGS published nothing for, inside a declared series interval or
outside every declared interval, and that split is measurable without any cause information.
A smaller share are archive-side losses the provider never had an outage for — either the
target statistic was published and dropped (191 days in 8 gaps across 5 station-years, all of
them 2024-2025, i.e. recent enough that the archive snapshot and the live service disagree),
or the same parameter was published under a different daily statistic. USGS also flags a
small share of *present* days as incomplete or partial aggregates.

Cannot be claimed: any cause-conditional rescheduling benefit. The NWIS daily-value service
returns a record only for days it has a value for, so a qualification code rides on an
observed day; a day with no record carries no code. Cause-naming tokens (maintenance,
equipment, ice, seasonal, discontinued, unavailable) were not observed at all in this
population. The simulated-placement counterfactual in the manuscript therefore cannot be
replaced by an observed one.

## What would be needed to do better

1. **USGS site-file remarks** (`https://waterservices.usgs.gov/nwis/site/?format=rdb&siteOutput=expanded`,
   or the site-file served by the modern API): free-text station remarks can mention a
   sensor outage, a gage move or a seasonal removal, but they are station-level and
   undated, so they cannot be joined to a gap day without a manual read. Worth doing for
   the long-gap stations only.
2. **Maintenance and calibration logs**, which are not published. USGS district offices hold
   them; a data request would be needed.
3. **Unit-value (instantaneous) records with their own remark codes.** The `uv` service
   carries a richer remark vocabulary than the daily-value service. If those codes are
   present, a daily record's absence can be attributed at sub-daily resolution. This study
   did not retrieve them; it is the single most promising follow-up.
4. **A provider that publishes gap reasons.** None of the other eight providers in the
   panel publishes a per-day cause field either, so this is not a USGS-specific limit.
5. **A design change**: ask whether the archive should be screened on *why* data are absent
   at all, or on what the absence does to the endpoint. The second question is answerable
   today and is what the manuscript's support-aware screen already does.

## Limits

- USGS only: 200 stations, 1,361 incomplete station-years.
  The other eight providers publish no comparable per-day field.
- Daily values only. The `uv` remark vocabulary was not retrieved (see above).
- Multi-series sites: a day can have a record under one 00010 time series and nothing under
  another; the analysis is at day level and says so. A blank value cell can carry no code
  while a sibling series' cell carries one.
- Retrieval is a snapshot (2026-10-12 06:34:41 -04:00	(natwebvaas01)
  and following); provisional records can be revised.
- Coverage cross-check: 109 stations have
  modern-API series metadata as well as a series catalog row; their declared 00010 daily-mean
  spans agree within one day at 104 of them
  (max span difference 9837 day(s)). The catalog
  is used for the analysis because the modern API rate-limits unauthenticated bulk access.
- The declared coverage interval from the catalog is a coarse declaration (first and last
  record of a series). A gap inside such an interval is *not* proof that the provider owed a
  value that day, and every 'inside declared coverage' count here should be read that way.
- Subsampling: all USGS stations in the incomplete-year population.

