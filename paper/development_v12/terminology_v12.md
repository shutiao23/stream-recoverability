# Terminology v12 (frozen labels for the revision)

Use these labels in the manuscript, SI, figures, and review response. Do not
relabel a split, tier, or estimand after seeing outcomes. This file replaces
the v11 binary supported/fallback vocabulary and the model-agnostic
"recoverability" framing.

| Term | Meaning |
| --- | --- |
| `model-conditional historical stress test` | Artificial gaps cut wholly inside the fitting years of a record and recovered with a named recovery model; the resulting curve inherits that model's error structure and ranks only that model's future error. Never "model-agnostic recoverability." |
| `within-network historical stress testing replicated across an outcome-disjoint network panel` | The study design. Stress curves are built per network and evaluated on networks whose outcomes were never used to build, tune, or select anything. Replaces "cross-network transfer." |
| `outcome-disjoint panel` | A panel whose networks have no recovery outcomes in any earlier panel (development, first, or second). QC-only reuse is disclosed separately and capped. |
| `direct support` / `directly supported horizons` | Units whose gap duration is in {7, 30, 90, 180} days AND a fitting-period curve cell exists (exact local, or the documented station/network-duration fallbacks where counted). The 874-unit and 841-unit numbers in the second panel. |
| `exact local support` | Station x duration x season curve cell exists; tier 1 of the support hierarchy. |
| `station-duration support` | Station x duration cell exists, season collapsed (tier 2). |
| `network-duration support` | Network x duration cell exists, station collapsed (tier 3). |
| `network-mean fallback` | Prediction is the network-wide mean of all fitting-period losses (tier 4); constant within a network, within-network rank undefined by construction. Second panel: 596 units = 572 horizon-unsupported + 24 direct-horizon without a station curve (CORRECTS the v11 "572 fallback" count, which missed the 24). |
| `unavailable` | No fitting-period support at all (tier 5); zero scored units in the panels. |
| `same-unit paired comparison` | Both predictors evaluated on identical unit subsets; differences bootstrapped by paired network resampling. The t01 fix for the v11 unequal-subset comparison. |
| `paired DeltaRho` | Bootstrap mean of per-draw (empirical - simple) Spearman; network-level and station-gap-level versions. |
| `within-network rank` | Spearman computed after removing network means (residualized pooled), or per-network Spearman with >= 3-4 units; undefined in the fallback tier. |
| `network-difficulty control` | A predictor that separates only network means (e.g., network-mean-only benchmark, pooled rho 0.326; network historical mean rung of the t03 ladder, 0.772 on the full panel). Shows the 0.805 is not between-network difficulty. |
| `continuous support-aware risk surface` | REML hierarchical model of log(1+MAE) on fitting-period placements (100,397 rows) with monotone duration spline, cyclic DOY, covariates, network/station random effects; provides predictions, 90% intervals, and support status at any duration. |
| `interpolation` | Surface predictions at 14 and 60 days, inside the fitted duration range (448 units; calibrated, slope 1.025). |
| `extrapolation` / `extrapolation boundary` | Surface predictions at 365 days, beyond the fitted range (124 units; rank 0.270, coverage 46.8%): THE boundary; supports abstention for point release, not loss capture. |
| `abstention` | Withholding a prediction/release on support or ambiguity grounds; counted as zero captured loss / zero gain in decision endpoints. Never inflates a budget metric. |
| `model-source x model-target matrix` | Cells = Spearman between a fitting-period stress curve of source family and outer-evaluation losses of target family, on the same networks. |
| `engineered-feature block` | Linear/PCHIP boundary, seasonal-boundary ridge, donor ridge, XGBoost: shared difficulty (self 0.93-0.98, cross 0.72-0.98). |
| `pipeline-specific difficulty` | Outside the block: BiLSTM (self 0.29-0.69, cross to block -0.24..0.28; neural vs XGBoost stress Spearman 0.067) and air2stream (self 0.64, cross ~0.24). |
| `mechanism-matched curve` | Trial gaps generated with the same missingness mechanism as the evaluation gaps (multi-block, donor-synchronous, forcing, online, uniform, summer- or high-temperature-biased). |
| `support-destroying mechanism` | Missingness that removes recovery information (donors, future boundary, forcing): donor-synchronous, target+primary-covariate, online. A uniform curve applied to these collapses rank (0.88-0.98 -> 0.20-0.40). |
| `expected Gaussian MAE` | sqrt(2/pi) x mean per-day conditional SD; the code-defined estimand of the operator column previously mislabeled "conditional-variance lower bound." Neither a variance nor an SD (t10). |
| `remainder (MAE excess)` | Realized MAE minus expected Gaussian MAE (0.165 -> 4.268 C, 7 -> 365 d). NOT identifiable as model error + drift; contains covariance misspecification, parameter-estimation error, non-Gaussianity, aggregation, finite-sample error. |
| `CapturedLoss@B` | Fraction of total observed loss in the top-B% of units ranked by a policy; oracle = 1 for the true top set at B. |
| `NDCG@B` | Position-discounted normalized gain over the score-ranked list truncated at B. |
| `network-balanced regret` | Mean over networks of within-network mean (selected loss - best-family loss). |
| `released units` | Units remaining after an abstention rule; comparators re-evaluated on the same released units for fair coverage-risk views. |
| `fit-period fit` / `simple descriptors` | Route-A linear model (gap length, target autocorrelation, donor R2, additive d/4 heuristic, nearest-donor correlation) with coefficients fit on fitting-period data only (development + first panel for the second-panel comparisons). |
| `calibration slope (equal-network weighted)` | Weighted OLS of observed on predicted with weights 1/(rows in network); the paper's calibration convention. |
| `rolling-origin cutoff` | Outer chronological split at 60/70/80% of record years; stress curve built strictly inside each training block. |
| `history-length learning curve` | Network Spearman vs fitting history (2/4/6/8/full years): 0.608 / 0.872 / 0.916 / 0.938 / 0.944; minimum usable history ~4 years. |
| `deployment-matched curve` | Stress curve built with the full 70% training block (equal to deployment length); diagnostic only (requires the evaluation window), quantifies the 49%-vs-70% training-length gap (paired MAE diff 0.013 C; Spearman 0.989). |
| `thermal-metric distortion` | |truth record - record with gap days filled (reconstruction) or dropped (no-fill)| for ten thermal-regime metrics; reconstruction restores computability (no-fill leaves amplitude undefined in 20.9% of placements). |
| `protocol v3` | Third-confirmation protocol: 80-120 outcome-disjoint networks; external timestamping (separate pre-outcome commit + OSF/Zenodo registration before outcomes); frozen margins; primary endpoints paired network-level DeltaRho on direct-support units (+0.038 observed; 80% power at N = 120), DeltaCapturedLoss@20%, NDCG@5%, thermal-metric protection floor (>= -0.02); full-panel within-network superiority vs simple NOT claimed (DeltaRho -0.093). Drafted, not yet registered; no v3 outcomes exist. |
| `v2 confirmation` | Internally hash-bound 57-network second panel; amendment and outcomes share one version-control commit; NOT externally verifiable preregistration. Provenance description only; never appears in the abstract. |
| `station retention / automatic filling` | Unsupported actions; no certified safe-fill set or placement margin exists (v2 triage released zero; placement regret 6.0% directional without margin). |
