# Input access route for peer review and for third parties

Status: written 2026-10-12, alongside the amendments. This document answers the
question "how does someone else get the data this paper reads?" — the residual
item of finding F08 (`docs/reviews/`) after the input manifest was built.

## What the study reads

| Input | Size | Where it comes from |
|---|---|---|
| 146 daily temperature panels (station × date, °C) | 30.2 MB | nine providers, routes in `results/wrr_submission_ready/current_data_acquisition.csv` |
| NASA POWER daily 2 m air temperature (development panel) | 0.36 MB | `results/development_v11/independent_air2stream_equivalent/daily_forcing.parquet` |
| Case tables and all derived artifacts | tracked in this repository | `results/v17_fitness/`, `results/v18_closure/`, `results/wrr_submission_ready/` |

Every panel's path, byte count and SHA-256 is in
`results/wrr_submission_ready/current_data_manifest.csv`; the air-forcing hash is
in the same manifest chain. A missing or altered input stops the rebuild rather
than silently changing a result (`scripts/228_wrr_rebuild_from_inputs.py`).

## Three routes, in order of preference

**Route 1 — reproduce from the providers.** Re-download the same products with
the routes recorded per network in `current_data_acquisition.csv`, then verify
against `current_data_manifest.csv`. This is fully public and needs no
permission for eight of the nine providers; it is the route a third party should
use. Retrieval dates and any provider-side revisions will change bytes, so the
hash check is the point: a mismatch means the provider revised the series.

**Route 2 — the frozen panel set for peer review.** Because one provider (LUBW)
reserves copyright on its raw values, the panel set is *not* redistributed in
the public repository. The authors can hand reviewers the exact bytes through
the journal's confidential data channel:

```bash
PYTHONPATH=src python3 scripts/262_wrr_reviewer_input_bundle.py
# -> dist/wrr_study_inputs_v1.tar.gz (7.9 MB) + .sha256
#    manifest: results/wrr_submission_ready/reviewer_input_bundle_manifest.json
```

The bundle contains the 146 panels, the air forcing, and a SHA-256 manifest; it
is built from the same bytes the analysis read and is verified against the input
manifest before it is written.

**Route 3 — reproduce the numbers without the raw panels.** The case tables
(the 51 524 designed cases with every feature and estimator error), the frozen
certificate, the wave-2 confirmation cases
(`results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/`),
the withdrawn first-seal artifacts (preserved for audit transparency), and the
amendment inputs are all tracked in the repository. Every reported number can
be recomputed from them, and `scripts/254_wrr_claim_binding_check.py` recomputes
the headline set. The raw panels are needed only to rebuild cases from scratch.
Wave-2 panel paths and SHA-256 digests are in
`results/wrr_submission_ready/p0_07_wave2_ingest/wave2_inputs_manifest.csv`.
Load the certificate with `constraints-freeze-certificate.txt`
(scikit-learn==1.2.2), not `constraints.txt`'s 1.7.2 pin.

## Licensing summary (evidence quoted in `metadata/data_rights.csv`)

| Provider | Terms |
|---|---|
| USGS | US Government public domain |
| FOEN | opendata.swiss, open use with source |
| GKD Bayern | CC BY 4.0 |
| CHMI | CC BY 4.0 |
| SYKE | CC BY 4.0 |
| NVE | NLOD / CC BY 3.0 NO |
| UK Environment Agency | OGL v3.0 |
| SMHI | CC BY 4.0 SE |
| Hub'Eau | Licence Ouverte / Etalab |
| ARSO | terms require attribution on publication; no named licence |
| Rijkswaterstaat | open data with source and retrieval date |
| LUBW | **copyright reserved** — raw values not redistributed; derived statistics only |

## What is *not* a data problem

The study reuses public archives; it adds no field sampling and needs no ethics
approval. The gaps in this dataset are the object of study, not missing inputs.
