# Regulation-panel clean reproduction

The nationwide result is reproducible without any Chattahoochee data. Its cache is
deliberately ignored by Git because it contains 3.38 million re-downloadable USGS
rows and the 55 MB GAGES-II source archive. Compact aggregate results and content
identities are versioned.

## Clean online bootstrap

Create a USGS Water Data API key at <https://api.waterdata.usgs.gov/signup/> and
expose it only to the process. The program sends it in the official `api_key` header
only to `api.waterdata.usgs.gov`; it never writes the key to requests or manifests.

```bash
USGS_WATERDATA_API_KEY='<key>' PYTHONPATH=src \
python scripts/38_run_regulation_panel.py \
  --legacy-transport \
  --bootstrap-equivalence-batches 26 \
  --output-dir results/regulation_panel_v1_legacy_transport
```

This command downloads and verifies the GAGES-II archive, discovers the frozen USGS
roster, populates the first 26 modern-API batches used for equivalence, downloads all
27 official legacy `/dv` batches, requires exact agreement on every approved overlap,
and only then computes metrics. All downloads are restartable and atomically cached
under `data/cache/regulation_panel_v1/`.

## Offline rerun after bootstrap

```bash
PYTHONPATH=src python scripts/38_run_regulation_panel.py \
  --offline \
  --legacy-transport \
  --bootstrap-equivalence-batches 26 \
  --output-dir results/regulation_panel_v1_legacy_transport
```

The offline command fails rather than contacting the network if any required source
or batch is absent. Machine-readable cache readiness and the exact commands are in
`results/regulation_panel_v1_legacy_transport/bootstrap_status.json`; portable SHA-256
identities are in `artifact_manifest.json`.

## Test and format checks

```bash
PYTHONPATH=src pytest -q tests/test_regulation_panel.py
ruff check src/stream_recoverability/analysis/regulation_panel.py \
  scripts/38_run_regulation_panel.py tests/test_regulation_panel.py
```

