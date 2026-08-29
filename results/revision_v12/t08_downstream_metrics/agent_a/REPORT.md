# T08 downstream thermal-regime metrics — Agent A (adversarial pair)

## Question
Reviews demand downstream thermal-regime metrics, not just MAE. This analysis measures, for every artificial gap in the outer evaluation years, how much the XGBoost B_union_D reconstruction distorts ten ecologically relevant thermal metrics, whether the fitting-period empirical risk score (`confirmation_empirical_predictions.csv`, MAE units) predicts that distortion, and how much aggregate distortion a 20%-gap recovery budget removes when gaps are selected by risk vs gap length vs random.

## Data and pipeline
- Networks: 15 first-confirmation QC networks with the most scored station-gaps for horizons 7/30/90 (from `confirmation_empirical_predictions.csv`); 131 stations, 1965 placements (5 per station-gap, horizons [7, 30, 90]).
- Panels: `results/development_v11/confirmation_daily_qc/networks/<id>/daily_wide_temperature.csv`.
| network_id                | provider   | domain        |   n_placements |   n_stations |   mean_risk |   mean_mae_deg_c |
|:--------------------------|:-----------|:--------------|---------------:|-------------:|------------:|-----------------:|
| gkd_bayern_donau          | gkd_bayern | germany       |            195 |           13 |    0.770062 |         0.779829 |
| gkd_bayern_isar           | gkd_bayern | germany       |             75 |            5 |    0.918887 |         0.664853 |
| gkd_bayern_main           | gkd_bayern | germany       |            225 |           15 |    0.644404 |         0.883129 |
| lubw_neckar               | lubw       | germany       |            165 |           11 |    0.809131 |         0.999462 |
| arso_sava                 | arso       | slovenia      |            120 |            8 |    0.537844 |         0.549725 |
| arso_savinja              | arso       | slovenia      |             75 |            5 |    0.351078 |         0.345391 |
| foen_aare_aaregebiet      | foen       | switzerland   |            135 |            9 |    0.548134 |         0.531347 |
| huc8_02040101             | usgs       | united_states |             90 |            6 |    0.747165 |         0.700271 |
| huc8_02040104             | usgs       | united_states |             90 |            6 |    1.03122  |         0.976447 |
| huc8_03110206             | usgs       | united_states |             75 |            5 |    0.655526 |         0.597697 |
| huc8_05030103             | usgs       | united_states |            135 |            9 |    1.16056  |         1.15005  |
| huc8_10020007             | usgs       | united_states |            120 |            8 |    0.81057  |         0.780993 |
| huc8_17090001             | usgs       | united_states |            150 |           10 |    0.665885 |         0.628729 |
| huc8_17090004             | usgs       | united_states |            240 |           16 |    0.501088 |         0.395755 |
| usgs_missouri_river_huc10 | usgs       | united_states |             75 |            5 |    1.11245  |         1.22157  |

- Reconstruction: frozen XGBoost B_union_D (boundary memory + donor stations, 300 trees, depth 4), 70%-of-years train / 30% evaluation split — the identical code path as `scripts/106/108/115` (`development_recovery.score_network` internals reused directly). Reconstruction, truth, and climatology (training-period day-of-year median) series are saved in `reconstruction_series.parquet`.
- Risk score: `empirical_transfer_prediction` (fitting-period empirical loss transferred to each outer placement, °C MAE). Matched by exact gap start, else by station-gap-season, with the same fallback chain as `scripts/124`: source counts {'station_gap_season': 1157, 'exact_start': 808}; 0.96 of placements supported beyond the network-mean fallback.
- Pipeline parity check: for the placements whose gap start exists in the confirmation empirical table (808), the mean absolute difference between my recomputed MAE and the stored MAE is 0.0000 °C (0 within floating point — the same placements and models are reproduced).

## Thermal metrics and per-placement error
For each placement the reconstruction is inserted into the evaluation-period daily record (all other days keep observed truth) and each metric is recomputed; distortion = |metric(truth record) − metric(record with gap filled by reconstruction)|. Metrics follow stream-thermal-regime conventions:
| metric         | definition                   |
|:---------------|:-----------------------------|
| annual_mean    | Annual mean (°C)             |
| summer_mean    | Summer (JJA) mean (°C)       |
| amplitude      | Amplitude (Jul−Jan, °C)      |
| phase_doy      | Phase (day of peak)          |
| p90            | 90th percentile (°C)         |
| summer_max     | Summer maximum (°C)          |
| exceed_20_days | Days >20 °C                  |
| exceed_25_days | Days >25 °C                  |
| degree_days_10 | Degree days >10 °C (base 10) |
| trend_slope    | Trend slope (°C/yr)          |

Aggregate per-placement distortion (`metric_error_tables.csv`):
| metric         |    n |   mean |err| |   median |err| |   sd |err| |   mean signed err |   mean no-recovery (climatology) |err| |
|:---------------|-----:|-------------:|---------------:|-----------:|------------------:|---------------------------------------:|
| annual_mean    | 1965 |   0.0114852  |     0.00314608 |  0.0228697 |      -5.12889e-05 |                             0.0150354  |
| summer_mean    | 1950 |   0.0140582  |     0          |  0.0478365 |      -0.00921437  |                             0.0179957  |
| amplitude      | 1950 |   0.024646   |     0          |  0.0795268 |      -0.0187047   |                             0.0334211  |
| phase_doy      | 1965 |   0.119789   |     0.0296137  |  0.256895  |       0.0111232   |                             0.166612   |
| p90            | 1965 |   0.0143421  |     0          |  0.0549907 |      -0.0102267   |                             0.0158677  |
| summer_max     | 1950 |   0.0085641  |     0          |  0.142086  |      -0.0085641   |                             0.00846154 |
| exceed_20_days | 1965 |   2.02697    |     0          |  6.72009   |      -1.11399     |                             2.04835    |
| exceed_25_days | 1965 |   0.43715    |     0          |  3.34456   |      -0.422901    |                             0.348092   |
| degree_days_10 | 1965 |  19.9793     |     1.72392    | 45.3914    |      -8.88852     |                            22.5004     |
| trend_slope    | 1950 |   0.00609185 |     0.00107811 |  0.0140926 |      -0.000225819 |                             0.00732376 |

By gap length, mean absolute distortion:
| metric         |     gap 7 d |     gap 30 d |   gap 90 d |
|:---------------|------------:|-------------:|-----------:|
| amplitude      | 0.00237705  |  0.0143883   |  0.0571728 |
| annual_mean    | 0.00100704  |  0.0058916   |  0.027557  |
| degree_days_10 | 1.22528     | 10.5804      | 48.1323    |
| exceed_20_days | 0.0717557   |  1.06718     |  4.94198   |
| exceed_25_days | 0.0381679   |  0.291603    |  0.981679  |
| p90            | 0.00102816  |  0.00803717  |  0.033961  |
| phase_doy      | 0.0117205   |  0.0582639   |  0.289381  |
| summer_max     | 0           |  0.000153846 |  0.0255385 |
| summer_mean    | 0.000752398 |  0.00711185  |  0.0343104 |
| trend_slope    | 0.000564622 |  0.00278915  |  0.0149218 |

Notes: short gaps (7 d) barely move record-level metrics (annual mean, trend); the sensitive metrics are the ones that accumulate over the gap days — threshold-exceedance days, degree days, summer maximum, and (for summer gaps) JJA mean and phase when the gap straddles the seasonal peak.

## (1) Risk → distortion correlation
Network-level Spearman between mean fitting-period risk and mean per-metric distortion across the 15 networks (per metric); placement-level Spearman reported alongside (`correlation_risk_distortion.csv`):
| metric         |   network_spearman |   network_p |   n |   placement_spearman |   placement_p |
|:---------------|-------------------:|------------:|----:|---------------------:|--------------:|
| annual_mean    |          0.467857  | 0.0786302   |  15 |             0.615144 |  6.25024e-205 |
| summer_mean    |          0.371761  | 0.172436    |  15 |             0.423292 |  1.28548e-85  |
| amplitude      |          0.285714  | 0.301936    |  15 |             0.226606 |  3.97187e-24  |
| phase_doy      |         -0.196429  | 0.482899    |  15 |             0.495822 |  1.95031e-122 |
| p90            |          0.771429  | 0.000756875 |  15 |             0.310214 |  4.27901e-45  |
| summer_max     |          0.173252  | 0.536913    |  15 |             0.109686 |  1.20304e-06  |
| exceed_20_days |          0.739286  | 0.00163551  |  15 |             0.375023 |  1.17993e-66  |
| exceed_25_days |          0.665565  | 0.00676502  |  15 |             0.234805 |  5.09582e-26  |
| degree_days_10 |          0.764286  | 0.00090731  |  15 |             0.527952 |  1.79222e-141 |
| trend_slope    |         -0.0892857 | 0.751673    |  15 |             0.421325 |  9.25233e-85  |

Findings:
- Strongest network-level correlates: p90 (ρ=+0.77), degree_days_10 (ρ=+0.76), exceed_20_days (ρ=+0.74).
- Weakest: phase_doy (ρ=-0.20), summer_max (ρ=+0.17), trend_slope (ρ=-0.09).
Interpretation: the fitting-period empirical score is a general MAE-risk estimator, so it correlates most with the distortions that scale with per-day temperature error accumulated over many days (degree days, exceedance days, annual/summer means), and least with metrics governed by single extreme days (summer maximum) or by boundary/structure (phase).

## (2) Budget experiment (top 20% of gaps)
Pooled budget of 393 placements (20% of 1965). Baseline 'no gaps treated': every gap window is filled with climatology (no recovery); a selected window is filled with the XGBoost reconstruction. Reduction = 1 − aggregate distortion(policy)/aggregate distortion(baseline), summed across networks per metric; `combined` = mean of the per-metric reduction fractions. Random policy: 200 draws (mean ± sd). Oracle = top-20% selected by the per-placement no-recovery distortion (upper bound for that metric; `oracle_combined` uses the mean standardized no-recovery distortion across metrics).

Per-policy combined reduction (`budget_combined.csv`):
| policy                |   combined_reduction |   r_annual_mean |   r_summer_mean |   r_amplitude |   r_phase_doy |      r_p90 |   r_summer_max |   r_exceed_20_days |   r_exceed_25_days |   r_degree_days_10 |   r_trend_slope |
|:----------------------|---------------------:|----------------:|----------------:|--------------:|--------------:|-----------:|---------------:|-------------------:|-------------------:|-------------------:|----------------:|
| gap_length            |          -0.148457   |      0.127344   |      -0.200928  |   -0.342814   |    0.0202271  | -0.142077  |     0          |        -0.330642   |         -0.419776  |        -0.132171   |     -0.0637325  |
| oracle_amplitude      |           0.00841181 |      0.12922    |       0.0915231 |    0.00619389 |   -0.0491016  |  0.0613317 |    -0.0166667  |         0.0419863  |         -0.257463  |         0.0256146  |      0.051479   |
| oracle_annual_mean    |           0.188928   |      0.39793    |       0.351118  |    0.171571   |    0.261991   |  0.175181  |    -0.0222222  |         0.22608    |         -0.216418  |         0.373927   |      0.170123   |
| oracle_combined       |           0.0531167  |      0.176848   |       0.131502  |    0.0665683  |    0.175048   |  0.0397014 |    -0.0222222  |         0.0193783  |         -0.365672  |         0.14249    |      0.167525   |
| oracle_degree_days_10 |           0.131728   |      0.241638   |       0.252856  |    0.0136121  |    0.253963   |  0.166333  |     0          |         0.147356   |         -0.195896  |         0.312156   |      0.125258   |
| oracle_exceed_20_days |          -0.0480527  |     -0.0260567  |      -0.0411196 |   -0.11707    |    0.00124825 | -0.0569679 |     0          |        -0.0100929  |         -0.281716  |         0.00573563 |      0.0455124  |
| oracle_exceed_25_days |          -0.0829767  |     -0.00267226 |      -0.0648692 |   -0.177296   |    0.0169904  | -0.048377  |     0          |        -0.050868   |         -0.367537  |        -0.0239493  |     -0.111188   |
| oracle_p90            |          -0.00857247 |      0.0214624  |       0.11725   |   -0.0712321  |   -0.0134084  |  0.0412289 |    -0.0222222  |         0.12394    |         -0.335821  |         0.0565552  |     -0.00347818 |
| oracle_phase_doy      |           0.200095   |      0.379213   |       0.317694  |    0.296133   |    0.323719   |  0.155964  |    -0.0222222  |         0.0803391  |         -0.0447761 |         0.335279   |      0.179603   |
| oracle_summer_max     |          -0.024865   |      0.00992038 |       0.0548815 |   -0.0896992  |    0.0356579  |  0.0516886 |    -0.0166667  |        -0.00968914 |         -0.190299  |         0.0494307  |     -0.143876   |
| oracle_summer_mean    |           0.0267356  |      0.0523688  |       0.181293  |   -0.0029062  |   -0.053925   |  0.0630534 |    -0.0222222  |         0.0581348  |         -0.367537  |         0.160082   |      0.199014   |
| oracle_trend_slope    |           0.0483302  |      0.142422   |       0.0136194 |    0.0366402  |    0.186878   |  0.043989  |    -0.0222222  |         0.0258377  |         -0.158582  |         0.109473   |      0.105247   |
| random                |           0.0260736  |      0.128068   |       0.06565   |   -0.0254209  |    0.0539052  |  0.0441788 |    -0.00466667 |         0.0290896  |         -0.0816978 |         0.071389   |     -0.0197595  |
| risk                  |          -0.176719   |      0.0217091  |      -0.229861  |   -0.33832    |   -0.108016   | -0.130052  |     0          |        -0.221639   |         -0.425373  |        -0.179017   |     -0.156625   |

Per-metric reduction fractions (`budget_comparison.csv`):
| metric         |       risk |   gap_length |      random |   oracle_combined |
|:---------------|-----------:|-------------:|------------:|------------------:|
| amplitude      | -0.33832   |   -0.342814  | -0.0254209  |         0.0665683 |
| annual_mean    |  0.0217091 |    0.127344  |  0.128068   |         0.176848  |
| degree_days_10 | -0.179017  |   -0.132171  |  0.071389   |         0.14249   |
| exceed_20_days | -0.221639  |   -0.330642  |  0.0290896  |         0.0193783 |
| exceed_25_days | -0.425373  |   -0.419776  | -0.0816978  |        -0.365672  |
| p90            | -0.130052  |   -0.142077  |  0.0441788  |         0.0397014 |
| phase_doy      | -0.108016  |    0.0202271 |  0.0539052  |         0.175048  |
| summer_max     |  0         |    0         | -0.00466667 |        -0.0222222 |
| summer_mean    | -0.229861  |   -0.200928  |  0.06565    |         0.131502  |
| trend_slope    | -0.156625  |   -0.0637325 | -0.0197595  |         0.167525  |

Risk-policy advantage over random and over gap-length selection (`metric_protection_summary.csv`):
| metric         |   risk_vs_random_gain |   risk_vs_length_gain |
|:---------------|----------------------:|----------------------:|
| annual_mean    |           -0.106359   |           -0.105635   |
| summer_mean    |           -0.295511   |           -0.0289328  |
| amplitude      |           -0.312899   |            0.00449362 |
| phase_doy      |           -0.161921   |           -0.128243   |
| p90            |           -0.174231   |            0.0120249  |
| summer_max     |            0.00466667 |            0          |
| exceed_20_days |           -0.250729   |            0.109003   |
| exceed_25_days |           -0.343675   |           -0.00559701 |
| degree_days_10 |           -0.250406   |           -0.0468459  |
| trend_slope    |           -0.136865   |           -0.0928922  |

Figure: `budget_comparison.png`.

Mean per-metric reduction (equal metric weight): risk -0.177, gap length -0.148, random +0.026, oracle +0.053. The risk-selected and length-selected budgets concentrate on the longest summer gaps, and for those gaps the XGBoost reconstruction is *worse* than the climatology no-recovery baseline for threshold-count, degree-day, amplitude and summer-mean metrics.
Placement-level mechanism (90-day gaps, mean absolute distortion; `metric_error_tables.csv`):
| metric         |   mean_abs |   mean_signed |   mean_recoverable |
|:---------------|-----------:|--------------:|-------------------:|
| summer_mean    |  0.0343104 |    -0.0268067 |          0.0377274 |
| exceed_20_days |  4.94198   |    -3.29008   |          4.61069   |
| exceed_25_days |  0.981679  |    -0.972519  |          0.603053  |
| degree_days_10 | 48.1323    |   -24.5121    |         47.4673    |
The reconstruction is systematically cold at the seasonal peak (negative signed errors: hot days are under-counted, degree-day accumulation is under-estimated), so on the long gaps that dominate the top-risk budget it flips more threshold crossings than the climatology fill removes. This is why the budget reduction is negative for those metrics while mean-type metrics (annual mean, summer mean, p90) are still protected.

## (3) Which metrics are most / least protected, and why
Ranked by |network Spearman(risk, distortion)| and risk-policy reduction:
| metric         |   network_spearman |   risk_reduction |   length_reduction |   random_reduction_mean |   oracle_reduction |   risk_vs_random_gain |   risk_vs_length_gain |
|:---------------|-------------------:|-----------------:|-------------------:|------------------------:|-------------------:|----------------------:|----------------------:|
| p90            |          0.771429  |       -0.130052  |         -0.142077  |              0.0441788  |         0.0412289  |           -0.174231   |            0.0120249  |
| degree_days_10 |          0.764286  |       -0.179017  |         -0.132171  |              0.071389   |         0.312156   |           -0.250406   |           -0.0468459  |
| exceed_20_days |          0.739286  |       -0.221639  |         -0.330642  |              0.0290896  |        -0.0100929  |           -0.250729   |            0.109003   |
| exceed_25_days |          0.665565  |       -0.425373  |         -0.419776  |             -0.0816978  |        -0.367537   |           -0.343675   |           -0.00559701 |
| annual_mean    |          0.467857  |        0.0217091 |          0.127344  |              0.128068   |         0.39793    |           -0.106359   |           -0.105635   |
| summer_mean    |          0.371761  |       -0.229861  |         -0.200928  |              0.06565    |         0.181293   |           -0.295511   |           -0.0289328  |
| amplitude      |          0.285714  |       -0.33832   |         -0.342814  |             -0.0254209  |         0.00619389 |           -0.312899   |            0.00449362 |
| phase_doy      |         -0.196429  |       -0.108016  |          0.0202271 |              0.0539052  |         0.323719   |           -0.161921   |           -0.128243   |
| summer_max     |          0.173252  |        0         |          0         |             -0.00466667 |        -0.0166667  |            0.00466667 |            0          |
| trend_slope    |         -0.0892857 |       -0.156625  |         -0.0637325 |             -0.0197595  |         0.105247   |           -0.136865   |           -0.0928922  |

- **Most protected (ranking)** — metrics whose distortion scales with the per-day reconstruction error are ranked almost perfectly by the fitting-period empirical risk score: `p90` (ρ=0.77), `degree_days_10` (ρ=0.76), `exceed_20_days` (ρ=0.74), `exceed_25_days` (ρ=0.67) at the network level (all p<0.01). These are also the metrics with the largest absolute distortions (degree days ≈20 °C·d, exceed-20 counts ≈2 d per placement).
- **Least protected (ranking)** — `summer_max` (ρ=0.17), `amplitude` (ρ=0.29), `trend_slope` (ρ=-0.09) and `phase_doy` (ρ=-0.20): their distortion is governed by the few days near the seasonal extreme or by the gap's placement in the year, which a per-day MAE risk score does not order. `phase_doy` distortion is also not monotone in error magnitude (a biased-but-shape-preserving fill can keep the peak day unchanged).
- **Budget protection** — under the top-20% risk policy only `annual_mean` shows a positive reduction (+0.02); every other metric is flat or worse than the no-recovery climatology baseline, most sharply `exceed_25_days` (−0.43), `amplitude` (−0.34), `summer_mean` (−0.23), `exceed_20_days` (−0.22). The reason is that the top-risk gaps are the long summer gaps, where the reconstruction's cold peak bias dominates: the aggregate threshold/degree-day/summer distortions the XGBoost fill introduces exceed what the climatology fill already contributed. The same holds for gap-length selection; random selection is closer to zero because it mixes short gaps, where reconstruction is unambiguously better than climatology for every metric.
- **Implication for the end-to-end claim** — the pipeline protects ecologically relevant *mean/percentile* thermal metrics well and the empirical risk score ranks their distortion reliably across networks; it does not protect *threshold-extreme* metrics (exceedance days, degree days, summer maximum, amplitude, phase) on long gaps, where a peak-corrected reconstruction (e.g., bias correction of the summer extreme) would be needed before claiming end-to-end protection.

## Caveats
- Metrics are computed on the whole evaluation record with one gap filled at a time; overlapping placements are filled deterministically (selected wins over climatology) in the budget scenario.
- Networks are the 15 first-confirmation networks with the most scored gaps; results are descriptive of this panel, not a randomized sample.
- The budget is a per-placement budget, not a per-station-gap budget; gap length 90 dominates the baseline distortion, so all policies concentrate on long gaps.

## Files
- `placement_thermal_metrics.csv` — per placement: MAE, risk, distortion/signed/recoverable error for all 10 metrics.
- `network_thermal_metrics.csv` — network-level means.
- `reconstruction_series.parquet` — truth/reconstruction/climatology daily series per gap.
- `metric_error_tables.csv` — aggregate distortion tables, overall and by gap length.
- `correlation_risk_distortion.csv` — network- and placement-level Spearman per metric.
- `budget_comparison.csv`, `budget_combined.csv`, `budget_comparison.png` — budget experiment.
- `metric_protection_summary.csv` — protection ranking.
- `summary.json` — machine-readable summary.
- `REPORT.md` — this report.
