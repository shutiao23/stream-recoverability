# OSF/Zenodo registration package — v14 prospective confirmation study (protocol v5)

| field | value |
| --- | --- |
| status | ready-to-paste; run the power analysis (protocol v5 §3.3) before the pre-outcome commit; then execute §5 checklist |
| governs | `paper/v14_plan/protocol_v5.md` §6 (registration gate) — supersedes `paper/development_v13/protocol_v4.md` §9 wording rules only insofar as v5 changes them |
| registration target | prospective, outcome-disjoint 80–120-network panel; **no v5 outcome may be computed or viewed before the external registration gate flips** |
| source docs | protocol_v5.md (full), claims_v14.md, EXECUTION_STATUS.md, manuscript_v14_skeleton.md, manuscript_v13.md §2.10 |

---

## 1. Registration metadata (paste into OSF project settings)

**Proposed OSF title.** *Prospective confirmation of differential (benefit) ranking for stream-temperature gap reconstruction — protocol v5 (analysis plan registered before outcome scoring)*

**Description (~1 paragraph, paste as-is).** Daily-mean stream-temperature records with missing gaps face a decision problem: is reconstructing a given gap with a given recovery model better than the default handling (calendar-day climatology) the user would otherwise apply? We define realized benefit B = MAE(default) − MAE(model) per evaluation placement, positive when reconstruction beats the default, and we rank gaps by a differential stress curve — benefit measured on artificial gaps cut into a network's own fitting years by the same model it will rank. Prior exploratory work (P0 differential stress test, already-scored panels, `results/v14/p0_differential/REPORT.md`) established per-duration placement-level Spearman replication targets of 0.297 / 0.303 / 0.370 / 0.555 and network-level 0.718 / 0.551 / 0.662 / 0.647 at 7/30/90/180 d, and showed that cross-duration budget comparisons are dominated by gap length. This registration freezes the confirmatory protocol for a new, outcome-disjoint prospective panel (80–120 networks; quotas: US 40–65%, ≥ 2 non-US domains each ≥ 15, non-US total ≥ 30; no network from any earlier panel): a within-duration-stratum fixed-budget primary endpoint, per-duration direction-replication endpoints, a 180-d harm-avoidance gate, and frozen GO/NO-GO thresholds. Water Resources Research has no Registered Report track and is a TOP-framework signatory; this external registration goes beyond the journal baseline to make the confirmatory analysis plan verifiably pre-outcome.

**Authors (placeholder).** [First author; write-up + methods], [second author], et al. — fill before submission; the registration is author-agnostic and can be updated in project metadata without touching the registered snapshot.

**License.** OSF project: CC-BY 4.0 (metadata and registered artifacts). Repository code remains under the repository license; raw provider daily observations are not redistributed unless terms permit (`metadata/data_rights.csv`).

**Embargo guidance.** Register with an embargo (OSF allows up to 4 years). Recommended: 12 months, or "until article acceptance". The registration is timestamped at creation (that timestamp is the preregistration proof); its content and DOI resolve publicly only when the embargo lifts. If a live public DOI is required before acceptance, lift the embargo early. The OSF *project* may stay private while the registration is embargoed; do not edit the project after registering — the registration freezes the snapshot (use a new component for post-registration context, never inside the registered tree).

## 2. OSF registration form — form type **"Preregistration"** (study information fields)

Register with OSF's **Preregistration** template (general/study-information form), *not* Registered Report (WRR has no RR track). Paste the blocks below into the corresponding fields.

### 2.1 Hypotheses (three RQs, each with directional prediction)

**H1 — RQ1 (direction):** the differential (predicted incremental benefit) curve ranks realized benefit **positively** on outcome-disjoint networks, per duration stratum. Directional confirmatory prediction: network-level Spearman ≥ 0.35 with two-sided 95% network-cluster bootstrap CI lower bound > 0 in **≥ 2 of the 4 strata** (7/30/90/180 d), zero margin. Prior-panel replication targets (exploratory, not margins): placement-level ρ = 0.297 (7 d), 0.303 (30 d), 0.370 (90 d), 0.555 (180 d).

**H2 — RQ2 (decision):** at fixed treatment budgets B ∈ {10, 20, 30}% applied **within each duration stratum**, ranking by the differential curve delivers **higher mean realized benefit** than (i) gap-length-only (frozen-random tie order within a stratum), (ii) random, and (iii) the v13 model-risk curve; and at 180 d — where the model is on average net-harmful against the climatology default — the differential curve selects a **least-harmful** treated set (harmful rate of the treated set **not above** the stratum's own harmful rate, mean benefit above the stratum mean).

**H3 — RQ3 (boundaries):** directional sub-hypotheses for the staged extensions: (P1) the differential curve beats every Tier-0 trivial baseline (global constant, gap length, R&H γ_m, r6-diff station-history benefit, default-difficulty); (P2) at least one decision-layer value curve (EC(ξ)/δ, risk–coverage/E-AURC, η envelope) is positive over its realistic range; (P3, pre-registered directional hypothesis S7) the differential curve's advantage over r6-diff is **larger in the thermal-drift stratum than in the stable stratum** (either outcome reportable; no hard gate).

### 2.2 Design

Prospective confirmation study on an **outcome-disjoint panel**: 80–120 scored river networks never appearing in any earlier panel's outcome set; network = independent unit. Protocol: `protocol_v5.md` (uploaded). Estimand: realized benefit per evaluation placement. Design elements: candidate floor 150, expected retention 0.50; eligibility/QC, evaluate-once and attrition rules carried from protocol v4 §4; durations {7, 30, 90, 180} d with seasons DJF/MAM/JJA/SON and ≤ 20 placements per station × gap × season; 365-d units scored only with real same-horizon fitting support (support-or-abstain, never extrapolated); nested chronological splits — the first 70% of calendar years are fitting years, the last 30% supply evaluation truth; default handling (calendar-day climatology medians) estimated **only from inner-fitting years under the model's training mask** (no-leakage); benefit curves built strictly inside the inner split by the four-level fallback (station × gap × season → station × gap → network × gap → network mean); scoring conventions bit-for-bit those of `results/v14/p0_differential/run_script_140.py`. Predictors (frozen at registration, fitting-period data only): `diff` (primary), `duration` (tie-broken by frozen random order), `random` (frozen seed), `risk` (v13 curve imported unchanged, bit-match verified), Tier-0 baselines `r6_diff`, `default_difficulty`, `rh_gamma`; `oracle` and `loo_upper` reported as bounds only.

### 2.3 Endpoints

**Primary (P1-v5).** Within-stratum fixed-budget mean realized benefit of the differential ranking vs the three comparators (gap-length-only, random, v13 risk curve) at B ∈ {0.10, 0.20, 0.30} × g ∈ {7, 30, 90, 180} d: per-network paired differences d_i = μ_{g,B,i}(diff) − μ_{g,B,i}(comparator) on identical subsets; panel Δ = mean over networks; inference = two-sided 95% network-cluster paired bootstrap, 2,000 draws, networks resampled within provider strata. Success per gates G2′/G3′ (§2.6).

**Secondary.** S1 direction replication: per-duration placement-level and network-level Spearman (predicted vs realized benefit) with cluster-bootstrap CIs; replication targets 0.297/0.303/0.370/0.555 (placement) and 0.718 [0.550, 0.824]/0.551 [0.280, 0.753]/0.662 [0.443, 0.814]/0.647 [0.438, 0.789] (network; exploratory targets, not margins). S3 paired Δρ vs the v13 risk curve (G2 form, per duration). S4 full within-stratum budget grid (predictor × B × stratum: μ, h, n). S2′ **180-d harm-avoidance gate**: h_{180,0.20}(diff) ≤ h_180 AND μ_{180,0.20}(diff) > μ_180, with the network-cluster 95% CI on Δ = μ_{180,0.20}(diff) − μ_180 excluding zero. S5–S7 staged P1/P2/P3 endpoints (gated per PLAN §2/§4.1–§5, or reportable). No cross-duration pooled rank or budget statistic may gate any claim.

### 2.4 Data collection procedures

No new field campaign. Daily mean stream temperature series and forcing for candidate networks are assembled from official provider archives (US, Czech, Norwegian routes; NASA POWER retained with day-boundary disclosure; raw values not redistributed). Panel assembly: candidate pool (floor 150) → QC/eligibility (protocol v4 §4 rules, unchanged) → frozen scoring roster (`frozen_scoring_roster_v5.csv`, sorted, hash-bound) → expected 80–120 scored networks with provider quotas (US 40–65%; ≥ 2 non-US domains each ≥ 15; non-US total ≥ 30). Artificial evaluation gaps are cut from the archived geometry conventions: seasonally stratified starts, durations {7, 30, 90, 180} d, up to 20 placements per station × gap × season; model and default handler scored on **identical placement rosters**; each placement scored exactly once (evaluate-once). Attrition is logged per provider into `attrition_flow_v5.csv`. **No prospective outcome value is computed or viewed until the external registration gate (§5 steps 1–6) has flipped.**

### 2.5 Sample size plan (power analysis from P0 numbers — run before registration)

Inputs (protocol v5 §3.3; all from `results/v14/p0_differential/`): per-network realized-benefit distributions resampled by duration stratum from the P0 second panel (placements: 7 d 4,480; 30 d 4,480; 90 d 4,400; 180 d 3,938; 17,298 direct total; networks 57/57/56/53); effect anchors = P0 within-stratum B = 0.20 treated-set mean differences — differential vs duration-only: 7 d +0.219 °C (1.219 − 1.000), 30 d +0.235 (0.840 − 0.605), 90 d +0.324 (0.380 − 0.056), 180 d +1.011 (−0.636 − (−1.647)); differential vs risk: +0.193 / +0.224 / +0.637 / +2.245 °C (`budget_within_duration.csv`). Anchors are sizing inputs, **not margins**. Recipe: simulation on the within-stratum budget endpoint — placements as within-network replicates, networks as bootstrap units resampled within provider strata (2,000 draws); the panel is sized so the 95% paired network-bootstrap CI for G2′ at B = 0.20 achieves the frozen width target in ≥ 2 strata at N = 80–120 networks; worked-example scheme of protocol v4 §4.3 retained. Outputs (`power_parameters_v5.json`, `power_curve_v5.png`, `recommended_panel_size_v5.json`) are frozen in the pre-outcome commit.

### 2.6 Analysis plan (frozen GO thresholds, quoted verbatim from protocol v5 §3)

GO on the prospective panel requires **all** of: **G1′** per-duration network-level Spearman ≥ 0.35 of predicted vs realized benefit with the two-sided 95% network-cluster bootstrap CI lower bound > 0 in ≥ 2 of the 4 duration strata; **G2′** at B = 0.20 within each stratum the paired network-bootstrap 95% CI of Δ = μ(diff) − μ(risk) lies entirely above 0 in ≥ 2 of the 4 strata; **G3′** at B = 0.20 within each stratum μ_20(diff) ≥ 1.3 × μ_g **and** h_20(diff) < 15%, in ≥ 2 of the 4 strata (a stratum with μ_g ≤ 0 is governed by S2′ and does not count toward the ≥ 2); **S2′** h_{180,0.20}(diff) ≤ h_180 and μ_{180,0.20}(diff) > μ_180 with the CI on the difference excluding zero at the 95% level; **G4′** G1′ pass count ≥ 2. Reporting: per-stratum tables with harmful rate attached to every budget mean; paired comparisons on identical subsets with paired network resampling within provider strata; cells with < 15 networks labeled illustrative only; no cross-duration pooling of Spearman or budget statistics for claims; every network-level correlation carries a cluster CI. Reporting tables regardless of outcome: `attrition_flow_v5.csv`, `direction_replication_v5.csv`, `budget_within_duration_v5.csv`, `harm_avoidance_v5.csv`, `cross_duration_diagnostic_v5.csv` (labeled diagnostic only), `gates_v5.json`.

### 2.7 Plan B/C fallbacks (frozen)

**Partial GO** (0.25 ≤ network-level ρ < 0.35 in ≥ 2 strata, or G1′ met in only 1 stratum): primary claim shrinks to binary classification of harm (b < 0), AUC + precision@k; within-stratum budgets reported as exploratory. **Plan B trigger** (any stratum whose treated set's harmful rate exceeds the stratum's own rate h_g): that stratum is reported as a harm-failure with the full budget grid and no benefit claim. **NO-GO / Plan C** (network-level ρ < 0.25 in ≥ 3 strata): the confirmatory program stops; the honest negative folds into the negative-result narrative (`negative_result_note.md`) and no WRR submission is made on the benefit claim. **Automatic downgrade (non-amendable):** failure of any gate is failure of the claim; a scored panel < 80 networks is reported `insufficient_panel` with no confirmatory claim; post-outcome amendment of endpoints/margins/comparators/budgets/tie-breaks invalidates confirmatory status (`amended_post_outcome`).

## 3. Verbatim strings (copy exactly into the fields/materials noted)

**(a) Internal hash-bound freeze wording — paste wherever earlier panels are described (protocol v5 §6.3; retained verbatim from `manuscript_v13.md` §2.10 and the manuscript v14 Open Research section):**

> Frozen: the second-panel outcomes, the empirical predictor as originally frozen, and the second-panel scoring are internal and hash-bound, but because their amendment and outcomes entered version control in the same commit they are not externally verifiable preregistration. … Confirmatory claims await the protocol-v5 panel.

(Registration-form short form, equally frozen: "Internal hash-bound freeze is **not** externally verifiable preregistration.")

**(b) Pfister & Kirchner (2017) exploratory-vs-confirmatory labeling sentence — Methods/Open Research of the manuscript, claims matrix, and the registration's analysis plan (protocol v5 §6.3 wording, verbatim):**

> Post-hoc, amendment, and exploratory analyses are labeled explicitly and defended by citation to the debate on hypothesis testing in hydrology \cite{pfister2017debates}: confirmatory claims may be made only from endpoints under §2.2–§2.3 and §3; everything from the P0-era and earlier records (including every P0 number quoted in this protocol as context) is exploratory/descriptive evidence and is labeled as such in the manuscript and claim matrix.

Evidence-role vocabulary (claims_v14.md, verbatim): "**frozen** (internal, hash-bound; not externally verifiable preregistration), **exploratory / descriptive** (P0-era and earlier analyses on already-scored panels), **confirmatory** (only protocol-v5 gated endpoints on a prospective, externally registered panel — none exist yet)."

**(c) TOP-framework compliance statement for WRR (manuscript Open Research):**

> Water Resources Research is a signatory of the Transparency and Openness Promotion (TOP) guidelines; the binding transparency requirements for this submission are data/code availability and analysis transparency. WRR offers no Registered Report track, so the external registration of the prospective-panel analysis plan (protocol v5 §6, deposited before any prospective outcome was computed or viewed) exceeds the journal's baseline. Data and code availability: [archival DOI]. Registration: [registration DOI].

## 4. OSF project file tree (components ↔ local artifacts)

Root project = the title of §1. One component per row; upload local files verbatim (no prospective-outcome file may be present in any of these at registration time).

| OSF component | Local files (exact paths) | Notes |
| --- | --- | --- |
| 01_Protocol_and_planning | `paper/v14_plan/protocol_v5.md`; `paper/v14_plan/claims_v14.md`; `paper/v14_plan/manuscript_v14_skeleton.md`; `paper/v14_plan/figure_plan_v14.md`; `paper/v14_plan/negative_result_note.md`; `paper/v14_plan/harmonization_decisions.md`; `paper/v14_plan/EXECUTION_STATUS.md`; `paper/references.bib` | commit-#1 core; + new `frozen_scoring_roster_v5.csv`, margins/tie-break annex if split out; sha256 manifest |
| 02_Registration_records | new files created at registration: `readiness.json` (`external_registration_verified: false`), `registration_record_v5.json` (template), `power_parameters_v5.json`, `power_curve_v5.png`, `recommended_panel_size_v5.json` | upload before registering; `registration_record_v5.json` filled with registry/DOI/URL/UTC/hash/flags **after** DOI minted, as a post-registration changelog note or in the project (never edits the registered snapshot's analysis plan) |
| 03_P0_evidence_base (context, exploratory) | `results/v14/p0_differential/`: `REPORT.md`, `gates.json`, `metrics_by_horizon.csv`, `paired_bootstrap.csv`, `budget_curve.csv`, `budget_within_duration.csv`, `derived_network_level.csv`, `season_loo_upper.csv`, `sanity_checks.txt`, `placement_predictions_{first,second}.csv`, `unit_predictions_{first,second}.csv`, `differential_fitting_losses_{first,second}.csv`, `differential_fitting_losses_{first,second}_{climatology,linear_interp}.csv`, `run_script_140.py` | the quoted evidence base; labeled exploratory/descriptive in every pasted block |
| 04_Archived_geometry_placement_tables | `results/development_v11/route_a_confirmation/placement_losses.csv`; `results/development_v11/second_confirmation/scoring/placement_losses.csv`; `results/development_v11/reviewer_completion/confirmation_empirical_fit_losses.csv`; `results/revision_v12/t02_support_hierarchy/agent_a/second_fit_losses.csv` | replayed geometry inputs of script 140 (first/second panels) |
| 05_Scripts_140-145_and_pipeline | `scripts/140_run_p0_differential_stress.py`; `scripts/141_run_p3_network_drift.py`; `scripts/142_p0_derived_metrics.py`; `scripts/143_run_p1_benefit_baselines.py`; `scripts/143_run_v14_p2_decision.py`; `scripts/144_run_p3_strata_comparison.py`; `src/stream_recoverability/experiments/differential_stress.py` (+ its unit tests `tests/test_differential_stress.py`) | script 145 (power analysis / v5 prospective scoring) does not exist yet — add it to this component at commit #1 |
| 06_P1_baselines | `results/v14/p1_baselines/`: `REPORT.md`, `metrics_table.csv`, `budget_within_duration.csv`, `rh_gamma_curve.csv`, `proxy_values.csv`, `placement_predictions_{first,second}.csv`, `unit_predictions_{first,second}.csv`, `sanity_checks.txt` | context (Tier-0 suite the v5 P1 gate consumes) |
| 07_P2_decision | `results/v14/p2_decision/`: `REPORT.md`, `laio_tamea_curves.csv`, `crps_check.csv`, `selective_risk_curves.csv`, `selective_metrics.csv`, `rev_curves.csv`, `rev_fixed_threshold.csv`, `eta_sensitivity.csv` | context |
| 08_P3_drift_strata | `results/v14/p3_drift/`: `README.md`, `REPORT.md`, `network_drift_covariates.csv`, `stratum_comparison.csv`, `stratum_direction_test.csv`, `direction_test.json` | frozen strata for S7 (19/19/19) |
| 09_Outcomes (created later) | `results/v14/p5_prospective/` planned: `attrition_flow_v5.csv`, `direction_replication_v5.csv`, `budget_within_duration_v5.csv`, `harm_avoidance_v5.csv`, `cross_duration_diagnostic_v5.csv`, `gates_v5.json`, `REPORT.md` | **never inside the registration**; separate project or component added after the registration snapshot is closed |

## 5. Step-by-step human execution checklist

1. **Power analysis.** Run the §2.5 computation from P0 numbers; freeze `power_parameters_v5.json`, `power_curve_v5.png`, `recommended_panel_size_v5.json`. Lock the prospective roster (`frozen_scoring_roster_v5.csv`) and margins annex. Verify no file above touches a prospective outcome.
2. **Commit #1 (separate public commit).** Commit protocol, roster, margins, power artifacts, predictor code paths (differential curve, imported v13 risk predictor, R&H γ_m), and `readiness.json` with `external_registration_verified: false` to the public remote; record commit hash and sha256 of every registered file.
3. **OSF account.** Create account at osf.io (ORCID-linked). If account creation is declined/unavailable, skip to step 11 (Zenodo fallback).
4. **Create project.** Title from §1; description from §1; license CC-BY 4.0; keep the project **private** during setup.
5. **Create the 9 components** of §4 and upload each component's file list exactly as tabulated (component 09 is optional now; if created, leave empty and mark "post-registration").
6. **Preregister.** Project → Registrations → *New registration* → choose the **"Preregistration"** form template → fill hypotheses/design/endpoints/data-collection/sample-size/analysis fields from §2 → set embargo (§1: 12 months or until acceptance) → confirm. Record creation timestamp immediately.
7. **Verify the gate.** Fill `registration_record_v5.json` (registry = OSF, DOI, registration URL, UTC time, commit hash, file sha256s, `separate_pre_outcome_commit: true`, `externally_verifiable_preregistration: true`); flip `readiness.json`; add both as changelog entries in the (now frozen) project or the new 09 component. **No prospective outcome may be computed or viewed before this record exists and hashes match commit #1.**
8. **Outcome scoring (commit #2).** Later, distinct commit referencing the registration DOI and binding commit #1's sha256; produce the §2.6 reporting tables. Outcome files written before the registration timestamp invalidate the panel.
9. **At acceptance.** Lift the embargo (if still set); make the project public; insert registration DOI + archival DOI via the templates below.
10. **Amendments.** Pre-outcome changes to roster/margins/endpoints/comparators/budgets/tie-breaks/power parameters: write an amendment record and make a **new external registration** before scoring the affected outcomes. Post-outcome: prohibited (except documentation-only changelog entries).
11. **Zenodo fallback (if OSF declined).** Create a Zenodo account (zenodo.org; GitHub login works). *New upload*: deposit the same commit-#1 file set (zip or per-file) with the §1 title/description and license; submit → DOI is minted immediately (metadata public; files can be restricted). Zenodo has no registration form — time-stamping rests on the upload timestamp plus commit #1's separate-commit hash; fill the description with §2.6's analysis plan verbatim. Complete step 7 with registry = Zenodo, then proceed identically (gate, commit #2). Zenodo has no embargo for the record; files may be restricted until acceptance if needed.
12. **Manuscript sentence templates (insert once DOIs exist, Open Research section; also `CITATION.cff`, `.zenodo.json`):**
    - Registration: "The prospective-panel analysis plan (protocol v5) was registered externally before any prospective outcome was computed or viewed: [OSF | Zenodo] registration [DOI] (https://doi.org/[DOI]), registered [YYYY-MM-DD]; registered commit [hash] and file sha256s are recorded in `registration_record_v5.json`."
    - Archival: "Analysis code and registered artifacts are archived under the repository license at Zenodo: [DOI] (https://doi.org/[DOI]). Provider daily observations are not redistributed unless terms permit; retrieval routes are documented in Supporting Information. The registration DOI and the archival DOI are distinct."
    - TOP statement: string (c) of §3 with both DOIs inserted.

## 6. Timing: before data collection vs at submission

**Must precede the start of prospective scoring/data collection (hard gates, in order):** roster freeze and predictor/geometry verification (fitting-period only) → power analysis frozen → commit #1 pushed and hashed → OSF project/components/uploads → **OSF "Preregistration" registration created (timestamp)** → embargo set → registration_record_v5.json verified → `readiness.json` flipped → only then any prospective outcome computed or viewed. Registering even earlier (before candidate-network raw data assembly) is permitted and safe; the registered content may not change afterward.

**Can wait until submission (no gate):** lifting the embargo / making the project public; Zenodo archival DOI deposit of the full permitted package; inserting both DOIs into the manuscript Open Research section, `CITATION.cff`, and `.zenodo.json`; drafting the final TOP statement text; figure production and claims-matrix row updates for the prospective panel (labels unchanged: confirmatory only for v5 gated endpoints).

## 7. Do-not-do list

- **No internal-hash-bound framing as preregistration.** Never describe any earlier-panel freeze, including P0's, as externally verifiable preregistration — use string (a) verbatim everywhere; "preregistered confirmation" applies only to the v5 panel after the §5 gate.
- **No edits to the registered analysis plan after panel scoring begins.** No re-fitting or re-calibration of predictors on prospective outcomes (v13 risk predictions must bit-match the archived predictor); post-outcome changes to endpoints, margins, comparators, budgets, or tie-breaks are prohibited — label any forced deviation `amended_post_outcome` with the Pfister–Kirchner sentence (string (b)); pre-outcome changes require a new registration. The automatic downgrade rule is non-amendable.
- **No loosening of frozen thresholds** (ρ ≥ 0.35 with CI lower > 0; 1.3 × μ_g; 15% harmful cap; S2′ inequalities) to recover a pass.
- **No cross-duration pooling of Spearman or budget statistics for claims** — pooled rows are labeled diagnostics only; no gating on them.
- **No outcome viewing before the gate.** No v5 outcome file computed, merged, or opened before `registration_record_v5.json` exists with matching hashes.
- **No Registered-Report language for WRR** — state plainly that WRR has no RR track and the registration is beyond-journal-baseline analysis transparency (string (c)).
- **No editing the OSF project after registration.** The registered snapshot is frozen; post-registration context goes into a separate component/project; never attach prospective outcome files inside the registered tree.
- **No placeholder or fake DOIs** in the manuscript — insert only after minting; registration DOI and archival DOI stay distinct.
- **No claim language from P0 as confirmatory** — every P0 number is exploratory/descriptive evidence that licensed the registration, and budget means are never reported without their harmful rates; cells with < 15 networks are illustrative only; no "more accurate reconstruction" framing vs \cite{johnson2021datagap} (model-conditional, benefit-oriented increment only).


---

## 8. Round-3 update (2026-09-04, required before execution)

The internal-panel evidence base changed with the round-2/3 revision; update the
registration metadata and description text before the pre-outcome commit:

- Durations: the fitted/designed grid is now **7/14/30/60/90/180 d** (14/60-d
  fitting cuts, `scripts/152_run_v14_r2_fitting_cuts_14_60.py`); H1's "4
  strata" wording becomes "≥ 2 of the 6 strata" with targets 0.297/0.319/0.303/
  0.327/0.371/0.556 (placement) and network 0.718/0.618/0.551/0.582/0.662/0.650.
- Description paragraph: replace the "replication targets of 0.297 / 0.303 /
  0.370 / 0.555 and network-level 0.718 / 0.551 / 0.662 / 0.647 at 7/30/90/180 d"
  sentence with the six-duration series and add: "benefit statements are always
  relative to the named default (calendar-day climatology fill; reporting norm
  (v), manuscript §2.7); the operational threshold statement is the two-scale
  interval (MAE crossing 105 d [98–114] / 91 d [85–95]; downstream family
  medians 39–60 d)."
- Registered artifact tree must include the round-3 regeneration outputs:
  `results/v14/p0_differential/` (six-duration CSVs), `paired_diff_vs_negrisk.csv`,
  `p1_baselines/family_benefit_table.csv`, `p4_flip_analysis/mae_crossing_ci.csv`,
  `figures_v3/`, and scripts 140–153; the "~60 d" figure and its "internal
  sub-grid analysis" never appear anywhere in the registered package.
