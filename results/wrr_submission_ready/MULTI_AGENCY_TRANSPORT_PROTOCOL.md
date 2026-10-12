# Multi-agency transport protocol (P0-07 extension) — SEALED FOR DESIGN

Written and committed **before** any multi-agency panel was fetched or scored.

## Why this exists

The primary P0-07 confirmation was scored once on 39 never-used USGS HUC4
networks (`p0_07_sealed_confirmation/verdict.json`, pooled contrast
−7.94 pp, empirical arm −1.74 pp). That panel satisfies the "never used"
requirement but not the original design gate of **at least three
climate/hydrologic contexts**: it is single-country and single-agency.

`CONFIRMATION_PROTOCOL_SEALED.md` therefore left multi-agency transport open:

> USGS-only; multi-agency contexts still pending

This protocol closes that gate with agencies that have **no participation in
the v17/v18 programme** (not in `results/v17_fitness/step1_panel/network_split.csv`,
not in the v16 evidence ledger, not in any v18 exploratory artifact).

## Honest disclosure of ordering

This transport test is **designed after** the USGS score was known. It is not a
pristine first confirmation and must never be reported as one. It is a
second-stage external-validity test:

- Primary confirmation: sealed USGS panel, scored once (unchanged).
- Transport test (this file): different agencies, different climate and
  regulation contexts, same frozen configuration, scored once.

Any result here is reported as **transport of a USGS-confirmed screen**, with
the ordering disclosed in the manuscript.

## Frozen configuration (no free parameters)

| Item | Value |
|---|---|
| Freeze file | `P0_06_method_freeze.json` (sha256 recorded in seal) |
| Model | `results/v17_fitness/step9_freeze/certificate.joblib` (unchanged) |
| Predict path | `Certificate.predict` using decision-time visible features only |
| Primary endpoint | hottest-30 mean daily water temperature (°C) |
| Tolerance | 0.5 °C (primary) |
| Retention | 70 % |
| Donor regime strata | frozen `none/sparse/rich` |
| Thresholds / features / conformal level | frozen; **no retuning after unsealing** |

## Eligibility rule (structural; fixed before fetch)

A network enters the transport panel only if all of the following hold:

1. Provider is absent from the v17 roster providers
   (`usgs, chmi, nve_hydapi, gkd_bayern, arso, lubw, foen, rws_waterwebservices, syke`)
   and from every v16/v18 development, descriptive, frontier or scoring artifact.
2. Station series is **river** water temperature (agency waterbody class or
   river-name evidence); lakes, reservoirs, sea and estuary stations are dropped.
3. Series is a provider **daily** statistic in °C. The provider's stated
   statistic is recorded per station; a series that is not a daily water
   temperature statistic is dropped.
4. Network is the agency-native grouping (catchment or river water body) with
   **≥ 2 stations having ≥ 4 complete calendar years** (the frozen minimum and
   a donor requirement).
5. Input files are hashed into `multi_agency_inputs_manifest.csv` before scoring;
   the seal records those hashes.
6. No station in the panel may appear in the v17/v18 study rosters.

## Panel targets

- ≥ 30 networks in total (design floor, not a sufficiency proof).
- ≥ 3 providers and ≥ 3 climate/hydrologic contexts (e.g. boreal, alpine,
  temperate-oceanic, continental).
- Per-provider network counts and station-year counts are reported even when a
  provider under-delivers; under-delivery is a reported failure, not a silent drop.

## Pre-declared success / failure criteria

Scored **once** against the frozen certificate at 70 % retention / 0.5 °C.

Let Δ be the network-clustered difference in consequential-error rate
(screen − longest-run length rule) in percentage points, pooled over the
transport panel.

- **Transport supported** if Δ ≤ −1.0 pp and the 95 % network-clustered interval
  excludes zero, and at least two providers have point estimates in the same
  direction.
- **Transport not supported** if the interval includes zero or the point estimate
  is positive.
- Regardless of outcome: report per-provider and per-context estimates, arm
  decomposition (empirical vs stratified), retention, and every failure.

Rationale for δ = 1.0 pp: the natural-outage (empirical) arm of the primary
confirmation gave −1.74 pp, so a 5 pp gate would be an unreachable bar and a
0 pp gate would be vacuous. δ is fixed now, before any transport data is scored.

## Outcome mapping (pre-declared, no post-hoc rescue)

| Outcome | Action |
|---|---|
| Supported | Report transport as external validity for the frozen screen, with agency and climate caveats. |
| Not supported | Report the failure; restrict headline claims to the USGS-confirmed setting; move the transport result to a limitations subsection. |
| < 3 providers or < 30 networks after honest recruitment | Report under-delivery and keep multi-agency transport as an open limitation. |

No re-scoring, no threshold changes, no dropping of providers after unsealing.

## Execution

```bash
# 1) ingest (per provider) -> multi_agency_ingest/<provider>/networks/...
# 2) python3 scripts/245_multi_agency_prior_access_audit.py
# 3) python3 scripts/249_multi_agency_transport_seal.py --seal
# 4) python3 scripts/250_multi_agency_transport_score.py --unseal-score   # once
```

Artifacts: `multi_agency_seal.json`, `multi_agency_inputs_manifest.csv`,
`p0_07b_multi_agency_transport/verdict.json`.
