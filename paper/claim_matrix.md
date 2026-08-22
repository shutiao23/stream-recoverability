# Claim-to-evidence matrix

No abstract, Key Point, or conclusion claim may be ticked until the named
artifact exists and the submission gate is `go`. Formal MAE, skill, and
frontier numbers remain forbidden until those rows exist. Validation ranks
below are model-selection evidence only.

| Claim | Role | Required artifact | Current status |
| --- | --- | --- | --- |
| C1. Structured outage length and surviving information jointly determine statistical recoverability of daily stream temperature | Primary | Complete `SCI_DENSE` T dual-frontier table | pending |
| C2. Cross-station observations are a major recovery source; value and physical reading depend on station, lag, and regime | Primary | Donor-C falsification effects and decision | pending |
| C3. A multisource nonlinear model adds value only under particular compound or long outages | Supporting, only if Stage 3 and formal frontier support it | Stage 3 stability table + proposed-versus-donor decision + T frontier | pending; Stage 2 does **not** support overall proposed superiority |
| C4. Network resilience is controlled by a small number of station-specific information dependencies | Supporting | Complete `SCI_NET` table | pending |
| C5. Recoverability patterns do or do not replicate on a second connected river network | External boundary | Evaluate-once Chattahoochee tables | not opened |
| Validation ranking exists | Selection only | published_v2 validation ranking | present; not a formal result |
| Proposed-versus-donor claim rule frozen | Gate | `design_freeze_v4` `model_funnel.proposed_versus_donor` | frozen before Stage 3 aggregation; comparator is donor regression; ties are not wins |
| Statistical T-frontier recoverability rule frozen | Gate | `design_freeze_v4` `statistics.statistical_recoverability` | frozen; recoverable iff 95% lower skill CI $> 0$; not an application threshold |
| Model roster frozen | Gate | `finalized_model_roster_v1` with no `budget_unstable` retained model | pending |
