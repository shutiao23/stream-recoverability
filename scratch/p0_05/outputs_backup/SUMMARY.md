# P0-05 — independence and power design for the final configuration

Script `scripts/314_wrr_p0_05_power_and_independence.py`; command `PYTHONPATH=src python3 scripts/314_wrr_p0_05_power_and_independence.py`; HEAD `0544f3b760cd`; script sha256 `aeb82d5f5d21d908…`; wall time 791 s.

## Estimator

* Primary contrast: consequential-error rate difference between the final screen (frozen certificate bound as the ranking score) and the incumbent length rule (`longest_run`) at matched 70% retention, tolerance 0.5 °C, in percentage points; negative = the screen is better.
* Non-finite selected errors count as consequential failures and stay in the denominator (`operating_point_contrast`).
* Interval: `stream_recoverability.experiments.v17_fitness.stats.cluster_bootstrap` — percentile interval from resampling whole networks with replacement; identical point estimate and interval to the project's `operating_point_contrast` (checked in `simulation_diagnostics.json`, max |difference| 0.0000000000 pp).
* Panels: development = out-of-fold certificate on the 110 development networks (`step6_screen/development_certificates.parquet`); wave-2 = frozen certificate on the 49 external networks (`p0_07_wave2_confirmation`). The pooled row is a sensitivity mixture.

## 1. Network-level variance of the primary contrast

| panel | cases | nets | pooled pp [95 % CI] | SD within-net contrasts | SD implied by bootstrap | SD ANOVA | ICC(contrast) | DEFF | N_eff |
|---|---|---|---|---|---|---|---|---|---|
| development | 40,704 | 110 | -6.35 [-7.12, -5.49] | 3.92 | 4.39 | 4.73 | 0.0185 | 7.82 | 14.1 |
| wave2_external | 13,017 | 49 | -5.89 [-6.92, -4.91] | 4.57 | 3.60 | 4.02 | 0.0131 | 4.47 | 11.0 |
| pooled_dev_wave2 | 53,721 | 159 | -6.32 [-6.94, -5.62] | 4.11 | 4.24 | 4.61 | 0.0173 | 6.84 | 23.3 |

SD within-net contrasts is the SD (ddof=1) of the per-network within-network contrast (each network does its own 70 % selection; the step-7 convention) — this is the variance component of the network-equal estimand. SD implied by bootstrap is `SE x sqrt(n_networks)` (the project's own convention in `scripts/186_v17_freeze.py`) and is the operative between-network SD for the pooled case-weighted estimand. SD ANOVA is `sqrt((MSB-MSW)/n0)` from the one-way random-effects decomposition of the exact case-level contrast `d_i = (x_i - y_i)/0.70`. The fixed-selection influence SDs are also in `network_variance_table.csv`; they overstate the bootstrap and are **not** used for power.

The network-equal mean is mildly jitter-seed sensitive because the length rule breaks ties in `longest_run` at random: seed 991 (the primary estimator's seed) gives -5.12 pp on wave-2 where the step-7 seed 61 gives -5.46 pp; the pooled case-weighted headline is unaffected (its point estimate and interval are identical to `operating_point_contrast`, verified in `simulation_diagnostics.json`).

ICC is the intra-network correlation of that case-level contrast (one-way random-effects ICC(1), unbalanced). Large ICC x large networks is why the design effect is high: the contrast is mostly a within-network case-level quantity, so cases are not independent evidence about networks.

## 2. Design simulation (N x MUE)

### Headline

* At N=20 development networks the design reaches 0.50 power for a 2 pp effect and 1.00 for 5 pp (MDE80 2.77 pp); at N=80, 0.98 for 2 pp with MDE80 1.40 pp.
* The pre-declared 5 pp effect of `scripts/186_v17_freeze.py` is detected with practical certainty from N=20 upward; the binding requirement is the 2 pp MUE.
* The **effective independent network count is far below the network count**: at the current development panel size the contrast behaves like 14.1 independent networks (wave-2: 11.0), because the intra-network correlation of the contrast is small but the networks hold hundreds of cases each.

Each draw samples N networks with replacement from the panel's empirical network distribution (all cases of a drawn network; duplicated draws are independent clusters), recomputes the contrast and its network-clustered bootstrap interval (200 inner draws per study, joblib n_jobs=96). Outer draws per panel: development = 1000, wave2_external = 1000, pooled_dev_wave2 = 800; the pooled mixture is a pre-declared sensitivity with a smaller budget, and any reduction below the pre-declared 2000 draws is recorded here and in the `note` and `outer_draws` columns of `power_table.csv`. This run recorded: outer draws reduced from the pre-declared 2000 to 1000 (CPU contention with co-running agents; 1000 draws keeps the Monte Carlo SE of a 0.8 power estimate near 0.013)

| panel | N | mean point pp | SD of points | mean bootstrap SE | power @panel effect | empirical alpha at 0 | power 2 pp | power 3 pp | power 5 pp | MDE80 pp | analytic MDE80 pp | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| development | 20 | -6.20 | 1.05 | 0.94 | 1.000 | 0.107 | 0.502 | 0.850 | 1.000 | 2.77 | 2.69 | 60 |
| development | 40 | -6.25 | 0.69 | 0.69 | 1.000 | 0.071 | 0.800 | 0.995 | 1.000 | 2.00 | 1.96 | 62 |
| development | 60 | -6.27 | 0.57 | 0.56 | 1.000 | 0.079 | 0.938 | 1.000 | 1.000 | 1.59 | 1.59 | 64 |
| development | 80 | -6.28 | 0.50 | 0.49 | 1.000 | 0.071 | 0.984 | 1.000 | 1.000 | 1.40 | 1.37 | 66 |
| wave2_external | 20 | -5.83 | 0.81 | 0.81 | 1.000 | 0.100 | 0.726 | 0.987 | 1.000 | 2.18 | 2.29 | 59 |
| wave2_external | 40 | -5.86 | 0.58 | 0.57 | 1.000 | 0.074 | 0.957 | 1.000 | 1.000 | 1.56 | 1.60 | 62 |
| wave2_external | 60 | -5.88 | 0.46 | 0.46 | 1.000 | 0.057 | 0.995 | 1.000 | 1.000 | 1.25 | 1.31 | 64 |
| wave2_external | 80 | -5.89 | 0.40 | 0.40 | 1.000 | 0.065 | 1.000 | 1.000 | 1.000 | 1.10 | 1.13 | 65 |
| pooled_dev_wave2 | 20 | -6.14 | 0.96 | 0.92 | 1.000 | 0.107 | 0.520 | 0.885 | 1.000 | 2.66 | 2.65 | 48 |
| pooled_dev_wave2 | 40 | -6.19 | 0.67 | 0.68 | 1.000 | 0.098 | 0.835 | 1.000 | 1.000 | 1.93 | 1.91 | 49 |
| pooled_dev_wave2 | 60 | -6.24 | 0.55 | 0.55 | 1.000 | 0.079 | 0.960 | 1.000 | 1.000 | 1.60 | 1.56 | 51 |
| pooled_dev_wave2 | 80 | -6.26 | 0.47 | 0.48 | 1.000 | 0.065 | 0.991 | 1.000 | 1.000 | 1.35 | 1.34 | 53 |

*Power* is the share of simulated studies whose network-clustered 95 % interval excludes zero after the study is re-centred on a true effect equal to the MUE (shift model: the same shift is applied to every draw, so the empirical shape and width of the sampling distribution are preserved). *Empirical alpha at 0* is the same calculation with a true effect of exactly 0 pp; it should sit near 0.05 and is the coverage check of the whole machinery. *MDE80* solves the same simulated power function for 80 %; the analytic column is `2.802 x SD_implied / sqrt(N)` and is reported as a cross-check, not as the headline.

### Coverage check (read this before quoting the power numbers)

| panel | N | SD of simulated points | mean bootstrap SE | ratio | empirical alpha at 0 |
|---|---|---|---|---|---|
| development | 20 | 1.05 | 0.94 | 1.114 | 0.107 |
| development | 40 | 0.69 | 0.69 | 1.003 | 0.071 |
| development | 60 | 0.57 | 0.56 | 1.006 | 0.079 |
| development | 80 | 0.50 | 0.49 | 1.037 | 0.071 |
| wave2_external | 20 | 0.81 | 0.81 | 1.007 | 0.100 |
| wave2_external | 40 | 0.58 | 0.57 | 1.012 | 0.074 |
| wave2_external | 60 | 0.46 | 0.46 | 0.989 | 0.057 |
| wave2_external | 80 | 0.40 | 0.40 | 1.005 | 0.065 |
| pooled_dev_wave2 | 20 | 0.96 | 0.92 | 1.039 | 0.107 |
| pooled_dev_wave2 | 40 | 0.67 | 0.68 | 0.987 | 0.098 |
| pooled_dev_wave2 | 60 | 0.55 | 0.55 | 0.995 | 0.079 |
| pooled_dev_wave2 | 80 | 0.47 | 0.48 | 0.985 | 0.065 |

If the empirical alpha at zero exceeds 0.05, the nominal 95 % network-clustered percentile interval under-covers at that design size, and the power figures that come from that same interval are optimistic; the analytic MDE80 column, which uses the simulated SD of the points rather than the interval width, is the more conservative reading at small N. The ratio column shows whether the bootstrap SE reproduces the design's own sampling SD.

## 3. Independence audit: provider and network leverage

### Shares

| panel | provider | networks | share nets | cases | share cases | case-weighted pp | network-equal pp |
|---|---|---|---|---|---|---|---|
| development | arso | 10 | 9.1 % | 3,389 | 8.3 % | -3.75 | -3.75 |
| development | chmi | 12 | 10.9 % | 5,994 | 14.7 % | -8.58 | -6.88 |
| development | foen | 2 | 1.8 % | 2,855 | 7.0 % | -1.40 | -1.35 |
| development | gkd_bayern | 7 | 6.4 % | 10,443 | 25.7 % | -6.11 | -5.71 |
| development | lubw | 6 | 5.5 % | 1,854 | 4.6 % | -5.47 | -4.48 |
| development | nve_hydapi | 13 | 11.8 % | 2,188 | 5.4 % | -5.35 | -3.28 |
| development | rws_waterwebservices | 2 | 1.8 % | 327 | 0.8 % | -2.18 | -2.19 |
| development | syke | 2 | 1.8 % | 705 | 1.7 % | -10.55 | -8.88 |
| development | usgs | 56 | 50.9 % | 12,949 | 31.8 % | -5.64 | -5.46 |
| wave2_external | hubeau | 4 | 8.2 % | 735 | 5.6 % | -9.92 | -3.67 |
| wave2_external | uk_ea | 1 | 2.0 % | 21 | 0.2 % | -6.67 | -6.67 |
| wave2_external | usgs | 44 | 89.8 % | 12,261 | 94.2 % | -5.87 | -5.28 |
| pooled_dev_wave2 | arso | 10 | 6.3 % | 3,389 | 6.3 % | -3.75 | -3.70 |
| pooled_dev_wave2 | chmi | 12 | 7.5 % | 5,994 | 11.2 % | -8.58 | -6.88 |
| pooled_dev_wave2 | foen | 2 | 1.3 % | 2,855 | 5.3 % | -1.40 | -1.35 |
| pooled_dev_wave2 | gkd_bayern | 7 | 4.4 % | 10,443 | 19.4 % | -6.11 | -5.67 |
| pooled_dev_wave2 | hubeau | 4 | 2.5 % | 735 | 1.4 % | -9.92 | -3.73 |
| pooled_dev_wave2 | lubw | 6 | 3.8 % | 1,854 | 3.5 % | -5.47 | -4.47 |
| pooled_dev_wave2 | nve_hydapi | 13 | 8.2 % | 2,188 | 4.1 % | -5.35 | -3.15 |
| pooled_dev_wave2 | rws_waterwebservices | 2 | 1.3 % | 327 | 0.6 % | -2.18 | -2.17 |
| pooled_dev_wave2 | syke | 2 | 1.3 % | 705 | 1.3 % | -10.55 | -8.73 |
| pooled_dev_wave2 | uk_ea | 1 | 0.6 % | 21 | 0.0 % | -6.67 | -6.67 |
| pooled_dev_wave2 | usgs | 100 | 62.9 % | 25,210 | 46.9 % | -5.79 | -5.33 |

### Weighting scenarios

| panel | scenario | basis | contrast pp | 95 % CI |
|---|---|---|---|---|
| development | network_equal | equal_networks | -5.10 | [-5.89, -4.34] |
| development | provider_equal | equal_providers | -4.69 | [-5.52, -3.82] |
| development | downweight_usgs_to_median_provider_by_networks | networks | -4.80 | [-5.65, -3.98] |
| development | downweight_usgs_to_median_provider_by_cases | cases | -5.12 | [-6.23, -4.23] |
| development | leave_usgs_out_network_equal | equal_networks | -4.72 | [-5.62, -3.82] |
| development | leave_usgs_out_case_weighted | cases | -6.43 | [-7.64, -5.40] |
| development | case_weighted_pooled | cases | -6.35 | [-7.12, -5.49] |
| wave2_external | network_equal | equal_networks | -5.18 | [-6.49, -3.96] |
| wave2_external | provider_equal | equal_providers | -4.96 | [-7.44, -2.17] |
| wave2_external | downweight_usgs_to_median_provider_by_networks | networks | -4.64 | [-7.62, -1.31] |
| wave2_external | downweight_usgs_to_median_provider_by_cases | cases | -4.50 | [-7.68, -0.73] |
| wave2_external | leave_usgs_out_network_equal | equal_networks | -4.08 | [-9.79, 1.78] |
| wave2_external | leave_usgs_out_case_weighted | cases | -9.64 | [-14.66, -2.02] |
| wave2_external | case_weighted_pooled | cases | -5.89 | [-6.92, -4.91] |
| pooled_dev_wave2 | network_equal | equal_networks | -5.07 | [-5.72, -4.44] |
| pooled_dev_wave2 | provider_equal | equal_providers | -4.68 | [-5.62, -3.72] |
| pooled_dev_wave2 | downweight_usgs_to_median_provider_by_networks | networks | -4.70 | [-5.55, -3.79] |
| pooled_dev_wave2 | downweight_usgs_to_median_provider_by_cases | cases | -5.05 | [-6.05, -4.14] |
| pooled_dev_wave2 | leave_usgs_out_network_equal | equal_networks | -4.63 | [-5.57, -3.63] |
| pooled_dev_wave2 | leave_usgs_out_case_weighted | cases | -6.57 | [-7.57, -5.35] |
| pooled_dev_wave2 | case_weighted_pooled | cases | -6.32 | [-6.94, -5.62] |

### Leave-one-provider-out (network-equal)

| panel | dropped | nets left | cases left | network-equal pp | Δ vs all pp |
|---|---|---|---|---|---|
| development | arso | 100 | 37,315 | -5.24 | -0.14 |
| development | chmi | 98 | 34,710 | -4.88 | 0.22 |
| development | foen | 108 | 37,849 | -5.16 | -0.06 |
| development | gkd_bayern | 103 | 30,261 | -5.06 | 0.04 |
| development | lubw | 104 | 38,850 | -5.13 | -0.03 |
| development | nve_hydapi | 97 | 38,516 | -5.34 | -0.24 |
| development | rws_waterwebservices | 108 | 40,377 | -5.14 | -0.04 |
| development | syke | 108 | 39,999 | -5.04 | 0.06 |
| development | usgs | 54 | 27,755 | -4.72 | 0.38 |
| wave2_external | hubeau | 45 | 12,282 | -5.29 | -0.12 |
| wave2_external | uk_ea | 48 | 12,996 | -5.14 | 0.03 |
| wave2_external | usgs | 5 | 756 | -4.08 | 1.10 |
| pooled_dev_wave2 | arso | 149 | 50,332 | -5.17 | -0.10 |
| pooled_dev_wave2 | chmi | 147 | 47,727 | -4.92 | 0.15 |
| pooled_dev_wave2 | foen | 157 | 50,866 | -5.11 | -0.04 |
| pooled_dev_wave2 | gkd_bayern | 152 | 43,278 | -5.04 | 0.02 |
| pooled_dev_wave2 | hubeau | 155 | 52,986 | -5.11 | -0.04 |
| pooled_dev_wave2 | lubw | 153 | 51,867 | -5.10 | -0.03 |
| pooled_dev_wave2 | nve_hydapi | 146 | 51,533 | -5.24 | -0.18 |
| pooled_dev_wave2 | rws_waterwebservices | 157 | 53,394 | -5.10 | -0.04 |
| pooled_dev_wave2 | syke | 157 | 53,016 | -5.03 | 0.04 |
| pooled_dev_wave2 | uk_ea | 158 | 53,700 | -5.07 | 0.00 |
| pooled_dev_wave2 | usgs | 59 | 28,511 | -4.63 | 0.44 |

### Verdict on provider-level generalisation

**No — the current evidence does not support provider-level generalisation beyond a directional statement.** In the wave-2 external panel USGS holds 94.2 % of cases and 89.8 % of networks; the non-USGS pool is 5 networks (756 cases) across 2 providers, one of which (UK EA) is a single network of 21 cases. Concretely, on the wave-2 panel:

* `case_weighted_pooled`: -5.89 pp [-6.92, -4.91]
* `network_equal`: -5.18 pp [-6.49, -3.96]
* `provider_equal`: -4.96 pp [-7.44, -2.17]
* `downweight_usgs_to_median_provider_by_networks`: -4.64 pp [-7.62, -1.31]
* `downweight_usgs_to_median_provider_by_cases`: -4.50 pp [-7.68, -0.73]
* `leave_usgs_out_network_equal`: -4.08 pp [-9.79, 1.78]
* `leave_usgs_out_case_weighted`: -9.64 pp [-14.66, -2.02]

The direction and rough size survive re-weighting on this panel, but the intervals widen sharply once USGS is removed and the non-USGS stratum rests on 5 networks. 'Three providers' is therefore three *sampling frames* on one dominant agency's measurement practice, not three independent validated populations; a provider-level claim needs new networks from providers that are not in any opened panel.

## 4. What is missing: claims that need networks used nowhere yet

Machine-readable in `independent_evidence_requirements.csv`. Claims whose current wording needs networks outside every opened panel (development, reserved-36 opened, wave-2, sealed USGS, transport, NVE probe): C14, DEPLOY-CERT, F07, L1, M1, P0-05, P0-06-TRANSPORT-SAN, P0-07-POOL, P0-07-TRANSPORT, R1, REG. The 36-network reserved panel is opened and is **not** proposed as new confirmation, and neither is any other opened panel.

Design requirements from the analytic relation `N = (2.802 x SD / MUE)^2` (panel-specific SD):

| panel | MUE 2 pp | MUE 3 pp | MUE 5 pp |
|---|---|---|---|
| development | 38 networks | 17 networks | 7 networks |
| wave2_external | 26 networks | 12 networks | 5 networks |
| pooled_dev_wave2 | 36 networks | 16 networks | 6 networks |

Residual untouched pool in the repository: the multi-agency prior-access audit flagged 54 never-used networks, but 53 of them are now used by scored/opened panels (the p0_07b transport score); the derived residual is 1 network(s) (`residual_unused_networks.csv`). Any new confirmation therefore needs newly recruited networks from providers not yet in the panel, and a fresh repo-wide prior-access audit before sealing.

## What this does not prove

1. **Not a new confirmation.** Nothing here scores a new panel. The reserved 36-network panel, wave-2, the sealed USGS panel, the transport panel and the NVE probe are opened and cannot be re-used as confirmation.
2. **The empirical distribution is the panel, not the target population.** Power is computed by resampling networks from the development or wave-2 network distribution. If a newly recruited population has a different between-network spread, the power numbers move.
3. **Shift model.** MUE power re-centres each simulated study on the MUE; it assumes the shape and width of the sampling distribution do not depend on the true effect. The normal-approximation columns are reported beside it and the empirical alpha at 0 is the coverage check.
4. **Wave-2 has 49 networks.** A design N of 60 or 80 cannot be drawn from the wave-2 pool without heavy network reuse (recorded as `mean_distinct_networks` and `share_draws_with_duplicates` in `power_table.csv`); those rows describe a super-population, not a feasible recruitment from the existing list.
5. **ICC is defined on a selection-derived variable.** `d_i` depends on the retention rule, so the ICC is a property of this operating point (0.5 and 0.9 retention are reported in `network_variance_table.csv`).
6. **Case counts are not independent observations.** Outage realisations repeat within station-years; every interval here clusters by network and the effective independent network count is far below the network count.
7. **Provider weighting is not a substitute for new providers.** Re-weighting changes the estimand; it does not add independent measurement practice.

## Files

* `power_table.csv` (required)
* `network_variance_table.csv` (required)
* `provider_leverage.csv` (required)
* `independent_evidence_requirements.csv` (required)
* `protocol_fingerprint.json` (required)
* `SUMMARY.md` (required)
* `weighting_scenarios.csv` (supporting)
* `leave_one_provider_out.csv` (supporting)
* `per_network_contrasts.csv` (supporting)
* `residual_unused_networks.csv` (supporting)
* `simulation_diagnostics.json` (supporting)

Wall time by section (s): section0_estimator_equivalence_seconds=50, section1_variance_icc_seconds=10, section2_design_simulation_seconds=719, section3_provider_leverage_seconds=12, section4_requirements_seconds=0; total=791.
