# Independence and overlap audits

These tables document **temporal overlap, matching balance, and pseudo-replication structure** in frozen catalogs. They are **not** model-performance evidence, skill scores, or ranking-stability results.

Do not cite them as validation-funnel output. Do not treat placeholder ranking files as ranks.

**Validation ranking must not treat 105 units (3 stations × 5 anchors × 7 strata) as iid.** The five 180-day anchors at each station share calendar dates.

## P0-5 named findings (validation anchors)

Read `anchor_named_findings.csv` first. It is the explicit report, not a hidden flag inside a pairwise dump.

1. **B1-R0105 (2016-12-02) ↔ B1-R0101 (2016-12-19)** — 163-day overlap, Jaccard 0.827. These two DJF anchors are not independent.
2. **All 30 same-station pairs** are in `anchor_same_station_pairwise_jaccard.csv`, with `flag_jaccard_ge_0_5` for Jaccard ≥ 0.5 (7 pairs).
3. **Unique years = {2016, 2017} only.** At every station `n_years=2 ≠ n_anchors=5` (`anchor_year_coverage.csv`).
4. **Per-station effective_n = union_days/180** (`anchor_station_effective_n.csv`): B1 ≈ 2.34, S2 ≈ 2.49, P3 ≈ 2.97.
5. **Cross-station identical center:** B1-R0102 = S2-R0105 = 2017-03-27.
6. **105 apparent ranking units are not iid** (see the warning above).

Optional frontier note (`frontier_station_effective_n.csv`): 365-day windows collapse to effective_n about 2.6–3.0. That is an overlap note, not performance.

Ranking CSVs remain schema placeholders with `pending_validation_results=true` and NA ranks.

## P0-6 named findings (M7b event catalog only)

M7a aggregate stress is refused in the same table as M7b episode pairs.

1. **Control rule = station / season / exact length only.** Year and day-of-year are ranking distances, not hard match constraints.
2. **Abutting (gap=0) fraction ≈ 83%** (296/355). Pre-event T/F/Ta `covariate_status=not_in_catalog`; SMDs are NA, not invented.
3. **All 20 n<5 strata** are listed in `event_n_lt5_strata.csv`. **All 7 missing strata** are listed in `event_missing_strata.csv`.
4. **12 same-type flood window-overlap pairs** are listed in `event_flood_same_type_overlaps.csv`. Cross-type same-station overlaps are counted in `event_named_findings.csv`. Date-overlap **effective n = 80** versus 355 episodes.

## How to regenerate

```bash
PYTHONPATH=src python scripts/22_audit_anchor_independence.py
PYTHONPATH=src python scripts/23_audit_event_matching.py
```

Both scripts read existing frozen catalogs. They do not rebuild catalogs and do not run the validation funnel.
