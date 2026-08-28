# Goal completion audit

Overall status: **incomplete**.

| ID | Requirement | Status | Work complete | Scientific gate | Evidence |
| --- | --- | --- | --- | --- | --- |
| P0 | Retitle around evidence actually supported by data | achieved | yes | pass | # Fitting-period error curves improve network-level risk ranking for stream-temperature gaps |
| P1a | Fitting-period empirical-transfer baseline | achieved | yes | pass | supported confirmation n=780; network Spearman=0.922; R2=0.812 |
| P1a_all | Report empirical-transfer performance on all 1,440 cells with fallback | achieved_weaker_complete_panel_result | yes | pass | n=1440; network Spearman=0.767; pooled Spearman=0.633; R2=0.145; sources={'network_mean_fallback': 660, 'within_horizon_training_curve': 780} |
| P1b | Learned error model with analytic-risk increment | achieved_negative_increment | yes | fail | LONO R2 0.7009 without operator and 0.7042 with operator |
| P1c | Network-grouped conditional conformal intervals | experiment_complete_gate_failed | yes | fail | simultaneous coverage=0.929; median-width/loss=2.217 |
| P1d | At least three recovery-model families | achieved | yes | pass | donor_blup_ridge/seasonal_boundary_ridge/xgboost_b_d |
| P1e | Conditional-variance saturation mechanism on fixed roster | achieved | yes | pass | 7 horizons; n=61 fixed stations |
| P1f | Bounded recurrent recovery sensitivity | complete_exploratory_negative | yes | fail | 6 networks; empirical-vs-BRITS station-gap Spearman=0.384; explicitly not full roster or SOTA LSTM |
| P1f2 | Bounded true bidirectional LSTM sensitivity | complete_exploratory_negative | yes | fail | 14 networks across 8 providers; torch.nn.LSTM bidirectional=True; empirical-vs-LSTM station-gap Spearman=0.338; network Spearman=0.631; explicitly not SOTA/full-roster confirmation |
| P1g | Air-temperature/flow process sensitivity | complete_development_proxy_negative_confirmation_unavailable | yes | fail | 50 development networks; XGBoost-vs-proxy network Spearman=0.343; published air2stream=False |
| P1h | Published air2stream or equivalent process model on independent networks | completed_equivalent_independent_subset_negative | yes | fail | Published 8-equation Crank-Nicolson equivalent on 8 US second-confirmation networks/14 stations; empirical-vs-air2stream network Spearman=0.238; original executable used=False; deterministic least-squares replaces PSO; US-only input-availability subset |
| P1i | Real-outage geometry or T4-style planted-geometry experiment | complete_matched_planted_geometry_negative_transfer | yes | fail | 1327 XGBoost B+D counterparts across 49 networks; empirical natural network Spearman=0.566 versus matched artificial=0.734; natural-minus-artificial delta=-0.168 (95% bootstrap -0.328, -0.012); actual missing days scored=False |
| P2a | Real-data leave-k-station-out replay with MI and QR baselines | achieved_open_development | yes | pass | 14 networks; policies=distance_even,greedy_mutual_information,oracle,qr_pivot,random,simple_risk_minimax |
| P2b | Finite-sample 5% false-release risk control | experiment_complete_no_nonempty_certified_release | yes | fail | 1600 budget-domain-model evaluations; certified fraction max=0.000 |
| P3_candidates | Second-confirmation candidate floor and 60-network target | achieved | yes | pass | candidates=242; strict-QC arrivals=60 |
| P3_domains | Amended second-confirmation domain composition | achieved_internal_amendment_not_external_preregistration | yes | pass | route_a_second_confirmation_v2_canada_quality_substitution; {"czechia": {"arrived": 15, "passed": true, "required": 15}, "norway": {"arrived": 10, "passed": true, "required": 10}, "united_states": {"arrived": 35, "passed": true, "required": 35}} |
| P3_canada | Original validated Canadian source stratum | complete_negative_external_quality_condition | yes | fail | Official four-station source was assessed but states observations are not validated or checked; zero qualified Canadian networks. |
| P3_scoring | Run independent second confirmation under the canonical hash-bound gate | scored_after_readiness_authorization | yes | pass | attempted=60; scored=57; attrited=3; simple network Spearman=0.6140782991962667; simple slope=1.0174320563432953; empirical network Spearman=0.715452424163858; empirical slope=0.9502513594290952 |
| P3_intervals | Independent second-confirmation interval endpoint | complete_negative_width_gate_failed | yes | fail | simultaneous coverage=1.000; median width/loss=8.398 |
| P3_triage | Independent 5% false-release triage endpoint | complete_negative_no_certified_release | yes | fail | 57-network evaluation; endpoint passed=False; simple released=0; empirical released=0 |
| P3_placement | Independent placement confirmation | complete_directional_no_preregistered_utility_gate | yes | fail | 13/13 complete replay matrices; simple minimax mean regret=0.240825 versus random=0.256213; relative reduction=6.006%; utility claim licensed=False |
| P3_heterogeneity | Provider, domain, thermal-state, and network-size heterogeneity | complete_descriptive_first_panel | yes | pass | moderators=domain_group,network_size_group,provider,thermal_state_shift; all rows descriptive_only=True |
| P3_climate_regulation | Climate-zone and regulation-state heterogeneity on 100+ scored networks | complete_descriptive_mixed_model | yes | pass | random-intercept/random-prediction-slope models: simple=104 networks, empirical=100 networks; known regulation simple=92, empirical=89; HUC2 climate and GAGES-II dam strata are descriptive/noncausal |
| P4_literature | Monitoring design, empirical gaps, kriging, and conformal literature | achieved | yes | pass | 10 required reference families present |
| P4_package | Complete manuscript, SI, six figures, cover letter, and checklist | achieved_pending_external_declarations | yes | pass | package files=7; figures=6 |
| ADMIN_authors | Author identities and legal declarations | incomplete_requires_authors | no | fail | metadata complete=False; approved=False |
| ADMIN_doi | Mint archival software DOI | incomplete_requires_repository_service | no | fail | CITATION.cff intentionally has no DOI |

The audit distinguishes completed experiments with negative gates, protocol-protected pending work, missing experiments, and external administrative blockers. A scientific gate failure is not relabelled as unfinished work or success.
