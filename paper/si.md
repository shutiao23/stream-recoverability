# Supporting Information

This SI package is the markdown source for a Water Resources Research supplement. It does not contain MAE, climatology-relative skill, recoverability-frontier days, or a claim that the proposed model outperforms a baseline.

## Contents

- **Text S1.** Independence and matching audits of validation anchors and the M7b event catalog ([`si_independence_audits.md`](si_independence_audits.md)). These tables document overlap and pseudo-replication. They are not model ranks.
- **Text S2.** Extended methods ([`methods.md`](methods.md)), including the executable M1–M10 grid, official PyPOTS reference settings, proposed architecture `s0_abcd_rs_v1`, and the validation-only funnel.
- **Text S3.** Data and software rights ([`../DATA_RIGHTS.md`](../DATA_RIGHTS.md); machine-readable [`../metadata/data_rights.csv`](../metadata/data_rights.csv)). Yearbook hydrology, CMA `RH`/`DH`, and GSOD-matched columns are not open. Reviewer access is AGU GEMS Data Files for Peer Review.
- **Text S4.** Publication inventory from `scripts/11_make_figures.py` ([`../results/final_results_manifest.json`](../results/final_results_manifest.json); captions in [`figure_captions.md`](figure_captions.md)). Result figures are omitted when their formal inputs are absent.
- **Text S5.** Confirmatory *feasibility* (constructability of the Upper-to-Middle Chattahoochee panel) is a protocol gate. It is not confirmatory performance. USGS hydrology remains `not_opened` until `finalized_model_roster_v1`.
- **Text S6.** Validation-only training-budget diagnostics. The frozen stage-2 rule records `hit_epoch_limit` but does not reject on it. On seed 11, `proposed` restored epoch 195 of a 200-epoch budget (`hit_epoch_limit=true`). Go/no-go also omits this flag, so a later `include_proposed_formally` decision would be possibly budget-dependent. This paragraph is `model_selection_only` and `formal_evidence=false`; it is not a development-test result and contains no MAE, skill, or frontier number.

## What this SI does not include

Pre-freeze files under `results/formal/` are invalid (`../results/formal/PRE_FREEZE_INVALID.md`). Validation-funnel parquet files, if present, are `model_selection_only` and `formal_evidence=false`. They must not be copied into Tables S* as WRR results.
