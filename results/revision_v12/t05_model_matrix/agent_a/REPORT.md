# Model-source x model-target transfer matrix (agent A)

Adversarial-pair analysis of whether stream-temperature gap-recoverability rankings transfer across model families. Source rows are fitting-period stress curves; target columns are outer evaluation-period losses. Spearman rank correlations at network and station-gap level, plus an OLS calibration slope (target on source) per cell.

## Families and evidence sources

| # | family | source stress | target outer loss |
|---|--------|---------------|-------------------|
| 1 | pchip_or_linear (linear boundary / PCHIP) | fitting-period run (this analysis) | linear/PCHIP outer evaluation (this analysis) |
| 2 | seasonal_boundary_ridge | fitting-period run (this analysis) | read-only roster (confirmation + development panels) |
| 3 | donor_blup_ridge | fitting-period run (this analysis) | read-only roster (confirmation + development panels) |
| 4 | xgboost_b_d | read-only empirical fit losses (confirmation, development, second-confirmation) | read-only roster + lstm-sensitivity + air2stream scoring files |
| 5 | bilstm | new training: 12 networks x 3 seeds, early stopping on fitting-period validation (this analysis) | read-only lstm_sensitivity_predictions.csv (frozen BiLSTM) |
| 6 | air2stream | read-only calibration RMSE per station (model_parameters.csv) | read-only independent_air2stream_equivalent/station_gap_losses.csv |

Note: family 6 follows the task specification of 8 networks / 89 station-gaps, which corresponds to the published 8-equation air2stream equivalent on second-confirmation USGS networks. The separate air2stream-inspired ridge proxy on the development panel (process_hybrid_station_gaps.csv, 50 networks) is a distinct read-only artifact; its manifest reports only target-vs-target XGBoost-vs-hybrid station-gap Spearman 0.373, not a fitting-period stress, so it is not a matrix row.

## Panels and coverage

Fitting-period stress placements for families 1-3 (new runs, 12 networks, <=5 placements per station-gap):

```
              panel            model_family  n_placements  n_networks
 first_confirmation        donor_blup_ridge           595           8
 first_confirmation         pchip_or_linear           595           8
 first_confirmation seasonal_boundary_ridge           595           8
second_confirmation        donor_blup_ridge           300           4
second_confirmation         pchip_or_linear           300           4
second_confirmation seasonal_boundary_ridge           300           4
```

Family-1 outer target placements (new runs, no model fitting):

```
                 panel  n_placements  n_networks
development_validation         30635          56
    first_confirmation         28728          42
   second_confirmation         28557          57
```

- **first_confirmation**: 42 networks; read-only roster families 2-4, family 1 computed here, frozen BiLSTM on 10 networks.
- **second_confirmation**: air2stream (8 networks/89 station-gaps), frozen BiLSTM (4 networks), XGBoost empirical predictions; family 1 computed here (57 networks).
- **development_validation**: 51-56 networks; read-only development roster families 2-4, XGBoost empirical fit losses; family 1 computed here (56 networks).

## First-confirmation submatrix (panel-consistent, families 1-5)

Same-panel cells on the first-confirmation networks, which is the panel the read-only roster targets come from. The bilstm row is network-granularity (10 networks); all other cells are station-gap-granularity.

```
target_family            pchip_or_linear  seasonal_boundary_ridge  donor_blup_ridge  xgboost_b_d    bilstm
source_family                                                                                             
pchip_or_linear                 0.976190                 0.928571          0.904762     0.904762  0.619048
seasonal_boundary_ridge         0.976190                 0.928571          0.904762     0.904762  0.547619
donor_blup_ridge                0.928571                 0.976190          0.952381     0.928571  0.738095
xgboost_b_d                     0.721903                 0.735192          0.937444     0.939065  0.672727
bilstm                         -0.042424                 0.042424         -0.200000    -0.236364  0.284848
```

## Headline network-level Spearman matrix (source rows x target columns)

Each cell is the best-covered panel result (see `matrix_cells_detail.csv` for per-panel cells).

| source \ target | pchip_or_linear | seasonal_boundary_ridge | donor_blup_ridge | xgboost_b_d | bilstm | air2stream |
|---|---|---|---|---|---|---|
| pchip_or_linear | 0.976 | 0.929 | 0.905 | 0.905 | 0.619 | -0.800 |
| seasonal_boundary_ridge | 0.976 | 0.929 | 0.905 | 0.905 | 0.548 | -0.400 |
| donor_blup_ridge | 0.929 | 0.976 | 0.952 | 0.929 | 0.738 | 0.000 |
| xgboost_b_d | 0.642 | 0.456 | 0.852 | 0.914 | 0.673 | 0.238 |
| bilstm | -0.042 | 0.042 | -0.200 | -0.236 | 0.285 | n/a |
| air2stream | -0.286 | n/a | n/a | 0.095 | n/a | 0.643 |

Number of networks per cell:

```
                         pchip_or_linear  seasonal_boundary_ridge  donor_blup_ridge  xgboost_b_d  bilstm  air2stream
source_family                                                                                                       
pchip_or_linear                        8                        8                 8            8       8           4
seasonal_boundary_ridge                8                        8                 8            8       8           4
donor_blup_ridge                       8                        8                 8            8       8           4
xgboost_b_d                           57                       51                51           51      10           8
bilstm                                10                       10                10           10      10           0
air2stream                             8                        0                 0            8       0           8
```

## Calibration slope per cell (OLS, target on source, network level)

| source \ target | pchip_or_linear | seasonal_boundary_ridge | donor_blup_ridge | xgboost_b_d | bilstm | air2stream |
|---|---|---|---|---|---|---|
| pchip_or_linear | 0.690 | 0.759 | 1.019 | 0.713 | 6.849 | -0.141 |
| seasonal_boundary_ridge | 0.695 | 0.766 | 1.008 | 0.707 | 8.718 | -0.092 |
| donor_blup_ridge | 0.540 | 0.613 | 0.871 | 0.608 | 6.098 | -0.030 |
| xgboost_b_d | 1.001 | 0.456 | 0.810 | 0.879 | 4.615 | 0.055 |
| bilstm | -0.005 | -0.002 | -0.020 | -0.016 | 0.317 | n/a |
| air2stream | -0.723 | n/a | n/a | -0.175 | n/a | 0.303 |

## Station-gap-level Spearman matrix

Cells merged on (network, station, gap) within a panel. The bilstm and air2stream rows are network-/station-granularity by construction (unit row equals network row).

| source \ target | pchip_or_linear | seasonal_boundary_ridge | donor_blup_ridge | xgboost_b_d | bilstm | air2stream |
|---|---|---|---|---|---|---|
| pchip_or_linear | 0.953 | 0.936 | 0.801 | 0.899 | 0.295 | -0.040 |
| seasonal_boundary_ridge | 0.906 | 0.919 | 0.799 | 0.863 | 0.223 | -0.054 |
| donor_blup_ridge | 0.768 | 0.787 | 0.918 | 0.862 | 0.256 | -0.242 |
| xgboost_b_d | 0.689 | 0.627 | 0.883 | 0.944 | 0.328 | 0.173 |
| bilstm | -0.042 | 0.042 | -0.200 | -0.236 | 0.285 | n/a |
| air2stream | -0.051 | n/a | n/a | 0.160 | n/a | 0.626 |

## Pooled network-level matrix (across panels)

Robustness view: each side aggregated to network means, then merged by network id across all panels. Pooling mixes panels whose networks differ in climate/period, which dilutes the panel-consistent cells (e.g. (4,4) drops from 0.94 to 0.62); cells with 4 fragile second-confirmation networks (rows 1-3, air2stream column) are the main distorter. The bilstm row reaches 12 networks here (10 first + 2 carried second confirmation).

| source \ target | pchip_or_linear | seasonal_boundary_ridge | donor_blup_ridge | xgboost_b_d | bilstm | air2stream |
|---|---|---|---|---|---|---|
| pchip_or_linear | 0.056 | 0.643 | 0.619 | 0.210 | 0.548 | -0.800 |
| seasonal_boundary_ridge | 0.056 | 0.643 | 0.619 | 0.210 | 0.548 | -0.800 |
| donor_blup_ridge | 0.413 | 0.714 | 0.595 | 0.497 | 0.476 | 0.000 |
| xgboost_b_d | 0.494 | 0.393 | 0.659 | 0.618 | 0.618 | 0.310 |
| bilstm | 0.140 | 0.042 | -0.200 | -0.021 | 0.364 | n/a |
| air2stream | -0.119 | n/a | n/a | 0.095 | n/a | 0.643 |

## Diagonal (self-transfer) vs off-diagonal (cross-transfer)

```json
{
  "diagonal_network_spearman_mean": 0.7831006901595138,
  "diagonal_network_spearman_median": 0.921163542340013,
  "diagonal_network_spearman_sd": 0.2727986221247321,
  "diagonal_station_gap_spearman_mean": 0.7742305423495986,
  "mann_whitney_diag_greater_p": 0.032979233470868,
  "mann_whitney_diag_greater_u": 116.5,
  "n_diagonal_cells": 6,
  "n_off_diagonal_cells": 26,
  "off_diagonal_network_spearman_mean": 0.4344668650339131,
  "off_diagonal_network_spearman_median": 0.6307579293060237,
  "off_diagonal_network_spearman_sd": 0.5266047649591853,
  "off_diagonal_station_gap_spearman_mean": 0.40121862858037616
}
```

- Diagonal network-level Spearman: mean 0.783 (median 0.921), vs off-diagonal mean 0.434 (median 0.631).
- One-sided Mann-Whitney (diagonal > off-diagonal, cells as units): U = 116.5, p = 0.0330.
- Engineered-feature block (families 1-4) only: self-transfer mean 0.943; all block cells (incl. off-diagonal) mean 0.880 — the block is internally nearly saturated, so the diagonal-vs-off-diagonal gap is driven by the neural (5) and process-model (6) families.

## Neural family: early-stopping convergence and seed stability

Training: mask-aware bidirectional LSTM (hidden 16), 40 windows x 128 days per network, fit years / validation years nested inside outer training years, Adam lr 1e-3, patience 12, max 100 epochs, best-validation checkpoint restored. 12 networks x 3 seeds = 36 runs. Source stress = mean over seeds of the raw-unit (deg C) validation MAE.

```
                              stress_mean  stress_sd  best_epoch_median  epochs_ran_median  hit_limit  n_seeds
network_id                                                                                                    
arso_drava                          0.791      0.091               71.0               83.0      0.000        3
arso_kamniska_bistrica              0.686      0.282               99.0              100.0      0.667        3
chmi_kamenice                       0.815      0.063               55.0               67.0      0.000        3
chmi_luznice                        1.266      0.295               96.0              100.0      0.667        3
foen_aare_aaregebiet                1.482      0.548               79.0               91.0      0.333        3
gkd_bayern_alz                      6.009      0.508               32.0               44.0      0.333        3
gkd_bayern_fraenkische_saale        1.068      0.836               43.0               55.0      0.000        3
huc8_02040102                       1.697      0.606               70.0               82.0      0.333        3
huc8_03010107                       0.949      0.270               80.0               92.0      0.333        3
lubw_neckar                         2.374      1.301               54.0               66.0      0.333        3
lubw_rhein                          2.419      0.613               77.0               89.0      0.333        3
rws_rijn_lek_nederrijn              0.840      0.002               51.0               63.0      0.000        3
```

- Early stopping engaged for most runs: median best epoch 68, median epochs ran 80, fraction of runs hitting the 100-epoch limit 0.28 (vs the frozen lstm_sensitivity run, which hit its 5-epoch limit in 93% of networks without convergence).
- Seed stability: mean within-network SD of raw stress = 0.451 deg C; median coefficient of variation = 0.27.
- Cross-model stress agreement on the same 10 networks: neural stress vs XGBoost empirical stress Spearman = 0.067; neural stress vs the frozen sensitivity run's own fitting-period validation loss = 0.503 (12 networks). The two neural implementations agree moderately with each other and not at all with the engineered-feature stress axis.
- The neural stress faithfully predicts the same model's outer behavior: for the 10 first-confirmation networks, the seed-11 model's own outer MAE correlates 0.30 with the frozen BiLSTM target and -0.22 with the XGBoost target, mirroring the row-5 cells (i.e. the row is a genuine structural divergence, not a stress-sampling artifact).
- Convergence curves (train/validation loss by epoch, mean +/- SD over the 36 runs) are in `neural_convergence_curves.csv` and plotted in `neural_convergence.png`.

## Cross-checks against known values

```
          target_family                  panel  units  station-gap rho  networks  network rho
        pchip_or_linear     first_confirmation    673         0.838592        42     0.721903
seasonal_boundary_ridge     first_confirmation    673         0.844125        42     0.735192
       donor_blup_ridge     first_confirmation    673         0.941206        42     0.937444
            xgboost_b_d development_validation    640         0.943967        51     0.913756
            xgboost_b_d     first_confirmation    673         0.960425        42     0.939065
                 bilstm     first_confirmation    117         0.327706        10     0.672727
             air2stream    second_confirmation     89         0.172616         8     0.238095
```

- XGBoost source vs XGBoost target (development panel): station-gap rho 0.944 (640 units, 51 networks); the stated reference was 0.945 over 874 units (slightly different aggregation).
- XGBoost source vs frozen BiLSTM target: station-gap rho 0.328 / network rho 0.673 (first confirmation, 10 networks); reference 0.338 / 0.631.
- XGBoost source vs air2stream target: station-gap rho 0.173 / network rho 0.238 (89 units, 8 networks); exact match to the published manifest values.
- First-panel roster descriptors (model_roster_metrics.csv) used the empirical-transfer-prediction pipeline (network rho 0.387/0.430/0.565 for donor ridge / seasonal ridge / xgboost); the raw fitting-period stress used here gives higher transfer (see detail table) because it is the direct stress curve rather than a lossy predicted-into-evaluation mapping.

## Conclusion

Recoverability difficulty is **shared within architecture families but pipeline-specific across them**. The engineered-feature regression families (1-4) form a tight shared-difficulty block: self-transfer network rho 0.93-0.98 and cross-transfer 0.72-0.98, and the project's XGBoost reference stress predicts the outer losses of the boundary and ridge families essentially as well as it predicts its own (0.72-0.94). Outside that block transfer breaks down: the properly trained neural model's fitting-period stress correlates at -0.24 to 0.28 with the block's outer losses and only 0.28 with the frozen BiLSTM targets (the two neural implementations disagree about which networks are hard), and the air2stream process model shows weak self-transfer (0.64 on 8 networks) and null-to-negative cross-transfer. The diagonal is nevertheless statistically above the off-diagonal (p = 0.033, one-sided MWU), i.e. each family is still its own best predictor, but the off-diagonal mean is carried almost entirely by the 1-4 block.

## Honest limitations

- Families 1-3 source rows rest on 8 (first confirmation) + 4 (second confirmation) networks with <=5 placements per station-gap and gaps {7,30,90,180}; cells with 4 networks are fragile and flagged in the detail table.
- The neural row is network-level only (12 networks: 10 first confirmation + 2 carried second confirmation); the frozen BiLSTM target comes from a single-seed 5-epoch run whose own manifest concedes non-convergence, so the weak (5,5) cell partly reflects that artifact.
- The air2stream row uses per-station calibration RMSE as the fitting-period stress (no gap-level fitting-period losses exist in the read-only artifacts; no new air2stream runs were permitted); it covers 8 networks / 14 stations.
- Panels are disjoint network sets; per-panel cells keep source and target on the same networks, and the headline picks the largest-n panel per cell (all per-panel values are in matrix_cells_detail.csv).
- Neural stress is measured on 12 validation windows per seed (nested last 25% of outer training years); window sampling adds seed-to-seed noise (mean within-network SD 0.45 deg C on a mean stress of 1.70 deg C).

## Artifacts

All outputs: `results/revision_v12/t05_model_matrix/agent_a/`

- `source_fit_stress_families_1_3.csv`
- `family1_target_losses.csv`
- `neural_source_stress.csv`
- `neural_source_stress_network.csv`
- `neural_histories.csv`
- `neural_convergence_curves.csv`
- `neural_convergence.png`
- `matrix_cells_detail.csv`
- `matrix_pooled_network_level.csv`
- `matrix_headline.csv`
- `matrix_network_spearman.csv`
- `matrix_calibration_slope.csv`
- `matrix_station_gap_spearman.csv`
- `matrix_n_networks.csv`
- `diagonal_vs_offdiagonal.json`
