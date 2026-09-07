# Claim matrix for the WRR revision

Claims are allowed only after the named artifact exists. Law claims are withdrawn unless Step 7 says otherwise.

| ID | Claim | Allowed only if | Artifact |
|---|---|---|---|
| Q | The user problem is adopt vs default for completed thermal-regime judgment | always (definition) | `docs/reviews/wrr_2026_09_06/PROBLEM_DEFINITION.md` |
| C1 | Neighbor-boundary training can create a long-gap sign change that matched long-block or no-boundary training does not | Step 2 on 42 networks | `results/wrr_revision/step2_fair_recovery/` |
| C2 | Seasonal empirical benefit equals `diff` on complete cells | numerical identity | `results/wrr_revision/step3_4_decision/` |
| C3 | A pre-fixed adopt/reject rule beats all-default on MAE placements of the published trainer | Step 4 P0 tables; fails at second-panel 180 d | `step3_4_decision/` |
| C4 | Freeze-aligned yearly replay: ranked rule beats all-default and ≤30 d seasonal; **does not beat gated always-donor** (confirmation −0.0025 °C; development −0.084 °C). Write as applicability of recoverer + reject gates | Inner-year history, duration switch, unused budget | `step6_frozen_replay` and `step8_frozen_replay` |
| C5 | Faults (donor sync, missing right boundary, transplanted geometry) change benefit | Step 5 | `step5_failures` |
| C6 | Confirmation networks unused in design reproduce the neighbour/long-block split | Step 8 after freeze, no retuning | `step8_confirmation` |
| L | Universal recoverability threshold independent of model/training | FORBIDDEN unless Step 7 structurally_correct always crosses | step7_mechanism |
| J | Johnson 49 d independently validates our MAE crossing | FORBIDDEN | review §7 |

Primary recoverer for confirmation is chosen on the first panel only, after Step 2, and written to `results/wrr_revision/DESIGN_FREEZE.json`.
