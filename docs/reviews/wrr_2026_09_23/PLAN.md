# v17 redesign — experimental programme

Companion to `REVIEW.md` (2026-09-23). This is the programme I would run if this
were my student's project. It reuses the existing corpus, replay harness and
provenance discipline; it replaces the question, the endpoint, the action space
and the comparison set.

---

## 0. The reframing in one paragraph

The v16 question — *adopt this reconstruction or keep the climatology default?* —
has an oracle headroom of 0.02–0.07 °C on a quantity whose natural interannual
standard deviation is 1.06 °C. It is not a decision. The question with room in
it, and the question practitioners actually face, is:

> Given the outage pattern in this station-year and the information actually
> available at this station, **is the completed year's thermal metric fit for
> use, and with what uncertainty?**

The incumbent answer is a fixed rule of thumb on outage length (Johnson et al.,
2021: about 7–9 consecutive weeks unfilled, extended to about 13 weeks with
imputation) and agency percentage-coverage standards. The deliverable of this
programme is a **usability certificate**: per station-year, a calibrated
prediction interval on the completed-year metric plus a use/exclude decision at
a tolerance the analyst names. The claim is that the certificate dominates
length-based screening on the retention–error frontier, out of sample, across
agencies — and that the reason it does is hydrologically interpretable.

Preliminary evidence that this is worth running, computed from the authors' own
legacy year table with seven crude features and network-grouped cross-validation
(at 70% retention, development panel):

| screen | share of retained years with hottest-30 error > 0.5 °C | > 1.0 °C | mean abs. error |
|---|---:|---:|---:|
| retain everything | 23.2% | 10.4% | 0.375 |
| fixed gap-length rule (incumbent) | 21.4% | 9.3% | 0.352 |
| gap-fraction rule | 19.8% | 8.5% | 0.315 |
| random at matched retention | 23.9% | 11.1% | 0.386 |
| **certificate** | **14.8%** | **5.5%** | **0.268** |
| oracle | 0.0% | 0.0% | 0.091 |

The incumbent length rule is barely distinguishable from random above 80%
retention (23.6% versus 23.2% at 90%). That is itself a result worth reporting.

---

## Step 1 — Population, truth, and a pre-declared split at full scale

**Why.** The v16 confirmation used 82 of 5,307 eligible station-years and drew
them from a pool whose donor availability differs from development by an order
of magnitude. Both problems are fixed here by construction.

**Do.**
1. Rebuild the eligible panel from `step1_universe`: river waterbodies, fully
   observed calendar years, reference never imputed. Target 161 networks, 547
   stations, 5,307 station-years.
2. Require at least four complete years per station for the leave-one-year-out
   recovery protocol (457 stations, 5,114 station-years survive).
3. Declare two stratification variables **before** splitting: donor regime
   (`none` = 0 synchronous donors, `sparse` = 1–2, `rich` = 3+) and provider.
4. Split networks — not station-years — into development and reserved
   confirmation, stratified on (provider × donor regime), with a fixed seed
   recorded in the protocol. Reserve approximately 30% of networks in each
   stratum.
5. Record the denominator table: every exclusion, its reason, and its count.

**Deliverable.** `results/v17_fitness/step1_panel/` with the roster, the split,
and the exclusion ledger. Nothing downstream may touch reserved networks until
Step 10.

## Step 2 — The outage design

**Why.** v16 placed at most four gaps of 30/90/180 days per year and produced a
population in which 29% of cases had exactly zero benefit. The outage design is
the experiment; it must span the decision-relevant space and be weighted to a
declared target distribution.

**Do.**
1. **Empirical arm.** Extract the real outage geometry of each provider from the
   raw records — run length distribution, start-month distribution, runs per
   year, and the joint structure across stations of the same network (co-missing
   donors). Transplant onto complete years.
2. **Stratified arm.** A balanced factorial over outage length
   {14, 30, 60, 90, 120, 180, 270} × peak-overlap class {none, partial, full},
   so the response surface is estimable rather than accidental.
3. Define the key geometric covariate explicitly: **peak-window overlap** =
   the fraction of the station's *climatological* hottest-30 window (estimated
   from training years only, so it is visible at decision time) that falls
   inside the outage.
4. Target roughly 12 realizations per station-year, giving of order 25,000–60,000
   scorable cases; weight the empirical arm to the provider's real distribution
   when reporting operational numbers, and report the stratified arm separately
   for mechanism.

**Deliverable.** `results/v17_fitness/step2_outages/`.

## Step 3 — Estimators, including the two incumbents v16 omitted

**Why.** The paper must compete with what people do. It currently competes with
a default it chose itself.

**Do.** For every case compute the completed-year metric under:
1. `observed_days` — compute the metric from recorded days only, ignoring the
   outage. *This is standard practice and was absent from v16.*
2. `doy_climatology` — the v16 default.
3. `smooth_climatology`.
4. `linear_interp` where both flanks exist.
5. `donor_only_ridge` where synchronous donors exist, retrained on the visible
   donor subset (the Step-4 finding of v16, which the v16 policy did not deploy).
6. `air_ridge` / `air2stream3` where NASA POWER forcing exists (8 networks, 14
   stations — report coverage honestly and keep this branch as a sub-study).
Recoverers are fit leave-one-year-out within the station, which is the correct
protocol for *offline archive repair*; a strictly-prior-years fit is reported as
a sensitivity.

**Deliverable.** The case table: truth, every estimator, signed and absolute
error of the completed-year hottest-30, days above 20 °C, and annual mean.

## Step 4 — Ceiling analysis: the gate v16 skipped

**Why.** Section 1 of the review. No decision experiment may be run before the
ceiling of its action space is known.

**Do.** For each candidate action space compute the oracle and report headroom
against the best fixed policy and against the 1.06 °C natural scale:
- adopt/reject a fixed reconstruction (v16's space — expected ceiling ≈ 0.02 °C);
- choose among reconstruction methods (expected ≈ 0.05 °C);
- **retain/exclude the station-year** (expected ceiling: the entire 23.2% →
  0% consequential-error range);
- retain/exclude combined with method choice.

**Gate.** Proceed only with action spaces whose ceiling exceeds three times the
declared decision resolution. Record the gate decision in the protocol.

**Deliverable.** `results/v17_fitness/step4_ceiling/` — and if the gate fails,
the programme stops here and says so.

## Step 5 — Mechanism (H1): what actually makes a station-year unusable

**Hypothesis H1.** At fixed outage length, the error of the annual thermal
metric is governed by (i) overlap between the outage and the station's
climatological peak window, (ii) the margin by which the observed days already
constrain the annual maximum, and (iii) the quality — not the mere presence — of
synchronous donor information. Outage length itself is a weak proxy for all
three, which is why Johnson et al. found timing effects "inconsistent in space
and time".

**Do.**
1. Variance decomposition of |error| over length, overlap, observed-peak margin,
   donor correlation, donor count, station thermal variance, regulation status.
2. Controlled manipulations, one factor at a time:
   - fix length, vary peak overlap across its three classes;
   - fix length and overlap, vary donor correlation by *subsetting* donors into
     high- and low-correlation sets of equal size;
   - **anomaly-shuffle control**: replace donor anomalies with phase-shuffled
     surrogates while preserving the donor seasonal cycle — this separates
     "donors carry synchronous anomaly information" from "donors merely supply a
     seasonal shape", which no previous step in this project has tested;
   - hide donors during the outage only (co-missing), versus hiding them
     throughout.
3. Report each as an effect on the *final metric error*, not on daily MAE.

**Deliverable.** `results/v17_fitness/step5_mechanism/`.

## Step 6 — The design: a calibrated usability certificate (H3)

**Do.**
1. **Predict**, from decision-time-visible features only, the absolute error of
   the completed-year metric for each *supported* estimator. Features: outage
   geometry; peak-window overlap; observed-peak margin; donor count, coverage
   during the outage and training-period deseasonalized correlation (min/mean/
   max); station training residual variance, seasonal amplitude, interannual
   metric variance; record length; air availability. No feature may use data
   hidden at decision time, and this must be enforced in code, not by
   convention.
2. **Select** the estimator with the lowest predicted upper error bound; this
   subsumes method selection into the same object.
3. **Calibrate** with split conformal prediction, grouped so that calibration
   and test never share a network. Produce a two-sided interval on the metric
   and a one-sided upper bound on |error|.
4. **Certify** at a user tolerance τ: usable if the conformal upper bound on
   |error| is ≤ τ. τ is reported in units of the station's interannual standard
   deviation as well as in °C.
5. **Mondrian variant**: calibrate within pre-declared strata (donor regime ×
   overlap class) to obtain conditional coverage, and report both marginal and
   conditional coverage.

**Deliverable.** `results/v17_fitness/step6_screen/`, plus a frozen model
artifact.

## Step 7 — Dominance over the incumbents on the frontier (H2)

**Do.** On development networks with network-grouped cross-validation, and again
under leave-one-provider-out:
- sweep retention from 100% down to 40% for every screen;
- baselines: retain-all; fixed outage-length thresholds (the Johnson-type
  incumbent, swept to trace its whole frontier); missing-fraction thresholds;
  warm-season-coverage thresholds; random at matched retention; model-internal
  prediction variance; oracle;
- report, at matched retention: rate of |error| > τ for τ ∈ {0.25, 0.5, 1.0} °C,
  mean |error|, severe-underestimate rate, and the retained sample's usability
  for trend work; and at matched error: retention;
- cluster all uncertainty by network, bootstrap at the network level.

**Deliverable.** `results/v17_fitness/step7_frontier/` with the frontier figure
as the paper's central result.

## Step 8 — Downstream consequence (H4)

**Why.** A referee will ask what changes in a scientific product. Answer it.

**Do.** Assemble multi-year per-station series of the annual metric under
simulated outages, then compare against the fully observed truth for:
1. the Theil–Sen trend in annual hottest-30 over the station's record;
2. the count of years exceeding 18 °C and 20 °C;
3. the identity and rank of the hottest year.
Compare truth against {use everything, length-rule screening, certificate
screening at matched retention}. Report bias and RMSE of the slope, and error in
exceedance counts. Include the loss of statistical power from excluding years,
so the tradeoff is stated honestly in both directions.

**Deliverable.** `results/v17_fitness/step8_downstream/`.

## Step 9 — Freeze, with a power calculation

**Do.** Freeze features, model, hyperparameters, conformal calibration,
tolerances and strata from development only. Write
`SUCCESS_CRITERION_v17.json` containing:
- primary claim (H2) with the effect size, the comparison rule and the
  clustering unit;
- **a pre-registered precision calculation in the units of the endpoint**,
  stating the number of reserved networks and station-years needed to resolve
  the declared effect — the single most important thing missing from v16;
- secondary claims (H3 coverage bands, H4 trend bias);
- explicit failure conditions and what the paper says if each fails.

**Primary success condition (proposed).** On reserved networks, at the retention
of the best fixed-length rule, the certificate reduces the rate of hottest-30
error > 0.5 °C by at least 5 percentage points absolute, with a network-clustered
bootstrap interval excluding zero; **and** marginal conformal coverage lies in
[0.87, 0.93] for a nominal 0.90 interval.

**Deliverable.** `results/v17_fitness/step9_freeze/`.

## Step 10 — Confirmation, scored once

**Do.** Open the reserved networks exactly once. Report by donor regime and by
provider, not only pooled. Add leave-one-provider-out as the agency-transfer
test. Report the result whatever it is, and record the opening in the ledger.

**Deliverable.** `results/v17_fitness/step10_confirmation/`.

## Step 11 — Manuscript v17

Structure: the usability question and the incumbent rule → why length is the
wrong axis (H1) → the certificate (design) → dominance on the frontier (H2) →
calibration (H3) → what changes downstream (H4) → confirmation and transfer
(H5) → limits. Carry forward from v16, unchanged: the training-mismatch
diagnosis, the right-boundary negative control, the non-river exclusion, the
`diff`-equals-seasonal-mean identity as a definition, and the provenance ledger.

---

## What must be true for this to be a strong paper

1. H1 holds and is interpretable — length is a weak axis, overlap and donor
   quality are strong ones.
2. H2 holds out of sample on networks and agencies never used for fitting, with
   an effect large enough to matter (≥ 5 points of consequential-error rate).
3. H3 holds — the intervals are honest, including conditionally.
4. H4 shows a change in a quantity a reader cares about.
5. Every claim is anchored to the 1.06 °C natural scale.

If H2 fails on the reserved networks, the paper still has H1 (a mechanism result
that corrects a published guideline's axis), H3 (calibrated uncertainty on
derived thermal metrics, which nobody currently reports), and the v16
training-mismatch diagnosis. That is a publishable paper with a negative
decision result — which is the position v16 tried to occupy without having
established H1 or H3 first.
