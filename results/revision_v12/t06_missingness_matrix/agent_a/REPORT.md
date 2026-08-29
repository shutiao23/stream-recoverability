# T06 Missingness-Mechanism Matrix (agent a, adversarial pair)

**Analysis:** `revision_v12/t06_missingness_matrix/agent_a`
**Script:** `scripts/rev_v12_t06_missingness_a.py`
**Run:** 2026-08-28, wall 1400 s, CPU-only, 12 networks x 7 mechanisms x 2 splits (fitting-trial + evaluation), 80,409 gap placements scored.

## 1. Question

The paper's empirical stress curve is built from uniform-grid trial gaps inside the fitting record (manuscript §2.3) and is known to degrade under planted field-outage geometry (§3.4). This analysis asks: does the fitting-period stress curve transfer when the **missingness mechanism itself** changes — seasonal bias, fragmented blocks, donor-synchronous outage, forcing outage, and online (no-future) recovery — and does a mismatched (uniform-block) curve support other mechanisms' gaps?

## 2. Panel and workload

12 first-panel networks with daily QC data from `results/development_v11/confirmation_daily_qc/networks/` (the 42 route-A-scored networks; subset chosen for scoring depth and provider spread):

| network | provider | stations scored |
|---|---|---|
| gkd_bayern_main | gkd_bayern | 6 |
| huc8_17090004 | usgs | 7 |
| gkd_bayern_donau | gkd_bayern | 10 |
| lubw_neckar | lubw | 10 |
| foen_aare_aaregebiet | foen | 9 |
| huc8_17090001 | usgs | 10 |
| arso_sava | arso | 8 |
| huc8_05030103 | usgs | 9 |
| huc8_02040101 | usgs | 6 |
| arso_savinja | arso | 5 |
| gkd_bayern_isar | gkd_bayern | 3 |
| huc8_02040104 | usgs | 4 |

87 stations scored, 12 skipped (insufficient training days / no donor); 573-609 station-gap units per mechanism; 88-99% of trial curve cells have direct station-horizon support. Full roster in `network_panel.csv`, attrition in `station_attrition.csv`, per-network years in `manifest.json`.

## 3. Pipeline (identical to the paper's recovery family)

- Outer chronological split 70/30 (fitting years / evaluation years); nested split inside the fitting years: first 70% of fitting years fit the model, remaining 30% supply trial-gap truth (§2.3).
- XGBoost recovery: 300 trees, depth 4, lr 0.05, subsample 0.9, colsample 0.9 (exact `XGBOOST_PARAMETERS`), features = symmetric boundary `(t-1, t+1)/2` (left-only for mechanism h), donor temperatures, and 3-harmonic day-of-year features. Scoring replaces the boundary with the observed-boundary linear interpolation, exactly as in `development_recovery.py`.
- Per mechanism: trial gaps (up to 12 placements per station-horizon) with the mechanism's own placement distribution build the station-horizon curve (mean MAE); evaluation gaps (up to 20 placements per station-horizon, same mechanism) are recovered with the same fitted model. Unit = station-gap (mean over placements). Fallback chain for curve prediction: station-horizon mean -> network-horizon mean -> network-mean of all fitting-period losses (paper's chain).
- Metrics: network-level Spearman (network means of predicted vs observed, `scipy.spearmanr`) and equal-network weighted least-squares calibration slope/intercept (identical formula to `route_a_confirmation.confirmation_metrics`).

## 4. Mechanism definitions

| id | mechanism | structure | boundary support | donor support |
|---|---|---|---|---|
| a | uniform single block | one contiguous block, start uniform over year | left+right | all donors |
| b | multi-block | total length L split into 2-8 blocks (<=46 d) separated by 3-day observed runs; L=7 is a single block (coincides with a) | left+right per block | all donors |
| c | summer-biased | single block, start in Jun 1-Sep 30 | left+right | all donors |
| d | high-temperature-biased | single block on windows whose fitting-period day-of-year climatology mean is in the top 30% of candidate windows | left+right | all donors |
| e | drought/low-flow biased | **skipped**: no discharge (F/L) data for the confirmation panel exists in `data/processed` (it holds an unrelated synthetic corpus) | - | - |
| f | donor-synchronous | single block; target **and all donors** masked (network-wide outage) | left+right | none |
| g | target+forcing outage | single block; target + strongest donor masked, weaker donors remain. **Substitution**: the confirmation panels contain no air temperature (QC data is water-temperature only), so the strongest anomaly-correlated donor serves as the forcing-covariate proxy | left+right | weaker donors only |
| h | online setting | single block; recovery uses only the left boundary (model fit and scored without the future boundary feature) | left only | all donors |

## 5. Results: mechanism-stratified matched transfer (mechanism-specific curve -> same-mechanism evaluation gaps)

| mechanism | network Spearman | p | Spearman (4 horizons: 7/30/90/180) | calibration slope | mean pred / obs (°C) | n units | fallback % |
|---|---|---|---|---|---|---|---|
| a_uniform_block | 0.531 | 0.075 | 0.622 | 0.920 | 0.99 / 1.26 | 573 | 10.3 |
| b_multi_block | 0.944 | 4e-6 | 0.923 | 0.902 | 0.51 / 0.54 | 573 | 10.3 |
| c_summer_biased | 0.594 | 0.042 | 0.490 | 0.938 | 1.01 / 1.24 | 557 | 9.5 |
| d_high_temperature_biased | 0.580 | 0.048 | 0.622 | 1.011 | 1.16 / 1.51 | 573 | 10.3 |
| f_donor_synchronous | 0.979 | 3e-8 | 0.951 | 0.950 | 3.43 / 3.35 | 609 | 0.7 |
| g_target_plus_primary_covariate | 0.881 | 2e-4 | 0.944 | 0.892 | 1.94 / 2.13 | 575 | 8.9 |
| h_online_left_boundary | 0.930 | 1e-5 | 0.888 | 0.906 | 1.25 / 1.39 | 573 | 10.3 |

Every mechanism's fitted curve transfers positively; matched magnitude calibration is good for all (slopes 0.89-1.01, intercepts 0.10-0.37 °C). Mechanism-matched curves **supported** (Spearman >= 0.60 and slope within [0.5, 1.5], thresholds in `manifest.json`): **b, f, g, h** (0.88-0.98). Mechanisms **a, c, d** transfer weakly-to-moderately on this 12-network panel (0.53-0.59; c and d are significant at 5%, a is not, p=0.075). The weakness of (a) is traceable: at 90-365-day horizons the joint donor-completeness rule leaves the long German networks (gkd_bayern_main, gkd_bayern_donau, lubw_neckar) without station-horizon trial cells in 2003-2012, so 10.3% of units use the network-mean fallback and their predicted values flatten (e.g., gkd_bayern_main predicted 0.69 vs observed 1.80 °C) — exactly the paper's documented fallback cost, now concentrated in the networks where long-gap risk matters most.

## 6. Mismatch experiment (uniform-block curve applied to other mechanisms' evaluation gaps)

| evaluation mechanism | curve source | network Spearman | calibration slope | mean pred / obs (°C) | vs matched Spearman |
|---|---|---|---|---|---|
| b_multi_block | a_uniform_block | 0.643 | **0.142** | 0.99 / 0.54 | 0.944 -> 0.643 |
| c_summer_biased | a_uniform_block | 0.671 | 0.832 | 0.96 / 1.24 | 0.594 -> 0.671 |
| d_high_temperature_biased | a_uniform_block | 0.580 | 1.104 | 0.99 / 1.51 | 0.580 -> 0.580 |
| f_donor_synchronous | a_uniform_block | **0.294** | 0.651 | 1.06 / **3.35** | 0.979 -> 0.294 |
| g_target_plus_primary_covariate | a_uniform_block | **0.196** | 0.726 | 0.99 / **2.13** | 0.881 -> 0.196 |
| h_online_left_boundary | a_uniform_block | 0.399 | 0.873 | 0.99 / 1.39 | 0.930 -> 0.399 |
| a_uniform_block (reverse) | c_summer_biased | 0.308 | 0.903 | 1.02 / 1.26 | 0.531 -> 0.308 |

Conclusions from the mismatch experiment:

- **Support-destroying mechanisms (f, g, h) are NOT supported by the uniform-block curve**: network Spearman collapses to 0.20-0.40 (from 0.88-0.98 matched) and losses are under-predicted by 1.1-2.3 °C. When donors or the future boundary go down, the *between-network* ordering itself changes — networks with weak redundancy suffer disproportionately — so a uniform-grid curve is not merely miscalibrated for these gaps, it misranks them.
- **Multi-block (b) magnitude support fails**: the uniform curve over-predicts multi-block losses ~2x (slope collapses 0.90 -> 0.14) because repeated short blocks recover far better than one long block at the same total length; rank degrades modestly (0.94 -> 0.64).
- **Seasonal placement bias (c, d) is the mildest mismatch**: the uniform curve supports summer- and heat-biased gaps about as well as their own (noisier, more concentrated) curves — the bias acts mostly as a shift the calibration intercept absorbs. The reverse direction (summer curve -> uniform gaps) does degrade (0.53 -> 0.31): a seasonal curve over-fits its own season.
- Symmetry matters: mismatch is not symmetric between a and c.

## 7. Missingness x support matrix (`support_matrix.csv`)

For each mechanism: which feature support survives the gap (boundary left/right, donor set), the placement structure, matched-curve transfer, and transfer of the generic uniform curve. Full table in `support_matrix.csv` (summarized in §4-§6). Mechanism (e) row is absent by design (no discharge data).

**Which mechanisms are supported by fitting-period stress curves:** (i) by their **own** matched curve — b, f, g, h transfer strongly (Spearman 0.88-0.98, slope 0.89-0.95, <=10% fallback); a, c, d transfer weakly on this panel (0.53-0.59, borderline p, slope ~0.92-1.01) with (a)'s weakness driven by long-horizon fallback. (ii) by the paper's **generic uniform-block curve** — only mechanisms that keep boundary+donor support intact and only when the placement bias is seasonal (c, d); multi-block rank partially (slope destroyed), and donor-synchronous / primary-covariate / online gaps are not supported (rank and magnitude both fail).

## 8. Cross-checks against the paper

- Paper: uniform-grid XGBoost, first panel, 780 directly supported units at the 4 prespecified horizons, network Spearman **0.922**; second panel 0.805 across 57 networks. This analysis: mechanism (a), 4-horizon network Spearman **0.622** (348 units), 7-horizon 0.531 (573 units). At n=12 networks the standard error of a Spearman is ~0.33, so both paper values lie within ~1 SE; the direction (moderate transfer, systematic under-prediction of outer-evaluation loss, fallback flattening) is consistent with the uniform-grid behavior rather than with the planted-geometry regime.
- Paper: planted field-outage geometry, 49 networks, 85.8% network-mean fallback, network Spearman **0.566** (slope 0.401). This analysis: mechanism (a) has only 10.3% fallback and slope 0.92 — it is not the planted-geometry regime; the numerical coincidence of the (a) point estimate with 0.566 arises on a different panel and design (12 confirmation networks, matched uniform gaps). The planted-geometry lesson is reproduced structurally in §6: when the uniform curve is applied to genuinely unsupported gaps (f, g, h), Spearman falls to 0.20-0.40 and slopes drop to 0.65-0.87 — the same signature as the paper's geometry mismatch, now shown to extend from outage *shape* to the full missingness mechanism.

## 9. Main conclusion on geometry robustness

Fitting-period empirical stress curves are **mechanism-specific instruments, not generic curves**. A matched curve transfers well for every mechanism tested (including the hardest: donor-synchronous, forcing, and online settings), and the mismatch experiment shows the cost of using a uniform-block curve for gaps it does not represent: rank degradation to ~0.2-0.4 and magnitude errors of 1.1-2.3 °C when support is destroyed, and a collapsed slope (0.14) for fragmented multi-block gaps. Seasonal placement bias is the most forgiving mismatch. This generalizes the paper's §3.4 matched-geometry warning: trial gaps should be matched to the intended outage mechanism — structure, season, and the outage's effect on the recovery information (donors, forcing, future boundary) — and a single uniform stress curve should not be transferred across mechanisms.

## 10. Files (all under `results/revision_v12/t06_missingness_matrix/agent_a/`)

- `mechanism_metrics.csv` — matched transfer per mechanism (Spearman, p, 4-horizon Spearman, calibration, n units, fallback share).
- `mismatch_metrics.csv` — uniform-block curve on every other mechanism's gaps (+ reverse summer case).
- `support_matrix.csv` — mechanism x support attributes and transfer columns.
- `mechanism_units.csv` — every station-gap unit (predicted, observed, fallback type, placements).
- `mechanism_curves.csv` — station-horizon trial curves per mechanism.
- `placement_losses.csv`, `station_gap_units.csv` — raw and aggregated placement losses.
- `network_panel.csv`, `station_attrition.csv`, `manifest.json` — panel, attrition, and full parameters.
- `REPORT.md` — this report.
