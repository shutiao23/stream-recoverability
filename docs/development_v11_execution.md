# v11 execution: open development to new confirmation

**Purpose:** turn the v9 diagnosis into a testable v11 study without reusing the
failed confirmation as evidence.

**Target route:** Route B if the complete operator demonstrates material
increment on open networks; Route A otherwise.

## 1. Starting facts

- The previous operator screen scored 44 open networks and did not beat donor
  \(R^2\): Spearman 0.67 versus 0.80.
- The recorded W8 increment after donor \(R^2\) was
  \(6.88\times10^{-5}\).
- Meteorology and hydraulics were not connected to the corpus-wide operator.
- Twin E ranked well but was miscalibrated (slope 0.760).
- Earlier decision results were weak: 2/10 placement wins at the former gate
  and zero safe fills at 5% false release.
- The former confirmation stopped after QC retained 32/40 networks. H1--H3
  were not scored.

The first five points are development diagnoses. The last point is an
incomplete experiment, not a negative confirmation.

## 2. Workstream A — assemble one open development corpus

1. Reclassify all previously exposed development and validation roles as open
   v11 development candidates. The failure-closure inventory contains 74
   development and 29 validation roles, of which 95 are nonempty, 68 retain at
   least three stations, and 67 pass full open-role qualification (47
   development and 20 validation). Report the final eligible count after the
   B/D/M/H and scored-outcome requirements.
2. Keep every previously touched network out of the new confirmation.
3. For every station, acquire aligned daily meteorology and available daily
   discharge/gage height over fitting and evaluation years.
4. Produce one station-day table with temperature, B/D membership, M/H
   variables, provider quality fields, and availability flags.
5. Require a common analysis window adequate for fitting plus held-out gaps;
   report each exclusion instead of substituting catalog date overlap for daily
   concurrency.
6. Bind the 1,470 known natural outage segments as an empirical geometry
   source where their networks remain eligible, and add a common artificial
   grid with observed truth.

**Completion artifact:** a table of eligible networks, stations, common years,
M/H coverage, and exclusion reasons. This is an inventory, not a performance
result.

## 3. Workstream B — complete and calibrate the operator

1. Evaluate the same station-gap outcomes under B, D, B+D, B+D+M, and
   B+D+M+H.
2. Retain station × gap as the response resolution and network as the grouping
   and resampling unit.
3. Evaluate linear and isotonic risk-to-MAE mappings in nested
   leave-one-network-out folds. Select one mapping by prespecified calibration
   error, then refit it on the full open collection.
4. Construct 90% predictive intervals from out-of-network residuals. Record
   coverage and width overall and by network, horizon, season, and domain.
5. Diagnose complete-operator residuals against target memory, seasonal range,
   donor count, air-water coupling, flow regime, topology, network size, and
   data-source domain.
6. Repeat at 30, 90, and 180 days, with 90 days primary.

**Development advancement gate:** both conditions are required:

- complete-operator out-of-network Spearman is at least 0.10 higher than donor
  \(R^2\); and
- station-gap \(\Delta R^2\) after the strongest simple model is at least
  0.05.

Development must also yield a single usable calibration mapping and interval
procedure. If the numerical H2 gate fails, stop Route B iteration on these
outcomes and execute Route A.

## 4. Workstream C — establish the baseline and decision contest

Use identical folds, gaps, and realized recovery losses for:

1. gap length + season;
2. ACF summaries;
3. donor \(R^2\);
4. nearest-donor correlation and distance;
5. the additive \(d/4\) heuristic;
6. the strongest simple combination;
7. the full calibrated operator.

For placement, compare:

1. focal minimax calibrated-risk placement;
2. greedy mutual-information placement;
3. donor-correlation placement;
4. distance placement;
5. degree placement;
6. random placement; and
7. an outcome oracle used only to define regret.

Calculate every policy at every feasible station budget. Choose one primary
budget fraction using open data, and retain the full curve for reporting. The
primary decision outcome is regret in worst-target MAE above the oracle.

## 5. Workstream D — stress transport before confirmation

### Nonstationarity

1. Identify candidate thermal-state changes using temperature distribution and
   coupling summaries, not recovery outcomes.
2. Fit risk and calibration on the pre-change period and score common gaps in
   the post-change period.
3. Report change in MAE bias, calibration slope, interval coverage, and
   placement regret.
4. Associate failures with observed changes in ACF, seasonal amplitude,
   air-water coupling, and discharge regime; do not assign reservoir cause.

### Cross-domain development test

1. Learn on US open networks and test on non-US open networks when enough are
   available.
2. Reverse the roles as a sensitivity if sample size permits.
3. Keep provider-specific day definitions and QC visible.
4. Do not allow a good pooled metric to hide a failed domain.

## 6. Route decision

### Route B: full operator advances

Proceed only after Workstreams A--D finish and the H2 advancement gate is met.
Record before confirmation:

- operator and all input variables;
- calibration family and interval method;
- recovery model and hyperparameters;
- gap geometry, horizons, placements, and loss;
- simple baselines and H3 policies;
- primary budget;
- H1 rank, calibration, and coverage thresholds;
- H2 and H3 contrasts; and
- exclusion and reporting rules.

### Route A: simple redundancy sufficiency

If either H2 condition fails:

1. make the strongest simple model primary;
2. estimate its calibrated sufficiency envelope on open networks;
3. predefine failure strata from open residuals;
4. retain rank + calibration + coverage as H1;
5. test whether simple-model placement has decision value using the same regret
   framework; and
6. recruit a new confirmation panel for this narrower claim.

Do not continue changing the operator against the same development outcomes to
recover Route B.

## 7. Workstream E — recruit a wholly new confirmation panel

Build a catalog of at least 55 new river-network candidates. Candidate sources
are Canada (ECCC and provincial programs), UK Environment Agency, German state
services, France Hub'Eau, and Switzerland FOEN. Provider availability and daily
concurrency must be verified during acquisition; listing a source is not proof
that it contributes an eligible network.

The completed recruitment and source-audit table contains 165 unique river
candidates across USGS, ARSO, CHMI, GKD Bayern, LUBW, FOEN, RWS, Hub'Eau,
ECCC, eHYD, and SYKE. Sixty pass strict stream-only daily-value QC. The scored
confirmation panel was fixed at the first 45 qualifying networks, before CHMI
finished; three lacked a scoreable evaluation gap and 42 entered H1/H3.

Recruitment targets:

- at least 55 candidates before outcome scoring;
- at least 40 QC-passed, scored independent networks;
- at least 15 non-US candidates to make at least 10 retained non-US networks
  plausible;
- at least three climate regimes; and
- at least three stations with sufficient common years per network.

Candidate count is deliberately above the analysis floor because the former
40-candidate pool retained only 32 networks after QC.

## 8. Workstream F — run and report confirmation

1. Complete source, schema, date, unit, and daily-concurrency QC for all
   candidates.
2. Publish the candidate-to-retained flow and every exclusion reason before
   calculating performance summaries.
3. If the retained panel is below 40 networks or below 10 non-US networks, do
   not score the planned confirmation. Report insufficient retained networks
   and close this attempt; later recruitment is a separate confirmation.
4. Apply the recorded operator/simple model, calibration mapping, recovery
   model, gaps, and policies unchanged.
5. Report H1 in three inseparable parts: rank, calibration, and coverage.
6. Report H2 against donor \(R^2\) and the strongest simple combination on the
   same networks.
7. Report H3 as the placement scatter, full policy regret curves, oracle gap,
   and primary budget contrast.
8. Report nonstationarity and domain strata whether favorable or unfavorable.
9. Fill the bracketed manuscript fields from this result set; do not import
   development numbers into the confirmation abstract.

### Completed result

The 42-network confirmation achieved station-gap Spearman 0.803 but missed
calibration (slope 0.806), simultaneous whole-network coverage (0.857), and
the fixed 5% false-release triage endpoint (observed 10%). US calibration was
near target (0.954); cross-domain calibration was not (0.753). The manuscript
therefore reports a transferable ordering without operational calibration.

## 9. Deliverables and completion order

| Order | Deliverable | Completion condition |
| --- | --- | --- |
| 1 | Open corpus table | Actual eligible N and complete B/D/M/H coverage reported |
| 2 | Operator/calibration comparison | Nested network-held-out predictions and interval diagnostics complete |
| 3 | Route decision memo | Route A or B selected from the written H2 gate |
| 4 | Decision benchmark | MI and all non-oracle baselines have full regret curves |
| 5 | Stress-test report | Nonstationarity and cross-domain rank/calibration/coverage reported |
| 6 | New candidate catalog | At least 55 wholly new candidates with source evidence |
| 7 | Confirmation readiness table | At least 40 retained, including at least 10 non-US |
| 8 | Confirmation results | H1--H3 or Route A equivalents reported completely |
| 9 | Manuscript completion | Abstract numbers, main figures, discussion, and SI tables agree |

## 10. Main outputs

- Predicted-risk versus realized-loss calibration plot.
- Coalition and simple-baseline incremental comparison.
- Per-network placement scatter.
- Full mutual-information and comparator regret curves.
- Nonstationarity shift plot.
- Cross-domain reliability panels.
- Complete per-network and per-gap tables in SI.

The final paper is ready only when its title, abstract, figures, and conclusion
all describe the selected route and no sentence implies a result that has not
been run.

## 11. Reviewer-completion extension

The requested empirical-transfer baseline, recovery-family sensitivity,
conditional interval diagnostic, labelled domain-adaptation curve, and
real-data station-retention replay are implemented by
`scripts/124_run_reviewer_completion.py`. They are method development performed
after the first-confirmation outcomes were available and are labelled that way
in every summary.

The empirical curve is built wholly within outer fitting years and is then
applied to the outer evaluation years. It is the strongest tested predictor on
the four supported horizons. That result displaces the former simple-
descriptor sufficiency claim; it does not retroactively become an independent
confirmation.

`configs/route_a_second_confirmation_protocol.yaml` records the required next
test. Recruitment now contains 242 candidates and 60 strict-QC arrivals that
were not scored in the first confirmation: 35 US, 15 Czech, and 10 Norwegian
networks. Total arrival and two-European-domain floors pass. The required
Canadian stratum remains empty after an official four-station Coast Guard
source was excluded because its observations are explicitly not validated or
checked. Scoring remains withheld by the executable readiness gate.
