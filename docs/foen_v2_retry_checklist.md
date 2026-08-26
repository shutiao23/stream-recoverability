# FOEN v2 commit-before-retry checklist

The v1 pilot is retired. Its 208 mode-000 objects and v1 registries remain in
place as failed-pilot custody and must not be opened, unsealed, deleted, moved,
or offered to the v2 resume path.

## 1. Pre-commit verification without a value query

```bash
PYTHONPATH=src pytest -q tests/test_foen_sealed_corpus.py
PYTHONPATH=src python scripts/73_cache_foen_sealed_corpus.py
```

The v2 dry-run must report 10 networks, 51 stations, 52 years, and 2,652
station-year requests, with:

- query-template SHA
  `11ace60436fe6edb9836c0d599cd3e5fa722c567270feeb7aa10c9d08de063ff`;
- `provider_requests_opened: false`;
- `query_template_executed: false`;
- `json_decoded/value_fields_inspected/sealed_outcomes_opened: false`;
- `v1_failed_pilot_objects_reused: false`.

Confirm the new v2 locations are empty. Do not inspect the old v1 vault:

```bash
find data/sealed_public_rivers_foen_v2/vault -type f 2>/dev/null
find results/framework/public_catalog/foen_sealed_byte_registry_v2 -type f 2>/dev/null
```

## 2. Commit before retry

Commit the v2 template/split, schema audit, deviation note, custody module,
runner, tests, this checklist, and the `.gitignore`/governance v2 vault
exclusion. Record the full 40-character SHA:

```bash
git rev-parse HEAD
```

Execution rechecks every protected file against that commit. An abbreviated SHA
or uncommitted protected-file drift fails before provider contact.

## 3. Retry exactly one network

```bash
PYTHONPATH=src python scripts/73_cache_foen_sealed_corpus.py \
  --execute \
  --max-networks 1 \
  --acknowledge-sealed foen-sealed-opaque-bytes-no-json \
  --implementation-commit <FULL_V2_IMPLEMENTATION_COMMIT>
```

This writes 208 new objects under the **v2** vault and registry. It never resumes
the 208 v1 objects because the namespaces and registry schemas differ.

The retry manifest must have zero custody failures and:

- `n_objects_registered: 208`;
- `v1_failed_pilot_objects_reused: false`;
- `opaque_response_diversity.n_unique_response_sha256 > 1`;
- `opaque_response_diversity.all_response_bodies_byte_identical: false`;
- `opaque_response_diversity.opaque_response_diversity_gate_pass: true`.

This is only a transport/compilation guard based on response-byte hashes. It is
not value inspection, QC, or evidence. If all 208 v2 bodies are again identical,
stop. Do not open them to diagnose the error.

## 4. Full run only after automatic pilot preflight

```bash
PYTHONPATH=src python scripts/73_cache_foen_sealed_corpus.py \
  --execute \
  --all-networks \
  --acknowledge-sealed foen-sealed-opaque-bytes-no-json \
  --acknowledge-full-corpus foen-all-ten-sealed-networks-authorized \
  --implementation-commit <FULL_V2_IMPLEMENTATION_COMMIT>
```

Before constructing any new provider request, the runner requires all 208 v2
pilot registries to exist, validates their object metadata without opening the
bodies, and enforces the byte-diversity gate. Missing, malformed, or identical
pilot custody blocks the full run.

Release-state 2/3 filtering is no longer attempted in the GraphQL `where`
clause, because the FOEN schema does not expose `releaseState` as a filter.
Release state remains inside the opaque response and is filtered only after a
separately authorized unseal. Downloading still does not make any Swiss network
qualified or countable toward T8.
