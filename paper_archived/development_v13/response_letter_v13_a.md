# Response letter — revision v13 (agent a, adversarial pair)

Manuscript: "Historical block stress tests rank future model-specific
reconstruction error across stream-temperature networks" (WRR; revision v13).

This letter responds to the simulated WRR review returned at the
Reject-and-Resubmit boundary (10 Major Comments plus writing, figure, and
data/software comments). The v13 package is `paper/development_v13/`
(`manuscript_v13_a.md`, `figure_plan_v13_a.md`, `claim_matrix_v13_a.md`,
`terminology_v13_a.md`, `protocol_v4_a.md`, `response_letter_v13_a.md`,
`evidence_ledger_v13_a.md`). All numbers cited below are artifact values from
`results/revision_v12/` (analysis ids t01–t12) and the v13 re-verification
agents (`results/revision_v13/strongest_baseline/{agent_a,agent_b}/`,
`results/revision_v13/decision_harmonization/{agent_a,agent_b}/`); where the
review and the artifacts disagree, the artifact value is used and the
resolution is stated explicitly. The two v13 strongest-baseline agents agree
with each other and with the v12 artifacts to 15 significant digits; the two
decision-harmonization agents reproduce the 8.5%-coverage point (regret
0.0067) exactly, with one documented convention difference on the random
comparator (single seeded draw vs 20-draw mean).

## Summary of how the revision changed

v13 is a re-centering, not a patch. Four structural decisions govern every
section:

1. **The comparator is now the strongest fitting-record baseline.** The
   station × horizon mean of a network's own fitting losses (rung 6 of the
   twelve-rung fitting-period baseline ladder, t03) nearly ties the proposed
   stress curve on the direct-support subset (pooled 0.942 vs 0.945; network
   0.763 vs 0.805; paired Δρ_net +0.042; unit-level correlation 0.992). All
   "ranks better" language is now stated against this baseline; the
   simple-descriptor contrast (+0.55) is retained only as a secondary
   comparison because the descriptors are not the strongest baseline at
   network level on any subset (t03 recommendation).
2. **The strongest conclusion is an empirical law, not a superior
   algorithm.** The paper now defines the Design as a framework
   (cut → recover → score → rank → support-check → abstain → confirm) and
   states the primary result as a persistence law: a model's fitting-period
   stress curve orders that same model's future error at directly supported
   horizons, as a within-network property. The words "strongest tested
   screen" are gone from the conclusions.
3. **Negative and coverage-conditional results are reported as such.**
   Triage failure of the empirical predictor (CapturedLoss@20% 0.338 vs
   0.512) is a reported negative; model selection with abstention is
   explicitly scoped to 8.5% released coverage (123 units / 8 networks) with
   a pre-registered coverage floor in protocol v4.
4. **Demotions and relabeling.** Missingness and model matrices move to SI
   with n-annotations and harmonization caveats (the donor-synchronous
   matched-transfer conflict 0.979 vs 0.490 is disclosed, not hidden);
   BiLSTM "self-transfer" is relabeled cross-instance transfer; the
   covariance estimand appendix moves to SI; downstream results are reported
   against both untreated baselines (no-fill and climatology default).

In addition, v13 fixes the second-panel network count (57 = 32 US / 15 CZ /
10 NO; the v12 text "35 US" was an arithmetic slip), implements 365-day
abstention as policy rather than diagnosis, and replaces protocol v3 with
protocol v4 (regret primary endpoint + coverage floors, external
timestamping retained). A pre-submission data gate (archival DOI) remains
open and is scheduled, not deferred silently.

---

## Major Comment 1 — Abstract/Fig 2 comparator choice

**Reviewer concern.** The headline paired comparison (+0.55 over "simple
descriptors") used a weak comparator. The strongest fitting-record baseline
— the station × horizon mean of the network's own fitting losses — nearly
ties the proposed curve on the direct subset (pooled 0.942 vs 0.945),
leaving a paired Δρ of only +0.042 whose CI straddles zero, with unit-level
correlation 0.992 between the two predictors. The abstract and Figure 2
therefore overstated the claim.

**Action taken in v13.** The paper is re-centered on the strongest baseline.
The abstract, Key Points, Results 3.1, and Figure 2 now lead with the
station × horizon mean (r6 of the t03 ladder) as the primary same-unit
comparator on the 874 direct-support units: pooled Spearman 0.942 vs 0.945,
network Spearman 0.763 vs 0.805, paired network-level Δρ +0.042. The claim
is worded as "ranks at least as well as the strongest fitting-record
baseline, with a directionally positive network-level advantage," never as
uniquely superior. The vs-simple contrast (+0.552 [0.309, 0.814] network;
+0.098 [0.059, 0.142] station-gap; t01) is demoted to a secondary
comparison, and the full-panel vs-simple numbers are reported as the
artifact-driven diagnostic they are. Figure 2's right panel plots the paired
bootstrap of Δρ against r6 (not against simple descriptors), with the
simple-descriptor distribution shown as a secondary inset.

**Evidence.** `results/revision_v13/strongest_baseline/agent_a/REPORT.md`
(re-verification; agent_a and agent_b summary_metrics agree to 15 digits) and
`results/revision_v12/t03_baseline_ladder/agent_b/` and `agent_a/`. On the
874 direct units: empirical 0.9453/0.8049/0.9383; r6 0.9424/0.7632/0.9235;
paired Δρ network +0.04123 [−0.00039, +0.11399], P(Δ>0) = 0.9705 (official
seed-42 run); seed-0 verification +0.04175 [−0.00059, +0.11543] is an exact
match to the v12 t01 paired bootstrap, so the CI straddles zero at both
seeds and the correct wording is "positive in 97.0% of bootstrap draws",
not "CI excludes zero". Pooled Δ +0.00283 [−0.00045, +0.00656], P = 0.9505.
Unit-level correlation between r6 and the empirical curve on direct units:
Pearson 0.9917 (the review's 0.992) and Spearman 0.9959 (the manuscript
states which correlation it uses; if rank correlation is intended, the
value reads 0.996). Against r6, the empirical advantage is concentrated at
90/180-day horizons (+0.021/+0.056 network Spearman); at 7 days r6 is
marginally ahead (0.9384 vs 0.9321) and at 30 days they tie (0.9157 vs
0.9154). First panel (direct 858): Δρ +0.00245 [−0.0237, +0.0275], P =
0.5995 — statistically zero. New scoping result from the re-verification:
on the full panels the network-level Δρ inverts (second all-1,446 −0.01101
[−0.03556, +0.00786], P = 0.1295; first all-1,440 −0.01184, P = 0.1650), so
the advantage over the station × horizon mean is confined to the
direct-support subset and every claim is scoped accordingly.

**Remaining caveat.** The network-level advantage over the strongest
baseline is small (+0.041) and not robustly CI-excluding; it is a
direct-support, between-network effect (after demeaning, empirical and r6
are statistically inseparable: residualized pooled 0.9359 vs 0.9298;
within-network medians 0.9650 vs 0.9676). Protocol v4 therefore registers
the paired Δρ against the station × horizon baseline (not against simple
descriptors) with a margin frozen before outcomes; the persistence law, not
superiority in magnitude, is the paper's claim.

---

## Major Comment 2 — The second panel is no longer an independent confirmation set

**Reviewer concern.** The second (57-network) panel was internally frozen but
its amendment and outcomes entered version control in the same commit; all
revision analyses are post-hoc development on already-scored panels. The
manuscript's provenance statements were buried in Methods 2.10 and the
abstract/Key Points still read as if the second panel were independent
confirmation.

**Action taken in v13.** Provenance labeling is now structural, not
decorative. (i) The abstract states the evidence roles: the second panel is
described as "internally frozen, not externally verifiable preregistration";
every revision result is described as development on previously scored
panels; only protocol v4 defines confirmatory evidence. (ii) Section 2.10 is
rewritten as "Evidence roles and third-confirmation rule" with an explicit
three-way classification — frozen pre-outcome (the empirical curve itself),
post-hoc development on frozen panels (all v12/v13 comparisons), future
preregistered (v4) — mirrored by the evidence ledger shipped with the
revision. (iii) Figure 1 carries a provenance legend (development 55 / first
42 / second 57 with provider counts and the v2 same-commit note). (iv)
Terminology v13 adds the label `post-hoc development analysis` and forbids
"independent confirmation" anywhere except protocol-v4 language.

**Evidence.** v12 Methods 2.10 and Open Research; `t12_confirmation_protocol/
agent_a/protocol_v3.md` §0 (v2 flaw: amendment and outcomes share one
version-control commit; v2 registration record fields
`externally_verifiable_preregistration: false`,
`separate_pre_outcome_commit: false`). The v13 provenance legend uses the
panel counts verified in `t01_paired_comparison/agent_a/provider_sensitivity.csv`
(see Major Comment on writing, and ledger row P1).

**Remaining caveat.** No text can restore the second panel's confirmatory
status; the claim hierarchy is permanently bounded by it. The confirmatory
burden is carried entirely by protocol v4 (external timestamping, margins
frozen before outcomes, separate pre-outcome commit), which remains
unregistered at submission time — a stated open item, not a completed one.

---

## Major Comment 3 — CapturedLoss is loss-targeting utility, not end-to-end decision utility; the triage negative stands

**Reviewer concern.** The decision section conflated a loss-capture metric
with end-to-end decision utility, and the empirical predictor is the worst
non-random fixed-budget triage policy on the full panel (CapturedLoss@20%
0.338 vs 0.512 for simple descriptors) — a negative result that must be
reported, not spun.

**Action taken in v13.** Triage is demoted to a reported negative and the
terminology is corrected. Results 3.8 now opens: "For fixed-budget
prioritization on the full second panel, the frozen empirical predictor is
the worst non-random policy." The structural mechanism is given
prominently: the network-mean fallback tier (572 units, including all 124
365-day units) under-ranks the largest losses (mean prediction 1.33 °C vs
observed 5.27 °C at 365 days; the tail carries 28.9% of total loss).
"CapturedLoss@B" is defined in terminology v13 as *loss-targeting utility*
(fraction of total observed loss captured in the top-B set), and the phrase
"end-to-end decision utility" is removed; the decision chain that would
justify that phrase (costs, actions, realized outcomes) is explicitly out of
scope. The paired differences are reported with CIs: empirical − simple
−0.174 [−0.198, −0.140]; surface − simple −0.012 [−0.031, +0.003]
(statistically indistinguishable); NDCG@20% simple 0.908 vs empirical 0.617.

**Evidence.** `results/revision_v12/t09_decision_utility/agent_a/`
(`utility_table_part1.csv`, `bootstrap_part1.csv`, `abstention_curve_part1.csv`)
and `agent_b/` (headline and bootstrap agree: agent_b CapturedLoss@20%
empirical 0.3362 vs simple 0.5134; bootstrap difference −0.1755
[−0.2008, −0.1431]). Both agents agree the negative is not an artifact of
the tie-breaking convention.

**Remaining caveat.** Loss capture is not decision utility; the paper claims
only the former. Protocol v4 registers captured-loss and NDCG@5% endpoints
vs random (not vs simple) as secondary primaries, and the triage negative is
carried into v4 as a direction-replication diagnostic with margin 0.

---

## Major Comment 4 — Model selection positive only at 8.5% coverage; coverage floors required

**Reviewer concern.** The Part-2 selection result (regret 0.0067) holds only
on 123 units / 8 networks (8.5% of the first panel), which is not
operational evidence: the released set is not a random sample, n is small,
the ridge-family calibration is in-sample on 8 networks, and 91.5%
abstention is not a deployable coverage. The claim needs coverage floors.

**Action taken in v13.** The model-selection section is reframed around
coverage. The released-unit result is reported as coverage-conditional with
all comparators re-evaluated on the same released units (best fixed 0.151,
global blocked-CV 0.151, per-network CV 0.164, gap-length rule 0.145,
random 0.341; proposed 0.0067 [0.0019, 0.0120]); the no-abstention null is
reported in the same table (proposed 0.084 vs best fixed 0.081, difference
+0.0037 [−0.0255, +0.0330]). The section states the four limitations the
review identified verbatim as boundary conditions: (1) the 123 released
units lie on the 8 t05 networks, which were selected, not sampled; (2) the
coverage is 8.5%, and selection gains are demonstrated only there; (3) the
seasonal-boundary/donor-ridge stress rows exist only on those 8 networks
and their recalibration regressions are in-sample (slopes ≈ 1.02/1.04,
intercepts ≈ 0, common-scale sensitivity reproduces all headline values);
(4) the sharp lever is the support rule, not ambiguity abstention
(ambiguity-only abstention slightly raises regret, 0.085 → 0.100 at δ =
0.10). The claim sentence is: "model selection with per-unit fitting-period
support for all candidates and explicit abstention reduces network-balanced
regret on the released coverage; operational use requires a coverage floor
and external confirmation." Protocol v4 makes the coverage floor a frozen
registration quantity (see data/software comments) and changes the primary
endpoint to a regret endpoint scored only where the floor is met.

**Evidence.** `results/revision_v13/decision_harmonization/agent_a/`
(`coverage_regret_curve.csv`, `coverage_regret_summary.md`,
`comparators_table.csv`) and `agent_b/` (same files; both agents reproduce
the 8.5% point exactly: proposed 0.0067, best fixed 0.1508, global CV
0.1508, per-network CV 0.1636, gap rule 0.1447; random differs by seed
convention — agent_a 0.3509 as a 20-draw mean vs agent_b 0.2686 as a single
seeded draw — and is reported with its convention). The harmonization adds
the fixed-coverage curve the review demanded: at fixed coverage c = 0.5 and
c = 0.7 the proposed selector's advantage over best-fixed/global-CV is small
and criterion-dependent (e.g., ambiguity-margin criterion: proposed 0.1147
vs 0.1300 at c = 0.5; width criterion: proposed 0.0719 vs best fixed 0.0462
at c = 0.5), and per-network average-CV dominates at every coverage
(0.0218–0.0613), so the order-of-magnitude result is specific to the
support-defined 8.5% release, which is exactly what the coverage floor
formalizes. The no-abstention null is reproduced identically by both agents
(proposed 0.0850 vs best fixed 0.0815; per-network CV 0.0383).
`results/revision_v12/t09_decision_utility/agent_a/` remains the source of
the released-unit comparators table.

**Remaining caveat.** The result is a proof-of-concept conditional on
support availability; until v4 registers a coverage floor and confirms on an
outcome-disjoint panel, no operational model-selection claim exists.

---

## Major Comment 5 — Downstream thermal conclusions depend on the untreated baseline

**Reviewer concern.** The downstream protection numbers were computed
against no-fill (gap days dropped). Against a climatology-fill default the
budget result reverses for threshold/degree-day metrics on long summer gaps
(the reconstruction is cold-biased at the seasonal peak), so the benefit is
baseline-relative: B = D(default) − D(model) − λC.

**Action taken in v13.** Multi-baseline reporting. Results 3.7 reports both
untreated alternatives with their own tables: (i) no-fill default (status
quo; canonical numbers): reconstruction error is 12–14% of no-fill error for
degree days, annual mean, and trend slope, and 30–37% for the 90th
percentile, amplitude, and days >20 °C; no-fill leaves amplitude undefined
in 20.9% of placements (reconstruction restores computability); budget
experiment (top-20% risk vs gap length vs random): degree days 39.5% vs
34.4% vs 17.1%, days >25 °C 10.9% vs 2.1% vs 3.6%, risk beats random 1.9–4.0×
except amplitude. (ii) Climatology-fill default (independent agent_a run):
budget reductions are negative for threshold, degree-day, amplitude, and
summer-mean metrics (e.g., exceed_25_days −0.43, amplitude −0.34, combined
mean −0.177 risk / −0.148 gap length) because the top-risk gaps are long
summer gaps where the reconstruction's cold peak bias dominates (signed
errors negative at 90 days: exceed_25_days −0.97 d, degree days −24.5 °C·d).
The section adopts the review's incremental framing: protection is reported
as reduction relative to a named default, and the cost term λC is stated
explicitly as an operational input the paper does not price. Figure 5 plots
both baselines. The no-fill numbers remain the headline (status quo for
downstream users), but every sentence that quotes a protection fraction
names its default.

**Evidence.** `results/revision_v12/t08_downstream_metrics/agent_b/`
(`metric_error_summary.csv`, `budget_comparison.csv`,
`uncomputable_no_fill.csv`, `risk_correlation.csv`) and `agent_a/`
(`metric_error_tables.csv`, `budget_combined.csv`, `budget_comparison.csv`,
`correlation_risk_distortion.csv`). The two runs use different panels
(agent_b 15 networks / 1,755 placements, common-support no-fill design;
agent_a 15 networks / 1,965 placements, climatology-default design); the
reversal the review identified is reproduced in the artifacts and is
reported as a baseline effect, not reconciled away.

**Remaining caveat.** Absolute benefit depends on the untreated baseline and
on the reconstruction's cold peak bias, which no MAE-type risk score
corrects. Protocol v4 fixes the no-fill default as primary and adds the
climatology default as a registered sensitivity; the thermal-metric
endpoint remains a protection floor (≥ −0.02), not superiority.

---

## Major Comment 6 — BiLSTM "self-transfer" is cross-instance transfer; common-panel design required

**Reviewer concern.** The neural row of the model matrix compares a
newly trained three-seed BiLSTM's fitting-period stress against outer losses
of a *different* training instance (the frozen single-seed sensitivity run),
with pairwise correlations only 0.14–0.43 between the neural quantities.
Labeling the diagonal "self-transfer" is wrong; a common-panel design is
required before any within-family transfer claim.

**Action taken in v13.** Relabeling and boundary conditions. Terminology v13
replaces "self-transfer" for the neural row with **cross-instance
transfer**: the compared instances are separately trained BiLSTMs (the
frozen 5-epoch bounded sensitivity run and the new early-stopped three-seed
model) on partly overlapping networks, so the diagonal cell is between
instances of the family, not within-instance replication. The manuscript
states the granularity spread explicitly (self/cross cells span 0.29–0.69
across granularity conventions; neural-vs-block cross cells −0.24 to +0.28;
neural-vs-XGBoost stress Spearman 0.067), and adds the seed-stability
diagnostics (median best epoch 68, 28% of runs hitting the epoch cap vs
92.9% for the frozen run; within-network SD of stress across seeds 0.451 °C,
median CV 0.27; the two neural implementations agree moderately with each
other, 0.503, and not at all with the engineered axis). The matrix moves to
SI with n-annotations per cell (n = 4–12 networks; 8 networks for the
air2stream row). The main-text claim is limited to the engineered-regression
block (self 0.93–0.98, cross 0.72–0.98) and the negative across-family
result; no within-family neural transfer is claimed.

**Evidence.** `results/revision_v12/t05_model_matrix/agent_a/`
(`matrix_network_spearman.csv`, `matrix_n_networks.csv`,
`neural_source_stress.csv`, `neural_histories.csv`,
`diagonal_vs_offdiagonal.json`; MWU diagonal > off-diagonal p = 0.033).
Resolution note: the review's pairwise range 0.14–0.43 lies inside the
spread of neural-vs-block correlations across granularity conventions
(agent_a reports station-gap 0.285–0.328 and network 0.285–0.673 for the
XGBoost-source-vs-BiLSTM-target cell across panels, and −0.24 to +0.28 for
the BiLSTM-source row at network level); all values are far below the
block's 0.72–0.98, so the qualitative conclusion is unchanged under either
number.

**Remaining caveat.** A common-panel neural replication (identical fitting
rosters and evaluation gaps for all families, multiple seeds) is required
for any within-family transfer claim; protocol v4's model roster registers
per-model self-transfer stress curves on identical third-panel gaps, which
is the only design that can certify (or falsify) neural within-family
transfer.

---

## Major Comment 7 — Missingness matrix: two implementations conflict (0.979 vs 0.490); harmonize or demote

**Reviewer concern.** The matched donor-synchronous transfer is 0.979 in one
implementation and 0.490 in the other; the matched-transfer table is not
stable across panel/convention choices and must be harmonized or demoted.

**Action taken in v13.** Demoted to SI with a disclosed harmonization
caveat, per the review's explicit alternative. The main text retains only
the implementation-invariant conclusion: matched mechanism curves transfer
positively, while a uniform-grid curve applied to support-destroying
mechanisms (donor-synchronous, target-plus-primary-covariate, online)
collapses rank and magnitude. The divergent cell is reported in SI with both
values and their causes: agent_a used a 12-network panel
(gkd/lubw/foen/arso/usgs, 87 stations, all-unit convention including
fallback rows) and found donor-synchronous matched network Spearman 0.979
(slope 0.950); agent_b used a different 12-network panel
(chmi/lubw/foen/rws/gkd/usgs, 91 stations, within-horizon supported
convention) and found 0.490 (slope 0.743, bootstrap CI [−0.24, 0.93]). The
panels share only a subset of networks, so the divergence is panel-and-
convention-driven, not a single-code error. The mismatch experiment agrees
across both implementations in direction and magnitude (agent_a:
donor-synchronous 0.979→0.294, target+primary-covariate 0.881→0.196, online
0.930→0.399, under-prediction 1.1–2.3 °C, multi-block slope 0.90→0.14;
agent_b: slope deltas −0.85 for donor-sync and −0.71 for multi-block in the
damaging direction). Harmonization on one 12-network panel with one
convention is a listed pre-submission TODO; until then the SI table prints
both columns and the main text cites only the qualitative result.

**Evidence.** `results/revision_v12/t06_missingness_matrix/agent_a/`
(`mechanism_metrics.csv`, `mismatch_metrics.csv`, `network_panel.csv`) and
`agent_b/` (`mechanism_metrics.csv`, `mechanism_bootstrap_intervals.csv`,
`mismatch_experiment.csv`).

**Remaining caveat.** The matched-transfer point estimates are SI-only until
harmonization; the third panel does not test missingness mechanisms, so the
mechanism-matching conclusion rests on these two 12-network implementations
and on the v11 planted-geometry result, which the SI states.

---

## Major Comment 8 — The surface fixes interpolation, not extrapolation; abstain or obtain real support

**Reviewer concern.** The continuous surface repairs the unsupported
horizons in the interpolation range but fails at the extrapolated 365-day
horizon (rank 0.270, 90% coverage 46.8%), its pure-transfer predictions are
underdispersed (calibration slopes 1.3–2.3), and new-network random effects
are shrunk to zero; the paper must abstain at the extrapolation boundary or
provide real support.

**Action taken in v13.** The surface is reported by regime, and 365-day
abstention is adopted as policy. Results 3.2 and Figure 3 separate the three
regimes explicitly: (i) supported range (direct 874 units; the surface is
not the headline there — the empirical curve is), (ii) interpolation
(448 units at 14/60 days: pooled Spearman 0.774, calibration slope 1.025 —
the surface's genuine contribution), (iii) extrapolation (124 units at 365
days: rank 0.270, 90% coverage 46.8% despite the pre-specified 1.435×
widening). The text states that every second-panel surface prediction is
pure transfer with network/station random effects shrunk to zero (new
levels), that calibration slopes 1.3–2.3 reflect underdispersion and
require external recalibration for absolute use, and that the 365-day
horizon is abstained from point-release use: the abstention row (8.6% of
units carrying 28.9% of total loss; released-unit network Spearman 0.691,
R² 0.663) is now a policy recommendation, not a diagnosis. Protocol v4
formalizes the T3 (extrapolation) exclusion from all primary endpoints.

**Evidence.** `results/revision_v12/t04_risk_surface/agent_a/`
(`evaluation_second_panel.csv`, `abstention_curve.csv`,
`surface_fit_summary.json`): full-panel pooled 0.893, R² 0.475, RMSE 1.096;
fallback-572 network 0.846 / pooled 0.879 / R² 0.381 (vs old fallback 0.597
/ 0.388 / −0.032); interpolated 448 pooled 0.774, slope 1.025; extrapolated
124 rank 0.270, coverage 46.8%; overall 90% coverage 92.5%; abstention row
0.691 / 0.663; first-panel cross-check network 0.898 vs 0.767.

**Remaining caveat.** Real support for 365-day use does not exist in the
current data; the option is closed pending external labels or v4 T3-excluded
confirmation. A width-based abstention rule is counterproductive (13%
abstained, network Spearman falls to 0.489), so the support-based rule is
the only one registered.

---

## Major Comment 9 — The strongest conclusion is an empirical law (persistence), not a superior algorithm; define the Design as a framework

**Reviewer concern.** Once the comparator is fixed to the strongest
baseline, the remaining strong result is not "we built a better screen" but
"recovery difficulty persists": a model's own fitting-period stress orders
its future error. The paper should define the Design as a reusable framework
and state persistence as the empirical law.

**Action taken in v13.** Two structural edits. (i) The Design is defined in
Methods 2.3 as a framework — model-conditional historical stress testing,
a six-stage procedure (cut seasonally stratified gaps inside the fitting
record → recover with the intended model → score → rank → attach support
tiers → abstain or confirm) that any recovery pipeline can be run through;
the three model families, seven missingness mechanisms, and two decision
experiments are presented as instantiations of the framework. (ii) The
primary conclusion is restated as the persistence law, with its evidence
bundled in Results 3.1–3.3: within-network station-horizon ordering
(residualized pooled Spearman 0.936; median within-network Spearman 0.965;
network-mean-only benchmark 0.326) that is stable across rolling-origin
cutoffs (Kendall W 0.811), requires ~4 years of fitting history
(0.608 → 0.944), and is essentially unaffected by the stress model's shorter
training length (paired difference 0.013 °C; Spearman 0.989). The
Conclusions no longer contain "strongest tested screen"; the bound
conditions (model conditionality, support, mechanism matching, abstention)
are presented as the law's scope.

**Evidence.** t01 (`within_network_decomposition.csv`, `beat_fraction.csv`),
t07 (agent_b canonical: `rolling_origin_rank_stability.csv`,
`learning_curve_metrics.csv`, `comparability_summary.csv`), t03 (the
network-difficulty controls r4/r6 that bound the law).

**Remaining caveat.** The law is established for the XGBoost-family recovery
models on 57 outcome-disjoint networks at directly supported horizons; its
scope across architecture families (cross-instance failure), missingness
mechanisms (mismatch failure), and regimes (the Chattahoochee thermal-shift
case) is bounded, and v4 is the external test of the law itself, not only of
a method.

---

## Major Comment 10 — Hydrologic significance should center on downstream outcomes, with multiple baselines

**Reviewer concern.** The paper's significance argument was organized around
MAE ranking and triage; hydrologic significance belongs to downstream
outcomes, and those must be reported against more than one untreated
baseline.

**Action taken in v13.** The downstream section is elevated and re-centered.
Results 3.7 is now the paper's hydrologic-significance section, leading with
what the risk score orders in units that matter (network-level Spearman of
fitting-period risk with distortion of: annual mean 0.764, degree days 0.743,
phase 0.729, 90th percentile 0.668; not amplitude 0.089 or summer maximum
0.250, whose distortion is geometry-governed), and reporting protection
against both baselines as described under Major Comment 5. The decision
section (3.8) now starts from the downstream budget result rather than from
MAE triage, and the triage negative follows as the instrument-level result.
The downstream limitations are stated: 15 networks, one recovery family,
horizons 7/30/90 days.

**Evidence.** t08 agent_a and agent_b (files cited under Major Comment 5).

**Remaining caveat.** Downstream evidence is descriptive of one panel and
one family; the v4 thermal-metric protection floor (≥ −0.02 on
thermal-stress units) is the confirmatory endpoint, and the cold-peak-bias
mechanism (agent_a climatology-default run) must be resolved before any
threshold-metric protection claim is made for long summer gaps.

---

## Writing comments

1. **Title — kept, deliberately.** "Historical block stress tests rank
   future model-specific reconstruction error across stream-temperature
   networks" is retained. Reasons: (i) it describes the framework and the
   empirical law (a curve ranks future error), not an algorithm-superiority
   claim; (ii) the alternative considered ("Historical stress tests guide
   recovery-model selection for stream-temperature outages") overstates the
   coverage-conditional selection result (8.5% released coverage) and would
   re-open Major Comment 4; (iii) "model-specific" preserves the
   conditionality the review demanded; (iv) the title names no comparator,
   so the strongest-baseline re-centering changes no title word.
2. **Abstract** — rewritten under 250 words (word count verified) with the
   corrected evidence priority: strongest-baseline paired Δρ (+0.042, CI
   straddling zero) before any other number; the persistence law as the
   claim; direct-support 0.945/0.805; triage negative (0.338); selection
   result with its 8.5% coverage floor; 365-day abstention; explicit
   statement that no automatic filling or station removal is supported and
   that all revision analyses are development on previously scored panels.
   The +0.55 vs-simple comparison appears only as a secondary contrast.
3. **Key Points** — each rewritten to ≤ 140 characters (verified by length
   check): persistence law with support scope; strongest-baseline
   near-match and within-network location of the ordering; model
   conditionality, support, and mechanism matching as the binding
   constraints on decision use.
4. **Plain Language Summary** — wording fixes: "stress tests" explained as
   cutting artificial gaps into past data; "recovery error" defined as the
   difference between filled and true temperature; "abstention" explained
   as holding back predictions that cannot be trusted; no jargon terms
   ("empirical predictor", "network Spearman") without a parenthetical
   gloss.
5. **Introduction** — five paragraphs, three research questions (unchanged
   structure from v12), with RQ1 reworded to lead with the persistence
   question ("does a fitting-period stress curve rank later recovery loss
   of the same model, and where does the ranking live?") and RQ3 reworded
   to lead with downstream outcomes and multi-baseline protection.
6. **Results reordered** — (1) outcome-disjoint panel, same-unit paired
   comparison vs the strongest baseline; (2) support hierarchy and the
   surface by regime; (3) per-horizon, within-network, and historical
   stability (the persistence law); (4) downstream thermal metrics with two
   baselines; (5) decision utility with coverage floors and the triage
   negative; model and missingness matrices to SI; covariance to SI;
   secondary heterogeneity to SI.
7. **Conclusions** — the phrase "strongest tested screen" is removed; the
   conclusions state the persistence law, its three bound conditions
   (model conditionality; support/mechanism matching; abstention and
   confirmation), and the v4 requirement.

## Figure comments

1. **Figure 1 (design and provenance).** Adds a provenance legend:
   development 55 networks / 1,260 units; first panel 42 / 1,440; second
   panel 57 / 1,446 with provider counts 32 USGS / 15 CHMI / 10 NVE; the v2
   same-commit provenance note; QC-only-reuse disclosure; support-tier
   schematic unchanged.
2. **Figure 2 (same-unit paired validation).** Comparator changed to the
   strongest fitting-record baseline: left panel observed vs predicted on
   the same 874 direct-support units for the empirical curve and the
   station × horizon mean (r6), with equal-network calibration lines and
    per-network medians; right panel paired 2,000-network bootstrap of
    Δρ(empirical − r6) with the +0.041 point and CI [−0.0004, +0.1140]
    (seed 42; seed-0 verification +0.0418 [−0.0006, +0.1154]), annotated
    "positive in 97.0% of bootstrap draws"; the simple-descriptor
    distribution and the full-panel fallback diagnostic appear as clearly
    labeled insets. Sources:
    `results/revision_v13/strongest_baseline/agent_a/` (`summary_metrics.csv`,
    `paired_bootstrap.csv`, `per_horizon_network_spearman.csv`,
    `predictor_correlation.csv`) with t01/t03 cross-checks.
3. **Figure 3 (surface by regime).** The three regimes are drawn as
   separated panels with explicit labels — supported (direct 874),
   interpolated (448 units, slope 1.025), extrapolated (124 units, rank
   0.270, coverage 46.8%) — plus the abstention row (8.6% of units / 28.9%
   of loss; released network Spearman 0.691, R² 0.663) and the fitted
   monotone duration curve. The covariance bound line is removed from the
   main figure (estimand appendix is SI).
4. **Figure 4 (decision: coverage–regret).** Replaces the mixed v12 Figure
   5. Primary panel: network-balanced regret vs fraction of coverage
   released for the proposed selector and all comparators evaluated on the
   same released units, with the 8.5% coverage floor marked and the
   no-abstention null (0.084 vs 0.081) shown at 100% coverage; inset (a)
   CapturedLoss@B budget curves for all policies including the triage
    negative; inset (b) Part-1 abstention coverage-risk curve. Sources:
    `results/revision_v13/decision_harmonization/agent_a/` (`coverage_regret_curve.csv`,
    `comparators_table.csv`) and `t09_decision_utility/agent_a/`
    (`abstention_curve_part2.csv`, `selection_regret_table_part2.csv`,
    `utility_table_part1.csv`).
5. **Figure 5 (downstream, multi-baseline).** New figure: ten thermal
   metrics with distortion of reconstruction relative to *both* untreated
   baselines (no-fill, climatology default), the no-fill uncomputability
   audit (amplitude undefined 20.9%), and the budget experiment plotted
   against both defaults; network-level risk–distortion correlations
   annotated. Sources: `t08_downstream_metrics/agent_b/` and `agent_a/`
   (as listed under Major Comment 5).
6. **Matrices to SI with n-annotations.** The model-source × model-target
   matrix (t05) and the missingness-mechanism matrix (t06) move to SI; every
   cell carries its n (networks) and the missingness table carries both
   implementation columns with the harmonization caveat (Major Comment 7);
   the neural row is labeled cross-instance (Major Comment 6).

## Data and software comments

1. **Archival DOI — still TODO before submission; plan and date gate.**
   No placeholder DOI is cited anywhere. The v13 Open Research section
   retains the mandatory checklist with a date-gated workflow: (i) assemble
   the permitted package (code, analysis configurations, provider request
   metadata, source-QC summaries, derived station-gap losses, figure input
   CSVs); (ii) deposit to Zenodo; (iii) mint the DOI; (iv) insert the minted
   DOI in the manuscript and repository metadata; (v) verify that every
   linked artifact resolves to the deposited version; (vi) only then file
   the submission. The checklist is a submission gate, not a wish list: the
   manuscript text states explicitly that the archival release has not yet
   been created and that submission will not proceed without it.
2. **Protocol v3 → v4 (replacement, `protocol_v4_a.md`).** v4 replaces
   protocol v3's binding primary (paired network-level ΔRho on
   direct-support units vs the simple baseline, observed anchor +0.038, 80%
   power at N = 120) for four reasons, all from the revision: (i) the
   strongest-baseline re-centering (Major Comment 1) changes the correct
   comparator to the station × horizon mean, against which the anchor is
   +0.042 with a CI straddling zero — powering against simple descriptors
   would register a strawman; (ii) the model-selection result is
   coverage-conditional (Major Comment 4), so v4 freezes a coverage floor
   (≥ 8.5% released with per-unit support for all candidate families) and a
   network-balanced regret margin as a primary endpoint, scored only where
   the floor is met; (iii) the 365-day T3 exclusion and the support-based
   abstention rules are formalized (Major Comment 8); (iv) downstream
   endpoints fix the no-fill default as primary with the climatology default
   as a registered sensitivity (Major Comments 5, 10). External
   timestamping is unchanged and mandatory: separate public pre-outcome
   commit (protocol, roster, endpoints, margins, power analysis, no
   outcomes) → OSF/Zenodo registration with DOI → outcome commit
   referencing the DOI; margins frozen before outcomes; amendments require
   a new registration. v4 remains a draft at submission: no v4 outcomes
   exist, and the manuscript says so.

## Mapping of review requirements to v13 deliverables

| Review requirement | v13 deliverable |
| --- | --- |
| MC1: strongest-baseline comparator in abstract/Fig 2 | `manuscript_v13_a.md` §1 (abstract), §3.1; Fig 2; ledger rows S1–S2 |
| MC2: second panel is post-hoc development; provenance labels | §2.10 evidence roles; abstract provenance sentence; Fig 1 legend; `terminology_v13_a.md`; ledger Evidence-role column |
| MC3: triage is loss-targeting utility; negative stands | §3.8; terminology (`CapturedLoss@B`, removal of "end-to-end decision utility"); ledger rows D1–D3 |
| MC4: coverage floors for model selection | §3.8; Fig 4; `protocol_v4_a.md` §4 (coverage floor + regret endpoint); ledger rows D4–D5 |
| MC5: downstream multi-baseline (no-fill vs climatology) | §3.7; Fig 5; SI downstream tables (both defaults); ledger rows F1–F5 |
| MC6: BiLSTM relabeled cross-instance; common-panel required | §3.4 (SI); terminology; SI model matrix with n; `protocol_v4_a.md` §5 (per-model self-transfer on identical gaps); ledger rows M1–M3 |
| MC7: missingness 0.979 vs 0.490 — harmonize or demote | §3.5 → SI; SI missingness matrix with both columns + caveat; TODO list; ledger rows N1–N3 |
| MC8: surface interpolation vs extrapolation; 365 abstention | §3.2; Fig 3; `protocol_v4_a.md` §7 (T3 exclusion); ledger rows U1–U6 |
| MC9: persistence law; Design as framework | §2.3 (framework definition), §3.1–3.3, §5 (conclusions); ledger rows C1–C7 |
| MC10: downstream-centered significance, multiple baselines | §3.7, §3.8 reordered; Fig 5; `protocol_v4_a.md` endpoint (d) floor; ledger rows F1–F5 |
| Writing: title/abstract/key points/plain language/intro/results order/conclusions | `manuscript_v13_a.md` (title kept, abstract <250 words, key points ≤140 chars, 5-paragraph intro, results reordered, conclusions without "strongest screen") |
| Figures: Fig1 provenance; Fig2 strongest baseline; Fig3 regimes; Fig4 coverage–regret; Fig5 multi-baseline; matrices to SI | `figure_plan_v13_a.md` (Figs 1–5; SI displays S6–S7 with n-annotations) |
| Data/software: archival DOI before submission | `manuscript_v13_a.md` Open Research (date-gated checklist; no placeholder DOI) |
| Data/software: protocol v3→v4 | `protocol_v4_a.md` (regret endpoint, coverage floor, T3 abstention, external timestamping) |
