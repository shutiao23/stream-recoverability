# Claim matrix for the WRR revision

Claims are allowed only after the named artifact exists. Law claims remain
withdrawn. After the 2026-09-07 review, several v16 confirmation claims are
restricted or withdrawn.

| ID | Claim | Allowed only if | Artifact | Status |
|---|---|---|---|---|
| Q | Adopt vs default for completed thermal-regime judgment | definition | `docs/reviews/wrr_2026_09_07/PROBLEM_DEFINITION.md` | restated; mean-benefit superiority is no longer the primary success rule |
| C1 | Neighbour-boundary training can create a long-gap sign change that matched long-block or no-boundary training does not | Step 2 on 42 networks | `results/wrr_revision/step2_fair_recovery/` | **stands** |
| C2 | Seasonal empirical benefit equals `diff` on complete cells | numerical identity | `step3_4_decision/` | **stands**; not two methods |
| C3 | A pre-fixed adopt/reject ranker beats all-default on MAE of the published trainer | Step 4 P0 tables | `step3_4_decision/` | mixed; fails at second-panel 180 d |
| C4 | Ranked yearly rule beats gated donor-only on hottest-30 | held-out river complete years | `step2_simple_headroom/` | **does not stand** (development complete years −0.046 °C network-equal; 846-case subset +0.014 with interval crossing 0) |
| C5 | Missing right boundary requires rejecting donor-only | Step 4 factorial | `step4_information/` | **withdrawn**; donor-only delta = 0.0 °C |
| C6 | 36 held-out IDs are 36 river confirmation networks with annual thermal truth | Step 1 roster | `step1_universe/` | **withdrawn**; 10 non-river; 191/310 confirmation station-years incomplete |
| C7 | Information-conditioned simple policy: donors → donor-only (right optional); else air ridge if air; else short+right → interp; else smooth climatology | Step 4 on 8 ARSO + 17 POWER networks | `step4_information/` | **supported on development**; on unseen, gated donor-only (+0.175) is at least as strong as this mix (+0.146) |
| C8 | 3-parameter air2stream runs without daily discharge and is beneficial when donors are missing | 17 POWER networks | `step4_information/cell_scores_power17.csv` | **supported** (+0.22 °C MAE); weaker than air ridge (+0.28 °C) |
| C9 | Missing or weak donors: retrain on the visible strong subset or switch to air; do not impute missing donor columns in the full model | Step 4 quality cells, 40 networks | `step4_information/quality_cell_scores.csv` | **supported on development** (partial-donor imputed −1.56 vs subset +0.74; weak imputed −2.59 vs air +0.26) |
| C10 | Calibrated thermal adopt/reject overlay beats the strong simple competitor on unseen river complete years | Step 10 | `step10_unseen_confirmation/` | **does not stand** (Δ −0.086 °C vs always-simple, outside ε = 0.05; harm falls by adopting 16%) |
| L | Universal recoverability threshold independent of model/training | FORBIDDEN | step7_mechanism | forbidden |
| J | Johnson 49 d independently validates our MAE crossing | FORBIDDEN | review | forbidden |

Opened v16 panels (42 + 57 + 36, including the 846-case subset) are
development or retrospective only. Unseen confirmation is the Step-1
`candidate_unseen` river complete station-years (36 networks, 82 eval
station-years scored). The paper claim after that confirmation is the
training-mismatch diagnosis plus simple-method applicability, not a new
superior decision layer.

Literature positioning (not claims of superiority): Li et al. (2017) fill
gaps with air–water relations and neighbours; Johnson et al. (2021) constrain
unfilled records and show filling can harm groundwater-influenced sites;
Beaufort et al. (2022) hide years, fill, and recompute heat peaks; Zaoui et
al. (2020) study reject-option regression with a fixed rejection rate, which
is not incremental benefit over a named climatological default. Almeida and
Coelho (2023) document the 3-parameter air2stream that does not use daily
discharge (C8).
