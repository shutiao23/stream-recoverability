# Multi-agency transport protocol (P0-07 extension) — SEALED FOR DESIGN

Original text written and committed **before** any multi-agency panel was fetched
or scored (commit `5acda75b47`). Two amendments follow, both made and committed
**after ingest attempts but before the panel was sealed or any transport case was
scored**: Amendment 1 (prior-access scope, including the `site_id` catalogue rule
and the exclusion of `nve_hydapi`) and Amendment 2 (assurance strata). The commit
history dates each amendment; no threshold, endpoint, retention, model or success
criterion has changed.

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

## Amendment 1 (before any transport scoring): what "never used" means here

The P0-07 extension audits prior access with
`scripts/245_multi_agency_prior_access_audit.py`, which scans **every CSV in the
repository carrying a `station_id` column**, provider-aware, and classifies use as

- **outcome-bearing** — losses, predictions, scores, metrics; or
- **descriptive** — series-derived summaries, exclusions, span/coverage audits.

A station is eligible only if it is absent from both classes. Pure station
**metadata catalogues keyed by `site_id`** (for example
`results/framework/public_catalog/ehyd_surface_temperature_stations.csv`) carry
no temperature values and cannot have informed a rule, window, model or caption;
they are not treated as series use, and this interpretation is recorded here
before the transport panel is sealed or scored.

This amendment also records why `nve_hydapi` is **not** part of the sealed
transport panel: that provider participated in v17 development, so new NVE
basins are reported separately as a secondary probe, never as transport
confirmation.

## Amendment 2 (before any transport scoring): assurance strata

Two providers publish daily river temperature whose quality flags are not
"checked/approved" at source: SMHI's parameter-4 corrected archive labels every
value `O = Okontrollerade värden` (uncontrolled), and Hub'Eau's long chronicles
are Sandre code 4 (`Non qualifié`). Excluding them would leave too few
climate contexts for the design gate; admitting them silently would overstate
data assurance. The protocol therefore defines two strata, fixed before scoring:

- `quality_checked` — the provider documents the values as checked or coarsely
  checked (e.g. USGS approved/provisional daily values, UK EA provider daily
  mean, Hub'Eau Sandre code 1 where present).
- `provider_published_unqualified` — the provider publishes the series but
  labels it uncontrolled/unqualified (SMHI code O, Hub'Eau code 4).

Scoring and reporting rules:

1. The pre-declared transport rule is evaluated on the **pooled** panel.
2. The verdict is reported **per stratum** as well, and a sensitivity that
   excludes `provider_published_unqualified` is reported with the same
   pre-declared rule.
3. If the pooled and quality-checked-only verdicts disagree, the manuscript
   reports the disagreement and treats transport as not established.
4. Every station carries `quality_assurance` in its `stations.csv`, and the
   stratum is recorded in the seal.

## Amendment 3 (before any transport scoring): a secondary provider stratum

Honest recruitment delivered fewer new-agency networks than the design floor:
Sweden (SMHI) 16 networks under the unqualified stratum, England (UK Environment
Agency) 2 networks. Austria (eHYD) publishes no daily surface-water temperature;
Belgium (waterinfo.be) publishes a real provider daily mean (`DagGem`) but no
station reaches four gap-free calendar years, so it cannot contribute truth
cases; Spain's CEDEX/ROEA has no temperature product and SAIH Ebro yields only
one flagged basin grouping of two stations on different rivers, hundreds of
kilometres apart. That leaves two contexts against a floor of three.

To add information without rewriting the pre-registered rule, the seal may also
contain a **secondary stratum** for networks from a provider that participated in
v17 development but whose stations are individually never used. Norway (NVE,
21 new basins) enters this way, labelled
`panel_role = secondary_development_provider`.

Reporting rules:

1. The pre-declared pooled decision rule is evaluated on the **primary** panel
   only (agencies absent from development). The primary panel is below the
   30-network / 3-context design floor, and that under-delivery is reported as
   such — the floor is not redefined.
2. The secondary stratum is reported separately with the same rule, and an
   "extended" pooled estimate (primary + secondary) is reported alongside it,
   always labelled as including a provider that participated in development.
3. The headline transport sentence may quote the primary panel only.

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
