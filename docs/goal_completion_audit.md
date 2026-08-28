# Goal completion audit

Overall status: **incomplete**.

| ID | Requirement | Status | Work complete | Scientific gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| P0 | Retitle around evidence actually supported by data | achieved | yes | pass | # Fitting-period error curves outperform structural risk estimates for stream-temperature gaps |
| P1a | Fitting-period empirical-transfer baseline | achieved | yes | pass | confirmation n=780; network Spearman=0.922; R2=0.812 |
| P1b | Learned error model with analytic-risk increment | achieved_negative_increment | yes | fail | LONO R2 0.7009 without operator and 0.7042 with operator |
| P1c | Network-grouped conditional conformal intervals | experiment_complete_gate_failed | yes | fail | simultaneous coverage=0.929; median-width/loss=2.217 |
| P1d | At least three recovery-model families | achieved | yes | pass | donor_blup_ridge/seasonal_boundary_ridge/xgboost_b_d |
| P1e | Conditional-variance saturation mechanism on fixed roster | achieved | yes | pass | 7 horizons; n=61 fixed stations |
| P2a | Real-data leave-k-station-out replay with MI and QR baselines | achieved_open_development | yes | pass | 14 networks; policies=distance_even,greedy_mutual_information,oracle,qr_pivot,random,simple_risk_minimax |
| P2b | Finite-sample 5% false-release risk control | experiment_complete_no_nonempty_certified_release | yes | fail | 1600 budget-domain-model evaluations; certified fraction max=0.000 |
| P3_candidates | Second-confirmation candidate floor and 60-network target | achieved | yes | pass | candidates=242; strict-QC arrivals=60 |
| P3_domains | US, Canada, and at least two European domains | incomplete_external_canada_quality | no | fail | {"canada": {"arrived": 0, "passed": false, "required": 1}, "czechia": {"arrived": 15, "passed": true, "required": 10}, "norway": {"arrived": 10, "passed": true, "required": 10}, "united_states": {"arrived": 35, "passed": true, "required": 10}} |
| P3_scoring | Run independent second confirmation only after all arrival floors | withheld_by_protocol | no | fail | withheld_until_all_arrival_floors_pass |
| P4_literature | Monitoring design, empirical gaps, kriging, and conformal literature | achieved | yes | pass | 10 required reference families present |
| P4_package | Complete manuscript, SI, five figures, cover letter, and checklist | achieved_pending_external_declarations | yes | pass | package files=7; figures=5 |
| ADMIN_authors | Author identities and legal declarations | incomplete_requires_authors | no | fail | metadata complete=False; approved=False |
| ADMIN_doi | Mint archival software DOI | incomplete_requires_repository_service | no | fail | CITATION.cff intentionally has no DOI |

The audit distinguishes a completed experiment with a negative gate from a missing experiment. Second-confirmation scoring is missing by design because the Canadian arrival floor has not passed.
