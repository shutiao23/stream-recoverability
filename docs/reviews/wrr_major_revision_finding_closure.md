# Finding closure after the major-revision round

Base: `8eade30bbf` plus the round of 2026-10-15 (`046c3e9234` and after).
This table supersedes the earlier closure audit for the findings the review of
2026-10-14 raised; the earlier F01-F22 audit for the 2026-10-12 review remains in
`F_FINDINGS_CLOSURE_AUDIT.csv`.

| id | severity | what the review asked | what was done | where |
|---|---|---|---|---|
| F01 | Major | stop claiming the support feature is the contribution; converge on one method | P0-01 converged the method and listed six withdrawn claims; the manuscript reports the support increment as 0.05 pp ([-0.17,+0.23]) and the contribution as indicator-conditioned admission | `major_revision_20261014/p0_01_final_method/`, `docs/reviews/wrr_major_revision_round1.md` |
| F02 | Major, high | the risk-cap operating point must not read evaluation labels | P0-02 chose every threshold on calibration networks only (5 folds x 3 seeds, one-sided clustered bound) and scored the held-out fold once; the label-chosen frontier is reported separately as retrospective | `p0_02_frozen_risk_thresholds/` (version note; a first pass with a mis-scaled tie-break jitter is withdrawn and reproduced) |
| F03 | Major | compare calibration, abstention and no-abstention at equal risk or equal error cost | P0-02 compares at a common 5 % risk target; P0-04 compares abstention against judging everything at an equal error budget and at equal coverage | `p0_02_.../risk_cap_contrasts.csv`, `p0_04_env_closed_loop/equal_budget_comparison.csv` |
| F04 | Major, high | run the final rule on the real calendar and under neighbour co-failure, with cross-year gaps | P0-03 replayed the certificate rule (418 groups, 14 networks, 22 cross-year placements, gap-length assertions asserted); the donor estimate is now unavailable rather than replaced by an observed-window value, and the fallback is labelled | `p0_03_final_method_replay/` |
| F05 | Major, high | the hot-year metric must include prediction error, not only selection shift | P0-04 reports the exact three-term decomposition and keeps the old quantity under the name `selection_shift_pp` | `p0_04_env_closed_loop/share_decomposition.csv` |
| F06 | Major | replace the dominance claim with conditional evidence | the heading, the mechanism paragraph, the figure caption and the SI title now state that position and length both act and interact, with the air reconstructor added and a design-based phase interval | manuscript §4.3.2, `p1_mechanism_boundary/` |
| F07 | Major | do not treat three providers as three validated populations | P0-05 quantifies provider leverage and the effective independent network count (14.1 and 11.0); P1-transfer reports each measurement class separately | `p0_05_power_independence/`, `p1_transfer_measurement/` |
| F08 | Major | one coverage table; results tied to a measurement class | P0-06 built the station-level coverage table, the provider contract table and the class shares; the manuscript and SI now quote results per class | `p0_06_coverage_recompute/`, SI Table S2 |
| F09 | Major | stop presenting the fixed-window approximation as an MNAR bound | the manuscript quotes the day-level specified-shift sensitivity (240 cases, six networks), states that it is not an identification bound, and withdraws the approximation | manuscript §4.4.6, `amendments/mnar_day_level/` |
| F10 | Major | scope the process attributions to the design that supports them | the baseflow comparison is flagged as indicative rather than a replication; the reference/non-reference flag is described as a coarse proxy | manuscript §4.4.5 |
| F11 | Major | repeated draws for the learning curve; multiplicity and paired intervals | P1 repeated the learning curves (20 draws per size, 333 fits) and found the sample-efficiency claim unsupported; the paper's main contrasts are pre-declared, the rest reported as exploratory | `p1_learning_curve_repeats/` |
| F12 | Major | one version of the claims across text, SI, figures and PDF | dominance wording removed everywhere, abstract 249 words, key points <= 140 characters, PDFs rebuilt from the current source, and a style/claim audit written | commit `046c3e9234`, `docs/reviews/wrr_yang_style_compliance.md` |
| F13 | Minor, submission | parameter roles, units, archiving and author metadata | units annotated in four tables; the deployment recipe states the three thresholds and their roles; author metadata remains a human gate and the build still refuses to mark the manuscript submission-ready | manuscript tables, `metadata/submission_author_metadata.json` |

## Evidence that the round verifies

* `scripts/254_wrr_claim_binding_check.py` exit 0; 34 claims in the registry, 12
  permitted in the abstract or conclusions.
* `scripts/221_v18_audit_manuscript.py` 92 checks passing;
  `scripts/199_v17_audit_manuscript.py` 137 table cells matching artifacts.
* `scripts/266_wrr_figure_qa.py` 0 hard failures, 0 footer collisions across 20
  PDFs; every figure one page with embedded fonts.
* Full pytest suite exit 0 on the final tree.

## Still open (deliberately)

1. **No pristine panel remains** for the converged method; the wave-2 seal belongs
   to the frozen certificate screen. Recorded as claim M9 and in the limitations.
2. **Author metadata** (`metadata/submission_author_metadata.json`) is a human
   gate; the build reports NOT submission-ready until it is filled.
3. **Permanent archive**: a Zenodo DOI is planned for acceptance; the study
   inputs tarball exists for confidential review today.
