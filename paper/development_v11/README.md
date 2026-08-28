# v11 empirical-transfer manuscript and confirmation

This directory is the completed v11 development and new-confirmation route,
not a continuation of the failed v10 confirmation. It does not change files under
`paper/main_v9/`, `paper/case_study_v1/`, or `paper/submission/`.

The completed reviewer-response evidence selects this claim:

> Recovery errors measured with artificial gaps wholly inside fitting years
> improve network-level ranking at directly supported horizons, while
> network-mean fallback, operational calibration, and decision control remain
> important boundaries.

The complete operator failed its preregistered incremental-R2 criterion. Simple
descriptors ranked the first-panel outcomes, but the newly
required empirical-transfer baseline was materially stronger and displaced
simple sufficiency as the positive claim.

## Files

- `manuscript.md`: complete evidence-aligned manuscript.
- `figure_plan.md`: generated main figures and supporting displays.
- `claim_matrix.md`: empirical-transfer claim-to-test-to-language map.
- `supporting_information.md`: protocol history, deviations, exclusions, and
  secondary analyses kept out of the narrative flow.
- `pilot_results.md`: the final 55-network matched development result.
- `route_a_results.md`: the 55-network matched B+D+M+H development result and
  the resulting model-selection decision.
- `../../docs/development_v11_execution.md`: execution and source-QC record.
- `../../results/development_v11/reviewer_completion/`: empirical-transfer,
  model-roster, conformal, domain-adaptation, and real placement-replay outputs.
- `../../configs/route_a_second_confirmation_protocol.yaml` and
  `../../configs/route_a_second_confirmation_amendment_v2.yaml`: original plan
  and internally hash-bound eligibility amendment.
- `../../results/development_v11/second_confirmation/scoring/summary.json`:
  completed 57-network second-confirmation metrics and failed decision
  endpoints.

## Prior evidence

The relevant v9 development screen scored 44 public networks. Network-level
Spearman correlation was 0.67 for the partial operator and 0.80 for donor
\(R^2\); the recorded slice-specific increment over donor \(R^2\) was
\(6.88\times10^{-5}\). Only 2 of 10 placement comparisons exceeded the former
15% target, and both operator and length-only triage released zero safe fills
at a 5% false-release setting. Twin E recovered rank (Spearman 0.936) but not
calibration (slope 0.760). A previous preregistered run stopped after QC retained
32 of 40 networks, so it produced no H1--H3 result.

Those facts motivate v11; they are not evidence for the target claim.

## Current evidence

- Development: 55 networks, 217 stations, 1,260 station-gap units.
- Exact operator/recovery roster agreement: 217/217 stations.
- Model selection: operator rank increment +0.127; nested delta-R2 +0.017,
  therefore the simple-descriptor model was retained.
- New confirmation panel: 45 QC-passed stream networks; 42 scored networks and
  1,440 station-gap units.
- Confirmation: Spearman 0.803, calibration slope 0.806, simultaneous network
  coverage 0.857, mean interval width 6.49 degrees C.
- Triage: 10% false release for the fixed simple threshold versus the 5% cap;
  H3 failed.
- Fitting-period empirical transfer: network-level Spearman 0.922, pooled
  Spearman 0.934, and \(R^2=0.812\) on 780 directly supported
  7/30/90/180-day units.
- Complete-panel empirical transfer: 780 within-horizon predictions plus 660
  network-mean fallbacks and no missing values; network-level Spearman 0.767,
  pooled Spearman 0.633, and \(R^2=0.145\).
- Learned error model: adding analytic risk after empirical and simple inputs
  changed development LONO \(R^2\) from 0.701 to 0.704.
- Bounded recurrent sensitivity: empirical-transfer versus local GRU-style
  BRITS loss has station-gap Spearman 0.384 on 75 units and network Spearman
  0.600 on six networks; this is exploratory, not an LSTM/full-roster result.
- Development process proxy: XGBoost versus air-temperature--flow ridge loss
  has station-gap Spearman 0.373 and network Spearman 0.343 on 50 networks;
  this is not published air2stream and lacks confirmation inputs.
- Horizon-Mondrian intervals narrowed median width to 1.15 degrees C but
  covered every row in only 40.5% of confirmation networks.
- Exact 5% risk control certified no nonempty release through a requested 200
  labelled station-gap budget.
- Real-data placement replay now covers 14 development networks after replacing the
  stale inventory filter with the matched outcome roster.
- Second-confirmation recruitment reached 242 candidates and 60 networks
  meeting prespecified quality criteria across US, Czech, and Norwegian
  domains. A dated amendment replaces the unavailable validated Canadian
  stratum and was internally frozen and hash-bound before recovery scoring.
  It has no separate public pre-outcome commit.
- Second confirmation scored 57 networks after three outcome-independent
  attritions. At directly supported horizons (874 units), empirical transfer
  reached station-gap Spearman 0.945, network Spearman 0.805, and slope 0.938.
  Across all 1,446 units, 572 network-mean fallbacks reduced these to 0.740,
  0.715, and 0.950; simple-model network Spearman was 0.614.
- Second-confirmation empirical intervals covered every network but had median
  width 8.40 times median loss. Exact 5% triage certified and released zero
  units for both predictors, so the decision endpoint failed.
- Second-panel placement had 13 complete networks and zero attrition. Minimax
  regret was 0.241 °C versus 0.256 °C for random placement, but no prespecified
  utility margin licenses a confirmatory benefit or station removal.

## Reproduce

Run, in order: `make development-v11-inventory`, `make development-v11-score`,
`make development-v11`, `make development-v11-mixed`,
`make development-v11-confirm`, `make development-v11-stratify`,
`make development-v11-triage`, `make development-v11-plots`, and
`make development-v11-reviewer-completion`. Validate the completed extension
with `make validate-development-v11-reviewer-completion`. Outputs are
ordinary replaceable tables and figures under `results/development_v11/`.

The second outcome panel is rebuilt with `make second-confirmation-readiness`
and `make second-confirmation-score`; the latter rechecks the hash-bound roster
before scoring.

`make development-v11-candidates` rebuilds the core candidate sources. Provider
acquisition scripts append their own ordinary source-QC rows. The exact scored
confirmation panel is retained in `route_a_confirmation/qualified_panel.csv`.
