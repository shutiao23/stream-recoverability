# T2 open-corpus M/H acquisition

Status: **production path implemented; 1/67 networks materialized**. This is
auxiliary-data acquisition, not T2 performance evidence. No sealed path or
water-temperature value is read, and no recovery metric or network interval is
computed.

## Frozen scope and plan

`scripts/78_acquire_t2_information_corpus.py` discovers only the overlap-
qualified `failure_closure6` development and validation inputs already bound to
the T2 workload. The current deterministic roster contains 67 networks and 340
T2 stations. Each network plan binds the source QC manifest hash, an outcome-
free `site_id,date` projection hash, coordinates, source-specific date windows,
the catalog split SHA, and its own SHA-256. The corpus plan SHA-256 is:

```text
db49ebb9dc00413477ffa00d4b0d25427df3052fc1ea31eebcdc24440bf8280a
```

POWER begins at 1981-01-01, so earlier target windows are explicitly left as
pre-archive attrition rather than sent as invalid requests. USGS F/L requests
retain the full open target window.

## Safety and recovery contract

- Execution is sequential (`parallel_workers: 1`) and every HTTP request has a
  configurable minimum start-to-start interval (default 1 second).
- Live execution requires one explicit scope and exact acknowledgement. A
  bounded selection uses `--network-id` or `--max-networks` plus
  `--acknowledge-network-count N`. The full roster requires `--all` plus
  `--acknowledge-all-network-count 67`.
- Each network writes its own request plan, raw exchanges, response hashes,
  auxiliary Parquet, coverage, provider metadata, failures, schema, and terminal
  manifest. Resume skips a network only after re-hashing every declared artifact
  and every raw response. A corrupt or plan-mismatched boundary fails closed.
  A transport or parser failure is `acquisition_retry_required`, not a terminal
  partial result, so the next invocation retries that network. Provider-confirmed
  absence is terminal `materialized_partial` and remains explicit attrition.
- POWER values are eligible only when finite and unequal to the provider fill
  value. USGS hydraulics are eligible only when `approval_status=Approved`;
  provisional rows remain audited with `value=NA`. Missing F/L is never filled.
- The global attrition table always contains all 67 planned networks, including
  those not yet materialized.

## Verified dry run and one-network execution

The provider-free dry run is stored under
`results/framework/t2_information_adapters_v1/corpus_acquisition_dry_run/`.
It planned 67 networks/340 stations, opened zero provider responses, and reports
all 67 networks as not yet materialized in that isolated dry-run root.

The first new production-path execution was explicitly bounded to
`huc8_02040103` (three development stations). It wrote 205,044 auxiliary rows
from 14 hashed raw responses. POWER M is present for all 15 station-variable
cells with mean eligible coverage 1.0. Approved discharge F is present at all
three stations; daily-mean gage height L is unavailable at all three, so the
network is honestly `materialized_partial`. Its 402 provisional USGS rows all
remain NA. Repeating the same command resumed the terminal network with zero new
provider requests.

## Commands

Provider-free full-roster planning:

```bash
PYTHONPATH=src python scripts/78_acquire_t2_information_corpus.py
```

One explicitly bounded network:

```bash
PYTHONPATH=src python scripts/78_acquire_t2_information_corpus.py \
  --execute \
  --network-id huc8_02040103 \
  --acknowledge-network-count 1 \
  --request-interval-seconds 1.0
```

Safe, sequential full-roster launch (not run during implementation):

```bash
PYTHONPATH=src python scripts/78_acquire_t2_information_corpus.py \
  --execute \
  --all \
  --acknowledge-all-network-count 67 \
  --request-interval-seconds 1.0
```

The all-network command is resumable at network boundaries. It is intentionally
not parallel and should be run under normal provider monitoring rather than
converted into concurrent workers.
