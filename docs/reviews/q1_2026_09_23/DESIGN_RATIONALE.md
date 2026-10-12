# Design rationale

One row per design decision: the failure it addresses, the root cause, the
principle it follows, the mechanism, and the experiment that would show it was
unnecessary. A component that cannot name the experiment that would retire it
is decoration.

## The screening layer

| observed failure | root cause | design principle | mechanism | evidence it is necessary | what would retire it |
|---|---|---|---|---|---|
| Length-based screening retains years whose peak is badly wrong and discards years whose peak is exact | The screen conditions on a property the estimand does not depend on | Condition the screen on whatever the target statistic is a function of | Peak-window overlap, computed from training years, as the primary covariate | Peak overlap alone gives 5.6% consequential error at 70% retention against 9.2% for length | Peak overlap and length discriminating equally (they do not: clustered AUC contrast excludes zero) |
| Errors vary by an order of magnitude between cases that look identical to a length rule | Donor information quality is invisible to record geometry | Add decision-time-visible information quality | Training-period deseasonalised donor correlation and coverage during the outage | Dropping donor features costs 0.85 points of the 6.3 | Donor features adding nothing once geometry and timing are present |
| The observed days sometimes already pin the annual maximum, and sometimes do not | Geometry cannot see how close the surviving record already is to the answer | Let the screen see how far the observed maximum already constrains the truth | Observed-peak margin against the station's climatological peak | Dropping it costs 0.2 points | Its permutation importance falling to zero |
| A point estimate cannot express that one completed year is trustworthy and another is not | A screen emits a binary admission with no scale | Emit a calibrated quantity, not a label | Selection-conditional multiplicative split conformal bound and interval | Marginal coverage 0.909 on reserved networks, adaptive width 0.06–1.87 °C | Coverage failing out of sample, which it does not, or the interval never being used downstream |
| Taking the smallest of several estimator bounds under-covers | Winner's curse: the minimum of several bounds is optimistic | Calibrate the composite procedure, not its parts | Conformity scores computed after the estimator is selected | The additive per-estimator version under-covered below 0.80 marginally | Per-estimator calibration covering correctly, which it did not |
| Pooled conformal coverage is right on average over networks and wrong inside the hardest ones | Conformal validity assumes an exchangeability that fails between river networks | Offer the analyst the level of validity their question needs | Calibration on per-network conformal quantiles, with a level dial | Per-network minimum rises 0.778 → 0.851 with no network below 0.85 | The pooled version already covering every network, which it does not |

## The reconstruction layer (settled, not a contribution)

| decision | reason | evidence |
|---|---|---|
| No estimator reads a gap-interpolated target boundary | A neighbour-day trainer that does collapses at long gaps; the same algorithm on long blocks does not | carried forward from the preceding programme |
| Support is declared per method, not by a blanket rule | Donor regression does not read the right flank, so requiring it would discard usable cases | hiding the right flank leaves the donor prediction unchanged |
| Missing donor columns are never imputed; the model is refit on the visible subset | Imputation is harmful, refitting is not | refit +0.74 °C against imputed −1.56 °C |
| Estimators are fit leave-one-year-out within the station | Offline archive repair does hold the rest of the record | a strictly-prior-years variant is reported and costs 0.4 points |

## Deliberate omissions

| not included | why | what it would have cost |
|---|---|---|
| A deep sequence model for reconstruction | The gate showed the entire method-selection action space has a ceiling of 0.080 °C, below what the confirmation can resolve | compute, and a claim the experiment could not test |
| A fixed reconstruction budget | Full default is always a legal action; a budget is a deployment constraint, not a scientific one | an untestable constraint imported from an earlier design |
| Basin attributes inside the screen | They are unavailable outside the United States panel, so a screen using them could not be recommended to the other eight agencies | generality |
| Cross-year outages | The annual endpoint is undefined across the boundary without a second convention | a confounded endpoint |
