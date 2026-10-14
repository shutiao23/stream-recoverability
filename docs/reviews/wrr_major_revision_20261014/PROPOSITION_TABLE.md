# WRR Major Revision — research proposition table

**Locked review commit:** `53c88cc2f56359859b4beb36456ee024434b87c1` (2026-10-14)  
**Verdict driving this plan:** Major revision (not accept; not strong accept)  
**Primary metric:** hottest continuous 30-day mean (°C)  
**Primary operating point (predeclared, do not retune after test):** 70% retention, 0.5 °C consequential-error tolerance  
**Candidate management target (predeclared before Step-2 test look):** at false-admit rate ≤ 5%, retain ≥ 5 percentage points more station-years than the strongest non-support baseline that is frozen in Step 2; a stricter risk cap may be added as a secondary operating point but must also be frozen before looking at held-out results.

## Locked primary proposition

> Given a river station with usable historical years, decide whether an incomplete year may enter an **annual thermal-extreme archive** under a stated error tolerance, retaining as many usable records as possible without raising false-admission risk.  
> **Data availability for an annual thermal indicator should be decided by indicator-conditioned risk, not by uniform completeness; target-support information is an interpretable, transferable risk representation.**

This replaces three competing papers that the draft has been trying to prove at once: (A) position universally dominates length, (B) the full complex screen is necessary end-to-end, (C) real-monitoring and decision risk are already closed. Only (primary proposition) is in scope for the next revision lock.

### Step-2 interim update (2026-10-14, development OOF)

First discriminating run (`results/wrr_submission_ready/major_revision_20261014/step2_same_info_ablation/`):

- Fitted risk ranker vs **peak-overlap rule**: **−2.60 pp** at 70%/0.5 °C [−3.11, −2.19]; **+10 pp** retention at ≤5% false-admit [+7, +12] → **keep fitted indicator-conditioned ranking**.
- **`peak_overlap` on top of same-capacity generic model**: **+0.05 pp** [−0.17, +0.23] → **do not claim engineered support share as irreplaceable full-data inductive bias**; keep it as interpretable rule / possible small-n aid.
- Manuscript gravity shifts toward **admission by fitted indicator risk**, with support share as transparent baseline and explanation—not as uniquely necessary feature once seasonal visibility and uncertainty proxies are in the model.

See `INTERIM_FINDINGS.md` in that results folder. Wave-2 sealed Δ vs length is unchanged and still valid for the full pipeline on designed missingness.

### Two outputs that must stay distinct

| Output | Question | Success is… | Not the same as… |
|---|---|---|---|
| **Archive admission** | Is the reconstructed hottest-30 accurate enough to enter the indicator archive? | Controlled error risk at a retention / risk-cap operating point | More years judged on a threshold |
| **Threshold judgment** | Does hottest-30 exceed a labelled scenario threshold? | More correct judgments at a fixed misjudgment budget, with abstention allowed | Higher precision of the numeric metric |

Phase analysis, continuous width scans, maintenance calendars, and regional trends are **SI / boundary** unless a Step below promotes them with a dedicated contrast.

---

## Claim register (claim → contrast → success → failure narrowing)

| ID | Claim (what we assert if successful) | Strongest contrast | Pre-registered success | If fails, narrow to… | Priority |
|---|---|---|---|---|---|
| **C0** Primary task | Indicator-conditioned admission under error tolerance | Uniform completeness / length rules already known weak | Narrative + Table lock only; no new experiment | — | Step 1 |
| **C1** Support representation adds inductive bias | Explicit target-support features beat a **same-capacity, same-info-budget** generic risk model that sees gap length, monthly visibility, donor quality, reconstructor disagreement, training size — but **not** constructed support share / peak overlap as engineered features | (i) length, warm-coverage, peak-overlap, estimator-disagreement **rules** (already run); (ii) **generic HGB risk model**; (iii) generic + support; (iv) + observed-peak margin; (v) + support-location uncertainty (only if Step 4 deploys it) | On frozen train/cal/test nets: network-clustered CI for (a) Δ error-rate at 70%/0.5 °C vs peak-overlap rule **and** vs generic model; (b) Δ retention at ≤5% false-admit. Learning curves at 10/25/50/all train nets with fixed cal+test | If gain vs peak-overlap is small/unstable → **promote peak-overlap (or simple seasonal rule) to primary method**; complex model becomes upper-bound / extension. If gain appears only at full data → claim **sample efficiency / interpretability**, proved by learning curves | **Step 2 (highest)** |
| **C2** Mechanism is conditional, not a universal law | Holding station-year, reconstructor, donors, and training fixed: support overlap changes error; length changes error at fixed overlap | Crossed position × length design; report both axes in °C or same risk metric; network-level intervals; then repeat under climatology / donor / strong air-driven reconstructor | Clear **conditional** relationships + labelled failure modes (false peak from fill residual; climate-window vs realised-peak mismatch; competing peaks). No requirement that length be null | Soften discussion that still implies reconstructor-independent geometry law; keep “conditional risk predictor” wording | Step 3 |
| **C3** Support-location uncertainty is a **deployed** design (or not claimed) | Adaptive / weighted support window improves **admission or abstention**, not only AUC or localisation | Fixed 30-d vs fixed wider vs train-derived adaptive vs probability-weighted; negative control: same width, wrong season | Improves final admission/abstention on same backend risk model | **DECISION 2026-10-14: DEMOTE** — see `STEP4_DEMOTION.md`; width scan stays SI/boundary; deployed method remains fixed 30-d | Step 4 |
| **C4** Value under monitoring-like missingness | Method helps under tasks that match intended use | Full-year real-mask replay; network co-failure; anomalous thermal years; report arms separately (no single pooled headline) | Per-task effect, failure rate, and when abstention correctly fires | Restrict application claim to **offline archive repair on designed/empirical transplant masks**; do not claim operational monitoring admission | Step 5 |
| **C5** Calibration is a decision module | Interval scale / selection-aware calibration changes admit counts and post-admit risk under a frozen risk cap | Uncalibrated bounds vs ordinary conformal vs post-selection / network-level calibration; threshold-abstention vs admit-all / length / risk-screen | Frozen rule on held-out nets meets risk target and retains more useful judgments than alternatives; report errors, corrects, abstentions from the **same candidate pool** | Drop “conformal” as innovation for ranking-only use; keep ranking; say calibration unproven for absolute admit thresholds | Step 6 |
| **C6** Transfer is regime-conditioned, not “three providers” | Frozen method meets benefit under non-USGS / different peak timing / donor scarcity | Case-weighted, network-equal, provider-separate; stratify by thermal/process differences | Honest scope sentence that matches strata with adequate n | “USGS-majority external confirmation with smaller non-USGS support”; no wide cross-institution guarantee | Step 7 |
| **C7** Environmental judgment closed loop | Same candidates → same missingness task → reconstruct → risk → admit/abstain → fewer costly wrong threshold calls without silently dropping critical river types | Length / seasonal / full screen / stratified admission on complete-reference panel | Decision figure with misjudgment cost + type exclusion; stratified retention helps the **estimand**, not only equalises retention | Keep fairness as descriptive bias; do not claim regional thermal estimates improve | Step 8 |

---

## What is already allowed evidence (do not re-litigate)

Locked at `53c88cc` / wave-2 seal (designed missingness panel):

| Result | Number | May claim as… | Must not claim as… |
|---|---|---|---|
| Full method vs length rule @70%/0.5 °C | Δ = **−5.89 pp**, CI **[−6.92, −4.91]**; 49 nets / 143 stations / 13 017 cases; 0 recon failures | Whole-pipeline benefit on this **designed** confirmation panel | Real-fault post-event benefit; necessity of every component |
| Wave-2 frontier @70% (table rates) | length 8.41%; warm 5.95%; peak-overlap 3.68%; estimator-disagreement 3.84%; screen-only 2.61%; full 2.35% | Descriptive ranking of alternatives on the same panel | Paired network CIs (not yet); “+1 pp is stable and decision-valuable” |
| Descriptive extras (table arithmetic) | full vs peak-overlap ≈ **−1.33 pp**; vs disagreement ≈ **−1.49 pp**; reconstructor selection ≈ **−0.26 pp** | Motivation for Step 2 | Confirmatory contrasts |
| Retrospective holdout | 9.7%→2.5% (Δ −7.13 pp) | Labelled retrospective holdout | Cross-agency confirmation |
| Empirical vs pressure arms (older reserved) | empirical ≈ −0.71 pp CI includes 0; pressure larger | Arm sensitivity / mixture warning | Wave-2 pooled Δ as real-outage expectation |
| USGS share of wave-2 | ≈ **94.2%** of cases | “USGS-majority extra-network confirmation” | Equal three-provider proof |
| Crossed position–length / day-level MNAR | Existing amendments | Exploratory / conditional predictor setup | Dominance law; fixed-reconstructor geometry ID |

---

## Execution order (frozen)

1. **Step 1** — this table (done when committed to working tree and used as claim lock).  
2. **Step 2** — same-info strong baseline + nested support features + learning curves + network CIs (**blocks design complexity**).  
3. **Steps 3 and 5 in parallel** — mechanism pairing; monitoring-matched tasks.  
4. **Step 4** — only if C3 remains a headline innovation.  
5. **Steps 6 → 7 → 8** — after method is frozen; no operating-point / provider shopping after final test.

**Person-day budget (analysis):** ~20–35 (data acquisition extra).  
**Not success:** more experiments of distant topics; another “beats length by ~6 pp” headline without C1.

---

## Manuscript centre of gravity after Steps 1–2

| Keep / elevate | Demote / condition |
|---|---|
| Indicator-specific admission decision | “First discovery that gap position matters” |
| Support as compressible, transferable risk representation | Reconstructor-independent universal geometry law |
| Wave-2 as designed-panel confirmation of whole pipeline | Wave-2 as proof every component is necessary |
| Threshold abstention as second product | Treating more threshold judgments as more accurate metrics |
| Honest scope (history + some donors; USGS-heavy external) | “Three agencies ⇒ broad institutional robustness” |

---

## Step-2 feature budgets (predeclared for implementation)

**Support-core (engineered target support):** `peak_overlap`, and only those derived directly from the climatological / historical support construction.  
**Generic risk budget (no engineered support share):** `longest_run`, `total_missing`, `missing_fraction`, `n_runs`, monthly visibility features (or `month_sin`/`month_cos` + `warm_observed_fraction` if monthly fractions unavailable without new featurisation), `n_complete_years`, `record_years`, donor quality block, reconstructor-disagreement / train residual features already on the case table.  
**Nested adds:** + support-core → + `observed_peak_margin` / `observed_peak` / `has_complete_window` → (+ Step-4 uncertainty features only if deployed).  
**Learner:** same HistGradientBoosting (or whatever Step-2 script freezes) and same train/cal/test network partition for every nest.  
**Baselines retained, not re-fought:** length, warm coverage, peak-overlap, estimator disagreement.

Artifact path for Step-2 outputs: `results/wrr_submission_ready/major_revision_20261014/step2_same_info_ablation/`.
