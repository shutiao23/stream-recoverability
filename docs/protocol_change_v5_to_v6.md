# Protocol change v5 to v6: major-review corrections

## Trigger and evidence status

This amendment was made in response to major review after the internal dense
results were visible. It is therefore a correction and robustness-analysis
record, not a claim that the new analyses were preregistered. The original
`recoverability_prediction_v1.json` remains byte-unchanged.

## 1. One frontier path

### Defect

`statistical_frontiers.csv` used the frozen anchor/year bootstrap with connected
overlap components. `dual_frontier_comparison.csv` independently called
`estimate_dual_frontiers`, which paired scenario/mask identifiers and used a
different confidence curve. Thus the climatology denominator was nominally the
same but censoring and frontier days could disagree.

### Correction

`run_frozen_analysis` now invokes `analyze_frontiers` for both climatology and
validation-selected best-simple skills. Compact dual-frontier tables are views
of those canonical artifacts, not new estimates. A post-run assertion checks
all 27 climatology station--model cells for identical frontier days and
censoring. The retired helper remains available for legacy unit tests but is
not a formal-output code path.

## 2. Model-versus-climatology p-values

### Defect

Every station's overlapping dense anchors formed one connected overlap
component. The hypothesis code averaged all complete curves to that single
number and then ran a two-sided Wilcoxon test with `n=1`, producing exactly
`p=1` for every row. The issue was loss of the inferential unit, not a reversed
alternative.

### Correction

Training seeds are collapsed first, followed by one mean across predeclared gap
lengths per anchor/year. The frozen two-sided Wilcoxon rule is applied to the
24 non-reference station--model hypotheses. The three climatology
self-comparisons are retained for table completeness as
`hypothesis_status=reference_not_tested` with missing p-values. BH adjustment
uses the 24 finite hypotheses. The confidence curve continues to use the
overlap-aware joint bootstrap, so this change does not treat hidden days as
independent.

## 3. Node importance

### Defect

The old estimator compared the same model after a singleton failure with that
model under the full network. Models that could not degrade gracefully produced
errors above climatology, so the output mixed sensor value with implementation
failure.

### Correction

At each matched target-gap unit, the estimator now selects the minimum MAE over
all available methods after failure and under the full network. Climatology is
included in both minima as a hard cap. Impacts are averaged only after this
unit-level reselection. Negative values remain visible and are interpreted as
finite-sample/model-selection variation, not information created by failure.

## 4. Reviewer-triggered scientific diagnostics

The revision adds:

- annual minima and amplitudes and pre/post thermal-memory summaries;
- a data-derived memory--range regulation fingerprint in 3 + 5 stations;
- expanded measured-covariate anomaly regressions;
- 2016--2017 and post-hoc 2016--2020 budget recalibration;
- state-matched climatology re-scoring;
- annual-mean-removed skill;
- absolute model and climatology MAE in degrees C;
- the evaluate-once Chattahoochee result after all execution gates passed.

The 2016--2020 state control overlaps evaluated outcomes and is labelled
post-hoc. No numeric external effect threshold is retroactively described as
preregistered; the frozen external evidence is the site/type roster and full
train-only predicted curves.
