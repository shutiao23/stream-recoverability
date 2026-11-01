REVIEW CANDIDATE — NOT A COMPLETE PUBLICATION DEPOSIT

This local archive contains project code, manuscript files and selected aggregate
results. The BC published daily input, unmodified Nechako author archive, and
Poudre author raw Parquet files are included under CC BY 4.0 with attribution.
The additional USGS observation-only daily API snapshot is included with
source attribution and acquisition queries. Run
`make review-usgs-observed-reproduction` to replay its original selection and
independently audit the nine reported windows using the supplied payloads.
This does not establish full-day sampling or model accuracy.
The main-record observation subset contains processed daily values for 95 of
the original 96 eligible stations and all 35 witness years; the LUBW station
is omitted. Run `make review-open-observed-reproduction` for its independent
record arithmetic and six screening-rule checks. It cannot establish eligibility
for the omitted station, sensor quality, upstream QC, or model accuracy.
The selected Nova Scotia portal JSON pages are included under the province's
Open Government Licence with attribution; the separately obtained legacy
workbooks remain local because their specific reuse terms are unresolved.
The original forward role assignment can retain other same-region source
groups. The bundled strict-region sensitivity covers affected release models
three archive stations, annual intervals and release-then-trend; it is not a complete strict-region rebuild. Its
restricted trained models and case-level outputs remain local.
The original source models depend on positive-weight LUBW cases even when
their target stations come from sources with recorded reuse paths. A post-hoc
candidate-provider, strict-region sensitivity is complete and its aggregate
comparisons are included. Its local models and case-level data are not included;
it is not a replacement for the original comparisons.
Other underlying source observations, main-model case-level tables and trained
model weights are not included. Make targets therefore cannot reproduce the study
from this archive alone. See dependency_inventory.json and DATA_RIGHTS.md.
A separate local-only case audit can be run if the rights-restricted evidence
is available; the restricted evidence itself is not included here.
The bundled Nechako archive contains all 32 source sites. Re-run the selected
site's reference qualification using `make review-nechako-qualification`;
its frozen screen found no qualifying complete reference year and did not
evaluate a reconstruction model.
The Poudre source files contain multiple sites and parameters. Re-run the
four selected sites using `make review-poudre-qualification`; no examined
site-year qualified and no reconstruction model was scored.
The USACE reservoir subset contains attributed time and temperature columns
from ten level-1 files. Run `make review-usace-open-reference` to reproduce
the 69 station-year availability results and the later conditional H30-bound
and observed-record screening; no full year met the stringent rule. The
conditional bounds assume missing samples lie within -5 to 50 degrees C and
do not validate source measurement quality or model accuracy.
The separate reservoir partial-history comparison additionally stages its
roster, weather, plans and aggregate scores. Its source-model weights and
per-case predictions, full source missingness generator and source calibration
are not included; the model comparison cannot be replayed from the candidate
alone. Given authorized access to those exact files, copy the included
`data/external/wrr_usace_reservoir_20261027/partial_history_roster.csv` into
`private/wrr_usace_reservoir_reference_20261027/partial_history_roster.csv`
and run `python scripts/838_usace_partial_history_predict.py`. The plan records
the exact paths of the additional required inputs. History
interpolation and zero actually complete training years differ from the original
complete-history model regime. The additional numerical dependencies used by
this generator are listed in `requirements-wrr-partial-history-replay.txt`.
The post-hoc feature-support, clipping and numerical-gate diagnostics include
aggregate reports and methods. Recomputing source training extrema, model leaf
paths or individual cases requires the restricted source-case table and model.
The source-history factorial sensitivity includes its selected processed water
and air inputs and aggregate scores. `make review-source-partial-history-reference`
checks water-year qualification and target H30; rerunning model predictions
requires separately restricted region-held models, calibration and source
missingness generator. It is an in-source, posthoc sensitivity, not independent
climate confirmation.
The USGS partial-history snapshot includes eight years of public continuous
observations, the processed daily source inputs, NASA forcing and a portable
reference replay. Run `python data/external/wrr_usgs_partial_daily_20261027/scripts/890_public_usgs_reference_replay.py`.
It does not reproduce model scores, because restricted source weights and
case-level predictions are not included. The evaluated observations were
previously opened; their clock and instrument quality remain unresolved.
The source support-warning evaluation includes the post-hoc aggregate policy
and tolerance summaries. Replaying its source cases or model outputs requires
the separately restricted source-case table and model; the matched-score
comparison uses the evaluated score distribution and is not prospective.
The Nova Scotia portal's reported-label completeness can be rerun using
`make review-nova-portal-completeness` without the legacy workbooks. This
does not establish timezone, point-level quality or independent validation.
The separate two-site Nova Scotia exploratory comparison includes selected
reported-clock daily inputs and attributed NASA POWER forcing, but not the
source-model weights or local-only case predictions. Its score audit requires
those local case files and does not establish strict-reference qualification.
The reported-day +/-1-hour sensitivity includes its attributed shifted daily
inputs and aggregate results; its per-case audit also requires locally held
baseline and shifted predictions, which are not in this package.

To recreate manuscript figures 2--5 using only the included aggregate tables:
    make review-figures-from-summaries
This checks figure rendering and assumes the summary tables; it does not
refit a model, verify individual cases, recreate Figure 1, or establish
independent scientific validation. See the original main and supporting PDFs.

The 2026-10-28 consistency materials are included: the all-station-year rule
accounting, failure-stratum cases, rank-convergence cases, the two-method
intersection table, the uncertainty case table, and the design-correction
manifest. From an extracted copy run
`python scripts/930_delivery_consistency.py`
to recompute those summaries and compare them with the manuscript text.
Compile review_completion_article.tex and review_completion_supporting.tex
afterward. This does not refit models or replace a restricted-data replay.

The 2026-10-29 scientific revision adds common-weight regional diagnostics,
within-station annual water-air estimates, paired year-set error decomposition,
common annual-longest-gap metrics, and three-seed fixed-input trajectory replay.
See docs/reviews/wrr_process_revision_20261029/README.md and scope.json under
results/wrr_process_revision_20261029. From an extracted copy, the frozen-input
numerical replay runs with `PYTHONPATH=src python scripts/962_process_trajectory_budget.py`.
The raw-archive audit (965) still needs the locally held original source-case and
whole-archive designs; their complete availability is not claimed by this ZIP.
That earlier revision did not re-estimate larger-budget source-role offsets.
The current experiment below completes that step on the fixed numerical subset.

The current experimental extension is in results/wrr_process_experiments_20261029.
It regenerates 2,370 original source-calibration cases and scores the same 27
target station-years at three nested budgets and seeds, without refitting D2.
It also enumerates every same-count subset on the 807-archive common cohort.
Read the dataset_catalog.csv, data_dictionary.csv and the current experiment
response/data guide before mixing source/target, seed/mask, or annual/trend units.
From an extracted copy, run:
    python scripts/975_replay_source_calibration.py
    python scripts/977_replay_time_support.py
These bounded replays use the included frozen daily/annual inputs and saved
references. They do not reconstruct all original data or retrain the daily or
D2 models. Source recalibration changes local endpoints and method comparisons;
500 paths on two target groups do not establish convergence or a general winner.
For current observation-only replay with the explicitly new content manifests:
    python scripts/967_current_observation_replay.py replay
Old unpinned receipts and manifests remain historical and are not silently
given current hashes as evidence of earlier provenance.

CITATION.cff describes an earlier v1.1.0 code-only release; it does not
identify or authorize this uncommitted manuscript revision. The authors and
archival citation for this revision are pending.

No software or dataset DOI is claimed for this revision. Author names, affiliations, funding,
conflicts, reviewer access and permanent data/code deposits remain to be
supplied or established. Do not submit this as a completed Open Research package.

The NEON qualification summarizes the CC BY 4.0 archive by Nicholas Marzolf,
https://doi.org/10.6084/m9.figshare.28074452.v1, and does not constitute an
independent backup-sensor or reconstruction-accuracy validation.


2026-10-31 MINOR-REVISION DELIVERY

Both PDFs in this archive were rebuilt from the included TeX sources. The
supporting PDF now carries the same finite-record title as the article and the
1981-2025 annual-longest-gap row. The cover letter now uses that same title and
states the 805-archive, 30-90-day controlled-gap scope. The revised article
clarifies that the main slope gains come from forward controlled 30-90-day gaps
and a finite-record target, treats the RMSE-to-median-slope ratio as aggregate
scale context, reports station/group heterogeneity of the fixed-count controls,
and states that paired group intervals are conditional on the saved annual
predictions and predefined groups. See
docs/reviews/wrr_multiview_review_20261031/MINOR_REVISION_COMPLETION_ZH.md.

The package-level acceptance record and package content fingerprint are stored
outside the archive in results/final_release_20261031/acceptance.json and
dist/wrr_final_candidate_20261031.manifest.json. The archive itself carries
RELEASE_RECEIPT.json and CONTENT_MANIFEST.sha256 for its included files.

The earlier 2026-10-29 ZIP remains a historical frozen candidate. Its passing
validation does not certify this revision.

Author names, affiliations, funding, conflicts, legal reviewer access and a
permanent repository/DOI remain author-supplied submission tasks. This archive
does not fill or imply them.

2026-10-31 STANFORD-PERSPECTIVE MINOR REVISION (r2)

The target is now stated explicitly as each station's fixed set of complete
reference years. The set need not be contiguous: 24 of the 41 forward stations
have internal calendar gaps and the smallest set has seven years. Masks,
retention rules and scores act on that same fixed set.

The supporting information now distinguishes three evidence levels for the
year-set error: the exact OLS weight identity, an iid linear working benchmark
for variance, and the observed archive result. The benchmark uses the complete-
reference residual variance and the exact Sxx weight-distance formula. Its
residual includes real interannual variability, curvature and observation error;
it is not a noise decomposition, a coverage guarantee or a causal attribution.

The empirical-calendar extension is in results/wrr_final_revision_20261031 and
is reproduced by scripts/981_stanford_revision.py. It covers 818 actual-mask
calendar archives (280 nontrivial choices, 2,646 feasible subsets) and keeps the
805-archive controlled-gap cohort separate. Calendar CDF has a point improvement
but its paired interval includes zero; Sxx and all-year intervals are negative.
These are simulated empirical-calendar masks, not external accuracy validation.
The two cohort differences are not a causal missingness effect.

D2's point-estimate accuracy and availability are reported separately. D2 is
available on 820/820 forward archives in both families; the classical comparator
is available on 738/820 and 701/820. On the comparator-unavailable subsets D2
RMSE is 0.2437 and 0.0933 degrees C per decade. Availability does not establish
accuracy, release suitability or probability-interval coverage.

The release tool now rechecks package/workspace byte identity and binds the
current TeX and PDF hashes to the package receipt and verification report before
writing acceptance. Changing only a TeX file, only a PDF, or another packaged
result after verification is rejected. See tests/test_final_release_freshness.py
and scripts/982_final_release_tests.py.

The package-level acceptance record and package content fingerprint for this r2
candidate are stored outside the archive in
results/final_release_20261031_r2/acceptance.json and
dist/wrr_final_candidate_20261031_r2.manifest.json. The earlier 2026-10-31
candidate remains a historical frozen archive; its passing record does not
certify this r2 revision.

2026-11-01 CORRECTED CANDIDATE

This candidate supersedes the r2 package. The r2 package and its acceptance
record remain historical and are not evidence for this revision.

Corrections relative to r2:
- The SI now defines subset OLS weights with each set's own centering and Sxx.
  The previous text truncated full-sample weights; the numerical code already
  used the correct subset centering, so the scientific tables did not change.
- scripts/983_verify_extension_replay.py now compares all 11 declared science
  tables by schema, primary keys, labels, legal NaN positions and finite values.
  It rejects finite-value changes, label changes, key changes, unexpected NaN
  and Inf, and it never uses NaN as a passing shortcut.
- results/wrr_final_revision_20261031/data_manifest.json is written after the
  scientific tables and scope, does not hash itself, and is checked for current
  hashes. table_spec.json records primary keys, units, legal missing values and
  which files are compact replay inputs.
- The uniform-random sign-disagreement quantity is stored as an expected count,
  not truncated to an integer. The deterministic 3/5/4/0 values are unchanged.
- The manuscript now limits Y_i to the forward analyses and states that offline
  analyses use their corresponding historical complete reference-year sets.
- The local source check `ruff check --select E4,E7,E9,F src` now passes, the
  full pytest suite passes, and the declared CI evidence gates run to
  inventory_only with --allow-no-go. These are local checks, not a remote CI
  run for this revision.

The candidate package and its manifest/acceptance record are named
dist/wrr_final_candidate_20261101.zip,
dist/wrr_final_candidate_20261101.manifest.json and
results/final_release_20261101/acceptance.json. The full package sha256 is in
the manifest and acceptance record, not in this README inside the package.

Author names, affiliations, funding, conflicts, legal reviewer access and a
permanent repository/DOI remain author-supplied submission tasks.

2026-11-01 SECOND POST-REVIEW REVISION (r2)

This candidate supersedes the first 2026-11-01 candidate and the 2026-10-31
candidate. It closes the remaining local engineering gaps:

- scripts/981_stanford_revision.py now labels compact-input paths without
  assuming they are under the code root. A test runs the full 8,115-row
  extension from an outside-root result directory with no original case cache.
- The full-test summary is generated from real JUnit (scripts/984), binds the
  JUnit hash, command, interpreter and source-tree hash, and scripts/985
  composes the local CI-equivalent record. 980 rejects zero-test, nonzero-exit,
  all-skipped, contradictory-count, stale-JUnit and stale-source summaries.
- table_spec.json now explains the masks object: year -> semicolon-separated
  start:length segments, with zero-based row position and consecutive daily-row
  length. The geometry table has per-field units, including degrees C^2 for the
  reference residual variance and decade^-2 for the squared weight distance.
- The SI all-ones vector uses \mathbf{1}; the PDF text is h = alpha 1 + b x_F +
  epsilon, not the previous missing-glyph form.
- The abstract adds the 818-archive empirical-calendar contrast (0.114 warm,
  0.067 all-year; CDF interval includes zero) and remains 247 words.

Current local checks: 1,699 full-suite tests (1,698 passed, 1 skipped),
131 declared-release tests, ruff 0 findings, package verification, delivery
check and strict 11-table replay (max finite difference 2.1316e-14). The local
evidence gates run to inventory_only with --allow-no-go; author/rights blockers
are not claimed resolved.

The candidate, manifest and acceptance record are named
dist/wrr_final_candidate_20261101_r2.zip,
dist/wrr_final_candidate_20261101_r2.manifest.json and
results/final_release_20261101_r2/acceptance.json. The full package sha256 is in
the manifest and acceptance record, not in this README inside the package.

2026-11-01 THIRD POST-REVIEW REVISION (r3)

This candidate fixes the acceptance regression left by the previous hardening:

- release_provenance.validate_summary() again requires failures == 0 and
  errors == 0, and now parses the hash-checked JUnit file and compares all five
  counts with the JSON summary. 980 and 985 reuse this single rule.
- Negative tests cover positive failure counts, positive error counts, JUnit
  counts that disagree with the summary, and a failing JUnit paired with a
  zero-failure summary.
- The abstract now says explicitly that the CDF selector's paired RMSE-
  difference interval from warm-season screening includes zero. The abstract
  remains 249 words.

Current local checks: 1,704 full-suite tests (1,703 passed, 1 skipped, JUnit
and summary counts agree), 136 declared-release tests, ruff 0 findings, package
verification, delivery check and strict 11-table replay (max finite difference
2.1316e-14). The source-identity hash covers src/**/*.py and pyproject.toml;
scripts and tests are bound separately through the test list and JUnit hash.

The candidate, manifest and acceptance record are named
dist/wrr_final_candidate_20261101_r3.zip,
dist/wrr_final_candidate_20261101_r3.manifest.json and
results/final_release_20261101_r3/acceptance.json. The full package sha256 is in
the manifest and acceptance record, not in this README inside the package.
