# FOEN commit-before-first-download checklist

No command in this checklist authorizes scoring or unsealing. The first two
sections must be completed and committed before the first value-bearing FOEN
HTTP request.

## 1. Verify without provider contact

```bash
PYTHONPATH=src pytest -q tests/test_foen_sealed_corpus.py
PYTHONPATH=src python scripts/73_cache_foen_sealed_corpus.py
```

The dry manifest must report exactly:

- `n_networks_planned: 10`
- `n_stations_planned: 51`
- `n_calendar_years_per_station: 52`
- `n_station_year_requests_planned: 2652`
- `provider_requests_opened: false`
- `query_template_executed: false`
- `content_parsed/json_decoded/value_fields_inspected: false`
- the locked split, catalog, and query-template SHA-256 values from BL-018.

Confirm that no FOEN provider vault or registry object was created by dry-run:

```bash
find data/sealed_public_rivers_foen_v1/vault -type f 2>/dev/null
find results/framework/public_catalog/foen_sealed_byte_registry_v1 -type f 2>/dev/null
```

Both commands must print nothing before the first execution.

## 2. Commit the implementation before executing

Commit at least these files together:

- `src/stream_recoverability/data/foen_sealed_corpus.py`
- `scripts/73_cache_foen_sealed_corpus.py`
- `tests/test_foen_sealed_corpus.py`
- this checklist
- `.gitignore` and `src/stream_recoverability/governance.py` with the FOEN vault
  exclusion
- the locked FOEN catalog, split, canonical CSV, GraphQL template, and protocol
  condition note (unchanged bytes are acceptable; they must exist in the commit
  tree).

Record the full commit SHA:

```bash
git rev-parse HEAD
```

The execution runner rejects abbreviated SHAs and verifies that every protected
path byte-matches that commit. Unrelated dirty worktree paths do not authorize
or prevent custody, but any drift in a protected path fails closed.

## 3. First-download pilot: one sealed network, still no parsing

Replace `<FULL_IMPLEMENTATION_COMMIT>` with the committed 40-character SHA:

```bash
PYTHONPATH=src python scripts/73_cache_foen_sealed_corpus.py \
  --execute \
  --max-networks 1 \
  --acknowledge-sealed foen-sealed-opaque-bytes-no-json \
  --implementation-commit <FULL_IMPLEMENTATION_COMMIT>
```

The deterministic first network is `foen_doubs_rhonegebiet`: four stations ×
52 years = 208 response objects. Every successful response body must be streamed
directly to the provider vault, hashed while writing, changed to mode `000`, and
paired with one strict registry JSON. Do not open an object to inspect whether a
year is empty or valid; a successful GraphQL response with an empty data array
is still an opaque sealed response.

After the pilot, check only filesystem/registry metadata:

```bash
find data/sealed_public_rivers_foen_v1/vault -type f -perm /0777 -print
find data/sealed_public_rivers_foen_v1/vault -type f | wc -l
find results/framework/public_catalog/foen_sealed_byte_registry_v1 -type f | wc -l
```

The first command must print nothing. On a failure-free fresh pilot, the two
counts must both be 208. If the run is interrupted, rerun the same command: only
exact object+registry pairs are resumed, without reopening sealed bytes. A
missing half, schema drift, size drift, or mode drift is a custody failure and
must not trigger blind redownload.

## 4. Full ten-network byte acquisition

Only after the one-network manifest has zero custody failures:

```bash
PYTHONPATH=src python scripts/73_cache_foen_sealed_corpus.py \
  --execute \
  --all-networks \
  --acknowledge-sealed foen-sealed-opaque-bytes-no-json \
  --acknowledge-full-corpus foen-all-ten-sealed-networks-authorized \
  --implementation-commit <FULL_IMPLEMENTATION_COMMIT>
```

A complete failure-free corpus has 2,652 registered station-year objects.
Downloading does not make any network qualified or countable toward T8. There is
no development-time read/QC method in the FOEN custody module. Parsing,
300-day-year QC, eight-common-year attrition, and scoring require a separate,
explicitly authorized one-time unseal procedure that is not implemented here.
