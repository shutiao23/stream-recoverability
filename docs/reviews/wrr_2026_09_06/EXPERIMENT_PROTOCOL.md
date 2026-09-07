# WRR revision experiment protocol

Frozen before confirmation scoring. Development uses the 42 first-panel
networks already scored under route A. The 57 second-panel networks remain
descriptive. Confirmation uses QC networks that are in neither panel.

## Step 2 — fair recovery (highest-priority falsifier)

Same stations, seasons, and gap starts. Grid: 7, 14, 30, 60, 90, 120, 150,
180, 365 days. Archived first-panel placements are reused where the length
exists; 120 and 150 days are generated with the same candidate rule.

Crossed factors, same donor set:

| Recoverer | Training | Target boundary at train | Target boundary at eval |
|---|---|---|---|
| xgb_neighbor_boundary | all observed train days | adjacent-day mean | gap-wide linear interp |
| xgb_longblock_boundary | sampled train gaps | gap-wide linear interp | gap-wide linear interp |
| xgb_neighbor_noboundary | all observed train days | none | none |
| xgb_longblock_noboundary | sampled train gaps | none | none |
| ridge_neighbor_boundary | all observed train days | adjacent-day mean | gap-wide linear interp |
| donor_only_ridge | all observed train days | none | none |
| linear_interp | none | n/a | gap-wide linear interp |
| smooth_climatology | train DOY ±7 d median | none | none |
| doy_climatology | train DOY median | none | none |

External-information group, scored only where forcing exists, and not mixed
into the same-information ranking: `air_ridge`, `air_flow_ridge`, `air2stream`.

Primary Step-2 endpoints: MAE, climatology-relative benefit, sign-change
interval, and hottest-30 / exceedance-20 error on a gap-centred 365-day
window. If long-block or no-boundary training moves or removes the crossing,
the “universal threshold” claim is withdrawn.

## Step 3 — competitive baselines

Benefit predictors, all fit on historical roles only: current stratified
difference (`diff`), `r6_diff`, `default_difficulty`, `-risk`, seasonal
empirical benefit (explicitly tested for identity with `diff`), same-covariate
ridge, and a history-only switch between `default_difficulty` and `-risk`.
The strongest development competitor is frozen before confirmation.

## Step 4 — adopt / reject

Inner training years fit the recoverer. Later fitting years estimate paired
benefits and choose the rule. Outer evaluation years test it. Rules: mean
threshold; conservative historical quantile; unsupported → default. Report
net \(B\) over all placements, adopt rate, harmful rate, and reliability.
The test is whether the rule beats all-default.

## Steps 5–6 — ablation, realistic faults, yearly replay

Ablate season, difference, support refusal, and uncertainty refusal using
strategy loss, not Spearman. Faults: donor co-missing, missing right
boundary, transplanted historical gap geometry, heatwave / low-flow subsets.
Replay compares all-default, all-reconstruct, best fixed recoverer, seasonal
rule, and the frozen decision rule on whole station-years. Budget may be left
unused.

## Step 7 — mechanism

Only if a law claim is retained. Otherwise the paper is a prediction-and-
decision study. The generative battery is in
`src/stream_recoverability/experiments/wrr_revision/mechanism.py`.

## Step 8 — confirmation

Design, recoverer, default, support rule, primary endpoint, and failure
criterion are frozen on the first panel. Scoring then runs on held-out QC
networks. Inference is network-level.
