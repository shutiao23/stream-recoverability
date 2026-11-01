# Incomplete river-temperature archives

Recover annual heat statistics and test what incomplete observations support
about records and trends. The current work separates annual recovery, value
release, and trend uncertainty. Calibrated classical reconstruction remains a
full comparator; the experiments do not assume that D2 must win.

The [current experiments](docs/reviews/wrr_process_experiments_20261029/EXPERIMENT_RESPONSE_ZH.md)
complete the original-source recalibration sensitivity and enumerate every
same-count year subset. Calendar-based choices that include fixed complete years
improve on the warm-season screen in aggregate; all-year recovery improves further.
The same-count gains are not uniform across stations and groups. Recalibrating
2,370 source cases changes endpoints and local comparisons on the fixed 27 targets.
The data catalog distinguishes source calibration, target scoring, mask repetitions,
Monte Carlo seeds, historical native20 and nested samples.

The 2026-10-31 minor revision rebuilt both PDFs from the current sources, updated
the SI title and the 1981--2025 annual-gap row, and clarified controlled-gap scope,
the RMSE-to-median ratio, local heterogeneity and conditional group intervals. The
new package and acceptance record are listed under Current artifacts; the earlier
ZIP remains a historical frozen candidate.

Run `make review-process-experiments` to reproduce the analyses and manuscript,
then `make review-process-experiments-check` for independent arithmetic and
adversarial checks. The [data guide](docs/reviews/wrr_process_experiments_20261029/DATA_GUIDE_ZH.md)
records tables, keys, units and weights. The earlier fixed-budget-only revision
remains an archived baseline, not the completion claim for this experiment.

The main workflow uses ordinary files and readable cache names. Selected review
evidence, including the additional USGS observation snapshot, is listed in a
file manifest. Measurement quality and training/evaluation separation remain part of
the scientific method.

```bash
pip install -e '.[review,revision,dev]'
make review                # rerun targets using the required existing local source assets
make review-archive        # projected distributions, whole-archive trends and task support
make review-annual         # twenty held-region source comparisons with common support
make review-release       # three reported outputs and existing failure scenarios
make review-stress        # rule comparison and small heat/donor-outage experiments
make review-integrated     # released values and bounds followed by trend inference
make review-report        # generate the figures, research report and PDFs
make review-figures-from-summaries  # redraw four figures from included aggregate tables
make review-current-observation-replay # pin current content and replay the 95-station/USGS observation evidence
make review-package-check # extract ZIP, replay observations, redraw architecture and four summary figures, build PDFs
make review-bc-audit      # local case arithmetic and four hidden-value perturbation probes
make review-local-case-audit # verify restricted, local-only case evidence if prepared
make review-isolated-local-evidence # extracted code + read-only local evidence, Linux namespaces
make review-isolated-groupmax # recheck later group-max annual/trend results with local inputs
make review-heat-gap-source-audit # recheck matched-gap source comparisons with local restricted outputs
make review-heat-gap-source-replay # serially replay those source models, then run the audit
make review-nova-field-audit # acquire public field data if absent; replay nonconfirmatory date checks
make review-isolated-nova-field # fresh public download and offline arithmetic in an extracted package
make review-beaufort-proxy-open-replay # reproduce the literature-inspired summer-peak proxy from included processed inputs
make review-test          # scientific tests
```

The report and extracted-package checks require Graphviz (`dot`), LaTeX with
`latexmk`, and Poppler (`pdftotext` and `pdftoppm`) in addition to the Python
environment. Figure pixel equality is environment-dependent.

The archive experiment uses neighboring stations as observed covariates. It
jointly hides selected gap days in multiple target years before refitting daily
models; unmasked target observations and the designated donors remain usable.
Offline repair and the pre-2010-trained forward experiment are reported
separately, as are real calendars and controlled long gaps. All joint sampling
methods preserve the same annual marginal samples within an estimator; the two
estimators have different annual distributions. Both annual estimators respect
the observed-window bound, and a normal-spacing tail continuation is compared
with the former constant-tail assumption. The extrapolated tail is a modeling
assumption, not a coverage guarantee. Task calibration withholds unsupported
and degenerate cases; its available cases are compared with the same baseline.

```bash
make review-independent    # NZ reference qualification and additional approved-record corroboration
```

These external checks are unregistered unless an actual registration is recorded. The additional approved USGS records corroborate the observation-only record claim; sparse complete reference years do not provide a new reconstruction-accuracy validation. The revised intake reports prior-contact checks and qualification of USGS, NEON, Réunion and Canadian records, including failures. The BC published-daily comparison is exploratory; individual hourly completeness is not established.
Failed qualification, unavailable predictions and negative results stay in the
reported denominators. Author and deposit details remain to be supplied.

Current candidate (2026-11-01 second post-review revision):

- [Main manuscript](paper/wrr_tr/review_completion_article.pdf)
- [Supporting information](paper/wrr_tr/review_completion_supporting.pdf)
- [Latest revision completion report](docs/reviews/wrr_stanford_perspective_20261031/REVISION_COMPLETION_20261101_R2_ZH.md)
- [Latest post-review report](docs/reviews/wrr_postfix_review_20261101/REVIEW_ZH.md)
- [Earlier post-review audit](docs/reviews/wrr_plan_audit_20261101/REVIEW_AND_PLAN_ZH.md)
- [Candidate package](dist/wrr_final_candidate_20261101_r2.zip)
- [Candidate manifest](dist/wrr_final_candidate_20261101_r2.manifest.json)
- [Current acceptance record](results/final_release_20261101_r2/acceptance.json)
- [Current extension replay](results/final_release_20261101_r2/extension_replay.json)
- [Current local CI-equivalent summary](results/final_release_20261101_r2/ci_local_summary.json)

The full candidate sha256 is recorded in the external manifest and acceptance
record. Because this README is inside the package, it does not embed its own
package hash. The current candidate is a local release candidate, not a
completed publication deposit; author metadata, legal reviewer access and a
permanent archive remain pending.

Historical artifacts (not current evidence for the latest candidate):

- [First 2026-11-01 candidate](dist/wrr_final_candidate_20261101.zip), [manifest](dist/wrr_final_candidate_20261101.manifest.json), [acceptance](results/final_release_20261101/acceptance.json)
- [r2 2026-10-31 package](dist/wrr_final_candidate_20261031_r2.zip), [manifest](dist/wrr_final_candidate_20261031_r2.manifest.json), [acceptance](results/final_release_20261031_r2/acceptance.json)
- [Earlier 2026-10-31 candidate](dist/wrr_final_candidate_20261031.zip), [acceptance](results/final_release_20261031/acceptance.json)
- [Minor-revision completion report](docs/reviews/wrr_multiview_review_20261031/MINOR_REVISION_COMPLETION_ZH.md)
- [Previous frozen experiment package](dist/wrr_process_experiments_20261029.zip)
- [Experiment response](docs/reviews/wrr_process_experiments_20261029/EXPERIMENT_RESPONSE_ZH.md)
- [Independent source-calibration audit](results/wrr_process_experiments_20261029/source_calibration/independent_audit.json)
- [Experiment validation](results/wrr_process_experiments_20261029/validation.json)
- [Revised review-response results](results/wrr_review_response_20261027/)
- [Original whole-archive results](results/whole_archive/)
- [Research completion report](docs/SIMPLE_WORKFLOW_ZH.md)
- [Earlier study history](docs/project_history.md)

Raw observations and large training caches are local data products. The default
review workflow reuses existing daily refits, model weights and visible-quality
caches. A clean-environment rebuild of the full analysis, durable deposit and completed author and
funding information still require the listed source materials and authors. The aggregate-only
figure command redraws four figures from supplied summaries; it does not verify those
summaries. The evidence-architecture Figure 1 is regenerated from its Graphviz source, not from original observations. The separate USGS
observation-only replay checks ten saved daily API payloads, four output tables and
nine witness windows. The separate main-record subset supplies processed daily
values for 95 of 96 eligible stations and checks all 35 original witnesses plus
screening decisions; it cannot establish eligibility of the omitted LUBW station.
Neither check rebuilds the main models or establishes sensor accuracy.
Existing numbered scripts and older Make targets remain available for earlier analyses.

Local case-level audit evidence is described in [LOCAL_CASE_AUDIT_ZH.md](docs/reviews/wrr_review_response_20261027/LOCAL_CASE_AUDIT_ZH.md). This evidence is not authorised for distribution and is not a full raw-data rebuild.
The isolated local check requires Linux user, mount and network namespaces and
explicit local evidence. It hides the working repository from the child process,
mounts the evidence read-only, and runs the extracted candidate code without
network access. It uses the existing installed Python environment and does not
establish data permissions, external reviewer access or source-model retraining.
The group-max check also mounts the original whole-archive case cache, candidate
source models, a required pre-2010 stochastic bridge-repair table and selected
processed inputs read-only; these are not in the ZIP and their redistribution
remains unresolved. The repair dependency was identified post hoc and the
group-max audit fails if its locally verified version is absent or altered.
The twenty source-seed annual exports and the open-source archive calibration
also require local stochastic bridge-repair tables. Post-hoc replays compare
saved outputs with and without those tables; the relevant rerun entry points
fail when a documented table is missing or its bytes change. This does not
make the original plans prospectively complete or resolve data permissions.

### Replaying the saved review models

The original 13 candidate-provider source models contain scikit-learn 1.2.2
objects. The general project lock selects 1.7.2 and emits cross-version
deserialization warnings. A post-hoc check using those newer locked scientific
dependencies reproduced the selected annual and trend audits, but this does not
establish compatibility for every model, analysis or future version.

For historical review replay, a separate, narrower environment pins the
saved-model version and the dependencies used in local replay checks. On Linux
x86-64 with Python 3.11, it can be installed separately:

```sh
WRR_REVIEW_VENV="$HOME/.venvs/wrr-review"
python3.11 -m venv "$WRR_REVIEW_VENV"
"$WRR_REVIEW_VENV/bin/python" -m pip install -r requirements-wrr-review-replay.txt
"$WRR_REVIEW_VENV/bin/python" scripts/553_verify_review_package.py
"$WRR_REVIEW_VENV/bin/python" scripts/727_isolated_review_evidence_check.py
"$WRR_REVIEW_VENV/bin/python" scripts/728_isolated_groupmax_check.py
```

The environment must be outside the workspace: the isolated checks hide that
workspace from the child process. These commands default to
`dist/wrr_review_response_candidate.zip` within the
workspace; pass `--archive /path/to/candidate.zip` when it is stored elsewhere.
The last two commands require the explicit local evidence, saved model files and
processed inputs at the expected workspace paths; they are not in that ZIP.
They require Linux user, mount and network namespaces and use the installed TeX
and Graphviz tools where applicable. This environment is for the named replay
checks; it does not install or validate the full training workflow, authorize
access to restricted inputs or replace a permanent data and software deposit.
Only load joblib models from a trusted source.
