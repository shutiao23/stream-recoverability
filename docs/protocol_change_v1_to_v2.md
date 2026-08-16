# Protocol change: `design_freeze_v1` to `design_freeze_v2`

`configs/design_freeze_v1.yaml` remains the historical freeze. It is not silently rewritten. The executable default is `configs/design_freeze_v2.yaml`.

This document records protocol repairs made before confirmatory performance is observed. It does not report confirmatory results, invented data hashes, or frontier numbers.

## Why v2 exists

An adversarial review of the v1 freeze found three scientific-identity failures that would invalidate a shared Group D / architecture claim:

1. The external network was labelled Lower Chattahoochee (HUC `03130004`) while the frozen site IDs sit on the Upper-to-Middle main stem (HUCs `03130001` / `03130002`).
2. Main Group D mixed Jinsha bright-sunshine duration (`DH`, hours) with NASA POWER all-sky shortwave (`ALLSKY_SFC_SW_DWN`, MJ/m²/day) under the same column name.
3. NASA POWER `time_standard=UTC` was already requested, but the mismatch with USGS local civil days and POWER's LST default was not predeclared as a time-label alignment sensitivity.

v2 repairs those identities. It does not reopen 2018–2020 `development_test` for tuning.

## A. Network rename

| Item | v1 (historical) | v2 (executable) |
| --- | --- | --- |
| Network id | `lower_chattahoochee_mainstem_case_study` | `upper_to_middle_chattahoochee_mainstem_case_study` |
| Data version | `external_lower_chattahoochee_v1` | `external_upper_middle_chattahoochee_v1` |
| HUC8 | implied Lower `03130004` | Upper `03130001` and Middle `03130002` |
| Site IDs | `02334430`, `02335000`, `02335450`, `02336000`, `02337170` | unchanged |

The confirmatory object is **one** Upper–Middle Chattahoochee mainstem network panel. It is not five independent basins and not internal-style nested-point **M1**. External masks remain a compact 30%-only + blocks + outages replication on one connected panel.

## B. Solar / Group D semantics

Main Group D on **both** networks is `Ta`, `P`, `W`, `RH`, `Rs`, where `Rs` is NASA POWER `ALLSKY_SFC_SW_DWN` in MJ/m²/day.

Jinsha bright-sunshine duration `DH` (hours) is a Jinsha-only sensitivity channel. It is not the main architecture meteorology channel and is not used in the confirmatory external grid. v2 never keeps the column name `DH` with an “actually Rs” comment.

Because Group D identity and units changed, the proposed architecture token is **`s0_abcd_rs_v1`**. The retired token `s0_abcd_v2` is invalid for a main model whose meteorology channel is `Rs`.

Internal `published_v1` retains Jinsha `DH` sunshine hours as a sensitivity-only channel. NASA POWER `Rs` was added by `scripts/24_rebuild_internal_nasa_rs.py`; hydro and CMA/GSOD columns were not edited. Artifact SHA-256 values are recorded in `configs/design_freeze_v2.yaml` and `results/data_audit/internal_nasa_rs_rebuild.json` after the rebuild.

## C. Time standards

NASA POWER requests keep `time_standard=UTC` (already present in the request URL and checked in the response header). This protocol does **not** silently switch to LST.

USGS daily values are date-indexed station-local civil days (EST/EDT as published). POWER without an override defaults to LST. UTC versus that local/LST day is a **calendar-day label-alignment** issue, not hydraulic travel time.

The predeclared `meteorology_alignment_v1` sensitivity is lag ∈ `{-1, 0, +1}` days. Lags are never selected using confirmatory or `development_test` performance. Report all three lags or withhold an alignment claim.

## D. Feasibility gate

`scripts/20_run_confirmatory_evaluation.py --feasibility-only` runs after a finalized roster exists and before evaluate-once:

- Reuses confirmatory preflight (roster, inventory, design, code identity).
- Materialises all 60 external masks.
- Checks approved finite `T` truth, exact mask lengths, and information-condition geometry.
- Writes `confirmatory_feasibility_report.json`, `confirmatory_mask_contract.parquet`, and `confirmatory_coverage_by_site_split_variable.csv`.
- Does not train, does not compute MAE/RMSE/skill, and does not create the once-lock.
- Fails if the once-lock already exists.

Evaluate-once may create the once-lock **only after** that feasibility-equivalent 60-mask constructability check succeeds, either in-process before the lock or by requiring prior feasibility artifacts. The lock must not precede the dry-run.

Ordinary `scripts/08_run_experiments.py` and `ExperimentRunner` cannot train or write skill on `evaluation_split=confirmatory`. That path exists only on the once-locked `scripts/20` runner.

## What is not claimed

- No confirmatory performance, MAE, RMSE, or skill.
- No invented SHA-256 for unbuilt `external_upper_middle_chattahoochee_v1`. Internal NASA `Rs` hashes are named only after `scripts/24_rebuild_internal_nasa_rs.py` writes the files.
- No silent mutation of `design_freeze_v1.yaml`.
- Dual frontiers (climatology-relative and best-simple-baseline-relative) are **declared** in v2 statistics only. This wave does not invent frontier numbers.

## Migration checklist

1. Point `DEFAULT_DESIGN_PATH` and script `--design` defaults at `configs/design_freeze_v2.yaml`.
2. Rebuild confirmatory data as `external_upper_middle_chattahoochee_v1` against v2 after a finalized roster exists.
3. Re-finalize the model roster against the v2 design hash before opening confirmatory values under the new name.
4. Internal main panel NASA `Rs` is now in `published_v1` (additive). `DH` remains sensitivity-only.
5. Run `--feasibility-only` before evaluate-once.
6. Never tune meteorology lags on confirmatory performance.
