# External confirmation recruitment (P0-07 failure收口)

## Finding (authoritative, 2026-10-12)

After correcting stale `candidate_unseen` labels for networks later placed in
the v17 panel:

- Station-years never used anywhere in the repo programme: **26**
- Networks never used in the repo programme: **8**
- Among those, stations with ≥4 complete years: **0**
- Design floor for sealed confirmation: **≥30 networks** with ≥4 complete years/station and ≥3 climate/hydro contexts

Therefore **no sealed never-used confirmation panel can be scored from the current checkout**.  
`scripts/230_wrr_sealed_confirmation.py --unseal` must continue to refuse.

Stale path that must not be used again: re-scoring the opened v17 reserved panel
(including its 8 formerly `candidate_unseen` networks).

Artifacts:

- `confirmation_recruitment_summary.json`
- `confirmation_recruitment_pool.csv` (empty eligible set under the hard rule)

## What counts as eligible

A network is eligible only if all of the following hold before freeze:

1. Absent from v16 prior-access roles other than unused candidate labels that were never later consumed
2. Absent from the v17 fitness panel (`network_split.csv`)
3. Absent from all v18 exploratory scoring/caption selection
4. River waterbody; reference years without imputation; ≥4 complete years per station
5. Input hashes recorded in a new seal file before any feature engineering for confirmation

## External sources already have parsers (ingest, then seal)

| Source | Module | Why useful |
|---|---|---|
| USGS NWIS additional HUC groups | `nwis_temperature.py` | daily mean contract (`statCd=00003`) |
| NVE HydAPI new basins | `nve_water_temperature.py` | measured daily river T |
| Hub'Eau (France) | `hubeau_temperature.py` | new climate/regulatory context |
| UK EA | `uk_ea_temperature.py` | new context |
| SMHI | `smhi_water_temperature.py` | new context |
| ECCC automated (if river-qualified) | `eccc_automated_temperature.py` | only after river QC passes |
| eHYD | `ehyd_temperature.py` | only if daily (not monthly-only) series qualify |

Existing Hub'Eau / eHYD / ECCC directories under `confirmation_daily_qc/networks/` are
mostly empty placeholders (5-byte files) and are **not** a ready panel.

## Execution recipe after recruitment

```bash
# 1) ingest ≥30 networks into a new sealed root (not the v17 panel roots)
# 2) write results/wrr_submission_ready/confirmation_inputs_manifest.csv with sha256
# 3) update confirmation_seal.json hashes
# 4) dry-run, then single unseal score against P0_06_method_freeze.json
PYTHONPATH=src python3 scripts/230_wrr_sealed_confirmation.py --dry-run
PYTHONPATH=src python3 scripts/230_wrr_sealed_confirmation.py --unseal
```

## Manuscript failure收口 (already partially applied)

Until the external panel is scored once:

- Abstract/conclusions may report only retrospective holdout + exploratory labels
- Do not claim independent confirmation of v18 continuum/crossover/dilation/maintenance
- Prefer Journal of Hydrology methods framing if recruitment slips past submission timing
