# Supporting Information S1: Independence and matching audits

These tables document **temporal overlap, matching balance, and pseudo-replication** in frozen catalogs. They are **not** validation-funnel ranks, MAE, skill, or formal recoverability results.

Regenerate with:

```bash
PYTHONPATH=src python scripts/22_audit_anchor_independence.py
PYTHONPATH=src python scripts/23_audit_event_matching.py
```

Machine-readable copies live under `results/audits/`.

## S1.1 Validation anchors (P0-5)

The ranking design has 105 apparent units (3 stations × 5 anchors × 7 strata). Those units are **not iid**. Every station’s five 180-day anchors occupy only calendar years 2016 and 2017 (`n_years=2 ≠ n_anchors=5`).

Named findings:

1. **B1-R0105 (2016-12-02) and B1-R0101 (2016-12-19)** share a 163-day window (Jaccard 0.827).
2. Seven of 30 same-station pairs have Jaccard ≥ 0.5.
3. Per-station effective sample size (union days / 180): B1 2.34, S2 2.49, P3 2.97.
4. **B1-R0102 and S2-R0105** share the identical centre date 2017-03-27.

Frontier 365-day windows collapse to effective *n* about 2.6–3.0. That is an overlap note, not a performance frontier.

Placeholder ranking CSVs keep `pending_validation_results=true` and do not invent ranks.

## S1.2 M7b event/control catalog (P0-6)

M7a aggregate stress is excluded from this table.

1. Controls match on station, season, and exact length only. Year and day-of-year are ranking distances, not hard constraints.
2. 296 of 355 pairs abut (gap = 0; fraction 0.834).
3. Pre-event T/F/Ta standardised mean differences are `not_in_catalog`, not invented.
4. 20 strata have *n*<5; 7 station/event/season cells are empty.
5. 12 same-type flood window-overlap pairs; date-overlap clustering yields effective *n* = 80 versus 355 episodes.

## S1.3 Consequence for later statistics

Cluster bootstrap and overlap-aware effective *n* are required. Daily cells are not independent replicates. These audits do not authorise a model roster.
