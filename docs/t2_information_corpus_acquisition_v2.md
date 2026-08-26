# T2 M/H acquisition v2: legacy NWIS network batches

Status: **v2.3 provider-code corrections implemented; resume held until tests and
operator handoff**.

## Why v2 exists

The first corpus-wide OGC run was stopped after repeated HTTP 429 responses in
an environment without `USGS_API_KEY`. Its existing root is retained unchanged
as a v1 transport audit. At shutdown it contained seven terminal partial
networks, thirteen retry-required networks, and one interrupted directory.

USGS documents that modern API keys raise rate limits and exposes limit state in
response headers. Its migration guide says more than a few OGC requests per hour
requires a key. USGS also continues to list the original Water Services as
production-ready. The legacy daily-values service supports multiple sites in
one request plus `parameterCd=00060,00065` and `statCd=00003` filters:

- https://api.waterdata.usgs.gov/docs/ogcapi/keys/
- https://api.waterdata.usgs.gov/docs/ogcapi/migration/
- https://api.waterdata.usgs.gov/docs/
- https://waterservices.usgs.gov/docs/dv-service/daily-values-service-details/

The v2 correction is therefore a transport change, not a data or estimand
change. It has independent code, schema, request-plan SHA, raw custody, network
manifests, attempt archives, and output root:

```text
data_versions/global_network_corpus_v1/
  open_role_auxiliary_legacy_v2/failure_closure6/
```

No v1 artifact is reused as v2 input. V1 is read only by the separately invoked
transport-regression audit and is never mutated.

## Frozen v2 plan

The outcome-free failure-closure roster remains 67 networks and 340 stations.
For every network, v2 sends one legacy NWIS RDB request containing all qualified
sites, both H parameters, the daily-mean statistic, and the union minimum and
maximum dates. Returned rows are then filtered back to each station's locked
window. The largest network request is estimated at 179,952 site-days; all 67
are below the predeclared 200,000-site-day one-request bound. Consequently the
full plan contains exactly:

- 67 Legacy NWIS network-batch requests for F/L;
- 340 station-specific NASA POWER requests for M;
- 407 provider requests total, sequential and never parallel.

Corpus plan SHA-256:

```text
681f4bb3db4fbdcc78b3129fc028832a7adc4a3b48dfdf5d7fb1790bc0d78edf
```

This v2.3 SHA binds the parser contract and locked provider nonnumeric-code
roster into every network SHA.

## Provider QC and retry safety

- Legacy RDB values retain the raw qualifier. Only a qualifier whose approval
  prefix is `A` (`A`, `A:e`, `A:R`, and similar colon-qualified forms) is
  eligible. `P` and every other non-A finite value remain audited with `value`
  set to NA.
- Every legacy value also retains exact `raw_text`. The locked provider codes
  `Ice`, `Eqp`, and `***` are not treated as numbers: `value` and `raw_value` are NA,
  `quality_approved` is false, `approval_status` is `Provisional`, and
  `qc_status` is `excluded_non_numeric_provider_code`, regardless of qualifier.
  USGS RDB comments identify `Eqp` as equipment malfunction and `***` as value
  unavailable. Any other nonempty nonnumeric provider text fails closed. The
  v2.3 preflight scans every current raw `response.rdb` and requires the observed
  nonnumeric set to equal exactly `{Ice, Eqp, ***}`; the newly identified `***`
  shape occurs in nine rows and carries qualifier `P`.
- Approved estimated qualifiers such as `A:e` retain approval but use
  `qc_status=approved_estimated`.
- F remains converted by `ft3/s * 0.028316846592`; L remains converted by
  `ft * 0.3048`. Source is explicitly `usgs_legacy_nwis_dv_rdb`, never
  `usgs_ogc_daily`.
- POWER retains its finite, non-fill provider screen. Missing sources are not
  interpolated or filled.
- Default request spacing is three seconds. HTTP 429, temporary 5xx, timeouts,
  and network failures receive deterministic exponential retry with no jitter:
  four retries, 15-second initial backoff, 240-second cap, and a 120-second
  minimum global cooldown after 429.
- Exhausting one request's retry budget opens a global circuit and stops the
  selected run. Broad per-station exception handling cannot continue hammering
  either provider.
- A complete terminal network is hash-verified and resumed. Before retrying any
  v2 directory with a nonterminal manifest or no manifest, every current file is
  moved into `attempts/attempt_XXXX/`; the archive records every relative path,
  byte count, SHA-256, reason, and total bytes. Nothing is deleted or mixed into
  the new attempt.
- Resume verifies both sides of every exchange: request artifact/SHA and response
  artifact/SHA. Before the first provider call, an atomic root execution manifest
  is written with `status=in_progress`; normal, circuit-break, and conservative
  failure exits atomically replace it with the terminal state. Previous root
  states are retained under `root_run_history/`.
- If a crash leaves `.attempt_XXXX.in_progress`, the next invocation validates
  its archive intent, moves the remaining current files into that same staging
  directory, rebuilds the complete inventory, and atomically promotes it to
  `attempt_XXXX`. Collisions fail closed while preserving both sides for manual
  recovery.

## Pre-v2.3 terminal migration

Older v2/v2.1/v2.2 terminal networks are not edited in place. V2.3 adds the
locked `***` contract and therefore changes every network plan SHA. On resume each
stale terminal is first moved intact into an audited attempt with reason
`terminal_rebuild_parser_contract_v2_3`, then rebuilt under the v2.3 contract.
Interrupted directories are archived with reason `interrupted_missing_manifest`.
This is an explicit rebuild, not a silent manifest migration.

## Real one-network pilot

Only `huc8_02040103` was executed. It made four provider calls—one Legacy NWIS
network batch and three POWER point requests—with zero retry and no open
circuit. The real RDB response produced 34,174 H rows with these qualifiers:

| qualifier | rows |
|---|---:|
| A | 30,727 |
| A:e | 2,949 |
| A:R | 96 |
| P | 401 |
| P:e | 1 |

There are 33,772 A-approved F rows. All 402 P/P:e rows are NA. Daily-mean L is
absent for all three sites, matching the OGC audit, so the network is honestly
`materialized_partial`.

The separate v1-v2 regression compared every approved OGC H row against v2:

- OGC rows: 33,772;
- legacy rows: 33,772;
- one-to-one overlap: 33,772;
- exact values: 33,772;
- missing or extra rows: 0 / 0;
- maximum absolute converted-value difference: 0.0;
- regression status: passed.

This verifies transport equivalence for one open network only. It is not T2
performance evidence.

## Commands

Provider-free dry run:

```bash
PYTHONPATH=src python scripts/79_acquire_t2_information_corpus_v2.py
```

Reproduce the bounded pilot or integrity-check its resume boundary:

```bash
PYTHONPATH=src python scripts/79_acquire_t2_information_corpus_v2.py \
  --execute \
  --network-id huc8_02040103 \
  --acknowledge-network-count 1 \
  --request-interval-seconds 3 \
  --max-transient-retries 4 \
  --retry-backoff-initial-seconds 15 \
  --retry-backoff-max-seconds 240 \
  --http-429-cooldown-seconds 120
```

Reproduce the transport regression:

```bash
PYTHONPATH=src python scripts/80_compare_t2_information_transports.py \
  --network-id huc8_02040103
```

Safe sequential full-v2 restart command (documented, **not executed**):

```bash
PYTHONPATH=src python scripts/79_acquire_t2_information_corpus_v2.py \
  --execute \
  --all \
  --acknowledge-all-network-count 67 \
  --request-interval-seconds 3 \
  --max-transient-retries 4 \
  --retry-backoff-initial-seconds 15 \
  --retry-backoff-max-seconds 240 \
  --http-429-cooldown-seconds 120
```

This command resumes only integrity-verified v2 terminal networks. It neither
opens nor rewrites the OGC v1 audit root.
