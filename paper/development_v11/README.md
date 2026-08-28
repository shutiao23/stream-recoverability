# v11 empirical-transfer manuscript and confirmation

This directory is the completed v11 development and new-confirmation route,
not a continuation of the failed v10 confirmation. It does not change files under
`paper/main_v9/`, `paper/case_study_v1/`, or `paper/submission/`.

The completed reviewer-response evidence selects this claim:

> Recovery errors measured with artificial gaps wholly inside fitting years
> predict later gap-recovery loss better than simple structural descriptors or
> analytic conditional covariance; operational calibration remains domain
> dependent.

The complete operator failed its incremental-R2 advancement criterion. Simple
Route A descriptors ranked the first-confirmation outcomes, but the newly
required empirical-transfer baseline was materially stronger and displaced
simple sufficiency as the positive claim.

## Files

- `manuscript.md`: complete evidence-aligned manuscript.
- `figure_plan.md`: generated main figures and supporting displays.
- `claim_matrix.md`: empirical-transfer claim-to-test-to-language map.
- `supporting_information.md`: protocol history, audit trail, exclusions, and
  secondary analyses kept out of the narrative flow.
- `pilot_results.md`: the final 55-network matched development result.
- `route_a_results.md`: the 55-network matched B+D+M+H development result and
  the resulting advancement decision.
- `../../docs/development_v11_execution.md`: execution and source-QC record.
- `../../results/development_v11/reviewer_completion/`: empirical-transfer,
  model-roster, conformal, domain-adaptation, and real placement-replay outputs.
- `../../configs/route_a_second_confirmation_protocol.yaml`: executable plan
  for a future independent confirmation; it is not a completed result.

## Evidence status at creation

The relevant v9 development screen scored 44 public networks. Network-level
Spearman correlation was 0.67 for the partial operator and 0.80 for donor
\(R^2\); the recorded slice-specific increment over donor \(R^2\) was
\(6.88\times10^{-5}\). Only 2 of 10 placement comparisons exceeded the former
15% target, and both operator and length-only triage released zero safe fills
at a 5% false-release setting. Twin E recovered rank (Spearman 0.936) but not
calibration (slope 0.760). The previous sealed run stopped after QC retained
32 of 40 networks, so it produced no H1--H3 result.

Those facts motivate v11; they are not evidence for the target claim.

## Current evidence

- Development: 55 networks, 217 stations, 1,260 station-gap units.
- Exact operator/recovery roster agreement: 217/217 stations.
- Route decision: operator rank increment +0.127; nested delta-R2 +0.017,
  therefore Route A.
- New confirmation panel: 45 QC-passed stream networks; 42 scored networks and
  1,440 station-gap units.
- Confirmation: Spearman 0.803, calibration slope 0.806, simultaneous network
  coverage 0.857, mean interval width 6.49 degrees C.
- Triage: 10% false release for the fixed simple threshold versus the 5% cap;
  H3 failed.
- Fitting-period empirical transfer: confirmation Spearman 0.934 and
  \(R^2=0.812\) on 780 supported 7/30/90/180-day units.
- Learned error model: adding analytic risk after empirical and simple inputs
  changed development LONO \(R^2\) from 0.701 to 0.704.
- Horizon-Mondrian intervals narrowed median width to 1.15 degrees C but
  covered every row in only 40.5% of confirmation networks.
- Exact 5% risk control certified no nonempty release through a requested 200
  labelled station-gap budget.
- Real-data placement replay now covers 14 open networks after replacing the
  stale inventory filter with the matched outcome roster.
- Second-confirmation recruitment reached 242 candidates and 60 strict-QC
  arrivals across US, Czech, and Norwegian domains. Scoring remains withheld
  only because the predeclared Canadian validated-source floor is empty.

## Reproduce

Run, in order: `make development-v11-inventory`, `make development-v11-score`,
`make development-v11`, `make development-v11-mixed`,
`make development-v11-confirm`, `make development-v11-stratify`,
`make development-v11-triage`, `make development-v11-plots`, and
`make development-v11-reviewer-completion`. Validate the completed extension
with `make validate-development-v11-reviewer-completion`. Outputs are
ordinary replaceable tables and figures under `results/development_v11/`.

`make development-v11-candidates` rebuilds the core candidate sources. Provider
acquisition scripts append their own ordinary source-QC rows. The exact scored
confirmation panel is retained in `route_a_confirmation/qualified_panel.csv`.
