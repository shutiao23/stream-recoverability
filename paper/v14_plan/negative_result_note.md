# Negative-result note (v13 spin-off) — draft for submission

Status: companion submission for the v14 program (PLAN §8.5). Target: HESS Technical Note or
*Environmental Modelling & Software*. Length: ~4,000–5,000 words + 3 figures + 2 tables.
This note is also the "prior work we no longer claim" citation of the v14 manuscript and of
protocol v5 (`protocol_v5.md` §1.2): v14 predicts *benefit over the default handling*; this
note closes the *loss-ranking* question.

---

## Working title

**Predicting reconstruction error for stream-temperature records: local difficulty
persistence is real, but a station's own history already captures it**

Honest one-line framing (candidate abstract opener / key point):
"Recovery-error prediction: local difficulty persistence is real, but station history
already captures it."

## Abstract (draft, ~180 words)

Missing stream-temperature records must often be reconstructed before the missing truth
arrives, and a manager would like to know, in advance, how large the reconstruction error of
a specific recovery model will be on a specific gap. We tested whether historical block
stress tests — seasonally stratified artificial gaps cut into the already-observed fitting
years of a record and recovered with the intended model — rank that model's future recovery
loss on outcome-disjoint networks. On a second panel of 57 previously unseen networks
(1,446 units; 874 units at directly supported 7/30/90/180-day horizons), the stress curve
ranked future loss with network-level Spearman 0.80 and station-gap Spearman 0.945 — but a
station-by-horizon historical mean of the same record's fitting losses nearly matched it
(pooled 0.942 versus 0.945; paired network difference +0.042, 95% CI [−0.0006, +0.1154];
predictor correlation 0.992), and the season-stratified curve added nothing over station
history at 7 and 30 days. The same predictor failed as a fixed-budget triage instrument
(CapturedLoss@20% 0.337 versus 0.512 for simple descriptors). Local recovery difficulty
persists and is measurable, but it is already encoded in the station's own record; the
incremental value of model-conditional stress testing must be sought elsewhere — in
decisions framed as benefit over the default handling, not in loss ranking.

## Outline

### 1. Motivation and the question

- Scenario: failed logger; gap geometry known at onset; default handling fixed by the
  downstream workflow; the manager needs an expected recovery error *for the intended model*
  before the truth arrives.
- Question: does a fitting-period block stress curve rank the same model's future loss on
  networks whose outcomes were never used to build anything?
- Where this sits relative to the literature: trial-gap tools are established
  (\cite{richardson2007longgaps}); what has not been tested is their prospective, outcome-
  disjoint, model-conditional rank validity. [Keep short — this note reports a null, it does
  not survey.]

### 2. Design (summary)

- Development collection (55 networks, 217 stations, 1,260 units), first panel (42
  networks/1,440 units), second outcome-disjoint panel (57 networks: 32 US/15 CZ/10 NO;
  1,446 units; 874 direct units).
- Nested chronological splits; 70/30 outer split; seasonal placement strata; 7/30/90/180 d
  direct horizons; model-conditional gradient-boosting recovery; MAE (°C) primary loss.
- Comparator of record: the station × horizon historical mean (r6) — the strongest
  information obtainable from the fitting record without a model.
- Inference: network bootstrap within provider strata; paired comparisons on identical
  subsets.

### 3. Results that are the negative finding (all quoted verbatim from v13 artifacts)

| Quantity | Value |
| --- | --- |
| Empirical predictor, pooled Spearman (874 direct units) | 0.945 |
| Empirical predictor, network-level Spearman | 0.805 |
| r6 station × horizon mean, pooled / network | 0.942 / 0.763 |
| Paired network Δρ (empirical − r6) | +0.042, CI [−0.0006, +0.1154] (straddles zero) |
| Predictor correlation | 0.992 (Pearson; Spearman 0.996) |
| Per-horizon network ρ (empirical / r6), 7/30/90/180 d | 0.932/0.916/0.865/0.659 vs 0.938/0.915/0.843/0.603 |
| CapturedLoss@20% (empirical vs simple descriptors) | 0.337 vs 0.512; paired −0.174 [−0.198, −0.140] |
| 365-day extrapolation | rank 0.270 (network), 90% interval coverage 46.8% (124 units, 8.6% of units, 28.9% of loss) |
| Rolling-origin stability (canonical set) | network ρ 0.984/0.944/0.911 at 60/70/80% cutoffs; Kendall W 0.811 |
| Model-selection | regret 0.084 vs best-fixed 0.081 (null); 0.0067 only at 8.5% coverage (proof of concept) |

Interpretation structure: (i) persistence is real and within-network (network-demeaned
pooled ρ 0.936; median within-network ρ 0.965); (ii) the increment over station history is
modest everywhere and zero at short durations; (iii) loss ranking does not imply
intervention value (budget/triage negative); (iv) 365-day extrapolation fails without real
same-horizon support.

### 4. Why the season-stratified curve does not beat station history

- r6 and the full curve use the same information source (the network's own fitting losses);
  season stratification and covariates add rank information only where the station record is
  too short or the season cells are empty.
- Structural statement (short, non-speculative): loss of a given model is largely
  determined by station and gap duration — observables the station's own history already
  encodes; the residual that stress testing could predict is small at the rank level.
- Boundary conditions observed: interpolation works (14/60 d; surface pooled ρ 0.774),
  extrapolation fails (365 d), model-family and missingness-mechanism transfer are bounded
  (report the direction-only findings; the mechanism matrix is harmonized in v14's SI with
  intervals, per `paper/v14_plan/harmonization_decisions.md`).

### 5. Implication: the estimand, not the machinery

- Recommendation (one paragraph): future work should predict **benefit over the default
  handling** (B = MAE_default − MAE_model), where the signal lives in the default's
  difficulty rather than in model difficulty — pursued in the companion paper/protocol
  (v14 differential stress test; `paper/v14_plan/protocol_v5.md`).
- Evidence footnote for that claim: on the same development corpus, ranking model MAE
  correlated negatively with realized benefit (ρ = −0.230) while ranking default difficulty
  correlated positively (+0.659) — flagged as descriptive context, not as a result of this
  note.

### 6. Open research and evidence roles

- Artifacts archived under the repository's versioned results namespaces (per-panel scoring,
  master ladder tables, paired bootstraps; see `paper/development_v13/evidence_ledger_v13.md`).
- Evidence-role statement: second-panel outcomes are internally frozen and hash-bound but,
  because amendment and outcomes entered version control in the same commit, they are not
  externally verifiable preregistration; all revision analyses are post-hoc development on
  already-scored panels (\cite{pfister2017debates} labeling). No automatic filling or
  station-removal recommendation is made anywhere in this note.

## Figures (planned)

1. The near-tie: observed vs predicted loss for the empirical curve and r6 (paired Δρ
   distribution inset; CI straddling zero).
2. Per-horizon network ρ: empirical vs r6 (0.932/0.916/0.865/0.659 vs 0.938/0.915/0.843/
   0.603), with the short-duration convergence marked.
3. Triage negative + 365-day boundary: CapturedLoss@B curves (0.337 at 20%) and the
   extrapolation failure (0.270 / 46.8%).

Relationship to v14 (as submitted in the v14 manuscript): this note is cited as the prior
work we no longer claim (loss ranking, station-history near-tie, triage negative), so the
v14 paper never re-argues loss ranking.
