# Step 2 interim findings (development OOF + reserved learning curves)

**Script:** `scripts/301_wrr_mr_step2_same_info_ablation.py`  
**Date run:** 2026-10-14 (working tree; baseline science lock `53c88cc`)

## Verdict for claim C1 (as pre-registered)

| Contrast | Result | Meets pre-registered bar? |
|---|---|---|
| Fitted risk model (+support) vs **peak-overlap rule** @70%/0.5 °C | **−2.60 pp** [−3.11, −2.19] | Yes (beneficial CI excludes 0) |
| Same @ risk-cap ≤5%: extra retention | **+10.0 pp** [+7, +12] | Yes (≥ +5 pp and CI > 0) |
| **+support vs generic** (same learner) @70% | **+0.05 pp** [−0.17, +0.23] | **No** — no detectable support increment |
| +peak-margin vs +support @70% | +0.01 pp [−0.19, +0.18] | No further gain |
| Learning curves (reserved) | At 10–25 nets, support / peak-margin sometimes slightly better; at 110 nets rates converge (~2.4%) | Weak sample-efficiency signal only; not a full-data necessity proof |

## What this means for the paper (failure-narrowing applied)

1. **Do not** claim that engineered hidden-support share is an *irreplaceable* inductive bias once a same-capacity model already sees warm-season visibility, gap geometry, donors, and reconstructor disagreement.
2. **Do** claim that a **fitted, indicator-conditioned risk ranker** (generic seasonal + uncertainty features) stably beats the strongest simple seasonal **rule** (peak-overlap) on both OP-70 and OP-RISK5.
3. Keep `peak_overlap` as: (a) the strongest **transparent rule** baseline; (b) an **interpretability / communication** device; (c) a possible **small-n** aid — pending a dedicated small-n CI, not a full-data necessity claim.
4. Reconstructor selection (~0.26 pp on wave-2 frontiers) remains a separate, small increment — not the main story.

## Caveats (do not overclaim the null)

- `generic` already includes `warm_observed_fraction` (seasonal coverage). That is allowed by the protocol but correlates with peak-season exposure; the null is “support share beyond seasonal+uncertainty features,” not “beyond length alone.”
- Per-month visibility fractions were unavailable on the case table; harmonics + warm fraction stand in.
- Panel is development OOF / opened reserved — **not** a new sealed wave-2 nest. Wave-2 still supports the *full frozen certificate vs length* pipeline only.
- Ranking uses a single-head quantile on `abserr_policy`; it isolates representation, not the full multi-estimator certificate object.

## Next actions implied by this result

1. Update manuscript centre of gravity: **risk ranking / admission**, not “support share as unique mechanism.”
2. Step 4 default: **demote** undeployed support-width uncertainty from primary innovation unless a deployed rule beats fixed 30-d on admission.
3. Continue Steps 3 and 5 (mechanism conditions; monitoring-like tasks) — still required; Step 2 does not close application claims.
4. Optional sensitivity: rebuild monthly visibility features and re-run nested contrast before final C1 wording freeze.
