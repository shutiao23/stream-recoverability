# Harmonization decisions (v14 P0-era, from PLAN §6.2)

Scope: the four "harmonize or delete" conflicts carried in `paper/v14_plan/PLAN.md` §6.2 (lines 291–300) plus the §8.6 submission-gate TODO #3 (t10 RMSE). Every number below is quoted verbatim from artifacts; nothing was recomputed except where explicitly stated (t10 RMSE derivation, §4). Source of truth for "canonical": the v13 evidence ledger (`paper/development_v13/evidence_ledger_v13*.md`) and the v13 merged manuscript's editorial appendix (`manuscript_v13.md` lines 860–975), cross-checked against the underlying v12 artifacts.

---

## 1. Missingness matrix (t06) — Decision: unified rerun (adopt agent_b's validated machinery and conventions as the single canonical pipeline; rerun for provenance); if the rerun is declined, delete the whole missingness section (§2.9 paragraph, §3.7, SI S7) rather than ship both columns

### Evidence

**Both versions, verbatim rows (agent_a file = 7 columns of the 23-col schema; agent_b rows quoted with all columns):**

`results/revision_v12/t06_missingness_matrix/agent_a/mechanism_metrics.csv` (col order: mechanism,matched,network_spearman,network_spearman_p,pooled_spearman,calibration_intercept,calibration_slope,mean_predicted_loss,mean_observed_loss,n_units,n_networks,network_spearman_4horizon,n_units_4horizon,fallback_fraction,station_horizon_units):

```
L2: a_uniform_block,True,0.5314685314685316,0.07536233505348364,0.8572298094442996,0.340765104538489,0.9200454617524911,0.9882626196594592,1.2586065415267242,573,12,0.6223776223776225,348,0.10296684118673648,514
L6: f_donor_synchronous,True,0.9790209790209792,3.0898013985487064e-08,0.9790101000497565,0.08687217709072997,0.9496429916411671,3.428091921621996,3.3500855140558348,609,12,0.9510489510489512,348,0.006568144499178982,605
```

`results/revision_v12/t06_missingness_matrix/agent_b/mechanism_metrics.csv` (key supported_* and full_* columns):

```
L2: uniform_block, supported_network_spearman=0.9440559440559443, supported_pooled_spearman=0.9149189035312938, supported_calibration_slope=1.020822394708415, supported_n_networks=12, supported_n_station_gaps=306, supported_mean_predicted_loss=1.0069499721311854, supported_mean_observed_loss=0.9813260509835002, full_n_station_gaps=346, full_n_networks=12, full_network_spearman=0.6433566433566434, fallback_unit_fraction=0.11560693641618497, mechanism_label="(a) uniform single block"
L6: donor_sync, supported_network_spearman=0.4895104895104896, supported_pooled_spearman=0.722365172090978, supported_calibration_slope=0.7429790042691368, supported_n_networks=12, supported_n_station_gaps=306, supported_mean_predicted_loss=2.374284178253616, supported_mean_observed_loss=2.539016166837887, full_n_station_gaps=346, full_n_networks=12, full_network_spearman=0.2937062937062937, fallback_unit_fraction=0.11560693641618497, mechanism_label="(f) donor-synchronous outage"
```

So the conflict as PLAN states it: donor-sync **0.979** (agent_a, `agent_a/mechanism_metrics.csv:6`) vs **0.490** (agent_b, `agent_b/mechanism_metrics.csv:6`); uniform **0.531** (agent_a, `:2`) vs **0.944** (agent_b, `:2`) — reversed ranks. Bootstrap intervals (agent_b only, `agent_b/mechanism_bootstrap_intervals.csv:2,8`): donor_sync network Spearman 0.4895104895104896, 95% CI **[−0.23616200828157347, 0.925472021517852]**, slope 0.7429790042691368 [0.5251, 0.9268], n=12, 306 units; uniform_block 0.9440559440559443 **[0.6884, 1.0]**. agent_a computed no bootstrap intervals.

**Convention differences (scripts):** both scripts read the same panel store — `NETWORK_ROOT = ROOT/"results/development_v11/confirmation_daily_qc/networks"` at `scripts/rev_v12_t06_missingness_a.py:40` and `scripts/rev_v12_t06_missingness_b.py:70` (165 daily-QC network dirs) — but differ beyond the panel constant:

- Panel: agent_a `NETWORKS` (`rev_v12_t06_missingness_a.py:43-56`) vs agent_b (`rev_v12_t06_missingness_b.py:74-87`). Intersection = {foen_aare_aaregebiet, gkd_bayern_donau, gkd_bayern_isar, lubw_neckar, huc8_17090004} = **5 of 12** (verified against both lists; also `manuscript_v13.md:601-602` and appendix item 6, `manuscript_v13.md:909-910`: "verified against `network_panel.csv` and `provenance.json`"; the "six in common" slip in `manuscript_v13_b.md:109` was corrected — `paper/development_v13/REPORT.md:117-118`).
- Horizons/units: agent_a imports `GAP_LENGTHS = (7, 14, 30, 60, 90, 180, 365)` (`src/.../development_recovery.py:21`), units = station-gap means over 573–609 station-gaps incl. network-mean-fallback units (fallback_fraction 0.007–0.103; `agent_a/REPORT.md:30,64`); agent_b uses `HORIZONS = (7, 30, 90, 180)` × DJF/MAM/JJA/SON cells (`rev_v12_t06_missingness_b.py:89-96`), units = within-horizon **supported** station-gaps only, fallback excluded (306 of 346; `agent_b/REPORT.md:62-67`; `mechanism_metrics.csv` `full_` vs `supported_` columns). agent_a's own REPORT attributes its weak uniform cell to fallback flattening at 90–365 d (`agent_a/REPORT.md:64`), i.e. the uniform 0.531-vs-0.944 gap is substantially a scope convention.
- Mechanism microstructure: (c) summer window Jun 1–Sep 30 (agent_a, `rev_v12_t06_missingness_a.py:62`) vs Jul 1–Aug 31 (agent_b, `rev_v12_t06_missingness_b.py` docstring L17, `agent_b/REPORT.md:52`); (d) top-30% day-of-year-climatology windows (agent_a, `REPORT.md:46`) vs ≥75th-percentile window-mean temperature (agent_b, `REPORT.md:53`); (b) 2–8 blocks ≤46 d, 3-day separators (agent_a `REPORT.md:44`) vs 2–4 blocks, 2-day separators (agent_b `REPORT.md:51`).
- Forcing (mechanism g): agent_a = "target + strongest donor masked, weaker donors remain", with the strongest donor standing in for air temperature because "the confirmation panels contain no air temperature" (`agent_a/REPORT.md:49`; docstring `rev_v12_t06_missingness_a.py:12-13`); agent_b = "target + air temperature (NASA POWER T2M at the network centroid, the repo's own acquisition path) masked; model B∪D∪Ta" (`agent_b/REPORT.md:56`; `rev_v12_t06_missingness_b.py:127-132`). POWER T2M cache covers exactly agent_b's 12 networks (`agent_b/power_ta_cache/`, 12 CSVs).
- Mismatch experiments also disagree in direction: agent_a forward collapse donor-sync 0.979→0.294, forcing 0.881→0.196, online 0.930→0.399 (`agent_a/REPORT.md:73-76`); agent_b finds no forward collapse for donor-sync (0.490→0.524) but a reverse collapse (donor-sync curve on uniform gaps 0.944→0.098, Δρ −0.846; `agent_b/REPORT.md:100-101`).

**Current manuscript treatment (v13 merged):** §3.7 demotes the matrix to supporting information (`manuscript_v13.md:587-616`: "no mechanism-matched transfer value—including implementation A's donor-synchronous 0.979—is asserted as evidence"); §2.9 (`manuscript_v13.md:330-339`) and editorial appendix item 6 (`manuscript_v13.md:904-914`) document the divergence and forbid citing either value; the v13 ledger keeps it an open gating TODO (`evidence_ledger_v13.md` N2 row L69, T3 row L106; `paper/development_v13/REPORT.md:96-99`, TODO item 3 L129-130). `results/revision_v13/decision_harmonization/agent_a/divergence_note.md` covers only t08, not t06.

### Rerun feasibility (assessed as asked)

- Shared inputs: yes — both scripts read the identical panel directory (`.../confirmation_daily_qc/networks`) with the same `read_temperature_panel`; no new in-situ data needed.
- But a unified rerun is **not** "edit a panel constant": the two codebases are independent implementations that differ in unit definition, horizons, mechanism microstructure, forcing, and fallback handling (above), so re-scoring with one chosen code path is required. That is cheap: agent_a measured 1,400 s wall for 12 nets × 7 mechanisms (`agent_a/REPORT.md:5`); agent_b ~95 s, 5 workers (`agent_b/REPORT.md:160`). agent_b's machinery is the natural base: it is a parameterized copy of the frozen `recovery_roster` pipeline, reproduces `confirmation_empirical_fit_losses.csv` to ~5e−16, and validates mechanism (a) at unit level against the frozen reference on 9 shared networks (prediction corr 0.996; network Spearman 0.933 vs reference 0.900; 236/239 units matched; `agent_b/REPORT.md:25-30`), and its 12-network panel roster is fully POWER-cached. Extending to any network outside those 12 requires NASA POWER fetches for mechanism (g) (the only external-data dependency; agent_a's donor-proxy substitution avoids it but is agent_a-specific).
- Risk: low technically (deterministic, minutes of compute, validation gate available: mechanism (a) must land in the uniform-grid regime ≈0.92–0.94, cf. agent_b 0.944 vs paper 0.922); the substantive risk is that at n=12 a network-Spearman bootstrap CI is ±0.3–0.5 wide (donor-sync CI [−0.24, 0.93]), so the harmonized output must be reported with intervals, not as point values.

### Justification

Unify-and-rerun, per PLAN's first option, is more defensible than deletion here: (i) the matrix is the deliverable that answered the review demand ("missingness-mechanism matrix beyond uniform grid gaps", `agent_b/REPORT.md:11`), and deletion would also remove the only two findings that ARE consistent across implementations (mechanism mismatch harms transfer in at least one direction; seasonal placement bias is the mildest mismatch — `agent_a/REPORT.md:82`, `agent_b/REPORT.md:105-111`, retained in v13 §3.7/claim matrix), which v14's §6.1 non-stationarity and gap-geometry arguments still lean on; (ii) the conflict is almost entirely convention, not contradiction: at n=12 the two donor-sync point estimates (0.979, 0.490) sit well inside each other's sampling uncertainty (agent_b CI [−0.24, 0.93] contains 0.98), and agent_a's own REPORT traces its weak uniform cell to fallback units the canonical supported-unit convention excludes; (iii) both agents already validate bit-for-bit against the same frozen pipeline at the panel level (agent_a `t07` style cross-checks in `agent_a/REPORT.md:93`; agent_b §1 validation), so a single canonical run on agent_b's machinery closes the open TODO T3/N2 ("harmonization … is a pre-submission TODO") at ~30 min compute instead of carrying two irreconcilable SI tables into v14, where PLAN §6.2 warns any reviewer would read the unresolved 0.979-vs-0.490 pair as a quality signal (PLAN.md:300). Because agent_b's script is deterministic on fixed inputs, rerunning it on its own cached roster reproduces its table exactly; the canonical values below are therefore the expected outcome of the rerun and the single set to standardize on, with agent_a's run archived as the documented independent implementation. Fallback if the rerun is declined: delete the missingness section entirely (PLAN option 2) — but that is strictly worse here because the section is already demoted to SI and carries no main-text claim, so the incremental cost of unification is a script run, not a rewrite.

### Canonical values

`agent_b/mechanism_metrics.csv` `supported_*` columns + `mechanism_bootstrap_intervals.csv` (12 networks, supported within-horizon station-gap units, 2000-draw network bootstrap):

| mechanism | supported network Spearman | 95% CI | calib. slope | 95% CI | n units |
|---|---|---|---|---|---|
| uniform_block (a) | 0.944 | [0.688, 1.000] | 1.021 | [0.944, 1.086] | 306 |
| multi_block (b) | 0.888 | [0.533, 1.000] | 1.016 | [0.939, 1.086] | 306 |
| summer_biased (c) | 0.909 | [0.651, 1.000] | 1.043 | [0.893, 1.156] | 292 |
| high_temp_biased (d) | 0.958 | [0.779, 1.000] | 0.907 | [0.800, 0.978] | 304 |
| donor_sync (f) | **0.490** | [−0.236, 0.925] | 0.743 | [0.525, 0.927] | 306 |
| forcing_outage (g) | 0.937 | [0.697, 1.000] | 0.987 | [0.911, 1.054] | 306 |
| online (h) | 0.965 | [0.806, 1.000] | 0.942 | [0.773, 1.035] | 306 |

Reporting rule after the rerun: matched transfer quoted only in SI with bootstrap intervals; the two implementation-invariant qualitative findings remain in main text; agent_a's archived numbers are never presented beside the canonical set as unresolved.

### Files to change

- `paper/development_v13/manuscript_v13.md`: §2.9 lines 323–339, §3.7 lines 587–616, editorial appendix item 6 lines 904–914 (replace "no value asserted / both columns in SI" with the canonical-table statement + archive note).
- `paper/development_v13/evidence_ledger_v13.md` (and `_a.md`, `_b.md` mirrors): N1/N2/N3 rows L68–70 (L61–63 in `_b`), T3 row L106 (L110 `_b` K3-adjacent), open-TODO flags → closed.
- `paper/development_v13/claim_matrix_v13.md:216` (MC7 row) and `response_letter_v13*.md` (e.g. `response_letter_v13.md:124-130,216`): rephrase from "no matched value citable" to canonical-SI statement.
- `paper/development_v13/figure_plan_v13.md:443-454` (figure-plan item 7) and `paper/development_v13/REPORT.md:96-99,129-130`.
- Rerun provenance: `scripts/rev_v12_t06_missingness_b.py` frozen panel/forcing/scoring; results under `results/v14_*/t06_harmonized/`; acceptance gate: mechanism (a) network Spearman ≈ 0.92–0.94 (frozen uniform-grid regime).

---

## 2. BiLSTM matrix row 0.28 vs 0.68 — Decision: relabel as "cross-instance BiLSTM-family transfer" and treat as illustrative only (adopt PLAN's relabel; do not keep only one instance)

### Evidence

- agent_a cell: `results/revision_v12/t05_model_matrix/agent_a/matrix_network_spearman.csv:6` — row `bilstm`, column `bilstm` = **0.28484848484848485** (10 networks; row is network-granularity).
- agent_b cell: `results/revision_v12/t05_model_matrix/agent_b/matrix_network_spearman.csv:7` — row `5_bilstm`, column `5_bilstm` = **0.6848484848484848** (10 networks).
- Both are cross-instance by design: row (source) = newly trained mask-aware BiLSTM, 12 networks × 3 seeds, early stopping; column (target) = read-only frozen `lstm_sensitivity_predictions.csv` (`agent_a/REPORT.md:13`: "new training: 12 networks x 3 seeds, early stopping on fitting-period validation (this analysis) | read-only lstm_sensitivity_predictions.csv (frozen BiLSTM)"; `agent_b/REPORT.md:22`, same structure). The 0.28-vs-0.68 gap is a convention difference (granularity/aggregation of the same cross-instance estimand), not a different target.
- Current treatment: manuscript §3.6 (`manuscript_v13.md:570-585`) still opens "its **self-transfer values** of 0.29-0.69 are cross-instance transfer, because the source is a newly trained mask-aware BiLSTM (12 networks, three seeds, median best epoch 68, 28% reaching the epoch cap) and the target is the older frozen bounded-run predictions (agent_a convention 0.28; agent_b convention 0.68 at the network level)"; §2.9 (`manuscript_v13.md:326-330`) relabels; editorial appendix item 7 (`manuscript_v13.md:916-923`) says "Adopted: relabeled 'cross-instance BiLSTM-family transfer' with both conventions reported" but mis-assigns the targets ("0.2848 (…, target = newly trained mask-aware BiLSTM) and agent_b convention 0.6848 (…, target = older frozen bounded-run predictions)" — both REPORTS show the target is the frozen instance in both agents). Ledger M2 (`evidence_ledger_v13.md:61`), terminology (`terminology_v13.md:46`), claim matrix (`claim_matrix_v13.md:147-148`: "NOT allowed: 'self-transfer of the BiLSTM'") already enforce the relabel. No same-instance BiLSTM cell exists in either artifact, so PLAN's "source and target must be the same instance" cannot be satisfied and the illustrative-only demotion is mandatory, not optional.

### Justification

Keeping one instance alone would be arbitrary: neither convention is canonical, and the two conventions bracket a genuinely seed/aggregation-sensitive quantity (agent_a `REPORT.md:166-169`: median best epoch 68, 28% epoch cap vs 93% for the frozen run; seed sensitivity documented). The relabel is already the v13 consensus across terminology, claim matrix, response letter, and ledger; the only unfinished work is (a) removing the vestigial "self-transfer values of" phrasing in §3.6, (b) stating illustrative-only status, and (c) fixing the reversed source/target parentheticals in appendix item 7. The neural row then carries no within-family claim, exactly as PLAN requires.

### Canonical values

None asserted: report both conventions as an illustrative range with labels — **0.28 (agent_a network-level convention) and 0.68 (agent_b network-level convention), i.e. cross-instance BiLSTM-family transfer 0.29–0.69**; no "self-transfer" anywhere for the neural family; no same-instance BiLSTM cell exists.

Relabeled sentence (replaces `manuscript_v13.md:571-575`; parallel wording for `manuscript_v13_b.md:105` if drafts are kept):

> "The bidirectional-LSTM row is reported as **cross-instance BiLSTM-family transfer** and is illustrative only: its apparent self cell (0.28 at the network level under agent_a's convention; 0.68 under agent_b's) compares a newly trained mask-aware BiLSTM source (12 networks, three seeds, early stopping; median best epoch 68, 28% reaching the epoch cap) with a different training instance as target (the older frozen single-seed bounded-run predictions, which hit its epoch limit in 93% of networks), so no cell is a same-instance self-transfer for the neural family, and no within-family claim is made from this row."

Also fix `manuscript_v13.md:581-584` (diagonal statement): "Overall, the diagonal (self-transfer, mean 0.783) exceeds the off-diagonal (mean 0.434; …)" → the diagonal comparison holds for the engineered block; the neural cell on that diagonal is cross-instance and the gap "is driven entirely by the neural and process rows" is retained only under the cross-instance label.

### Files to change

- `paper/development_v13/manuscript_v13.md:570-585` (§3.6), `:916-923` (appendix item 7: relabel sentence + fix reversed "target =" parentheticals).
- `paper/development_v13/manuscript_v13_a.md:569-577` and `manuscript_v13_b.md:105` (pair drafts, if retained as living text).
- Confirm no change needed: `terminology_v13.md:46`, `claim_matrix_v13.md:147-148`, `evidence_ledger_v13.md:61` (already relabeled).

---

## 3. Rolling-origin values — Decision: adopt the agent_b canonical subset-20 set everywhere — network Spearman **0.984 / 0.944 / 0.911** at 60/70/80% cutoffs, Kendall **W = 0.811** (tie-adjusted predicted ranks, 13 networks); replace the agent_a-based main text (0.947/0.922/0.949, W 0.917)

### Evidence

- Canonical (agent_b) artifact: `results/revision_v12/t07_rolling_origin/agent_b/REPORT.md:42-44` — "| 0.60 | 5240 | 13 | 0.776 | **0.984** | … | 0.70 | 8440 | 20 | 0.761 | **0.944** | … | 0.80 | 5550 | 20 | 0.795 | **0.911** | …" (pooled / network Spearman; placement-level pooling over all directly supported cells); `agent_b/REPORT.md:49-56` — "kendall_w_predicted_ranks: **0.811** (n_networks = 13)"; `agent_b/rolling_origin_rank_stability.csv:5` — `kendall_w_predicted_ranks 0.8107448107448108` on 13 networks; `agent_b/canonical_subset_crosscheck.csv:4-5` — 70%-cutoff subset-20 network Spearman 0.9443609022556391 identical for "from existing predictions" and "rerun" (frozen-pipeline inheritance: `agent_b/REPORT.md:16-18`, reproduces `confirmation_empirical_fit_losses.csv` to ~5e−16).
- Challenger (agent_a) artifact: `results/revision_v12/t07_rolling_origin/agent_a/rolling_origin_metrics.csv:2,4,6` — cutoff 0.6/0.7/0.8, scope `supported_only`, `curve_source=rebuild_10_per_season`, network_spearman 0.9472527472527472 (14 nets, n=324) / 0.9218045112781955 (20, 502) / 0.9488721804511278 (20, 549); `agent_a/rolling_origin_rank_stability.csv:2` — kendall_w 0.9169719169719169 on 14 networks (6 attrited). agent_a's own REPORT documents the different scope: rebuilt stress curves with 10 placements/season on supported station-gap cells vs the canonical frozen tables (`agent_a/REPORT.md:26`) and, on the frozen tables, its own 70%-subset value is 0.962 (`agent_a/REPORT.md:35`).
- Which is canonical per v13 editorial note: the evidence ledger designates agent_b: C5 row `evidence_ledger_v13.md:41` "… network Spearman 0.984/0.944/0.911; Kendall W 0.811 … Status: **retained (canonical agent_b values)**"; T4 row `:107` "canonical agent_b values in main text"; mirrored in `evidence_ledger_v13_b.md:44` (D1) and `:110` (K3). This matches v12, whose own claim matrix states "canonical values are the agent_b subset-20 design" (`paper/development_v12/claim_matrix_v12.md:19`) and whose manuscript text reports 0.984/0.944/0.911 with 13-network attrition and W 0.811 (`paper/development_v12/manuscript_v12.md:411-415`; `:556`).
- Where the conflict lives: the merged v13 main text switched to agent_a's levels — `manuscript_v13.md:471-477` "reproduced supported-only network Spearman of 0.947, 0.922, and 0.949 (the 60% leg attrites to 14 networks …) … Kendall's W of 0.81-0.92 across implementations (0.811, tie-adjusted, 13 networks, in the canonical implementation; 0.917 in the agent_a re-run)" — justified in appendix item 5 (`manuscript_v13.md:895-902`) by the claim that "The v12 manuscript reported 0.984, 0.944, 0.911 at 60/70/80% cutoffs; those values **could not be reproduced from the artifacts**." That rationale is false as stated: agent_b's artifacts reproduce them exactly (REPORT.md:42-44, rank-stability CSV), and both agents bit-reproduce the canonical 42-network 70% headline (0.934/0.922/0.864; `agent_a/REPORT.md:16`, `canonical_subset_crosscheck.csv:2`). The divergence is a pooling-scope difference (supported station-gap cells with 10/season rebuilds vs placement-level pooling over all directly supported cells from the canonical frozen tables), not a reproduction failure.
- Wording precedent: the merged response letter still quotes the canonical W — `response_letter_v13.md:447` "cutoffs (Kendall W 0.811)".

### Justification

The ledger's designation plus artifact traceability decide it. The agent_b set (i) is the one the v12 manuscript published and the ledger/response letter call canonical; (ii) inherits the frozen pipeline by construction and is cross-checked against the existing frozen confirmation predictions restricted to the same 20 networks (0.94436, `canonical_subset_crosscheck.csv:4-5`); (iii) pools ~5–17× more data per cutoff (8,440 vs 502 cells at 70%) with placement-level coverage of all directly supported cells; (iv) the merged text's reason for dropping it is demonstrably wrong, so publishing 0.947/0.922/0.949 would bake a false claim ("could not be reproduced") into the editorial record. W 0.811 on 13 networks is the tie-adjusted value from the canonical artifact; the "0.81–0.92 range" main-text compromise (which mixed conventions) is replaced by the single canonical W with the agent_a independent-run W 0.917 (14 networks) reported only in SI, matching evidence_ledger T4's intent ("canonical agent_b values in main text; re-run on one convention if reviewers object" — the unify decision resolves the "re-run if objected" branch now).

### Canonical values

Network Spearman **0.984 (60% cutoff, 13 networks, 5,240 cells), 0.944 (70%, 20 networks, 8,440 cells), 0.911 (80%, 20 networks, 5,550 cells)**; Kendall **W = 0.811** (tie-adjusted predicted-rank W across the three cutoffs, 13 networks present at all cutoffs; pairwise predicted-rank Spearman 0.802/0.808/0.538). Calibration slope 0.842/0.724/0.868, R² 0.596/0.499/0.608 (60/70/80). Every occurrence of both number sets in `paper/development_v13/*.md` (grep for 0.947|0.984|0.917|0.811|0.944|0.922|0.949|0.911; hits with rolling-origin meaning in **bold**; other hits are different quantities sharing a token — learning-curve full-history 0.944, missingness multi-block/uniform-matched 0.944, IQR endpoint 0.9441, 0.29–0.69-range adjacent 0.68/0.28, network Spearman 0.965/0.944 pairs):

| file | lines | content |
|---|---|---|
| `manuscript_v13.md` | **471-477** | main text §3.3: agent_a set + W range → replace with canonical set/W; **895-902** appendix item 5 → rewrite (delete "could not be reproduced"; canonical = agent_b set) |
| `manuscript_v13.md` | 479, 594, 604 | learning-curve 0.944; missingness 0.944 — no change |
| `manuscript_v13_a.md` | **471-475, 888-894** | agent_a draft mirrors of the above → update if kept as living text |
| `manuscript_v13_b.md` | **89, 149** | main text + note: already canonical (0.984/0.944/0.911, W 0.811; agent_a values as independent implementation) — no change |
| `evidence_ledger_v13.md` | **41** (C5: canonical set; fix garbled parenthetical "14 networks at all cutoffs; 60% leg attrites to 13" → 13 networks at all cutoffs, 7 of 20 attrited at 60%), **107** (T4) | no numeric change |
| `evidence_ledger_v13_a.md` | 41, 107 | mirror of C5/T4 — same fix |
| `evidence_ledger_v13_b.md` | **44** (D1), **110** (K3) | already canonical — no change |
| `response_letter_v13.md`, `_a.md`, `_b.md` | **447** | quotes W 0.811 — consistent; no change |
| `figure_plan_v13.md` | **426-429** | item 5: reports agent_a W 0.917 on 14 nets / agent_b W 0.811 on 13 as "divergence documented with both files" → canonical figure tables must consume agent_b values |
| `figure_plan_v13_a.md` | **422-423** | mirror → same |
| `figure_plan_v13_b.md` | **445**, **515-516** | 445 uses agent_a W 0.917; 515-516 instructs replacing "'13 networks / Kendall W 0.811' … by the artifact values (14 networks, W 0.917)" → revert instruction to canonical (13 networks, W 0.811) |
| `figure_plan_v13*.md` | 140/145 (0.9441 IQR), 439-463 (0.944 multi-block), 444 | different quantities — no change |
| `terminology_v13*.md` | 54 | learning-curve 0.944 — no change |
| `claim_matrix_v13*.md` | 157 | missingness 0.944 — no change |

### Files to change (rolling-origin)

- `manuscript_v13.md:225-235` (§2.5 Methods — currently describes agent_a's "10 placements per season" rebuild; rewrite to the canonical design: parameterized copy of the frozen pipeline, canonical inner 70/30 split, all directly supported cells, 20-network long-record subset), `:471-477` (§3.3), `:895-902` (appendix item 5).
- `figure_plan_v13.md:426-429`; `figure_plan_v13_b.md:445,515-516`; `figure_plan_v13_a.md:422-423`.
- `evidence_ledger_v13.md:41` (and `_a.md:41`) parenthetical correction.
- If figure/SI tables quote per-cutoff metrics: use `agent_b/rolling_origin_cutoff_metrics.csv` (per-network) + `agent_b/rolling_origin_rank_stability.csv`.

---

## 4. t10 RMSE transcription (0.631 CSV vs 0.694 note) — Decision: the correct value is **0.631** (7 d) and **5.755** (365 d); 0.694/5.271 is a typo confined to one interpretation note and its generator script; correct both

### Evidence

- 0.631 (CSV): `results/revision_v12/t10_covariance_fix/agent_a/mechanism_horizon_corrected.csv:2` — `realized_rmse 0.6310730210004103` (7 d; row 365 d = 5.755368…); identical value in `agent_a/mechanism_replication_check.csv:2`; `agent_a/REPORT.md:23` table row "| 7 | 0.475 | 0.379 | 0.544 | **0.631** | 0.165 | 0.156 |" and `:29` "| 365 | 0.565 | 0.451 | 4.719 | **5.755** | 4.268 | 5.190 |"; agent_b independently recomputed the same column: `agent_b/mechanism_recomputed.csv:2` contains the identical `0.6310730210004103` (`realized_rmse_mean`; its alternative placement-weighted pooled value is 0.7226, also ≠ 0.694).
- 0.694 (note): `results/revision_v12/t10_covariance_fix/agent_a/corrected_mechanism_interpretation.md:38-39` — "realized MAE rises from 0.544 to 4.719 degC and realized RMSE from **0.694 to 5.271** degC. … from 0.219 to 4.706 degC in RMSE scale." Hard-coded in its generator: `scripts/rev_v12_t10_covariance_fix_a.py:613`. The note's own remainders (0.219 = 0.694 − 0.475; 4.706 = 5.271 − 0.565) are self-consistent but wrong-endpointed; the CSV-consistent remainders are 0.156 (0.631 − 0.475) and 5.190 (5.755 − 0.565), as in `agent_a/REPORT.md:23,29` and the `remainder_rmse` column of `mechanism_horizon_corrected.csv`.
- Underlying artifact: `results/development_v11/reviewer_completion/mechanism_decomposition.csv` has **no RMSE column** (header L1: gap_length,n_stations,conditional_variance_lower_bound,simple_prediction,realized_loss,model_and_drift_remainder); `realized_loss` is the per-horizon mean of per-station **MAE** (7 d: 0.544406598163684), reproduced exactly by the t10 script (`rev_v12_t10_covariance_fix_a.py:104-147`, max|d| ~1e−16 at L145). The RMSE series is derived, not transcribed: `rev_v12_t10_covariance_fix_a.py:104-128` merges `DEV11/station_gap_outcomes.csv` × `nested_lono_predictions.csv` × `recovery_scoring/station_gap_summary.csv` (rows with `information_condition == B_union_D_union_M_union_H`, column `rmse_deg_c`), restricted to the 61 stations complete across all 7 horizons, and sets `realized_rmse = mean of per-station rmse_deg_c` (L126-127).
- Exact derivation (recomputed for this memo from those artifacts): on the 61-station complete subset, mean of per-station `rmse_deg_c` = **0.631073** (7 d), **0.798** (14), **0.989** (30), **1.188** (60), **1.490** (90), **2.849** (180), **5.755368** (365). The pooled sqrt-mean-square alternative on the same subset is 0.6798 at 7 d (0.6888 over all 217 rows); neither equals 0.694, and no artifact reproduces 5.271 (mean-rmse 5.755; pooled 6.29). So 0.694/5.271 is not any RMSE convention of this artifact set — it is a stray legacy pair in the note only.
- Current record: ledger T2 (`evidence_ledger_v13.md:105`) "0.631 used (CSV is the published column); resolve the note text before submission", K1 row `:76` prints 0.631→5.755; `paper/development_v13/REPORT.md:127-128` TODO 2; response letters "0.631 used, pending confirmation" (`response_letter_v13.md:653`, `_b.md:227`); claim matrices `:193` 0.631→5.755; `paper/development_v12/REPORT.md:75,121-130`.

### Justification

The 0.631/5.755 series is the only RMSE series derivable from the frozen artifacts (both adversarial agents compute the identical value independently), it is internally consistent with the `remainder_rmse` column and the REPORT table, and it is already the number used everywhere except one note. The 0.694/5.271 pair matches nothing derivable under any pooling convention and appears in exactly one prose location whose own figures of merit (0.219/4.706) shift with the endpoints. Typo correction is unambiguous and closes PLAN §8.6 TODO 3 and ledger T2.

### Canonical values

Realized RMSE by horizon: **0.631 / 0.798 / 0.989 / 1.188 / 1.490 / 2.849 / 5.755** (7/14/30/60/90/180/365 d; mean over the 61 complete stations of per-station-gap RMSE, `recovery_scoring/station_gap_summary.csv` `rmse_deg_c`, condition B∪D∪M∪H); RMSE-scale remainders vs conditional SD: 0.156 … 5.190.

### Files to change

- `results/revision_v12/t10_covariance_fix/agent_a/corrected_mechanism_interpretation.md:38-39` — correct the sentence to "… realized RMSE from 0.631 to 5.755 degC … from 0.156 to 5.190 degC in RMSE scale" (0.631 − 0.475 = 0.156; 5.755 − 0.565 = 5.190).
- `scripts/rev_v12_t10_covariance_fix_a.py:613` — same correction in the generator template (regenerate the note).
- Status-close in: `paper/development_v13/evidence_ledger_v13.md:105` (T2) and `_a.md:105`, `_b.md:109` (K2); `paper/development_v13/REPORT.md:127-128`; `response_letter_v13.md:653`, `response_letter_v13_b.md:227`; `paper/v14_plan/PLAN.md:413` (§8.6 item 3).

---

## Report-only items (no decision required)

1. **BiLSTM "0.29–0.69" / 0.28 / 0.68 range**: consistently relabeled as cross-instance everywhere — `manuscript_v13.md:326-330` (§2.9), `:570-575` (§3.6, vestigial "self-transfer values of 0.29-0.69" phrasing — handled by Decision 2), `:916-923` (appendix item 7, with the reversed source/target parentheticals — handled by Decision 2); `manuscript_v13_b.md:105,156`; `terminology_v13.md:46` (+ `_a/_b`); `claim_matrix_v13.md:138,147-148` (+ `_a/_b`); `evidence_ledger_v13.md:61` (M2) and `_b.md:53` (E2); `response_letter_v13*.md:315,332-333`; `figure_plan_v13*.md:439-440` ("self 0.285"). No other inconsistencies remain outside the Decision-2 fixes.

2. **"not externally verifiable"**: the phrasing is used consistently and matches PLAN §8.3's own endorsement (keep): `manuscript_v13.md:343-347` (§2.10: frozen = "internally frozen and hash-bound, but because their amendment and outcomes entered version control in the same commit they are not externally verifiable preregistration"); `manuscript_v13_b.md:21`; `claim_matrix_v13*.md:20`; `response_letter_v13*.md:132`. No change.

3. **28.9% passage (manuscript §3.4, `manuscript_v13.md:510-525`)**: internally consistent and artifact-backed. 8.6% = 124/1,446 (0.085754) with abstained-loss share 0.289257 (28.9%) in `results/revision_v12/t09_decision_utility/agent_a/abstention_curve_part1.csv` (surface_extrapolated rows); 28.9% = 652.9/2,257.2 °C (`figure_plan_v13_b.md:240`); the "1.33 C vs 5.27 C" under-prediction = 1.326/5.265 from `predictions.csv` (`response_letter_v13_b.md:162`); consistent restatements at `manuscript_v13.md:453,520-523,956`, ledger U5/D3 rows (`evidence_ledger_v13.md:53,95`), `terminology_v13.md:28,32`. No change.

## Deferred items

- Execution of the t06 unified rerun itself (a compute step, not resolvable from artifacts): the decision here fixes pipeline (agent_b), conventions (supported-unit scoring, mechanism set a–h minus e, NASA-POWER forcing (g) with the cached 12-network roster, or donor-proxy if new downloads are disallowed), and the acceptance gate; actual harmonized outputs land under a v14 results namespace.
- Provenance of the stray 0.694/5.271 pair: no artifact under any RMSE convention reproduces it; presumed legacy draft text. Correction specified in Decision 4 regardless.
- Token-level leftover surfaced by the conflict-3 grep (not one of the four PLAN conflicts): `figure_plan_v13.md:431` quotes agent_a learning-curve levels (0.678/0.881/0.965) while the canonical learning curve is agent_b's 0.608/0.872/0.916/0.938/0.944 (ledger C6, `terminology_v13.md:54`, `manuscript_v13.md:478-480`); fix when figure plans regenerate.
- The "not externally verifiable" wording and all 28.9%/8.6% passages were checked against artifacts; the loss-share arithmetic (652.9/2,257.2) is quoted from the figure plan, not recomputed from the raw placement file.
