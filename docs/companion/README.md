# Companion derived dataset and evidence dashboard (P2-03, minimal)

This directory is a **companion release**, not a manuscript artifact. It carries evidence identity: which claim each number belongs to, what the number's denominator is, which evidence class it has, and which file under `results/` it was read from. Nothing here is re-analysed; every value is read at build time from an existing result.

## Contents

- `companion_dataset.csv` — the tidy dataset (3045 rows; long format, one row per fact).
- `README.md` — this file.
- `../../dist/companion/index.html` — a single self-contained dashboard (data embedded, 101 labelled numbers); open it from disk, no server and no network.
- `../../dist/companion/dashboard_data.json` — the payload embedded in the dashboard, for reuse.
- `../../dist/companion/companion_dataset.csv` — byte copy of the tidy dataset.

`dist/` is gitignored output; `docs/companion/` is the released, tracked part.

## Rebuild (one command)

```bash
python3 scripts/264_wrr_companion_dataset.py
```

The command rewrites all five files above. It is read-only with respect to `results/`, `paper/`, `src/` and `metadata/`.

## Dataset schema

| column | meaning |
| --- | --- |
| `entity_type` | `network` \| `claim` \| `amendment` \| `provider` |
| `entity_id` | network id, claim id, amendment key, provider key, or a declared panel/protocol id (`panel`, `sealed_usgs_panel`, `multi_agency_panel`, `TRANSPORT`) |
| `field` | the fact name; array-valued facts carry a `[selector]` suffix |
| `value` | the fact, at full precision as read |
| `unit` | `percentage_points`, `percent`, `fraction`, `days`, `celsius`, `networks`, `stations`, `station_years`, `cases`, `count`, `bytes`, `text`, `bool` |
| `denominator` | required for every numeric row: what the number is out of |
| `evidence_class` | one of the six classes below |
| `artifact_path` | the file the value was read from (every row's path was opened by the build) |
| `notes` | unit conversions, discrepancy flags, cross-references |

## Evidence-class vocabulary

- **`sample_fact`** — Measured, descriptive property of the study sample, the real archive or a verified interface. No model contrast.
- **`retrospective_holdout`** — Model/rule contrast scored on a retrospective evaluation panel (v17 reserved network holdout or the frozen development case set). Not an independent unseen confirmation.
- **`sealed_confirmation`** — Score from a panel sealed before scoring (P0-07 USGS confirmation and its disclosed post-seal diagnostics).
- **`exploratory_post_open`** — Design, endpoint, level or window chosen after a panel was opened, or flagged exploratory by the claim registry. Must not be quoted as a result.
- **`proxy`** — Quantities about a proxy, or proxy expectations transported to cases whose truth is unobserved by construction.
- **`withdrawn`** — Superseded, unusable or explicitly withdrawn numbers. Must not be quoted as results.

### Assignment rule

The class of a claim is derived from its registry `evidence_type` through this map (declared in `scripts/264_wrr_companion_dataset.py`; the build fails if the registry ever contains an unmapped evidence type):

| registry `evidence_type` | evidence class |
| --- | --- |
| `deployment_description` | `sample_fact` |
| `deployment_interface_verified` | `sample_fact` |
| `endpoint_mismatch` | `withdrawn` |
| `exploratory_level_selected_on_opened` | `exploratory_post_open` |
| `exploratory_overclaim` | `exploratory_post_open` |
| `exploratory_post_open` | `exploratory_post_open` |
| `exploratory_with_implementation_bug` | `exploratory_post_open` |
| `exploratory_with_inference_flaws` | `exploratory_post_open` |
| `exploratory_with_method_switch` | `exploratory_post_open` |
| `incomplete_measurement_provenance` | `sample_fact` |
| `mislabelled_baseline` | `retrospective_holdout` |
| `overstated_reproducibility` | `withdrawn` |
| `proxy_not_truth` | `proxy` |
| `retrospective_network_holdout` | `retrospective_holdout` |
| `sample_fact` | `sample_fact` |
| `sealed_confirmation_single_provider_usgs` | `sealed_confirmation` |
| `sealed_multi_agency_transport_single_score` | `sealed_confirmation` |
| `supplementary_multi_agency_probe_below_floor` | `exploratory_post_open` |

One override exists, because the registry status and the closure audit withdraw a headline that the evidence type alone would not flag:

| claim | class | reason |
| --- | --- | --- |
| `L1` | `withdrawn` | F04 closure_mode=withdraw_proportion_law_from_headlines (results/wrr_submission_ready/F_FINDINGS_CLOSURE_AUDIT.csv); registry notes: 'Withdraw unconditional proportion headline.' |

## Claims that must not be quoted as results

Withdrawn, proxy-based or exploratory claims, plus claims the registry bars from the abstract and conclusions. These are exactly the entries in the dashboard's "what is not established" panel.

| entity | class | status | why not quotable | artifact |
| --- | --- | --- | --- | --- |
| `L1` | `withdrawn` | pending_new_confirmation | status=pending_new_confirmation; evidence_class=withdrawn; findings=F04; registry: may_enter_abstract_or_conclusions=False; AUC ordering ≠ proportionality. Withdraw unconditional proportion headline. | `results/v18_closure/e6_support_width/` |
| `L3` | `exploratory_post_open` | exploratory_interval_reported | status=exploratory_interval_reported; evidence_class=exploratory_post_open; findings=F05; registry: may_enter_abstract_or_conclusions=False; F05 amendment: 1000-draw network-clustered bootstrap of the whole curve; 90-day grid point +0.002 [-0.019,+0.027], first negative grid point 182 days; P(no crossover in swept range)=0.000; the 91.05-day point value is su | `results/wrr_submission_ready/amendments/e6_support_width_uncertainty/crossover.json` |
| `L7` | `exploratory_post_open` | exploratory_range_only | status=exploratory_range_only; evidence_class=exploratory_post_open; findings=F05; registry: may_enter_abstract_or_conclusions=False; F05 amendment: report a range (roughly one to three months) and per-width paired intervals; no single universal window; advantage is a hump peaking near 60 days, not monotone. | `results/wrr_submission_ready/amendments/e6_support_width_uncertainty/curve_with_ci.csv` |
| `D2` | `proxy` | proxy_quantified_labelled | status=proxy_quantified_labelled; evidence_class=proxy; findings=F07; F07 bridge: on sealed never-used designed cases (n=8973) the proxy has PPV 0.737 (cluster CI [0.709,0.761]) for a wholly hidden realised peak, sensitivity 0.866, and 3.1% of proxy-clear cases hide the realised peak. Tran | `results/wrr_submission_ready/amendments/peak_proxy_bridge/summary.json` |
| `A4` | `exploratory_post_open` | recomputed_exploratory_not_for_headline | status=recomputed_exploratory_not_for_headline; evidence_class=exploratory_post_open; findings=F02; registry: may_enter_abstract_or_conclusions=False; F02 fix: gaps are placed on a multi-year day axis and each affected calendar year contributes its own hidden length; the earlier truncation at day 366 is repaired. Values remain post-open exploratory and are barred from  | `results/wrr_submission_ready/e1_maintenance_recompute/maintenance_counterfactual.json` |
| `R1` | `exploratory_post_open` | pending_new_confirmation | status=pending_new_confirmation; evidence_class=exploratory_post_open; registry: may_enter_abstract_or_conclusions=False; Report as association on opened panel. | `results/v18_closure/e4_representativeness/` |
| `M1` | `exploratory_post_open` | exploratory_with_bias_sensitivity | status=exploratory_with_bias_sensitivity; evidence_class=exploratory_post_open; findings=F10; registry: may_enter_abstract_or_conclusions=False; P1-01 pattern-mixture: adding delta C to every filled day moves the hottest-30 mean by delta x hidden share of the realised peak window. Contrast (certificate minus length, same reconstruction) stays negative with cluste | `results/wrr_submission_ready/amendments/mnar_pattern_mixture/bias_curve.csv` |
| `HY` | `exploratory_post_open` | closed_by_rewrite | status=closed_by_rewrite; evidence_class=exploratory_post_open; findings=F13; registry: may_enter_abstract_or_conclusions=False; F13: rewritten as attribute associations on the US subset (140 of 204 stations); no geology law, expected signs undeclared, BFI split reported as median not tertile. | `results/v17_fitness/step21_hydrology/` |
| `N1` | `exploratory_post_open` | recomputed_exploratory_locked_method | status=recomputed_exploratory_locked_method; evidence_class=exploratory_post_open; findings=F11; registry: may_enter_abstract_or_conclusions=False; F11 amendment: same reconstruction choice on both arms. Dev 5.98->6.03, reserved 6.21->6.22; paired change +0.049 [-0.036,+0.150] and +0.013 [-0.175,+0.185]. AR(1) rho=0.7 and a mid-year 0.3 C step displace the endpoint  | `results/wrr_submission_ready/amendments/step22_noise_post_fix/summary.json` |
| `C14` | `exploratory_post_open` | pending_new_confirmation | status=pending_new_confirmation; evidence_class=exploratory_post_open; findings=F14; registry: may_enter_abstract_or_conclusions=False; Do not claim per-new-station guarantee from pooled coverage. | `results/v17_fitness/step18_cluster_conformal/` |
| `REG` | `withdrawn` | rewrite_required | status=rewrite_required; evidence_class=withdrawn; findings=F17; registry: may_enter_abstract_or_conclusions=False; Input is daily mean, not daily maximum; not a compliance validation. | `paper/wrr + SI fig S4` |
| `BASE` | `retrospective_holdout` | closed_by_faithful_baseline | status=closed_by_faithful_baseline; evidence_class=retrospective_holdout; findings=F15; registry: may_enter_abstract_or_conclusions=False; F15 amendment: the alpha=1.0 library ridge is relabelled as an in-library sensitivity; the cited method was reimplemented (per-station OLS on 2-10 day right-aligned air-temperature moving averages, July-August) and is be | `results/wrr_submission_ready/amendments/faithful_baseline/comparison.csv` |
| `MEAS` | `sample_fact` | closed_with_strata_and_sensitivity | status=closed_with_strata_and_sensitivity; evidence_class=sample_fact; findings=F09; registry: may_enter_abstract_or_conclusions=False; F09 amendment: usgs/foen/gkd_bayern/nve_hydapi/uk_ea documented daily means; chmi and rws are project-derived means of provider sub-daily values (provider daily products TD and GEM24H exist and are unused); syke is an 08 | `results/wrr_submission_ready/measurement_provenance_dictionary.csv` |
| `FAIR` | `withdrawn` | narrow_statement | status=narrow_statement; evidence_class=withdrawn; findings=F19; registry: may_enter_abstract_or_conclusions=False; Audit covers archived markdown expectations more than live TeX semantics. | `scripts/221_v18_audit_manuscript.py` |
| `NVE-PROBE` | `exploratory_post_open` | failed_transfer_or_underpowered | status=failed_transfer_or_underpowered; evidence_class=exploratory_post_open; findings=F01; registry: may_enter_abstract_or_conclusions=False; n_networks=2 <<30; contrast +2.3 pp; do not headline; multi-agency confirmation remains open by failure收口 | `results/wrr_submission_ready/p0_07_nve_probe/verdict.json` |
| `TRANSPORT` | `not scored` | panel under recruitment | no scored transport verdict exists; recruitment counts are reported as providers, not as a transport result | `results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md` |

Additionally, `N1` and the `step22_noise_pre_fix` amendment preserve the **superseded pre-fix noise numbers** under `evidence_class=withdrawn`; they are in the dataset so the withdrawal is auditable, not so they can be cited.

Claims whose own entity rows carry no number (their evidence is recorded under provider/network entities instead — for example `S3`, whose provider roles are rows of `provider_roles_from_split.csv` under `entity_type=provider`): `S3`.

## Known discrepancy flags carried by the dataset

| entity | field | value | note |
| --- | --- | --- | --- |
| `V17-H2` | `pooled_contrast_ci_low_arm_contrasts` | -8.980095089969291 | DISCREPANCY FLAG: step11 arm_contrasts.csv interval differs slightly from the step10 verdict interval stored on this claim |
| `V17-H2` | `pooled_contrast_ci_high_arm_contrasts` | -5.407305174918186 | DISCREPANCY FLAG: see pooled_contrast_ci_low_arm_contrasts |
| `L3` | `registry_prose_vs_artifact_crossover_interval` | registry states 76-107 days; artifact CI95 is [77.1125,107.0232] | DISCREPANCY FLAG: the dataset carries the artifact values; the registry prose rounds the lower bound down |
| `L3` | `registry_prose_vs_artifact_90d_interval` | registry states +0.002 [-0.019,+0.027]; artifact is +0.0016 [-0.0180,+0.0255] | DISCREPANCY FLAG: the dataset carries the artifact values |

These are places where the registry prose and the artifact disagree in rounding or in the stored interval. The dataset always carries the artifact value.

## What the build refuses to do

- It refuses to run if any referenced artifact is missing.
- It refuses to write a numeric row whose required field is empty, null or NaN.
- It refuses to cite an artifact it did not open in the same run.
- It refuses to assign an evidence class it has no mapping for.
- It refuses to drop a registry claim silently: every claim appears, and claims with no extractable headline are listed as text-only.
- It fails on cross-checks between artifacts (manifest vs. case-table summary, prior-access CSV vs. summary, provider roles vs. manifest, the two copies of the reserved pooled contrast, the proxy PPV reused in transport).

## Provenance of every row: artifacts read by the last build

| artifact | kind | rows read | bytes | dataset rows citing it |
| --- | --- | --- | --- | --- |
| `results/v17_fitness/step10_confirmation/verdict.json` | json | — | 1382 | 27 |
| `results/v17_fitness/step11_arm_robustness/arm_contrasts.csv` | csv | 6 | 2237 | 16 |
| `results/v17_fitness/step11_arm_robustness/verdict.json` | json | — | 978 | 4 |
| `results/v17_fitness/step18_cluster_conformal/summary.json` | json | — | 5337 | 9 |
| `results/v17_fitness/step1_panel/network_split.csv` | csv | 146 | 9904 | 3 |
| `results/v17_fitness/step21_hydrology/verdict.json` | json | — | 1189 | 8 |
| `results/v17_fitness/step3_cases/summary.json` | json | — | 400 | 13 |
| `results/v18_closure/e2_archive_deployment/archive_consequence.csv` | csv | 5 | 1019 | 30 |
| `results/v18_closure/e2_archive_deployment/disagreement_by_provider.csv` | csv | 7 | 356 | 28 |
| `results/v18_closure/e2_archive_deployment/matched_retention_disagreement.csv` | csv | 6 | 544 | 24 |
| `results/v18_closure/e2_archive_deployment/summary.json` | json | — | 1014 | 15 |
| `results/v18_closure/e2_archive_deployment/threshold_disagreement.csv` | csv | 2 | 421 | 12 |
| `results/v18_closure/e4_representativeness/elevation_retention.csv` | csv | 6 | 952 | 6 |
| `results/v18_closure/e4_representativeness/summary.json` | json | — | 716 | 8 |
| `results/wrr_submission_ready/F_FINDINGS_CLOSURE_AUDIT.csv` | csv | 22 | 8728 | 78 |
| `results/wrr_submission_ready/MULTI_AGENCY_TRANSPORT_PROTOCOL.md` | text | — | 9924 | 0 (read for a cross-check or a finding id) |
| `results/wrr_submission_ready/amendments/e6_support_width_uncertainty/REPORT.md` | text | — | 43645 | 0 (read for a cross-check or a finding id) |
| `results/wrr_submission_ready/amendments/e6_support_width_uncertainty/crossover.json` | json | — | 160880 | 22 |
| `results/wrr_submission_ready/amendments/e6_support_width_uncertainty/curve_with_ci.csv` | csv | 684 | 176668 | 21 |
| `results/wrr_submission_ready/amendments/faithful_baseline/contrasts.csv` | csv | 48 | 9332 | 8 |
| `results/wrr_submission_ready/amendments/faithful_baseline/summary.json` | json | — | 12808 | 12 |
| `results/wrr_submission_ready/amendments/mnar_pattern_mixture/summary.json` | json | — | 7535 | 42 |
| `results/wrr_submission_ready/amendments/outage_causes/cause_mix.csv` | csv | 36 | 2558 | 3 |
| `results/wrr_submission_ready/amendments/outage_causes/summary.json` | json | — | 11307 | 12 |
| `results/wrr_submission_ready/amendments/peak_proxy_bridge/summary.json` | json | — | 2781 | 24 |
| `results/wrr_submission_ready/amendments/provider_contract_sensitivity/provider_contract_contrasts.csv` | csv | 9 | 1320 | 44 |
| `results/wrr_submission_ready/amendments/provider_contract_sensitivity/summary.json` | json | — | 3381 | 14 |
| `results/wrr_submission_ready/amendments/regulatory_daily_max/daily_max_availability_summary.json` | json | — | 672 | 8 |
| `results/wrr_submission_ready/amendments/sealed_usgs_prior_access_diagnostic/summary.json` | json | — | 2454 | 49 |
| `results/wrr_submission_ready/amendments/step22_noise_post_fix/scenario_contrasts.csv` | csv | 22 | 7066 | 18 |
| `results/wrr_submission_ready/amendments/step22_noise_post_fix/summary.json` | json | — | 51135 | 19 |
| `results/wrr_submission_ready/amendments/step22_noise_pre_fix/noise_sensitivity.json` | json | — | 914 | 21 |
| `results/wrr_submission_ready/amendments/step5_mechanism_equal_k/contrast_by_k.csv` | csv | 7 | 1410 | 29 |
| `results/wrr_submission_ready/amendments/step5_mechanism_equal_k/summary.json` | json | — | 23063 | 10 |
| `results/wrr_submission_ready/amendments/step5_mechanism_pre_fix/donor_control_contrasts.csv` | csv | 2 | 306 | 9 |
| `results/wrr_submission_ready/amendments/winter_regulatory/REPORT.md` | text | — | 18586 | 0 (read for a cross-check or a finding id) |
| `results/wrr_submission_ready/amendments/winter_regulatory/cold_support_contrast.csv` | csv | 4 | 2620 | 2 |
| `results/wrr_submission_ready/amendments/winter_regulatory/summary.json` | json | — | 61427 | 10 |
| `results/wrr_submission_ready/claim_binding_check.json` | json | — | 3522 | 0 (read for a cross-check or a finding id) |
| `results/wrr_submission_ready/claim_registry.csv` | csv | 25 | 13715 | 301 |
| `results/wrr_submission_ready/current_data_manifest.csv` | csv | 146 | 33072 | 1216 |
| `results/wrr_submission_ready/e1_maintenance_recompute/maintenance_counterfactual.json` | json | — | 1393 | 14 |
| `results/wrr_submission_ready/e2_certificate_predict/summary.json` | json | — | 447 | 6 |
| `results/wrr_submission_ready/measurement_provenance_dictionary.csv` | csv | 12 | 26044 | 181 |
| `results/wrr_submission_ready/multi_agency_ingest/ehyd/ingest.json` | json | — | 18656 | 1 |
| `results/wrr_submission_ready/multi_agency_ingest/nve/ingest.json` | json | — | 450579 | 2 |
| `results/wrr_submission_ready/multi_agency_ingest/smhi/INGEST_STATUS.json` | json | — | 3008 | 7 |
| `results/wrr_submission_ready/multi_agency_ingest/uk_ea/complete_station_years.csv` | csv | 42 | 1780 | 1 |
| `results/wrr_submission_ready/multi_agency_ingest/uk_ea/networks_manifest.csv` | csv | 2 | 1221 | 1 |
| `results/wrr_submission_ready/p0_07_nve_probe/verdict.json` | json | — | 466 | 8 |
| `results/wrr_submission_ready/p0_07_sealed_confirmation/verdict.json` | json | — | 1003 | 28 |
| `results/wrr_submission_ready/p0_07b_multi_agency_transport/verdict.json` | json | — | 5141 | 39 |
| `results/wrr_submission_ready/prior_access_audit_multi_agency.csv` | csv | 291 | 17766 | 400 |
| `results/wrr_submission_ready/prior_access_audit_sealed_usgs.csv` | csv | 91 | 24100 | 283 |
| `results/wrr_submission_ready/prior_access_audit_summary.json` | json | — | 5172 | 0 (read for a cross-check or a finding id) |
| `results/wrr_submission_ready/provider_roles_from_split.csv` | csv | 9 | 526 | 45 |

### Amendment directories deliberately not covered

| directory | reason |
| --- | --- |
| `results/wrr_submission_ready/amendments/manuscript_audit` | no summary.json: this directory holds a per-manuscript-node claim-binding table (paper/wrr/wrr_manuscript.tex nodes), which is manuscript auditing rather than an amendment headline; it is out of scope for the companion dataset and is listed here so it is not silently dropped |

A directory that publishes `summary.json` and has no spec fails the build, so this list can only contain directories without a headline summary file.

## Scope limits

- Single-provider sealed confirmation (USGS only); multi-agency transport is not scored, so it is reported as a status, never as a number.
- The dataset inherits every limitation recorded in `claim_registry.csv`; the `status`, `population` and `registry_notes` rows carry them verbatim.
- Displayed dashboard numbers are rounded; the CSV holds full precision.

