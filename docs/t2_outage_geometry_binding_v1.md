# T2 v9.1 outage-geometry binding (open roles only)

Status: frozen geometry input, not a model result. The binding does not amend
`design_freeze_v4`, does not run T2, and does not license a T4 claim.

## Existing T4 audit

`scripts/58_score_natural_outages.py` correctly avoids claiming truth on real
missing days. It extracts length and season from the legacy catalogs and plants
that geometry in later observed windows. Its manifest says `passed: false`,
`formal_evidence: false`, `unlabeled_missing_days_scored: false`, and reports no
network interval. The 0.691 network Spearman is an 11-network development point
estimate and is not confirmatory.

The legacy catalogs are retained unchanged for audit:

| catalog | rows | networks | stations | 7--180 d | <7 d | >180 d |
|---|---:|---:|---:|---:|---:|---:|
| `real_missing_blocks.csv` | 1,470 | 12 | 61 | 318 | 1,056 | 96 |
| `willamette_mainstem_real_missing_blocks.csv` | 97 | 1 | 3 | 19 | 75 | 3 |

The old runner does not bind a particular real gap to a particular observed
counterpart before scoring. That is adequate for its explicitly developmental
T4 check, but it is not a frozen T2 geometry interface. It also covers the old
public-river panels rather than the HUC8 open-role corpus.

## Frozen natural-outage catalog

`scripts/74_freeze_t2_outage_geometry.py` is locked to
`open_role_qc/failure_closure6/{development,validation}` and reads only
`site_id,date` from each complete-enough network's `daily_long_qc.csv`, after restricting stations to
`eligible_for_network == true`. It validates both role and network QC manifests
and requires `qualification_mode: failure_closure6`, `qualified_years_min: 6`,
`relaxation_applied: true`, the locked projection trigger, and
`overlap.complete_enough: true`. It refuses any role other than development or validation. Temperature and
qualifier columns are never loaded. Both role manifests must carry the same
locked split SHA (`2405169325fecaeb24bea9a5c9fc5ea66e303c14e41def1e3d32f6853679c1f1`).

For each station, internal missing runs of 7--180 days define empirical
geometry. Every row records network, station, real missing start/end, length,
and start season. A real missing interval always has
`actual_missing_truth_available: false`. It may be benchmarked only when the
catalog also freezes a disjoint, fully observed same-station interval of the
same length and start season, with one observed boundary on each side. The
counterpart is selected by a deterministic SHA-256 rank that does not inspect
temperature values. Rows lacking such a counterpart remain geometry-only and
must not be scored.

The corrected freeze has 2,355 natural geometry rows across all 67 qualified
open networks (47 development, 20 validation); all currently have a nonoverlapping
observed counterpart. A future network without an eligible 7--180 day natural
run would remain in the T2 corpus but contribute no natural-geometry row. These
are catalog facts, not success claims.

## Frozen adversarial stress catalog

The predeclared lengths are 30, 90, 180, and 365 days. Four rules are resolved
per eligible station whenever a fully observed truth-bearing target window
exists:

| stress | placement | donor mask | boundary contract |
|---|---|---|---|
| `record_left_edge` | earliest eligible window | preserve donors | no left; require right |
| `record_right_edge` | latest eligible window | preserve donors | require left; no right |
| `donor_thin` | minimum mean donor availability, SHA tie-break | preserve donors | require both |
| `synchronous_network_outage` | SHA-ranked window | mask every network station in-gap | require both |

All placement decisions use availability only. The adversarial catalog contains
5,406 resolved rows over the same 67-network failure-closure corpus. A row is a
future workload cell, not a score.

## Runner interface

The frozen files live in `results/framework/t2_outage_geometry_v1/`.

- Natural: filter `benchmark_eligible == true`; preserve the real geometry in
  `start_date,length_days,season`, plant at `benchmark_start_date`, and score
  only the held-out observed counterpart.
- Adversarial: plant at `start_date`, then apply `target_mask_scope` and
  `donor_mask_rule`. The target window is fully observed before masking.
- Both catalogs expose `network_id,station_id,start_date,length_days,season` and
  stable `geometry_id` values. `catalog_sha256.txt` contains byte-level hashes;
  the manifest additionally has order-invariant canonical table hashes.

The new module is intentionally separate from `t2_recovery_benchmark.py`.
That runner can call `load_frozen_geometry_bindings(directory)` and expand the
validated CSV rows into work items without changing geometry selection. The
loader rejects byte drift, sealed roles, and rows whose truth contract is not
satisfied.

## Still blocked

- Sealed-role geometry is neither built nor read.
- A future corpus version may contain natural rows without observed
  counterparts; those rows are not benchmarkable.
- Online-causal execution and its one-sided boundary handling are not
  implemented.
- Information cells requiring meteorology M or hydraulics H are unbound.
- Full model scoring and network-level achieved-skill aggregation have not run.
- There are 67 qualified open networks after the declared six-year failure
  closure, below the locked
  100-network interval floor, so network intervals remain withheld.
