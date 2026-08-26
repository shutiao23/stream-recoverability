# v9.1 T2 M/H adapter feasibility

Status: **blocked for corpus-wide production T2**. The adapter contract and a
burned-data smoke grid are executable. A bounded acquisition pilot now exists
for one open development network, but the HUC8 corpus is not yet populated
corpus-wide. The feasibility audit itself performed no download, did not
traverse a sealed vault, and computed no performance metric.

## Information identity

- **M** is station-specific daily `Ta`, `P`, `W`, `RH`, and `Rs` from the NASA
  POWER daily point service at the USGS station coordinate.
- **H** is station-specific USGS daily discharge `F` (parameter 00060) and gage
  height `L` (00065). Static drainage area, elevation, HUC, and coordinates are
  metadata, not time-varying H.
- The implemented nested feature sets are `B_union_D_union_M` and
  `B_union_D_union_M_union_H`. The adapter supplies M/H only; it does not claim
  to implement B or D and it does not alter the historical runner.

The national water-temperature catalog has station coordinates, so M requests
can be planned deterministically. Coordinates do not establish that M was
downloaded or provider-screened. Likewise, station metadata does not establish
that 00060/00065 are available over an evaluable window.

## Calendar alignment

All joins use an exact, timezone-naive provider day label. There is no hourly
resampling. Hydraulics uses the same date label as the target day. For M,
`lag_days = k` has one precise meaning:

```text
source meteorology date = target water-temperature date + k days
```

The predeclared `-1/0/+1` variants are separate sensitivity cells. They must all
be reported or the alignment claim withheld; held-out skill cannot select one.
These shifts test UTC/local calendar-label ambiguity and must not be described
as hydraulic travel time.

## Provider QC

NASA POWER lacks USGS-style observation approval. M is eligible only when the
record is a finite, natural `provider_value`, not the provider fill value. The
audit calls this `provider_screened_non_fill_not_provider_approval` and never
upgrades it to “approved.”

H is eligible only when USGS reports `approval_status=Approved`, the normalized
quality flag is true, and `qc_status` is `approved` or `approved_estimated`.
Provisional observations are excluded. Rejected or absent auxiliaries remain
NA; the adapter never interpolates, forward-fills, or backward-fills them.

## Leakage boundary

Feature centering and scaling are fit exclusively on the supplied training-day
mask. The adapter selects only M/H variable rows, so changing any target water
temperature cannot change its output. Auxiliary values inside an artificial
gap may be transformed only for an information condition that declares them
available. This is covariate availability, not permission to use gap truth.

The adapter does not own the B boundary contract. In particular, it neither
reads a future temperature boundary nor makes offline/online task decisions.
Those remain the responsibility of the recovery-model consumer. Missing-value
handling learned by a model must likewise be fit on training rows only.

## Local evidence and production block

The only complete local daily M/H bundle is
`external_upper_middle_chattahoochee_v1`, a historical, already burned,
never-sealed network. The audit reads only its `split == train` partition and
constructs six non-performance smoke cells: two nested M/H conditions by three
calendar lags. This verifies schema, QC, date alignment, train-only scaling,
and materialization; it is not T2 evidence and cannot enter the HUC8 corpus.

The current open-role HUC8 corpus contains 74 development and 29 validation
network directories with temperature/QC panels. Production remains blocked
until station-specific POWER and USGS 00060/00065 records are materialized
corpus-wide with raw-response hashes, passed through this QC contract, and
connected to model consumers before any performance metric is computed.

## Bounded open-role acquisition pilot

`scripts/76_acquire_t2_information_pilot.py` is hard-bounded to the
deterministic first complete development network, `huc8_01070004`. Its dry run
plans exactly three stations and does not open provider responses. `--execute`
requests station-coordinate POWER `Ta/P/W/RH/Rs` and station/date USGS daily
mean `00060/00065`, stores each raw request/response with SHA-256, applies the
provider QC above, and writes adapter-long Parquet, coverage, schema, failure,
request-log, and manifest artifacts. It reads only `site_id/date` from the open
temperature panel, never a temperature value, and cannot select another
network or role.

The executed pilot is intentionally `passed: false` and
`status: materialized_partial`: all three stations have complete POWER M and
daily discharge F over the provider-returned windows (with 34 provisional F
days excluded), while USGS reports no daily-mean gage-height L series for any
of the three stations. Missing L remains absent rather than filled. No
performance metric or network interval was computed; the artifact purpose is
`pipeline_verification_not_evidence`.

```bash
# Provider-response-free plan (written outside the executed pilot directory)
PYTHONPATH=src python scripts/76_acquire_t2_information_pilot.py

# The only enabled live acquisition scope
PYTHONPATH=src python scripts/76_acquire_t2_information_pilot.py --execute
```

Executable audit:

```bash
PYTHONPATH=src python scripts/75_audit_t2_information_adapters.py
```

The result is
`results/framework/t2_information_adapters_v1/feasibility_manifest.json` and
must retain `passed: false` until the open-role auxiliary corpus exists.
