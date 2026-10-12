# Response letter — v13 revision (agent resp_b)

Manuscript: *Historical block stress tests rank future model-specific reconstruction error across stream-temperature networks*
Deliverable pair: this letter + `evidence_ledger_v13_b.md` (sibling: `manuscript_v13_b.md`, `claim_matrix_v13_b.md`, `figure_plan_v13_b.md`, `terminology_v13_b.md`, `protocol_v4_b.md`).
All numbers cited below are artifact-derived; the evidence ledger gives the per-number provenance (v12 task artifact, v13 re-verification, status, evidence role, manuscript location).

## Summary of the revision

The v13 revision restructures the paper around what the evidence actually supports, in response to the ten major comments. Six structural decisions:

1. **The primary comparison is re-centered on the strongest fitting-record baseline** — the station × horizon historical mean of fitting-period MAE (t03 ladder rung r6), which matches the proposed curve's information access and is near-collinear with it (Pearson 0.992 on the direct 874 units). The headline is now a persistence claim — "ranks future loss at least as well as the strongest fitting-record baseline" (pooled 0.945 vs 0.942; network 0.805 vs 0.763; paired network Δρ +0.041, 95% CI [−0.0004, +0.114], positive in 97.0% of bootstrap draws) — not a magnitude-superiority claim against a weak comparator. The numbers were re-verified by an independent v13 analysis agent (`results/revision_v13/strongest_baseline/agent_a/`, REPORT + CSVs; sibling agent_b run pending reconciliation), and the seed-0 run reproduces the v12 paired bootstrap exactly.
2. **The empirical predictor's fixed-budget triage failure is reported as a negative result** (CapturedLoss@20% 0.338 vs 0.512 for simple descriptors; paired −0.174 [−0.198, −0.140]), and the metric is relabeled *loss-targeting utility*, not end-to-end decision utility.
3. **Model selection is reframed with prespecified coverage floors.** The only positive selection result (regret 0.0067) exists at 8.5% coverage (123 units / 8 of 42 networks) on t05-selected networks with in-sample family calibration; v13 states a coverage floor (≥ 50% of units and ≥ 60% of networks) below which no positive decision claim is made, and reports the no-abstention null (0.084 vs 0.081) first.
4. **The missingness matrix and the model matrix are demoted to Supporting Information with harmonization caveats.** Two independent t06 implementations disagree on two matched cells (donor-synchronous 0.979 vs 0.490; uniform 0.531 vs 0.944) and their mismatch-collapse patterns are not symmetric (agent_a's forward collapse is not reproduced by agent_b, which instead shows the reverse collapse), so no matched-strength number is citable as evidence and only the "mechanism mismatch is harmful in at least one direction" and "seasonal bias is the mildest mismatch" statements survive cross-implementation. The BiLSTM row is relabeled *cross-instance transfer* (its "self" cell compares different training instances; unit-level curves are seed-sensitive, pairwise station-gap correlation 0.14–0.43).
5. **Downstream thermal results are reported against both the no-fill status-quo baseline and a climatology-fill baseline**, because the two baselines give opposite signs for threshold/extreme metrics on long summer gaps (cold peak bias of the reconstruction). The incremental benefit is framed as B = D(default) − D(model) − λC, with the default and the cost term stated explicitly.
6. **The 365-day horizon is an abstention boundary, not a prediction** (rank 0.270, 90% coverage 46.8% despite pre-specified widening; released-unit gains 0.691/0.663 only under point-release abstention), the second-panel composition count is corrected (57 = 32 US + 15 CZ + 10 NO; the v12 text's "35 US" was wrong), the paper defines the Design as a framework rather than a champion algorithm, and the confirmation protocol is upgraded to v4 (regret endpoint + coverage floors), because no positive decision claim exists without it.

Evidence roles are attached to every result (frozen pre-outcome / post-hoc v12 development / v13 harmonization / future preregistered); nothing in v13 is described as independent confirmation.

---

## Major Comment 1 — Abstract and Figure 2 comparator choice

**Reviewer concern.** The abstract and Figure 2 compare the empirical stress curve against simple descriptor models, which are not the strongest fitting-record baseline. The station × horizon mean of the network's own fitting-period losses nearly ties the proposed curve (correlation ≈ 0.992) and the paired difference (+0.042) has a confidence interval straddling zero, so the abstract must not imply superiority in magnitude over the strongest possible fitting-record comparator.

**Action taken in v13.** The paper is re-centered on the station × horizon historical mean (r6) as the designated primary comparator:
- Abstract, Key Points, Results 3.1, Figure 2, and the claim matrix (C1) now lead with empirical vs r6 on the same 874 direct units, with the near-collinearity disclosed (Pearson 0.992; Spearman 0.996 — the manuscript states which).
- The paired difference is reported with its true interval and wording: network-level Δρ +0.041 (95% CI [−0.0004, +0.114]), "positive in 97.0% of bootstrap draws" — the wording "CI excludes zero" is removed because the lower bound is marginally negative.
- The vs-simple-descriptors comparison (+0.552 [0.309, 0.814] network; +0.098 [0.059, 0.142] station-gap) is retained as a secondary row in the same table, not the headline.
- Per-horizon r6 values are added (7 d 0.938, 30 d 0.915, 90 d 0.844, 180 d 0.604) so the reader sees the advantage is concentrated at 90–180 d and is negative at 7 d.

**Evidence.** `results/revision_v13/strongest_baseline/agent_a/REPORT.md` (§2, §3, §5; `summary_metrics.csv`, `paired_bootstrap.csv`, `predictor_correlation.csv`): second panel direct 874 — empirical 0.9453/0.8049/0.9383 vs r6 0.9424/0.7632/0.9235; paired network Δρ +0.04123 [−0.00039, +0.11399], P(Δ>0) = 0.9705 (seed 42; seed-0 verification reproduces v12 t01 exactly: +0.04175 [−0.00059, +0.11543]); pooled Δρ +0.00283 [−0.00045, +0.00656]; Pearson correlation 0.9917 (Spearman 0.9959). v12 sources: `t01_paired_comparison/agent_a/`, `t03_baseline_ladder/agent_a/` (r6 row, network ρ 0.763, pooled 0.942).

**Remaining caveat.** At the 95% level the network-level CI straddles zero; r6 ranks above the empirical predictor at 7 d (0.9384 vs 0.9321) and on the full panel at the network level (all 1,446: r6 0.7256 vs empirical 0.7155; first panel likewise). The v13 claim is therefore strictly "at least as well as the strongest fitting-record baseline at directly supported horizons," scoped to direct units and to the model that produced the curve. Certification of even this weaker claim requires the v4 preregistered third panel.

---

## Major Comment 2 — The second panel is not an independent confirmation set

**Reviewer concern.** The second panel was frozen and hash-bound, but its amendment and outcomes entered version control in the same commit, and every v12 revision analysis was post-hoc development on already-scored panels. The paper must not present the second panel or the revision analyses as confirmatory, and provenance must be labeled wherever it matters.

**Action taken in v13.**
- Terminology and methods now attach an explicit **evidence role** to every result: (1) frozen pre-outcome — first-panel analyses and the second panel (internally hash-bound; *not* externally verifiable preregistration); (2) post-hoc v12 development — all revision analyses (paired comparisons, support hierarchy, surface, matrices, rolling origin, downstream, decision experiments); (3) v13 harmonization — re-runs required before a finding is evidence (missingness matrix); (4) future preregistered — protocol v3/v4 outcomes (none exist).
- The words "confirmation" / "independent confirmation" are removed from all result claims; the second panel is described only as an *outcome-disjoint* panel, and the abstract and key points carry no provenance claims.
- Methods (preamble note + §2.11 evidence roles) attaches the roles throughout, and Figure 1's caption gains a provenance legend (panel roles, freeze status, support tiers).
- The Open Research section states that only a third panel under protocol v4, with separate pre-outcome commit and external registration, would be externally verifiable confirmation.

**Evidence.** v12 manuscript §2.10 already disclosed the same-commit flaw; v13 formalizes it as the four-class evidence-role scheme (`terminology_v13_b.md`, `claim_matrix_v13_b.md` header). No abstract sentence in v13 mentions amendment, hash-binding, or registration status.

**Remaining caveat.** All quantitative results in v13 remain development-grade evidence on two panels; nothing can certify them except the preregistered third panel. The third panel is planned (protocol v4, 80–120 outcome-disjoint networks) but does not exist.

---

## Major Comment 3 — CapturedLoss is loss-targeting utility, not end-to-end decision utility; the triage failure is a negative result

**Reviewer concern.** The Part-1 "decision utility" experiment measures what fraction of total observed loss falls into a budget-selected top set (CapturedLoss@B) — a loss-targeting utility, not an end-to-end evaluation of a management decision. And the result is negative: the frozen empirical predictor is the worst non-random triage policy (0.338 vs 0.512 at a 20% budget). This must be reported as a negative result, not folded into a positive decision story.

**Action taken in v13.**
- The metric is relabeled **loss-targeting utility** and the section is re-scoped accordingly (terminology: `loss-targeting utility` vs `end-to-end decision utility`, which is the three-part structure of triage + selection + downstream protection with coverage, abstention, and named baselines).
- Results 3.4 reports the triage result as a **strong negative**, first in its section and with the structural mechanism: the network-mean fallback (572 units, including all 124 365-day units) under-ranks the largest losses (mean prediction 1.33 °C vs observed 5.27 °C at 365 d), and the 365-day tail carries 28.9% of total loss.
- No sentence anywhere recommends the empirical predictor for triage; the claim matrix (C3a) allows only: "the frozen empirical predictor is the worst non-random fixed-budget triage policy on the full panel."

**Evidence.** `t09_decision_utility/agent_a/REPORT.md` and `agent_b/REPORT.md` (both agents agree): CapturedLoss@20% — simple 0.512 [0.485, 0.537], duration+season 0.504, surface 0.500, gap length 0.498, empirical 0.338 [0.302, 0.380], random 0.200, oracle 0.529; NDCG@20% simple 0.908 vs empirical 0.617; paired empirical − simple −0.174 [−0.198, −0.140] (agent_b: −0.1755 [−0.2008, −0.1431]); surface − simple −0.012 [−0.031, +0.003]; worst-decile recall@20% empirical 0.398 vs simple 0.842.

**Remaining caveat.** The negative triage result itself is panel-specific (one panel, one model roster, no cost structure). The v4 protocol registers a regret endpoint on a third panel so that a triage claim (positive or negative) can be made under external preregistration; until then the negative is a development-grade result.

---

## Major Comment 4 — Model-selection positive is only at 8.5% coverage; coverage floors required

**Reviewer concern.** The model-selection abstention result (regret 0.0067) applies to 123 units in 8 of 42 networks — 8.5% coverage, on networks t05 selected (not a random sample), with in-sample calibration for two families and comparators re-evaluated only on the released set. Four reasons (coverage, non-random subset, in-sample calibration, no external validation) make it not operational evidence; the paper must impose coverage floors before any positive claim.

**Action taken in v13.**
- v13 defines a **coverage floor** (≥ 50% of units and ≥ 60% of networks released) and states that **no positive decision claim exists in v13**: the 8.5% result is below the floor by construction.
- The no-abstention null is reported first: regret 0.084 (proposed) vs 0.081 (best fixed / global blocked-CV), paired difference +0.0037 [−0.0255, +0.0330]; per-network average-CV (0.038) beats the proposed selector without abstention and is disclosed as in-sample by design.
- The abstention result is labeled a **proof of concept on networks with full per-unit fitting-period evidence**, with all four reviewer reasons itemized in the limitations: (i) 8.5% coverage; (ii) released set confined to the 8 t05 networks (not a random sample); (iii) family-2/3 recalibration in-sample on 8 networks (slopes ≈ 1.02/1.04; a common-scale robustness run reproduces every headline number, so the calibration leakage does not drive the result); (iv) no external validation.
- Comparators are reported on the same released units (fair coverage view), and the coverage–regret curve (abstention threshold × support rule) is the reporting convention (Figure 4).
- Protocol v4 adds the coverage floors and a *deployable nested-CV selector* definition (family choice and coverage both chosen by nested CV on fitting-period data, abstention rule and floor fixed before deployment) as prerequisites for any future positive claim.

**Evidence.** `t09_decision_utility/agent_a/REPORT.md` Part 2: released set 123 units / 8 networks / 8.5% of the panel (91.5% abstained); regret 0.0067 [0.0019, 0.0120] vs same-unit comparators — best fixed 0.151, global CV 0.151, per-network CV 0.164, gap rule 0.145, random 0.341; no-abstention 0.084 vs 0.081; ambiguity-only abstention does not help (near-ties are cheap: regret rises to 0.0998 at 31.6% abstained); the support rule is the sharp lever.

**Remaining caveat.** Nothing in the read-only artifacts can extend family-specific stress beyond the 8 t05 networks, so the 8.5% ceiling is not an artifact of the abstention rule — it is the actual coverage of per-unit, all-candidate fitting-period evidence in the first panel. Reaching the coverage floor requires either more networks with full per-family stress (v4 panel) or a different evidence design (e.g., the shared-difficulty block mapping, which is a proxy, not unit-level support).

---

## Major Comment 5 — Downstream thermal conclusions depend on the untreated baseline

**Reviewer concern.** The downstream protection numbers (recon/no-fill 12–14%, 30–37%; budget reductions 39.5% etc.) are computed against a no-fill default. An independent run with a climatology-fill default found negative budget reductions on threshold metrics (the reconstruction is colder than climatology on long summer gaps). The conclusions therefore depend on the choice of untreated baseline, and an incremental-benefit framing (B = D(default) − D(model) − λC) is required.

**Action taken in v13.**
- The downstream design now specifies **three untreated defaults** — no-fill (drop gap days), climatology (day-of-year fill), and linear boundary interpolation — with two of them implemented (no-fill and climatology, in two independent implementations A and B whose panels differ and are reported side by side, never pooled).
- Results 3.5 (downstream) reports **both implemented baselines** side by side for the same ten metrics and the same budget experiment: the no-fill status-quo baseline (implementation B, canonical) and a climatology-fill no-recovery baseline (implementation A; implementation B's own climatology comparison agrees).
- The sign flip is explained mechanistically: top-risk gaps are the long summer gaps, where the reconstruction's cold peak bias (negative signed errors at the seasonal peak; e.g., exceed-20-days mean signed error −3.29 d at 90-d gaps) flips threshold crossings that climatology filling had already removed.
- All downstream claims are stated with their baseline: "reconstruction reduces distortion versus no-fill for integrated metrics (12–14% of no-fill error) and restores computability"; "against a climatology-fill no-recovery baseline, a risk-targeted budget is worse for threshold and extreme metrics (days >25 °C −42.5%)".
- The incremental benefit is framed as **B = D(default) − D(model) − λC** (terminology: `incremental benefit`), where D is the decision loss (metric distortion, captured-loss deficit, or selection regret), `default` is the named baseline, and C is the abstention/coverage cost scaled by λ. v13 reports D and C and leaves λ to the application; a benefit without a named default and an explicit cost term is not reported.

**Evidence.** No-fill baseline — `t08_downstream_metrics/agent_b/REPORT.md` (15 networks, 1,755 placements, 351 station-gaps): recon/no-fill error ratio 0.12 (annual mean), 0.14 (degree days), 0.13 (trend slope), 0.30 (p90), 0.34 (days >20 °C), 0.82 (days >25 °C), 0.84 (summer max); zero reconstruction error in 88–95% of placements for single-event metrics; no-fill leaves amplitude undefined in 20.9% of placements (367/1,755); risk–distortion network Spearman: annual mean 0.764, degree days 0.743, phase 0.729, p90 0.668, amplitude 0.089, summer max 0.250; budget top-20%: degree days 39.5% (risk) vs 34.4% (length) vs 17.1% (random). Climatology baseline — `t08_downstream_metrics/agent_a/REPORT.md` (15 networks, 1,965 placements): combined reduction −0.177 (risk), −0.148 (length), +0.026 (random); degree days −17.9%, days >20 °C −22.2%, days >25 °C −42.5%, amplitude −33.8%, summer mean −23.0%; annual mean still +2.2%. Implementation B's own climatology comparison agrees (agent_b `metric_error_summary.csv`): mean reconstruction error ≈ climatology for annual mean (0.093 vs 0.105 °C), degree days (21.7 vs 23.5 °C·d), and days >20 °C (2.23 vs 2.24 d), and worse for days >25 °C (0.516 vs 0.411 d) and summer maximum (0.124 vs 0.096 °C).

**Remaining caveat.** The budget experiment is a per-placement budget on 15 first-panel networks with one recovery family (XGBoost); the networks are the 15 with the most scored gaps, not a random sample. The cost term λC is not empirically estimated — no cost data exist — so the formula is the required framing, with λ to be supplied by the application or registered in v4.

---

## Major Comment 6 — The BiLSTM "self-transfer" cell is cross-instance transfer; common-panel design required

**Reviewer concern.** The BiLSTM "self-transfer" is not same-instance transfer in the engineered-block sense: the fitting-period stress curves and the outer losses come from different training instances (different runs/splits), and unit-level curves are seed-sensitive (pairwise station-gap correlation 0.14–0.43 across seeds). "Self-transfer" overclaims, and any architecture comparison requires a common-panel design (same networks, same splits, seed-averaged).

**Action taken in v13.**
- All BiLSTM-row language is relabeled **cross-instance transfer** (terminology v13: "the BiLSTM 'self' cell is cross-instance, not same-instance; do not write 'BiLSTM self-transfer'"). The matrix is demoted to SI with the relabel and per-cell n-annotations (12 networks for the neural row, 8 for the air2stream row, 3 seeds, 36 runs).
- The seed-stability evidence is reported alongside the row: network-level seed ranks are stable (0.82–0.87) but unit-level curves are seed-sensitive (pairwise station-gap 0.14–0.43); the row is therefore presented as a family-level qualitative divergence, not a precise cell estimate.
- The main text keeps only the architecture-family conclusion that is robust to the instance problem: difficulty ordering is shared within the engineered-regression block (self 0.91–0.98, cross 0.72–0.98) and pipeline-specific across architecture families, with the neural-vs-XGBoost stress disagreement (0.067) as the cleanest single number.
- Protocol v4 requires a **common-panel design** (same networks, same splits, seed-averaged stress for every candidate family) for any future architecture comparison.

**Evidence.** `t05_model_matrix/agent_a/REPORT.md`: BiLSTM row network Spearman 0.140/0.042/−0.200/−0.021 (to block) and 0.364 (to frozen BiLSTM target); "self" 0.29–0.69 across granularity conventions; neural stress vs XGBoost stress 0.067; diagonal vs off-diagonal one-sided MWU p = 0.033 (gap driven entirely by the neural and process rows); median best epoch 68, 28% epoch-cap vs 92.9% for the old bounded run. `t05_model_matrix/agent_b/REPORT.md`: seed stability — network Spearman 0.82–0.87 vs seed average; pairwise seed curves at station-gap level 0.14–0.43.

**Remaining caveat.** The two agents' granularity conventions differ (agent_a 0.29–0.69 "self" span covers both runs); the frozen BiLSTM target came from a single-seed, 5-epoch run that did not converge; and the matrix's neural row rests on 12 networks. A fully common-panel neural row requires the v4 panel.

---

## Major Comment 7 — Missingness matrix: two implementations conflict; harmonize or demote

**Reviewer concern.** The two independent t06 implementations disagree on a headline cell: matched donor-synchronous transfer is 0.979 (agent_a) vs 0.490 (agent_b), on different 12-network panels and with different mechanism definitions. The matrix cannot support a main-text matched-strength claim until harmonized.

**Action taken in v13.**
- The missingness matrix is **demoted to Supporting Information** with an explicit **harmonization caveat** (terminology: `missingness harmonization`): the independent implementations used different 12-network panels (only a small overlap) and different mechanism definitions, and they conflict on two matched cells — donor-synchronous 0.979 (agent_a) vs 0.490 (agent_b), and uniform 0.531 (agent_a) vs 0.944 (agent_b).
- The main text retains only what survives both implementations: (i) the matrix itself is unresolved and **no matched-transfer value from either implementation may be cited as evidence**; (ii) mechanism mismatch is harmful in at least one direction within each implementation, but the specific collapse pattern is implementation-dependent — agent_a's forward collapse (uniform curve on donor-synchronous gaps: 0.979→0.294) is *not* reproduced by agent_b (0.490→0.524), while agent_b shows the reverse collapse (donor-synchronous curve on uniform gaps: 0.944→0.098, Δρ −0.846) that agent_a does not report; (iii) the seasonal-placement-bias direction is the mildest mismatch in both implementations and is the only qualitatively consistent finding.
- Harmonization on one unified 12-network panel with one scoring convention is listed as a required v13 action (TODO) before the matrix can return to the main text.

**Evidence.** `t06_missingness_matrix/agent_a/REPORT.md` + `mechanism_metrics.csv`, `mismatch_metrics.csv` (matched: multi-block 0.944, donor-sync 0.979, forcing 0.881, online 0.930, uniform 0.531–0.622, summer 0.594, heat 0.580; slopes 0.89–1.01; forward mismatch collapses 0.979→0.294, 0.881→0.196, 0.930→0.399; under-prediction 1.1–2.3 °C; multi-block slope 0.90→0.14) and `t06_missingness_matrix/agent_b/REPORT.md` + `mechanism_metrics.csv`, `mismatch_experiment.csv` (matched: uniform 0.944, multi-block 0.888, summer 0.909, heat 0.958, donor-sync 0.490 with slope 0.743, forcing 0.937, online 0.965; forward uniform-on-donor-sync 0.490→0.524 no collapse; reverse donor-sync-on-uniform 0.944→0.098). Both agents' validation checks reproduce the reference pipeline on their own panels (agent_b mechanism (a) 0.944 vs paper 0.922 on its subset; unit correlation 0.996).

**Remaining caveat.** The divergence is unresolved — the v13 decision is demotion, not harmonization, and the two implementations also conflict on the matched uniform cell (0.531 vs 0.944). Even the directional mismatch evidence is not symmetric across implementations; only the "mechanism mismatch is harmful in at least one direction" and "seasonal bias is the mildest mismatch" statements can currently be made with cross-implementation confidence. Matched-strength claims remain gated on the harmonized re-run, which no artifact currently supports.

---

## Major Comment 8 — The continuous surface fixes interpolation, not extrapolation; 365-day abstention or real support

**Reviewer concern.** The surface's gains are in the interpolation range; at the extrapolated 365-day horizon rank is 0.270 with 90% interval coverage of 46.8% despite the pre-specified widening; pure-transfer predictions are underdispersed (calibration slopes 1.3–2.3); and second-panel predictions are pure transfer with new-network random effects shrunk to zero. The paper must either abstain from extrapolation or demonstrate real support at that horizon.

**Action taken in v13.**
- The surface is renamed **interpolation-capable support-aware risk surface** (the name carries the boundary), and Results 3.2 and Figure 3 separate the three regimes: direct support (7/30/90/180 d), interpolation (14/60 d, 448 units: pooled Spearman 0.774, slope 1.025, coverage 98.2%), extrapolation (365 d, 124 units: rank 0.270, coverage 46.8%).
- **Extrapolation abstention is the default operational posture** (terminology: `extrapolation abstention`): the 124 extrapolated units are withheld from point release (8.6% of units carrying 28.9% of total loss); abstention raises released-unit network Spearman to 0.691 and R² to 0.663. Abstention is justified for point release, explicitly not for loss-capturing budgets, and no loss-capture claim covers the extrapolated tail.
- The methods section discloses that all second-panel predictions are pure transfer of the shared surface (network/station random effects shrunk to zero for new networks) and that pure-transfer calibration is underdispersed (slopes 1.3–2.3), requiring external recalibration before absolute use; the 1.435× widening is reported as insufficient.
- The claim matrix (C2a) allows only: "the surface interpolates at 14/60 d"; "365-day extrapolation fails and is unsupported unless real fitting-period support exists at that horizon"; never "full-horizon risk estimator" or "predicts at any gap duration".

**Evidence.** `t04_risk_surface/agent_a/REPORT.md` + `evaluation_second_panel.csv`, `abstention_curve.csv`: full panel pooled 0.893, R² 0.475, RMSE 1.096; fallback 572 units network 0.846 / pooled 0.879 / R² 0.381 (vs old 0.597/0.388/−0.032); interpolated 448 units pooled 0.774, slope 1.025; extrapolated 124 units rank 0.270, coverage 46.8%; overall 90% coverage 92.5% (direct 96.0%, interpolated 98.2%); abstention → network 0.691, R² 0.663, RMSE 0.535; observed 365-d losses run to 9.4 °C vs predicted 2.36 °C.

**Remaining caveat.** Abstention removes the 365-day tail from point release but not from the loss budget: those units carry 28.9% of total loss and are exactly the units any triage application would most want to rank. Resolving the extrapolation problem requires external labels for recalibration or real fitting-period support at 365 days on the v4 panel; v13 does not claim either.

---

## Major Comment 9 — The strongest conclusion is an empirical law (persistence), not a superior new algorithm; define the Design as a framework

**Reviewer concern.** The paper's strongest, most defensible result is that historical block stress tests rank a recovery model's future error — a persistence/empirical-law claim about model-specific error structure — not that the specific empirical-transfer algorithm beats competitors. The Design should be defined as a framework, with the algorithm as one instantiation.

**Action taken in v13.**
- Section 1 (Introduction ¶4) now defines **the Design as the framework**: (i) cut seasonally stratified trial gaps wholly inside the fitting record of the intended recovery model; (ii) score the model's error on them; (iii) rank future gaps from the resulting curve; (iv) tag every prediction with its support tier; (v) abstain where support or calibration fails. The empirical-transfer curve is presented as the Design's primary instantiation and the surface as a second instantiation (smooth, interpolation-capable).
- The headline is restated as the **persistence of local recovery difficulty** (terminology v13): "the fitting-period stress curve ranks future loss at directly supported horizons at least as well as the strongest fitting-record baseline" — a law-style statement about the difficulty structure, not a claim that any algorithm is the best screen.
- The conclusion no longer contains "strongest screen" or any superiority phrasing; the claim matrix (C1) allows only the "at least as well as" formulation and explicitly forbids "uniquely superior in magnitude", "beats all baselines", "large gains from seasonal stratification".
- The near-collinearity with r6 (Pearson 0.992) is presented as *support for* the law-style reading: the empirical curve is the station × horizon mean plus season stratification, and the informative content is the shared fitting-record information, not the specific algorithm.

**Evidence.** `results/revision_v13/strongest_baseline/agent_a/REPORT.md` §5 (correlations), §7 (recommended manuscript framing); `claim_matrix_v13_b.md` C1 (allowed language); `terminology_v13_b.md` (`persistence of local recovery difficulty`).

**Remaining caveat.** The persistence law is established on two panels only (development-grade), and v13 does not claim to explain *why* difficulty persists beyond the descriptive mechanisms (support, season, donor structure, model family). The v4 panel is the required external test of the law itself.

---

## Major Comment 10 — Hydrologic significance should center on downstream outcomes, with multiple baselines

**Reviewer concern.** The hydrologic/ecological significance of the work lies in downstream outcomes — the protection (or distortion) of thermal-regime metrics that managers care about — not in ranking diagnostics. The downstream results must be reported with multiple baselines and honest limits.

**Action taken in v13.**
- Downstream thermal metrics are elevated in the v13 reporting order (Results 3.5, ahead of the model/missingness boundary sections, which move to SI) and in the Plain Language Summary and abstract, where the significance statement is about downstream regime metrics, computability restoration, and the baseline dependence of protection.
- Two baselines are reported throughout (no-fill status quo and climatology fill — see MC5), with the risk–distortion correlations at the network level (n = 15), the budget experiment for both baselines, and the explicit statement that single-event metrics (amplitude, summer maximum) are geometry-governed and not ordered by MAE-type risk scores.
- Figure 5 is the downstream multi-baseline figure (three-baseline forest of per-metric incremental benefit, with n-annotations).
- The claim matrix (C3c) requires every downstream sentence to name its baseline.

**Evidence.** See MC5 evidence block (agent_b no-fill + agent_a climatology numbers, both `t08_downstream_metrics/`).

**Remaining caveat.** Fifteen first-panel networks, one recovery family (XGBoost), horizons 7/30/90 d, five placements per station-gap; the network sample is not randomized; threshold-extreme metrics on long summer gaps remain hard for any MAE-type score, and the cost term in the incremental-benefit framing is unestimated.

---

## Writing comments

1. **Title kept.** *Historical block stress tests rank future model-specific reconstruction error across stream-temperature networks* is retained. Rationale: (i) it names the object being tested (model-specific reconstruction error) and the operation (ranking), not an algorithm and not a superiority claim — it is compatible with the law-style framing demanded by MC9; (ii) it is descriptive of the Design as a framework; (iii) the alternative recorded post-decision ("Historical stress tests guide recovery-model selection for stream-temperature outages") makes an operational promise the evidence cannot yet keep at prespecified coverage (MC4). Only one title may be submitted; if the editor prefers the operational title after v4 outcomes exist, it is documented in the v12 REPORT as the fallback.
2. **Abstract <250 words with corrected evidence priority.** The v13 abstract leads with the persistence claim vs the strongest fitting-record baseline (pooled 0.945 vs 0.942; network 0.805 vs 0.763; paired network Δρ +0.041, CI [−0.0004, +0.114], positive in 97.0% of draws), then support boundaries (0.887 exact tier; fallback 0.562; 365-d abstention), the triage negative (0.338 vs 0.512), the selection proof-of-concept at 8.5% coverage, and the downstream baseline dependence — in that priority order. Word count target: <250 (v12 was over).
3. **Key Points ≤140 characters each.** Rewritten to length limits; the first key point states the re-centered comparison and the corrected panel composition (57 networks: 32 US, 15 Czech, 10 Norwegian); the second states support boundaries; the third states conditionality and abstention. Each ≤140 chars.
4. **Plain Language Summary wording fixes.** "Stress test" (not "screen"), "recovery model" (not "algorithm"), "outcome-disjoint networks" (not "confirmation"), and no sentence implying automatic filling or removal. The summary states both what the results support (screening before a gap occurs, with support checks) and what they do not (automatic filling/removal, 365-day prediction, generic curves).
5. **Introduction: 5 paragraphs, 3 research questions.** The structure is retained; ¶4 now defines the Design as the framework with its instantiations (MC9); the three RQs are re-scoped: (1) does the fitting-period curve rank future loss at directly supported horizons at least as well as the strongest fitting-record baseline, and where does the ranking live; (2) how is the ordering bounded (duration, model family, missingness, environment); (3) what is the decision value at prespecified coverage, and what would certify it (protocol v4).
6. **Results reordered.** v13 order: 3.1 strongest-baseline paired comparison; 3.2 support hierarchy and duration (surface, interpolation, extrapolation boundary); 3.3 within-network and per-horizon stability (rolling origin/history to SI); 3.4 decision experiments (triage negative; selection null + proof of concept with coverage floor); 3.5 downstream (both baselines); 3.6 model-family boundaries; 3.7 missingness (directional + harmonization caveat); covariance mechanism to SI.
7. **Conclusion no longer "strongest screen".** Rewritten per MC9: the conclusion states the persistence finding with its three conditions (model conditionality; explicit support; prespecified coverage and baseline for decisions) and the v4 requirement. The phrase "strongest tested screen" is gone.

## Figure comments

1. **Figure 1 (design + provenance legend).** Adds: panel composition (development 55 networks/1,260 units; first 42/1,440; second 57/1,446 with 32 US + 15 CZ + 10 NO), the evidence-role legend (frozen pre-outcome vs post-hoc development), and the support-tier ladder with the interpolation (14/60 d) and extrapolation (365 d) regions flagged.
2. **Figure 2 (strongest-baseline comparator).** 2×2 grid on the same 874 direct units (57 networks): (A) empirical vs the station × horizon mean (r6) — predicted vs observed with equal-network calibration lines, pooled 0.945 vs 0.942, network 0.805 vs 0.763, slopes 0.938 vs 0.924, near-collinearity annotated (Spearman correlation 0.996; Pearson 0.992); (B) empirical vs simple descriptors (the demoted v12 headline, pooled 0.945 vs 0.846, network 0.805 vs 0.248); (C) paired-network-bootstrap Δρ forest against both baselines — vs r6: +0.041 [−0.000, +0.114] (network, win 0.971) and +0.003 [−0.000, +0.007] (pooled); vs simple: +0.552 [+0.309, +0.814] and +0.098 [+0.059, +0.142], with the full-panel fallback-artifact rows inset (+0.109 [−0.126, +0.356]; −0.097 [−0.158, −0.028]; vs r6 −0.011 [−0.036, +0.008]); (D) within-network distribution (empirical median 0.965 vs r6 0.968 vs simple 0.937; network-demeaned 0.936/0.930/0.896) with the network-mean-only benchmark (0.326).
3. **Figure 3 (supported / interpolated / extrapolated separation).** Three stacked panels: (A) predicted vs observed loss by duration with the three regimes visually separated (direct 7/30/90/180 d; interpolated 14/60 d in amber; extrapolated 365 d in red hatching) and the realized-MAE series vs the saturating expected-Gaussian-MAE bound (0.379–0.451 °C) overlaid; (B) 90% interval coverage by region (overall 92.5%, direct 96.0%, interpolated 98.2%, extrapolated 46.8% — annotated that the pre-specified 1.435× widening does not rescue the tail); (C) the abstention boundary (extrapolated-flag rule): 124 units = 8.6% of units carrying 28.9% of total loss, released-unit network Spearman 0.691, R² 0.663.
4. **Figure 4 (model-selection coverage–regret; replaces the mixed Figure 5 of v12).** Single coverage–regret panel: coverage (fraction of units released, 0–100%) on the x-axis against network-balanced regret, one line per selector (proposed, best fixed, global CV, per-network CV, gap rule, random, oracle), with the two verified endpoints — full coverage: proposed 0.084 vs best fixed 0.081 vs per-network CV 0.038; 8.5% coverage (123 units, 8 networks): proposed 0.0067 [0.0019, 0.0120] vs comparators 0.151/0.151/0.164/0.145/0.341 — connected by the v13 harmonization threshold sweeps (`results/revision_v13/decision_harmonization/...`). Protocol-v4 coverage floors (≥50% units / ≥60% networks) and the 70% target are drawn as vertical lines, and the current 8.5% operating point is marked "below the floor". The fixed-budget triage negative (CapturedLoss@20% 0.338 vs 0.512; diff −0.174 [−0.198, −0.140]) is stated in the caption; the Part-1 budget curves and abstention coverage-risk curves are reported in the text and SI rather than crowding this panel.
5. **Figure 5 (downstream incremental benefit vs untreated baselines).** Three forest panels, one per baseline — no-fill, climatology, interpolation — plotting per-metric incremental benefit B = D(baseline) − D(model) in each metric's units, with sign-reversal points drawn red: under no-fill all ten metrics are positive (fixed-model B e.g. +0.660 °C annual mean, +136.0 °C·d degree days, +0.577 °C/yr trend; risk-selected reductions 0.095–0.395), while under climatology summer maximum (−0.029 °C) and days >25 °C (−0.105 d) reverse and p90/days >20 °C are near zero. n-annotations (351 placements, 15 networks; amplitude 342; 270 treatable/54 treated for the risk-selected rows) and the computability annotation (amplitude undefined under no-fill in 20.9% of placements). The interpolation-baseline rows are the v13 harmonization deliverable.
6. **Matrices to SI with n-annotations.** The model-source × model-target matrix (t05) and the missingness-mechanism matrix (t06) move to SI, each cell annotated with n-networks (4–8 networks flagged fragile), seed counts for the neural row, implementation identity for the missingness cells, and the harmonization caveat (0.979 vs 0.490).

## Data and software comments

1. **Archival DOI — still TODO before submission; plan and date-gated workflow.** The archival release has not been minted. Plan: (i) the permitted package (code, configs, provider request metadata, QC summaries, derived station-gap losses, figure inputs) is already organized for deposit — `.zenodo.json` and `CITATION.cff` exist at the repository root; (ii) before submission, the authors deposit the permitted package in a persistent repository (Zenodo, per `.zenodo.json`), mint the DOI, insert it in the manuscript Open Research section and in the repository metadata, and verify that every linked artifact resolves to the deposited version; (iii) no placeholder DOI is cited. The workflow is **date-gated**: the Open Research section states that submission is conditional on completing the deposit step; each revision package (this v13 package included) documents that its artifact links are relative to the future deposit. This item is tracked as the open TODO in the v12 REPORT and remains open in v13; no analysis number depends on it.
2. **Protocol v3 → v4 replacement.** Protocol v3's binding primary endpoint was paired network-level ΔRho on direct-support units (observed +0.038; 80% power at N = 120), with captured-loss, NDCG@5%, and a thermal floor as additional endpoints. v13 replaces v3 with **protocol v4** because the review's MC3/MC4 require decision endpoints to be primary: v4 keeps the external-timestamping machinery (separate pre-outcome commit, OSF/Zenodo registration, margins frozen before outcomes) and makes the primary endpoint a **regret-based selection endpoint with prespecified coverage floors** (≥ 50% of units, ≥ 60% of networks), plus abstention rules and costs, coverage–regret curves, incremental-benefit endpoints B = D(default) − D(model) − λC with named baselines, and the deployable nested-CV selector definition. The v3 Δρ-replication endpoint is retained as a secondary ranking endpoint (it remains the law-test); full-panel superiority over any baseline is explicitly not claimed (observed full-panel Δρ vs r6 is negative: −0.011 on 1,446 units). Protocol v4 is drafted as `protocol_v4_b.md`; no v4 outcomes exist.

## Requirement → deliverable mapping

| Review requirement | v13 deliverable | Location |
| --- | --- | --- |
| MC1: strongest-baseline comparator (station × horizon mean; Δρ +0.042 CI straddling 0; corr 0.992) | Re-centered primary comparison; "positive in 97.0% of draws" wording; per-horizon r6 table | Abstract; Key Points; Results 3.1; Fig 2; claim matrix C1; `results/revision_v13/strongest_baseline/agent_a/` |
| MC2: second panel not independent confirmation; provenance labels | Four-class evidence-role scheme; "outcome-disjoint" only; Fig 1 provenance legend; Methods preamble + §2.11 | Methods §2.11; Fig 1; terminology (`evidence roles`); Open Research |
| MC3: CapturedLoss = loss-targeting utility; triage negative (0.338 vs 0.512) | Relabel; strong-negative triage section with structural mechanism | Results 3.4a; terminology (`loss-targeting utility`); claim matrix C3a |
| MC4: selection only at 8.5% coverage; coverage floors | Coverage floor (≥50% units / ≥60% networks); no positive decision claim; null reported first; proof-of-concept label | Results 3.4b; terminology (`coverage floor`); claim matrix C3b/C3d; protocol v4 |
| MC5: downstream depends on baseline; B = D(default) − D(model) − λC | Both-baseline reporting; incremental-benefit framing with explicit default and cost | Results 3.5; Fig 5; terminology (`incremental benefit`); claim matrix C3c |
| MC6: BiLSTM self-transfer is cross-instance (pairwise corr 0.14–0.43) | Relabel to cross-instance transfer; seed-stability disclosure; matrix to SI with n-annotations; common-panel requirement in v4 | Results 3.6; SI S2; terminology (`cross-instance transfer`); protocol v4 |
| MC7: missingness implementations conflict (0.979 vs 0.490) | Matrix demoted to SI; harmonization caveat (two conflicting matched cells: donor-sync 0.979/0.490, uniform 0.531/0.944); no matched value citable; only cross-implementation statements retained | Results 3.7; SI S3; terminology (`missingness harmonization`); claim matrix C2c |
| MC8: surface fixes interpolation not extrapolation (365: 0.270/46.8%; slopes 1.3–2.3; RE shrunk to 0) | Renamed "interpolation-capable"; extrapolation abstention default; regimes separated in Fig 3; pure-transfer disclosure | Results 3.2; Methods 2.4; Fig 3; terminology (`extrapolation abstention`); claim matrix C2a |
| MC9: strongest conclusion is an empirical law; Design as framework | Design-as-framework definition; persistence-of-difficulty headline; no "strongest screen" | Intro ¶4; Conclusions; claim matrix C1; terminology (`persistence of local recovery difficulty`) |
| MC10: significance centered on downstream outcomes, multiple baselines | Downstream elevated in results order/PL summary/abstract; dual baselines; n-annotations | Results 3.5; Fig 5; Plain Language Summary; claim matrix C3c |
| Writing: title/abstract/key points/PL/intro/results order/conclusion | Title kept with rationale; abstract <250 words re-prioritized; key points ≤140 chars; PL fixes; 5-¶/3-RQ intro; results reordered; conclusion rewritten | Front matter; §1; §3; §5 |
| Figures | Fig 1 provenance legend; Fig 2 strongest-baseline; Fig 3 regime separation; Fig 4 coverage–regret; Fig 5 downstream multi-baseline; matrices to SI with n-annotations | `figure_plan_v13_b.md` |
| Data/software | Archival DOI plan with date-gated workflow (TODO, pre-submission); protocol v3 → v4 replacement | Open Research; `protocol_v4_b.md` |

## Open items carried into v13 (see also evidence ledger TODO rows)

- Archival DOI (mandatory before submission; date-gated deposit workflow defined).
- t10 RMSE transcription (0.631 in the canonical CSV vs 0.694 in one interpretation note; 0.631 used, pending confirmation against the published column).
- t07 convention divergence (canonical subset-20 values used; agent_a's independent run agrees qualitatively).
- t06 harmonization (matrix demoted; harmonized re-run required before any revival).
- Figure renderings from the listed source CSVs; length check (trim Methods/SI if the journal limit binds).
