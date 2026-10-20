# Finding closure after the aligned-policy round (2026-10-20)

Base: `bfc797ef43` (the commit reviewed on 2026-10-19). This table supersedes the
2026-10-15 closure audit for findings F01–F11 of the 2026-10-19 review. The
point-by-point response with numbers is `paper/wrr/RESPONSE_TO_REVIEW.md`; the
round summary is `results/wrr_submission_ready/major_revision_20261020/README.md`.

| id | severity | what the review asked | what was done | where |
|---|---|---|---|---|
| F01 | Blocker | unify the delivered reconstruction and the failure event | the whole chain now reads `abserr_policy`; the script proves the policy error equals the stored prediction minus truth before use; the certificate error survives only as a ranking score. The object mismatch affected 6.90 % of external cases and understated the fitted-vs-peak gain by ~4.5 points | `p0_01_aligned_policy_admission/`, `p0_05_repair_attribution/`, `scripts/330`, `scripts/334` |
| F02 | Major | separate population risk from finite-batch error; check extreme-percentile stability | 2,000 repetitions per scenario with the deployed rule imported from the analysis code: population-risk violation 0.4 % (baseline), 0.6 % (near cap), 0.4 % (unequal groups), 2.4 % (twelve groups), against finite-batch exceedance 7.8/7.5/4.6/12.2 %. The old 8.5 % is retracted as a misreading. 1,000→10,000 bootstrap draws changes 42/150 thresholds, ≤3.9 points of retention (≤1.0 for the fitted score) | `p0_02_selection_calibration/`, `p0_01_.../threshold_stability.csv`, `scripts/332` |
| F03 | Major | one tie rule from calibration to deployment | no jitter anywhere; a threshold is an observed score and `s ≤ τ` admits whole tie blocks at every stage; the fixed-70 % rule breaks ties on a stable case key. The ablation bounds the old inconsistency at ~1.3 points | `scripts/330`, `scripts/334`, `p0_05_repair_attribution/` |
| F04 | Major | compare against "no screen" at the same risk budget | `reconstruct_all` is a first-class arm. Designed panels: it fails at 15.3 %/14.9 %, so the cap binds. Real calendars: 2.6–4.1 %, under the cap; screens keep 93–96 % and cut risk to 0.5–1.7 %; fitted-vs-peak falls to 0.2–2.4 points. The cap was not tightened afterwards | `p0_03_real_calendar_adoption/`, `scripts/331`, manuscript §4.4, §5.3 |
| F05 | Major | complete the environmental-judgement statistics | all three fold seeds, two hot thresholds, both weightings, a full confusion table, refusal cost and paired group-clustered intervals. Fitted score: selection +1.1 points, total +0.7 [−0.3, +1.6]; refused hot years 24.5 % against 0 % for reconstruct-all (which misses 1.3 % instead) | `p0_04_hot_year_closure/`, `scripts/333`, SI Table S7 |
| F06 | Major | keep the pre-specified practical threshold and let the result decide the paper's route | the margin is now met against the peak-window rule (8.0/7.3/7.0 external; 10.3/10.1/9.7 development) and not met against the certificate bound (+1.6 external; −1.7 to −2.6 development). The paper is a method study with a measured regime boundary, not a superiority claim | manuscript §4.4, §5.2–5.3, `p0_06_confirmation_protocol/PROTOCOL.md` |
| F07 | Major | one chain across text, SI, figures and PDF | manuscript rewritten (28 pp draft, 15 pp published layout), SI rewritten (13 pp), five new main figures (one draw.io system schematic) with source tables, old certificate-screen numbers moved to SI history | `paper/wrr/`, `scripts/335`, `p0_06_figures/` |
| F08 | Major | condition the mechanism claim; test residual correlation and competing peaks | "position governs" withdrawn; reconstructor range 0.24–0.64 °C at 30 days; linear interpolation keeps a 1.16 °C length effect at full support; misalignment 0.28–0.70 °C; residual persistence 0.84–0.88 and +0.16–0.36 °C above the median; competing peaks do not order the error (negative control) | manuscript §4.2–4.3, §5.1, `p1_mechanism_boundary/` |
| F09 | Major, conditional | keep the validation scope honest | the external comparison is a cross-fit on an opened panel; stated in the abstract, the limitations and the open-research statement. No sealed claim is made | manuscript abstract, §5.4, Open Research |
| F10 | Minor | counts, units and the SI | all counts regenerated from the aligned run (5,114; 53,721; 40,704; 13,017; 2,422; 418); shares as fractions, differences in points; the measurement-stratum gap is disclosed rather than assumed | manuscript §2.2, §5.4; SI §S5 |
| F11 | Minor, submission | FAIR and administration | scripts, protocol fingerprints, manifests and figure sources in place; the build refuses submission-ready status while the author block is a placeholder. No claim of independent full reproduction is made | `paper/wrr/build_report.json`, SI §S9 |

## What the round verifies

* `python -m pytest tests/` exit 0 on this tree (158 test modules).
* `python scripts/223_wrr_build.py` green except the author placeholder: three
  key points ≤140 characters, abstract 248 words, plain-language summary 200
  words, 61 headline numbers present, 27 references cited and rendered, no
  uncited entries, all three PDFs current.
* The five figures are rendered at the printed width (5.6 in for the four data
  panels, 5.29 in for the draw.io schematic) with embedded fonts and source
  tables written next to them (`p0_06_figures/fig{1,3,4,5}_source.csv`).
* The aligned script aborts if `abserr_policy` does not equal the stored
  prediction minus the reference value, so the object mismatch cannot silently
  return.

## Still open (deliberately)

1. **A pristine panel.** None remains for this method. A sealed confirmation
   would need new data; the paper states this and claims a cross-fit only.
2. **The documented-daily-mean subset.** The aligned advantage was not
   re-estimated inside the measurement stratum; the article says so instead of
   assuming transport.
3. **Author metadata.** A human gate. Names, affiliations, funding and ORCID
   identifiers are not inferred from a version-control alias.
4. **Permanent archive.** A Zenodo DOI is planned for acceptance; the repository
   is a development repository and is not offered as the archival copy.
