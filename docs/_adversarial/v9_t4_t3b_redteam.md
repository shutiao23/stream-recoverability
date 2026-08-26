# Red team: T4 natural outage and T3b gap triage

Date: 2026-08-26
Target: `src/stream_recoverability/experiments/natural_outage_scoring.py`, `gap_triage.py`, scripts 58–59, `sensor_policy.py`.

## Attacks that do not land

- Unlabeled missing days are not scored. Truth is held-out **observed** days; geometry is length/season from `real_missing_blocks.csv`.
- Manifests lock `passed: false`, `formal_evidence: false`, `confirmatory_eligible: false`, `n_networks_min_for_confirmation: 100`.
- Operator is fit on `train = observed & ~in_gap`, not on the planted block.
- Last-check temperatures are not opened.
- Freeze T3b numbers are read from v9: 5% false-release, 0.5 °C, +30% relative, +15 pp absolute. Numeric floors can flag; `passed` stays false.
- `POLICIES` now includes `degree` and `oh_bartos_2025_rank_revealing_qr` (and `current_network`).

## Must-fix / residual

1. **First T4 run scored 0 gaps.** Top empirical lengths are 3–6 days; shared `donor_regression_mae` required 10 test days. Fixed by `_gap_donor_mae` (min 5) and `MIN_EVAL_LENGTH=7` plus short/medium/long strata. The 1–6 day mass of the real catalog is **dropped**, not scored. That is a documented restriction, not the full empirical measure.
2. **Planted later-half gaps are not the same events as the real outages.** T4 is “same geometry,” not “those calendar holes.” Do not write “reproduced on natural missing blocks” as if the NaN stretches were labeled.
3. **`willamette_mainstem_real_missing_blocks.csv` is unused.** Loader skips `willamette_mainstem` wides. Freeze `t4_real_missing.existing_inputs` names that file.
4. **n≪100.** Even a large Spearman on 12 rivers is not T4 pass.
5. **T3b on later-year donor MAE (script 59 fallback) is not gap-specific.** Only `natural_outage_scores.csv` has `fill_mae` on planted gaps. Do not let `operator_vs_univariate_network.csv` substitute for triage.
6. **Relative improvement is `inf` if length-only releases nothing.** Do not treat infinity as a headline.

## Verdict

The design is the right T4 shape (geometry from real holes, labels from observed days). It is not T4 or T3 passed. Re-run after the 7-day floor must still refuse confirmation.
