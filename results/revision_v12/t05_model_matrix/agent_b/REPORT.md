# REPORT — Model-source × model-target transfer matrix (revision v12, t05, agent b)

**Script:** `scripts/rev_v12_t05_model_matrix_b.py`
**Output namespace:** `results/revision_v12/t05_model_matrix/agent_b/`
**Date:** 2026-08-28. Every number below was produced by the script from read-only
artifacts plus the dedicated runs described here; no value is taken from any other
source.

## 1. Design

Six model families; the deliverable is a matrix whose **rows** are per-family
*fitting-period stress curves* (losses on artificial gaps wholly inside the
fitting years) and whose **columns** are per-family *outer-split losses*
(artificial gaps in the evaluation years):

| # | Family | Source curve (row) | Target loss (column) |
|---|--------|--------------------|----------------------|
| 1 | Linear interpolation / PCHIP boundary | dedicated run, this script (primary: linear boundary between the two observed gap-boundary days; supplementary `pchip_record` variant: local-window PCHIP through fitting-period observed values) | dedicated run, this script (no read-only artifact existed for family 1) |
| 2 | Seasonal-boundary ridge | dedicated fitting-period run (reuses `_ridge_model`/`_model_frame` from `recovery_roster`) | read-only `confirmation_model_roster_losses.csv` |
| 3 | Donor-covariance ridge | dedicated fitting-period run | read-only `confirmation_model_roster_losses.csv` |
| 4 | XGBoost | read-only `confirmation_empirical_fit_losses.csv` | read-only `confirmation_model_roster_losses.csv` |
| 5 | Small bidirectional LSTM (this work) | dedicated run: 10 networks × 3 seeds, early stopping on a validation slice of the fitting period, seed-averaged for the matrix row | read-only BiLSTM outer losses `lstm_sensitivity_predictions.csv` (14 networks; 10 overlap) |
| 6 | air2stream-equivalent process model | **not computable**: no fitting-period curve exists in read-only artifacts and no new runs were permitted | read-only `independent_air2stream_equivalent/station_gap_losses.csv` (8 USGS networks, 89 units) |

**Common subset:** the 10 confirmation networks that also carry BiLSTM outer
losses (`arso_drava, arso_kamniska_bistrica, foen_aare_aaregebiet,
gkd_bayern_alz, gkd_bayern_fraenkische_saale, huc8_02040102, huc8_03010107,
lubw_neckar, lubw_rhein, rws_rijn_lek_nederrijn`). Dedicated fitting-period
runs used the same nested split as the read-only XGBoost curve (outer 70/30;
inner first-70% fit / last-30% score) and at most **5 placements per
station-gap unit**, gaps {7, 30, 90, 180} for families 1–3 and {7, 30, 90} for
the neural family. Source values are mapped to target placements by
(network, station, gap, season) exactly like the repository's
`empirical_transfer_predictions`, then averaged to station-gap and network
units. Per-cell calibration slopes are OLS slopes (target on source, with
intercept) at the station-gap level.

## 2. Validation: all known reference values reproduced exactly

| Check | Level | Value | Reference |
|---|---|---|---|
| empirical vs XGBoost, second panel, supported horizons | station-gap (874 units) | **0.9453** | 0.945 |
| XGBoost-source vs BiLSTM loss | station-gap (165) / network (14) | **0.3382 / 0.6308** | 0.338 / 0.631 |
| XGBoost-source vs air2stream loss | station-gap (89) / network (8) | **0.1726 / 0.2381** | 0.173 / 0.238 |
| descriptor predictor vs donor-cov ridge loss | network (42) | **0.3871** | 0.387 |
| descriptor predictor vs seasonal ridge loss | network (42) | **0.4304** | 0.430 |
| descriptor predictor vs XGBoost loss | network (42) | **0.5647** | 0.565 |

File: `crosschecks.csv`. The XGBoost row/column of the new matrix therefore
uses exactly the definitions the manuscript already reports.

## 3. Transfer matrix (10-network subset)

Network-level Spearman (rows = source stress curves, cols = target losses):

| source \ target | 1 boundary | 2 seasonal | 3 donor | 4 xgb | 5 bilstm | 6 air2 |
|---|---|---|---|---|---|---|
| 1 linear/PCHIP boundary | **0.952** | 0.879 | 0.867 | 0.770 | 0.600 | — |
| 1 pchip-record variant | 0.988 | 0.891 | 0.758 | 0.806 | 0.248 | — |
| 2 seasonal ridge | 0.952 | **0.830** | 0.867 | 0.745 | 0.552 | — |
| 3 donor ridge | 0.879 | 0.782 | **0.964** | 0.794 | 0.600 | — |
| 4 xgboost | 0.818 | 0.879 | 0.806 | **0.952** | 0.539 | 0.238 |
| 5 bilstm (this work) | 0.527 | 0.283 | 0.400 | 0.600 | **0.685** | — |

Station-gap Spearman:

| source \ target | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| 1 linear/PCHIP boundary | **0.917** | 0.904 | 0.839 | 0.878 | 0.075 | — |
| 1 pchip-record variant | 0.936 | 0.861 | 0.742 | 0.891 | −0.016 | — |
| 2 seasonal ridge | 0.886 | **0.903** | 0.845 | 0.850 | 0.053 | — |
| 3 donor ridge | 0.774 | 0.767 | **0.900** | 0.849 | 0.105 | — |
| 4 xgboost | 0.881 | 0.904 | 0.898 | **0.940** | 0.353 | 0.173 |
| 5 bilstm (this work) | 0.190 | 0.282 | 0.187 | 0.102 | **0.317** | — |

Per-cell calibration slopes (station-gap OLS): `matrix_station_gap_slope.csv`
(e.g. diagonal slopes 0.90–1.01 for families 1–4, 0.50 for the neural cell;
cross-transfer slopes 0.44–0.97 for the statistical families, 0.02–0.57 into
the BiLSTM column). Unit counts per cell: 84–143 units on 10 networks for
families 1–5; the air2stream column is 89 units on 8 USGS networks (the two
network sets do not overlap, so air2stream appears only as a cross-panel
column). `matrix_long.csv` and `matrix_*.csv` carry every value.

**Diagonal vs off-diagonal (families 1–5, core cells):**

| Level | Diagonal mean (n=5) | Off-diagonal mean (n=20) | Gap |
|---|---|---|---|
| Network | 0.876 | 0.707 | **+0.169** |
| Station-gap | 0.795 | 0.581 | **+0.214** |

Restricted to the four statistical families (1–4): network 0.924 vs 0.836
(+0.088); station-gap 0.915 vs 0.856 (+0.059).

**Big-sample check (read-only, 42 networks):** XGBoost self cell 0.951 network /
0.964 station-gap (673 units); XGBoost source vs seasonal ridge 0.690 / 0.818,
vs donor ridge 0.901 / 0.925. On the 8-network USGS air2stream panel: XGBoost
self 0.857 / 0.717, XGBoost source vs air2stream 0.238 / 0.173
(`matrix_extension_42networks.csv`, `air2stream_panel_cells.csv`).

## 4. Neural family (family 5)

- 30 fits: 10 networks × 3 seeds; mask-aware `BidirectionalLSTMImputer`
  (hidden 16, 1 layer), trained on artificial blocks in the fitting-period
  fit years, early stopping (patience 6) on a validation slice (last 25% of
  usable fitting years); scored on artificial gaps in the fitting-period score
  years (≤5 placements per station-gap). Two networks (`gkd_bayern_alz`,
  `gkd_bayern_fraenkische_saale`) trained univariate (1 feature) because donor
  stations begin after the fitting period.
- **Convergence evidence** (`neural_histories.csv`, `neural_summary.csv`,
  `neural_convergence.png`): 15/30 fits early-stopped; 50% hit the 40-epoch
  cap; median epochs run 38.5, median best epoch 34; median best validation
  loss 0.298 °C (IQR 0.21–0.77). Training loss descends monotonically on a
  log scale; validation loss varies across networks (0.11–1.06), with
  occasional early-peak-then-plateau behavior typical of small validation
  sets. Convergence is therefore demonstrated but the small validation set
  makes early stopping noisy (cf. the existing BiLSTM sensitivity, which hit
  its epoch limit >90% of the time; here only 50%).
- **Seed stability** (`seed_stability.csv`): each seed's stress curve vs the
  seed average: network Spearman 0.82–0.87, station-gap 0.63–0.76. Pairwise
  seed curves at station-gap level: 0.14–0.43 — unit-level curves are
  seed-sensitive; network-level rankings are stable.

## 5. Conclusion: pipeline-specific vs shared difficulty

1. **Within the statistical roster (families 1–4) recoverability difficulty is
   largely shared.** Off-diagonal transfer is strong (station-gap 0.77–0.90,
   network 0.75–0.95) and the diagonal is only modestly above it (network
   +0.09). A station-gap that is hard for one statistical family is hard for
   the others, and any family's fitting-period stress curve predicts the other
   families' outer losses about as well as it predicts its own.
2. **Transfer to the neural and process-model pipelines is weak and
   pipeline-specific.** The XGBoost-source curve, which transfers at 0.85–0.94
   to the statistical families, transfers at only 0.353 (station-gap) / 0.539
   (network) to BiLSTM outer loss and 0.173 / 0.238 to air2stream. The neural
   stress curve built here transfers even more weakly (station-gap 0.05–0.28
   to the statistical families' outer losses; 0.32 to its own BiLSTM column).
   Diagonal (self-transfer) strength is high for every statistical family
   (0.90–0.96 station-gap) but the neural self cell is only 0.317 / 0.685,
   and no air2stream self cell exists.
3. **Net conclusion:** recoverability ranking is a shared property of the
   information available to boundary/donor-driven statistical recovery models,
   but it is not a universal property of the gap itself — neural and
   process-model pipelines carry large family-specific difficulty, in line
   with the manuscript's existing BiLSTM (0.338/0.631) and air2stream
   (0.173/0.238) findings, which the matrix reproduces exactly.

## 6. Honest limitations

- Network-level Spearman rests on 10 networks for the core matrix (8 for the
  air2stream column); cells report their exact `n_units`/`n_networks`.
- Family-1 outer losses were computed by this script (no read-only artifact
  existed); the `pchip_record` row is a supplementary variant (local ±2000-day
  PCHIP boundary), not a separate family.
- The air2stream row (fitting-period source) is unavailable by design: no
  read-only fitting-period air2stream artifact exists and no new runs were
  permitted; the air2stream column is cross-panel only.
- The family-5 column is the read-only BiLSTM sensitivity (up to 3 placements
  per unit); the family-5 row is this work's separate BiLSTM instance (hidden
  16, ≤40 epochs). Neural source curves are seed-sensitive at the unit level
  (pairwise 0.14–0.43).
- Fitting-period sources exist only for gaps {7, 30, 90, 180} (matching the
  read-only XGBoost curve); target columns keep their full gap sets wherever
  the source covers them.
- The task description cites `process_hybrid_station_gaps.csv` as the
  air2stream losses; that file holds 50 development/validation networks. The
  8-network/89-unit values in the task and the paper correspond to
  `independent_air2stream_equivalent/station_gap_losses.csv`, which is what
  this analysis used.

## 7. Artifacts (all in `results/revision_v12/t05_model_matrix/agent_b/`)

- `crosschecks.csv` — reference-value reproduction
- `fit_losses_families_1_3.csv` — dedicated fitting-period sources (families 1, 1b, 2, 3)
- `target_losses_family_1.csv` — family-1 outer losses (linear boundary + pchip variant)
- `neural_fit_sources.csv`, `neural_histories.csv`, `neural_summary.csv`, `neural_convergence.png` — neural family
- `matrix_long.csv`, `matrix_network_spearman.csv`, `matrix_station_gap_spearman.csv`, `matrix_station_gap_slope.csv` — the matrix
- `diagonal_cells.csv`, `offdiagonal_cells.csv`, `diagonal_vs_offdiagonal.csv` — diagonal vs off-diagonal
- `seed_stability.csv` — neural seed stability
- `matrix_extension_42networks.csv`, `air2stream_panel_cells.csv` — big-sample and USGS-panel context
- `artifacts_index.csv`, `run_meta.json` — index and parameters
