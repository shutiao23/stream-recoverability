# Major revision, round 1 — what the new evidence changed

Date: 2026-10-15.  Base commit: `8eade30bbf`.  This note is the index to the
evidence produced in this round and the claims it changes.  Nothing here retunes
the wave-2 seal or re-uses it as a new confirmation.

## Deliverables

| item | script | artifact |
|---|---|---|
| P0-01 final method and claim set | `scripts/310_wrr_p0_01_final_method_plan.py` | `p0_01_final_method/{final_analysis_plan.yaml,final_claims.csv,SUMMARY.md}` |
| P0-02 honest risk-cap thresholds | `scripts/311_wrr_p0_02_frozen_risk_thresholds.py` | `p0_02_frozen_risk_thresholds/` (version note first in SUMMARY) |
| P0-03 final rule on the real calendar | `scripts/312_wrr_p0_03_final_method_replay.py` | `p0_03_final_method_replay/` |
| P0-04 environmental closed loop | `scripts/313_wrr_p0_04_env_closed_loop.py` | `p0_04_env_closed_loop/` |
| P0-05 power and independence | `scripts/314_wrr_p0_05_power_and_independence.py` | `p0_05_power_independence/` |
| P0-06 coverage, measurement contract, recompute | `scripts/315_wrr_p0_06_coverage_and_recompute.py` | `p0_06_coverage_recompute/` |
| P1 repeated learning curves | `scripts/316_wrr_p1_learning_curve_repeats.py` | `p1_learning_curve_repeats/` |
| P1 mechanism boundary | `scripts/317_wrr_p1_mechanism_boundary.py` | `p1_mechanism_boundary/` |
| P1 transfer and measurement | `scripts/318_wrr_p1_transfer_measurement.py` | `p1_transfer_measurement/` |
| Figure 1 (decision) | `scripts/319_wrr_figure1_decision.py` | `figures/wrr/f1_decision.pdf` |

## Claims changed

**Withdrawn**
- *Hidden support share is the governing, necessary mechanism.* Step 2: adding it
  to a same-capacity learner moves the error rate by +0.05 pp ([-0.17,+0.23]).
- *Position dominates length.* Step 3 and the mechanism-boundary crossed design:
  at a fully hidden window, lengthening the gap still raises the error
  (donor +0.15 C, air +0.35 C, linear interpolation +1.12 C).
- *A 5 % risk cap is operationally controlled by the published frontier.*
  P0-02: the published operating point was chosen on evaluation labels; the
  label-chosen frontier is optimistic by 1.5-3.2 pp for the certificate and
  fitted scores and 6.1 pp for the length rule.
- *Calibration adds screening value.* P0-02: the calibrated and uncalibrated
  certificate bounds admit an identical case set on the external panel; the
  calibration's role is the absolute-scale rule, not ranking.
- *The support features are sample-efficient.* P1 learning curves: support with
  10 networks is indistinguishable from generic with 25 and worse than generic
  with 50 or more (equivalent to about 18 of 110 networks).
- *The final rule had been tested on real outages.* P0-03 now runs it.

**Strengthened**
- At an honest 5 % false-admit cap, the fitted risk score keeps 27.1 pp
  ([23.9,30.3]) and the calibrated certificate 27.9 pp more of the external
  candidate pool than the gap-length rule (48.9 %).
- The final rule decides 95.9 % of replay candidates under all-donor failure
  against 79.9 % for the peak-window rule, with a usable-record share 16.0 pp
  higher ([7.9,23.8]) and no error penalty against the length rule.
- Every measurement-contract stratum and every warm-year stratum keeps the sign;
  the operational (past-to-future) design leaves the 70 %-retention conclusion
  unchanged (-0.07 pp, [-0.33,+0.24]).

**Newly bounded**
- The environmental closed loop decomposes exactly into prediction error
  (<= 0.46 pp here) and selection shift (<= 1.74 pp); abstention wins under one
  criterion only, which the earlier draft had not tested.
- The design behaves like 14.1 (development) and 11.0 (external) independent
  networks; 20 networks give 53 % power for a 2 pp effect, and the clustered
  interval over-rejects at that size (empirical alpha 0.18 at zero effect).
- The phase identifiability floor computed from the design matrix is 3.6x the
  uniform-sampling figure once residual autocorrelation enters, so the previous
  fixed A/sigma >= 4.5 rule was too permissive under the unrepaired protocol.

**Open**
- No panel unused anywhere in the project remains for a pristine confirmation of
  the converged method; the wave-2 seal belongs to the frozen certificate screen.
- The 47 ARSO stations still have an undocumented daily statistic (8.3 % of
  development cases) and the three SYKE stations are a morning reference reading.

## Manuscript changes in this round

- New Figure 1 (decision) replaces the design schematic, which moves to the SI.
- New results: honest risk cap; final rule on the real calendar; the hot-year
  decomposition; the learning-curve repeats; the operational transfer and
  measurement strata; the mechanism boundary including the air reconstructor and
  the design-based phase floor.
- Headings, abstract, key points and conclusions rebound to the converged claim;
  the dominance wording is gone from the title, the headings, the figure caption
  and the SI title.
- Desk checks pass (abstract 249 words, key points <= 140 characters); the
  build still reports NOT submission-ready only because the author block is a
  placeholder.
