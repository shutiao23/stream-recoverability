# v17 — fitness-for-use certification of gap-affected stream-temperature years

Run 2026-09-23. Paper `paper/v17/`, review and plan
`docs/reviews/wrr_2026_09_23/`, code
`src/stream_recoverability/experiments/v17_fitness/`.

| directory | what it holds |
|---|---|
| `step1_panel/` | population, complete-year truth, natural scale, the stratified network split |
| `step3_cases/` | the case table: 51,543 outage realizations on 5,114 station-years |
| `step4_ceiling/` | oracle ceilings per action space and the go/no-go gate |
| `step5_mechanism/` | H1 — timing versus length, and the two controlled donor experiments |
| `step6_screen/` | the certificate, out-of-fold, and its conformal coverage |
| `step7_frontier/` | the retention-error frontier against the incumbent rules |
| `step8_downstream/` | trends, exceedance counts, hottest-year identification, per-year judgements |
| `step9_freeze/` | the frozen model and the pre-registered success criterion with its precision calculation |
| `step10_confirmation/` | the reserved panel, opened once, plus leave-one-provider-out |
| `step11_arm_robustness/` | the headline result decomposed by outage design arm |
| `step12_ablations/` | adversarial ablations, the simple-baseline screen, per-network coverage |
| `step13_prior_years/` | the same study with estimators fit on strictly prior years |
| `step14_paper_tables/` | tolerance sweep, estimator choice, air-forcing coverage |
| `step15_baseline_strength/` | the incumbent paired with every reconstruction, including a non-deployable oracle |
| `step16_simple_rule/` | the deployable three-variable rule and its coefficients |
| `step17_metric_generality/` | which screening axis governs which thermal metric |
| `step18_cluster_conformal/` | cluster-aware calibration, and what site-level validity costs |
| `step19_weighting/` | the contrast under case-, network-, station- and provider-equal weighting |
| `step20_round4/` | mechanism gradients, an amplitude screen, the near-threshold subset, screening versus abstention |
| `step21_hydrology/` | catchment attribution: which rivers are hard, and the groundwater claim from the literature |
| `step22_robustness/` | clustered intervals on the axis contrasts, reference-noise perturbation, ecological-threshold sweep |
| `paper_numbers.json` | headline numbers, checked against the manuscript by the test suite |
| `manuscript_audit.json` | every table cell and audited inline claim, re-derived from the artifacts |
| `evidence_ledger.csv` | each claim mapped to its script, artifact, digest and manuscript section |

The reserved networks were opened once, on 2026-09-23, with the Step-9 model
applied without retuning. No station-year is used in both roles.

Outage realizations are seeded from a deterministic digest and the table is
written in a declared row order, so it is reproducible byte for byte. Earlier
versions seeded from Python's salted `hash()` and concatenated worker results
in completion order; neither was reproducible, and every number they produced
has been discarded rather than reported.
