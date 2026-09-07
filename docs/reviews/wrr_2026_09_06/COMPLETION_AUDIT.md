# Parent completion audit versus REVIEW.md

This file is the requirement-by-requirement audit. Status is taken from
current artifacts, not from intent. `complete` means the named evidence
exists and was recalculated from CSVs. The goal is not complete until every
row that the review made mandatory is `complete` or an explicit, evidenced
withdrawal.

Recentered question: using only historical observations and information
available at the gap, can a pre-fixed rule decide when to adopt
reconstruction versus default so that completed records improve specified
thermal-regime judgments, and beat historically supportable simple
alternatives, on data that did not participate in design?

| Review item | Required evidence | Artifact | Status |
|---|---|---|---|
| 1. \(B=\mathrm{MAE}_{clim}-\mathrm{MAE}_{model}\) is not a law | Fair recovery crossing disappears under long-block / no-boundary / donor-only | `step2_fair_recovery/` 42/42 nets | **complete**; law withdrawn |
| 1b. Threshold is not a station attribute independent of model | Same stations, neighbour vs donor/long-block | same | **complete** |
| 2. Precomputable threshold is not in-sample \(\rho\) | History→future threshold prediction **or** withdrawal of that claim | DESIGN_FREEZE `withdraw_universal_law` | **withdrawn**; no new \(\rho\) claim |
| 2b. Censoring: unobserved flip ≠ 365 d success | `crossing_days.csv` `censoring` column | step2 and step8 | **complete** |
| 3. Train/eval boundary mismatch | Neighbour vs long-block × boundary on/off | step2 | **complete** |
| 3b. Donor-only and climatology/interp controls | same | step2 | **complete** |
| 3c. Air / flow / air2stream as separate information group | scores where forcing exists | `step2_external/` | **complete** for air_ridge vs donor-only on 17 POWER networks. No discharge on this panel, so air2stream was not fit. |
| 4. All-default is a required competitor | policy net \(B\) including rejects as 0 | `step3_4_decision/` | **complete** for MAE placements of P0 and Step-2 |
| 4b. Zero-threshold on published trainer at 180 d | second panel 180 d net −0.016 | same | **complete**; does not beat all-default |
| 5. `diff` ≡ seasonal empirical | max abs gap \(8.88\times10^{-16}\) | same | **complete** |
| 5b. Competitive benefit baselines | r6, default_difficulty, −risk, switch, ridge | same | **complete** on MAE; not a unique design |
| 6. Downstream / thermal endpoint | hottest-30 station-year replay | `step6_frozen_replay/` + `step8_frozen_replay/` | **complete** (42-net development and 36-net confirmation, full-grid inner history) |
| 6b. Refuse reconstruction as a real action | freeze + replay vs all-default and gated always-reconstruct | same | **complete** |
| 7. Johnson 49 d not used as validation | manuscript + claims matrix | `paper/v16/` | **complete** (forbidden claim) |
| 7b. Beaufort cited as the fill-and-recompute precedent | manuscript §1 | `paper/v16/manuscript.md` | **complete** |
| 8. Second panel is not prospective | manuscript + freeze confirmation_panel | freeze + manuscript | **complete** |
| 8b. Confirmation on unused networks | 36 eligible IDs; recoverer table; frozen replay | `step8_confirmation/` + `step8_frozen_replay/` | **complete** (36/36 recoverer table; full-grid yearly replay) |
| 9. Unsupported / donor-missing / no right flank → one rule | freeze fields + step5 + frozen replay | freeze, step5, step6/8 replay | **complete**; unsupported, donor co-missing, and missing right boundary reject to default end-to-end |
| Step 1 problem definition | one page | `PROBLEM_DEFINITION.md` | **complete** |
| Step 7 mechanism or drop law | structural recoverer never crosses | `step7_mechanism/` | **complete**; law dropped |
| Core success chain on held-out data | pre-fixed rule, adopt/reject, hottest-30 over all cases, beats simple alternatives | `step8_frozen_replay/` | **complete with a narrowed claim**: ranked rule beats all-default and seasonal; **does not beat always-donor** (confirmation −0.0025 °C; mixed cases tied). Development: ranked +0.194 vs always-donor +0.278. Write as applicability of the repaired recoverer plus reject gates. |

The review’s success criterion is closed as an **applicability study**: a
pre-fixed recoverer plus donor/right-boundary gates improves hottest-30 on
held-out station-years relative to all-default and a ≤30 d seasonal rule.
The ranked \(\tau=0\) sorter does not beat the strongest simple alternative
(always reconstruct when those gates pass). `DESIGN_FREEZE.json` was not
retuned after seeing confirmation.
