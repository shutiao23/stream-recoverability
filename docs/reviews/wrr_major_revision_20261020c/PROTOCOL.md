# Scientific revision protocol, 2026-10-20c

The user authorised execution of every item in the attached adversarial review,
not another review or a prose-only revision. The source is
`/home/lzq/.codex/attachments/fdae9de4-eb48-48d2-97a6-3ac57db73bdb/pasted-text-1.txt`.
Existing manuscript edits and earlier results remain part of the working tree.
This protocol declares new experiments before their outcomes are computed. It
does not retroactively preregister the already opened development and external
panels. The machine-readable constants are in
`configs/wrr_revision_20261020c.json`.

## Question, endpoints and falsifiers

The primary object is the annual hottest consecutive 30-day mean (H30) from
daily mean river-water temperature. Consequential error is absolute H30 error
greater than 0.5 degrees C. The admission target is 5% failure among admitted
records. A downstream primary use is identifying a locally anomalous hot year
against the 90th percentile of available training-year H30 values. Fixed 18 and
20 degrees C classifications, annual mean, network representation and regional
hot-year frequency are secondary endpoints. Missing or unsupported estimates
are abstentions with their denominators retained.

H1: target-window information improves admission beyond gap length, calendar
season and flexible seasonal coverage. Failure is no reproducible improvement
against the same-information seasonal baseline. An ablation of the explicit
overlap feature does not establish absence of implicit target information.

H2: an uncertain-window design combining support, reconstruction reliability
and competing windows improves admission over the existing generic model with
H30 disagreement. The primary practical superiority margin is five retention
percentage points, at the common calibrated risk target. The two-point margin
is reserved for equivalence/noninferiority claims about a simpler method.
Both point differences and paired cluster intervals must be reported. Crossing
zero is not proof of equivalence. The certificate and direct H30 uncertainty
are mandatory additional comparators. Negative results remain in the report.

H3: the complete decision process improves locally anomalous hot-year decisions
on the original candidate pool for at least one declared, positive abstention
cost, without concealing loss of network coverage. Failure is no benefit against
reconstructing all records. No perfect or free human repair is assumed.

## Information and independence

Retrospective repair may use other available years. Prospective evaluation must
recompute climatology, donor relations, residual diagnostics and reconstructors
using strictly earlier years; a later split of cached features is insufficient.
Training, calibration and testing are separated at connected components of
shared station identities. New external stations are additionally checked by
original id, coordinates, source archive, river and observation dates. Connected
catchments or shared source records cannot be split as independent units.

All existing panels are development or retrospective diagnostics. New external
records are partitioned by a fixed salted hash of their independent component,
with 40% development, 30% calibration and 30% final test. Provider, coordinates,
time coverage and file completeness may be inspected for eligibility. Final
test outcomes are not inspected until the design, feature lists and thresholds
have been frozen. A downloaded event-only series cannot become continuous H30
truth. All source and target exclusions and missing metadata are reported.

Three transfer conditions remain distinct: frozen risk model and threshold;
frozen model with local calibration; local fitting and calibration. Local
historical reconstruction fitting is permitted only as explicitly declared.
Three fold seeds measure split sensitivity, not independent confirmation.

## Controlled recovery and mechanisms

Use the full eligible existing network roster, including single-station and
documented-daily-mean providers. Eligibility and exclusions are recorded before
scoring. Stratification uses provider, known hydrological attributes and donor
availability. Unknown regulation or groundwater status is not invented.
Within eligible station-years cross 30, 60 and 90-day runs with feasible none,
partial and full climatological overlap, with four starting-date realisations
per cell. Also compare equal-total-missing single and fragmented gaps and
within-warm-season position controls. Empty feasible cells stay empty. Report
station-years and networks, not just mask counts. Multiple masks reduce Monte
Carlo noise and are not independent hydrological replications.

For the identity H30(completed)-H30(truth)=mean(error in true window)+F, F is
called the window-switch increment. Separate switches that still underestimate
the true maximum from genuine overestimation. A stratified MAE association is
not identified with F. Cross the gap residual mean intervention with residual
permutation, including their interaction. Distinguish oracle interventions from
deployable bias correction estimated from historical data and visible anchors.

## Uncertain-support design and comparators

Generate conditional completed trajectories from training residuals while
preserving time dependence with 14-day blocks, using 128 draws. Observed target
days remain fixed. Obtain H30 and winning windows on every trajectory, yielding
probabilistic hidden support, support uncertainty, window competition and direct
H30 uncertainty. These quantities are scores, not coverage guarantees. A direct
H30 uncertainty screen is mandatory to test whether the extra window
representation is necessary. Preserve the same reconstruction, candidate pool,
training labels and calibration resources in the feature comparisons.

Mandatory baselines are reconstruct-all; published and calibrated length rules;
warm-season coverage; climatological overlap; a spline seasonal model; small
logistic models with and without support; the generic model with H30
disagreement; the existing certificate; direct H30 uncertainty; and the proposed
uncertain-support model. Compare H30-specific disagreement with daily residual
diagnostics at matched capacity and information. Ablate uncertain support,
reconstruction trust, competition and donor information. A process-based
Air2stream reconstruction is evaluated where forcing inputs permit it, and a
probabilistic reconstruction comparator is required. Extra inputs are an
information increment, not an architectural gain.

## Risk, stress, utility and power

Reproduce the zero-failure clustered-bootstrap counterexample. Assess rare
high-risk groups, nearly perfectly correlated failures, score-uninformative
failure types, zero-failure calibration samples, time shift and provider shift.
Any formal guarantee must state the independent unit and the selected-risk
estimand. Marginal interval coverage is not selected-risk control. A heuristic
bootstrap result is labelled empirical. Evaluate pooled case risk, equal-network
risk and predefined hydrological strata with denominators and uncertainty.

Cross warm anomalies and event placement (before/during/after) with target-only,
half-donor and all-donor outages. Use flow when available to identify compound
low-flow heat conditions. Outcomes defined using complete truth can construct
stress tests but cannot establish real missingness causes. Event definitions
estimated from training data are distinguished from independent event labels.

Evaluate the full candidate pool, fixed and local hot thresholds, near-threshold
cases, false positives, false negatives, abstentions, network representation and
regional frequency error. Costs of abstention are 0, .01, .025, .05, .1 and .25
relative to one false positive; false-negative costs are 1, 5 and 10. Rejected
records remain unknown or interval-valued; they never become cool records.

Power analysis resamples independent networks and redoes learning, calibration
and evaluation. Report 80% and 90% power for the declared five-point contrast,
and distinguish conditional-on-model from whole-procedure uncertainty. More
masks cannot substitute for more independent networks. Stop tuning when the
declared independent test has been scored; report a negative result as such.

## Publication and completion requirements

Rewrite the manuscript only after new results are available, around the final
question, method and five evidence groups: controlled recovery, decomposition,
same-information ablation, independent transfer and downstream value. Correct
prior-work scope, information-priority reconstruction, climatological residual
definition, false-peak language, risk semantics, and equivalence wording.
The working title is "When are incomplete river-temperature records fit for
estimating thermal extremes?". Rebuild the manuscript and SI, update figures,
tables, claim bindings and point-by-point responses, and run relevant checks.
Successful software execution alone cannot close a scientific requirement.

This task is complete only after every item in REQUIREMENTS.csv has explicit
supporting evidence, including any negative scientific outcome and its faithful
manuscript treatment. A missing acquisition or experiment remains incomplete.
