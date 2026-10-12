# Sealed confirmation protocol (P0-07)

Status: **sealed for design; not yet scored.**  
All expected numeric outcomes remain `[pending — 探索期数据，不可写入结论]` until this protocol is executed once on networks with no prior development, descriptive, or scoring use.

## Prior-access rule

Eligible confirmation networks must appear in
`prior_access_ledger_reserved_networks.csv` / a refreshed universe roster with
`prior_access_bucket = candidate_unseen` (or an equivalent never-used label), and
must not appear in any v16/v17/v18 development, descriptive, frontier, or
confirmation artifact used to choose rules, windows, models, or captions.

The current v17 `split_role=reserved` panel is **not** eligible as a whole:
28 of 36 reserved networks have prior access (see `prior_access_summary.json`).
Those results may be reported only as a retrospective network holdout.

## Frozen analysis plan (from P0-06)

File: `P0_06_method_freeze.json`

- Primary endpoint: hottest-30 mean (°C)
- Operating point: 70% retention, 0.5 °C tolerance (if the task definition is retained)
- Predict path: `Certificate.predict` with no truth/err/abserr columns
- Natural-outage evaluation is primary; stratified stress test is secondary and separate
- Conformal hyperparameters and feature choices are frozen before unsealing

## Recruitment targets (design gates, not sufficiency proofs)

- At least 30 never-used river networks
- At least three climate/hydrologic contexts
- At least four complete years per station
- Network-level power simulation after recruitment may require expansion; n=30 is a floor, not a claim of adequacy

## Success / failure criteria (lock before unsealing)

1. Declare the target population (natural incomplete years vs designed stress) and δ (minimum useful absolute risk reduction or decision-cost improvement) before seeing scores.
2. Do not reuse the pooled five-percentage-point target as the natural-outage success gate if baseline consequential rates are low.
3. Report network-clustered intervals, per-context performance, retention, and all failures.
4. Score once. No threshold retuning after unsealing.

## Execution entrypoint

```
PYTHONPATH=src python3 scripts/230_wrr_sealed_confirmation.py --dry-run
# after freeze hashes recorded:
PYTHONPATH=src python3 scripts/230_wrr_sealed_confirmation.py --unseal
```

Dry-run writes the candidate list and input hashes without scoring.  
Unseal refuses to run unless `P0_06_method_freeze.json` and input manifests match the recorded seal hashes.

## Failure收口

If confirmation fails: report the failure, remove the corresponding abstract/conclusion claims, and do not retune until significance appears. A bounded Journal of Hydrology methods paper remains an allowed fallback.

## Executed finding (2026-10-12)

Hard prior-access audit against the full programme (not stale v16 labels alone):

- never-used station-years in-repo: 26
- never-used networks: 8
- never-used networks with ≥1 station of ≥4 complete years: **0**
- design floor: 30 networks

**Consequence (superseded later the same day):** unseal scoring was blocked
until external networks were ingested and sealed. That was done: 39 never-used
USGS HUC4 networks were ingested, sealed and scored once
(`p0_07_sealed_confirmation/verdict.json`), and the panel's prior-access label was
then corrected by a repo-wide audit
(`AMENDMENT_prior_access_sealed_panel.md`) with a clean-subset diagnostic. A
pre-registered multi-agency transport test followed
(`MULTI_AGENCY_TRANSPORT_PROTOCOL.md`,
`p0_07b_multi_agency_transport/verdict.json`). The v17 reserved panel was never
re-scored. See `EXTERNAL_CONFIRMATION_RECRUITMENT.md` and
`confirmation_recruitment_summary.json` for the recruitment history.
