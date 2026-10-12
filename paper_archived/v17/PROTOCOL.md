# v17 experiment protocol

Frozen alongside `results/v17_fitness/step9_freeze/SUCCESS_CRITERION_v17.json`.

| Step | What it settles | Script | Artifact | Status |
|---|---|---|---|---|
| 1 | Population, complete-year truth, natural scale, stratified network split | `scripts/180_v17_panel.py` | `step1_panel/` | done — 146 networks, 457 stations, 5,114 station-years |
| 2–3 | Outage design and the case table | `scripts/181_v17_cases.py` | `step3_cases/` | done — 51,543 cases |
| 4 | Ceiling of each action space against the reserved panel's resolution | `scripts/182_v17_ceiling.py` | `step4_ceiling/` | done — adopt/reject and method selection fail the gate; retain/exclude passes |
| 5 | Mechanism (H1) and the two controlled donor experiments | `scripts/183_v17_mechanism.py` | `step5_mechanism/` | done |
| 6–7 | The certificate, its calibration, and the retention-error frontier | `scripts/184_v17_screen_frontier.py` | `step6_screen/`, `step7_frontier/` | done |
| 8 | Downstream consequence (H4) | `scripts/185_v17_downstream.py` | `step8_downstream/` | done — per-year gain confirmed, trend gain not |
| 9 | Freeze and pre-registration, with the precision calculation | `scripts/186_v17_freeze.py` | `step9_freeze/` | done |
| 10 | Reserved networks, scored once, plus leave-one-provider-out | `scripts/187_v17_confirm.py` | `step10_confirmation/` | done — primary and coverage claims pass |
| 11 | Figures | `scripts/188_v17_figures.py` | `figures/v17/` | done |
| 12 | Robustness of the headline result to the outage design | `scripts/189_v17_arm_robustness.py` | `step11_arm_robustness/` | done — relative reduction stable, absolute reduction is not |
| 13 | Adversarial ablations, simple-baseline screen, per-network coverage | `scripts/190_v17_ablations.py` | `step12_ablations/` | done — 60% of the benefit is available from three variables |
| 14 | Strictly-prior-years sensitivity | `scripts/191_v17_prior_years.py` | `step13_prior_years/` | done — contrast −6.23 → −5.79 points |
| 15 | Tables the manuscript promises (tolerance sweep, estimator choice, air coverage) | `scripts/192_v17_paper_tables.py` | `step14_paper_tables/` | done |
| 16 | Headline numbers extracted for the manuscript-consistency test | `scripts/193_v17_paper_numbers.py` | `paper_numbers.json` | done |
| 17 | Was the incumbent handicapped? | `scripts/194_v17_baseline_strength.py` | `step15_baseline_strength/` | done — no; it beats an oracle reconstruction |
| 18 | The deployable three-variable rule | `scripts/195_v17_simple_rule.py` | `step16_simple_rule/` | done — reserved −5.44 points on its own |
| 19 | Does the finding hold for other thermal metrics? | `scripts/196_v17_metric_generality.py` | `step17_metric_generality/` | done — **no**: timing wins for warm extremes, length for averages |
| 20 | Cluster-aware conformal calibration | `scripts/197_v17_cluster_conformal.py` | `step18_cluster_conformal/` | done — site-level validity for a 1.5x widening; frontier unchanged |
| 21 | Is the headline carried by the largest agencies? | `scripts/198_v17_weighting.py` | `step19_weighting/` | done — no; every weighting clears the declared effect |
| 22 | Audit every number in the manuscript against its artifact | `scripts/199_v17_audit_manuscript.py` | `manuscript_audit.json` | done — 126 checks, all passing |
| 23 | Four gaps a fourth reading finds: mechanism gradients, an amplitude screen, the near-threshold subset, screening versus abstention | `scripts/200_v17_round4_gaps.py` | `step20_round4/` | done |
| 24 | Catchment attribution: which rivers are hard, including the groundwater claim from the literature | `scripts/201_v17_hydrology.py` | `step21_hydrology/` | done — topography predicts difficulty; the groundwater prediction reverses and is decomposed |
| 25 | Endpoint, threshold and reference-noise robustness, with clustered intervals on the axis contrasts | `scripts/202_v17_robustness.py` | `step22_robustness/` | done — all five contrasts exclude zero; nothing moves under 0.15 °C of reference noise |
| 26 | Evidence ledger: claim to script, artifact and digest | `scripts/203_v17_evidence_ledger.py` | `evidence_ledger.csv` | done |
| 27 | Figures for the catchment and robustness results | `scripts/204_v17_figures_q1.py` | `figures/v17/fig5`, `fig6` | done |

## Standing rules

1. **Gate before rule.** No decision experiment is run until the oracle ceiling
   of its action space is measured and compared with the margin the
   confirmation panel can resolve. Three times the resolvable margin is the
   threshold.
2. **Anchor to the natural scale.** Every tolerance and every effect size is
   reported in degrees and in interannual standard deviations of the endpoint
   (1.06 °C here). Instrument precision is not used to set a decision margin.
3. **Stratify the reservation.** Reserved networks are drawn within
   provider × donor regime, so the confirmation population is exchangeable with
   development on the covariate the design conditions on.
4. **Cluster by network.** Every interval resamples whole networks. Reusing a
   station-year under several outage realizations does not create independent
   observations.
5. **Compete with practice.** The comparison set always contains the
   observed-days estimator and fixed-length screening, because those are the
   incumbents.
6. **Report the frontier.** A screening rule is judged on retention against
   error, never on a single scalar.
7. **Declare the weighting of designed populations.** Where the case set mixes
   a designed arm with an empirical one, the freeze must state how they are
   weighted in the primary test. Ours did not, and §3.4 of the manuscript
   records the consequence.
8. **Visible information only.** No feature may read a day the outage hides;
   enforced in `feature_frame` and tested in `tests/test_v17_fitness.py`.
9. **Disjoint networks.** Fitting, conformal calibration and test never share a
   network.
10. **Deterministic experimental units.** Outage realizations are seeded from a
    digest, never from `hash()`, which Python salts per process. A case table
    that cannot be regenerated makes every number downstream unverifiable, and
    a test pins this.
11. **Side outputs are named after their run.** A script that can write several
    outputs must not overwrite a shared summary file; the manuscript's numbers
    are extracted from the primary artifacts.
12. **Row order is part of reproducibility.** Workers return out of order; the
    case table is sorted on a declared key before it is written, and a test
    pins that. Comparing a sorted view of two runs is the check that cannot
    see this defect.
13. **A perfect score is a question, not a result.** A zero error rate is
    checked on the hard subset before it is reported; ours was mostly a
    statement about how few cases were close to the threshold.
14. **The action space is chosen per question, not once.** The same calibrated
    object supports screening and abstention, and which is better depends on
    whether the question is what enters an archive or what one judgement says.
15. **A claim is scoped to the endpoints it was tested on.** Before a general
    statement about records is made, it is checked on more than one derived
    metric.
16. **A mechanism is measured, not argued.** A mechanistic story that implies a
    directional prediction about how error scales is turned into a measurement
    before it is stated as an explanation.
17. **A directional prediction from the literature is tested as stated.** The
    groundwater claim was written down with its expected sign before the
    regression was run, and is reported as rejected.
18. **The prose is tested against the artifacts.** Headline numbers live in a
    machine-readable block in the manuscript and are compared with
    `paper_numbers.json` by the test suite, and every table cell plus the
    audited inline claims are re-derived from the artifacts by the audit
    script, which the test suite runs. Proofreading is not a control: three
    careful readings left four wrong numbers in the text.

## Reproduction

```
python3 scripts/180_v17_panel.py
python3 scripts/181_v17_cases.py --workers 96
python3 scripts/182_v17_ceiling.py
python3 scripts/183_v17_mechanism.py --workers 96
python3 scripts/184_v17_screen_frontier.py
python3 scripts/185_v17_downstream.py
python3 scripts/186_v17_freeze.py
python3 scripts/187_v17_confirm.py
python3 scripts/188_v17_figures.py
python3 scripts/189_v17_arm_robustness.py
python3 scripts/190_v17_ablations.py
python3 scripts/181_v17_cases.py --workers 96 --fit-protocol strictly_prior_years --out cases_prior_years.parquet
python3 scripts/191_v17_prior_years.py
python3 scripts/192_v17_paper_tables.py
python3 scripts/194_v17_baseline_strength.py
python3 scripts/195_v17_simple_rule.py
python3 scripts/196_v17_metric_generality.py
python3 scripts/197_v17_cluster_conformal.py
python3 scripts/198_v17_weighting.py
python3 scripts/193_v17_paper_numbers.py
python3 scripts/200_v17_round4_gaps.py
python3 scripts/201_v17_hydrology.py
python3 scripts/202_v17_robustness.py
python3 scripts/204_v17_figures_q1.py
python3 scripts/203_v17_evidence_ledger.py
python3 scripts/199_v17_audit_manuscript.py
python3 -m pytest tests/test_v17_fitness.py
```

Total wall time on 128 cores is about fifty minutes, and the case table is byte-reproducible.
