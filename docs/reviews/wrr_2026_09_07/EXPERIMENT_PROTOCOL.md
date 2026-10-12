# Next-round experiment protocol (frozen with SUCCESS_CRITERION.json)

Development uses first-panel **river complete calendar years** only.
Second-panel and v16 confirmation, including the 846-case subset, are
retrospective. Unseen confirmation is `step1_universe` `candidate_unseen`
and must not be opened for rule selection.

| Step | Status | Artifact |
|---|---|---|
| 1 Universe and complete-year truth | done | `results/wrr_revision/step1_universe/` |
| 2 Simple methods and oracle headroom | diagnostic on existing replay | `step2_simple_headroom/` |
| 3 Success criterion | frozen: risk control, ε = 0.05 °C | `SUCCESS_CRITERION.json` |
| 4 Information factorial | 2×2 + air + quality cells done | `step4_information/` |
| 5 Decision labels = complete-year \(B_q\) | development eval done | `step5_thermal_decision/` |
| 6 Ablations + same-adoption-rate random reject | development done | `step6_ablations/` |
| 7 Realistic failure replay | done | `step7_failure_replay/` |
| 8 Hydrological hypotheses | development done | `step8_hydrology/` |
| 9 End-to-end freeze | frozen; overlay not superior | `step9_e2e_freeze/` |
| 10 Unseen confirmation and paper | done: training-mismatch + simple applicability | `step10_unseen_confirmation/`, `paper_archived/v16/` |

Information-conditioned simple policy (development): donors → donor-only
(right optional); else air ridge if air exists; else ≤30 d with both flanks
→ linear interpolation; else smooth climatology.
