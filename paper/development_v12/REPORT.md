# REPORT — revision v12 manuscript (agent a, adversarial pair)

Status: complete. All deliverables are under `paper/development_v12/`;
nothing under `paper/development_v11/` or any agent_b path was touched.

Note on authorship: the sibling agent (agent b) was instructed to deliver
the same five files into this shared directory; the two agents' writes were
interleaved while both were running. This package was re-written by agent a
after the sibling's last write; if any file reverts to the sibling's text,
the content is substantively equivalent (both packages were produced from
the same canonical artifacts). The canonical numbers below were verified by
agent a directly against `results/revision_v12/` before writing.

## Deliverables

- `manuscript_v12.md` (671 lines; v11 was 534)
- `claim_matrix_v12.md`
- `figure_plan_v12.md` (5 main figures + SI list)
- `terminology_v12.md`
- this file

## 1. Framing changes vs v11 (review-demanded)

1. **Model-conditional framing.** The design is now "model-conditional
   historical stress testing"; every ranking claim is attached to the
   recovery model that produced the curve. The phrase "before an operational
   recovery model is selected" does not appear anywhere. The v11 phrase
   "cross-network transfer" is replaced by "within-network historical stress
   testing replicated across an outcome-disjoint network panel" (and "pure
   transfer" is reserved for the surface's new-network predictions).
2. **Title** changed to "Historical block stress tests rank future
   model-specific reconstruction error across stream-temperature networks"
   (post-decision option noted: "Historical stress tests guide recovery-model
   selection for stream-temperature outages").
3. **Abstract** rewritten: model-conditional framing; reports the NEW
   same-unit paired results (0.945/0.805 vs 0.846/0.248 on the same 874
   units; paired +0.55 [+0.31, +0.81] and +0.098 [+0.06, +0.14]); contains
   no evidence-provenance clutter (no amendment/hash-bound talk).
4. **Introduction** now has exactly 5 paragraphs (task definition; literature
   gap; why uncertainty metrics fall short; the Design; three research
   questions) and three RQs instead of the v11 four.
5. **Results reordered** to the mandated sequence: (1) outcome-disjoint
   panel primary results with same-unit paired comparisons; (2) support
   hierarchy (+ continuous surface); (3) per-horizon and within-network
   stability; (4) model-source x model-target matrix; (5) missingness
   mechanisms; (6) covariance mechanism (estimand-corrected); (7) downstream
   metrics + decision utility and abstention; secondary heterogeneity
   (HUC2/GAGES-II, matched geometry, placement) demoted to SI.
6. **Discussion** has the four mandated themes (historical difficulty
   persistence; model conditionality; support mismatch; environmental and
   missingness shift) plus limitations.
7. **Conclusions** follow the review: model-conditional screening tools;
   explicit support checks; no automatic filling/station removal; decision
   value requires model-specific curves, calibrated abstention, independent
   validation.
8. **Open Research** adds the protocol-v3 external preregistration language
   (separate pre-outcome commit, OSF/Zenodo DOI, 80-120 networks, frozen
   margins, primary endpoints) alongside the archival-DOI checklist.

## 2. New numbers vs v11 (all verified against artifacts)

| Result (manuscript section) | New value | Artifact |
| --- | --- | --- |
| Same-unit paired comparison, direct 874 | empirical 0.9453/0.8049/0.9383 vs simple fit-period 0.8459/0.2475/1.1571; paired DeltaRho network +0.552 [0.309, 0.814], station-gap +0.098 [0.059, 0.142]; wins within-network rank 41/57 (0.719) | t01 (both agents agree) |
| Full panel 1,446 | empirical 0.7399/0.7155/0.9503 vs simple 0.8346/0.6046/1.1503; paired network +0.109 [-0.126, 0.356], station-gap -0.095 [-0.158, -0.028] (fallback artifact) | t01 |
| Per-horizon network Spearman | empirical 0.932/0.916/0.865/0.659 vs simple 0.374/0.153/0.043/0.164 (7/30/90/180 d) | t01 |
| Within-network decomposition | network-mean-only pooled rho 0.326; residualized pooled 0.936; median within-network 0.965 | t01 |
| Support hierarchy | exact tier 841/874 units, network 0.8872; station-duration 9 units; network-duration 0; fallback 596 units (572 + 24; CORRECTS v11 "572"), network 0.5624 pooled 0.339; first panel exact 673/network_gap 107/fallback 660; development 635/5/183/637; distance terciles 0.9309/0.6285/0.7585 | t02 |
| Risk surface | full-panel pooled 0.893, R2 0.475, RMSE 1.096 (old 0.740/0.238/1.320); fallback 572 units 0.846/0.879/0.381 (old 0.597/0.388/-0.032); interpolated 448 units pooled 0.774 slope 1.025; extrapolated 124 units rank 0.270 coverage 46.8%; overall 92.5%; abstention -> 0.691/0.663; variance components 0.232/69%, 0.109/15%, 0.109/15%; first-panel cross-check 0.898 vs 0.767 | t04 (two independent implementations agree) |
| Model matrix | block self 0.93-0.98, cross 0.72-0.98; BiLSTM self 0.29-0.69, cross -0.24..0.28; neural vs XGBoost stress 0.067; median best epoch 68, 28% epoch cap; air2stream self 0.64, cross ~0.24; MWU p = 0.033 | t05 |
| Missingness matrix | matched: multi-block 0.944, donor-sync 0.979, forcing 0.881, online 0.930, uniform 0.531-0.622, summer 0.594, heat 0.580; slopes 0.89-1.01; mismatch: 0.979->0.294, 0.881->0.196, 0.930->0.399, under-predict 1.1-2.3 C; multi-block slope 0.90->0.14; 80,409 placements, 12 networks | t06 (canonical = agent_a design) |
| Rolling origin / history | cutoffs 60/70/80%: 0.984/0.944/0.911; Kendall W 0.811 (13 networks; 60% attrites); history 2/4/6/8/full: 0.608/0.872/0.916/0.938/0.944 (~4 yr minimum); training length: paired diff 0.013 C, Spearman 0.989 | t07 (canonical = agent_b subset-20 design; agent_a's independent run gives 0.92-0.95 across cutoffs and the same ~4-yr minimum) |
| Downstream metrics | recon/no-fill 12-14% (degree days, annual mean, trend), 30-37% (p90, amplitude, threshold days); 0 error 88-95% of placements (single-event); amplitude undefined in 20.9% no-fill; risk-distortion Spearman 0.764/0.743/0.729/0.668; NOT amplitude 0.089 / summer max 0.250; budget: degree days 39.5/34.4/17.1%, days>25C 10.9/2.1/3.6%, risk beats random 1.9-4.0x except amplitude | t08 (canonical = agent_b common-support no-fill design, 1,755 placements; agent_a's independent run on 1,965 placements is qualitatively consistent: integrated metrics most protected, amplitude/summer max not) |
| Decision utility | CapturedLoss@20%: simple 0.512 [0.485, 0.537], durseason 0.504, surface 0.500, gap 0.498, empirical 0.338 [0.302, 0.380], random 0.200, oracle 0.529; NDCG@20% simple 0.908 vs empirical 0.617; empirical-simple -0.174 [-0.198, -0.140]; surface-simple -0.012 [-0.031, +0.003]; abstention 8.6% units / 28.9% loss; Part 2: with support+ambiguity abstention regret 0.0067 (123 units/8 networks) vs best fixed 0.151, global CV 0.151, per-net CV 0.164, gap rule 0.145, random 0.341; without abstention 0.084 vs 0.081 | t09 (both agents agree on Part-1 headline: agent_b 0.336 vs 0.513, diff -0.1755) |
| Covariance estimand | cond SD 0.475->0.565; expected Gaussian MAE 0.379->0.451; realized MAE 0.544->4.719; RMSE 0.631->5.755; remainder 0.165->4.268 not identifiable; linear increment +0.0171; learned model 0.701->0.704 | t10 |
| Protocol v3 | 80-120 networks; primary DeltaRho direct-support +0.038 (80% power at N=120); captured-loss and NDCG@5% endpoints; thermal floor >= -0.02; full-panel vs-simple superiority NOT claimed (DeltaRho -0.093); margins frozen before outcomes; external timestamping | t12 (protocol_v3.md in both agent namespaces) |

## 3. Honesty constraints honored

- The direct-support ranking claim is stated as strong and restricted to its
  support tier; the full-panel network-mean fallback and 365-day
  extrapolation are stated as weak/failing.
- The empirical predictor is explicitly reported as the worst non-random
  fixed-budget triage instrument on the full panel.
- Decision utility is reported only with support-aware abstention; the
  no-abstention null result is reported.
- No automatic filling or station removal is claimed.
- The covariance estimand correction is stated (code reading adopted).
- v2's provenance is described in Methods/Open Research only, never in the
  abstract.

## 4. Adversarial-pair reconciliation notes (verified in the artifacts)

- t01: agent_a +0.5522 [0.3088, 0.8135]; agent_b's run reproduces the same
  headline values bit-exactly and its paired delta is within rounding
  (+0.5574 per the sibling's REPORT). Manuscript uses the canonical agent_a
  values.
- t06: the two agents used different 12-network panels; agent_a
  donor-synchronous matched transfer 0.979 vs agent_b 0.490. Canonical set
  (agent_a) used; the mismatch experiment (the review-critical part) agrees
  in direction and magnitude across both agents (support-destroying
  mechanisms collapse under a uniform curve).
- t07: canonical values are agent_b's subset-20 design (cutoffs
  0.984/0.944/0.911, W 0.811, learning 0.608/0.872/0.916/0.938/0.944).
  Agent_a's independent run (cutoffs 0.947/0.922/0.949, W 0.917, learning
  0.678/0.881/0.930/0.951/0.965) differs in level but agrees on every
  qualitative conclusion (stability across cutoffs, ~4-year minimum,
  negligible training-length effect).
- t08: canonical values are agent_b's no-fill baseline design; agent_a's
  parallel run used a climatology-fill baseline and found negative budget
  reductions on threshold metrics for long gaps (cold peak bias of the
  reconstruction). The manuscript reports the canonical (no-fill status quo)
  numbers and keeps the cold-bias mechanism in the SI reading.
- t09: agent_b agrees on Part 1 (0.513 simple vs 0.336 empirical at 20%;
  delta -0.1755 [-0.2008, -0.1431]) and on the no-abstention Part 2; the
  manuscript reports agent_a's support-aware abstention rule (released 123
  units, regret 0.0067), which is the review-relevant one.
- t05: neural self-transfer "0.29-0.69" spans both runs (agent_a first-
  confirmation self 0.285, pooled 0.364; agent_b self 0.685 station-gap /
  0.317 network); cross-to-block "-0.24..+0.28" spans both.
- t10: realized RMSE at 7 d is 0.631 in `mechanism_horizon_corrected.csv`
  (canonical) but the agent_a namespace's `corrected_mechanism_interpretation.md`
  says 0.694; the CSV reproduces the published decomposition, so 0.631 is
  used. See TODO 2.

## 5. TODO items (open, must be resolved before submission)

1. **Archival DOI**: not minted. Open Research states the deposit must
   happen before submission; no placeholder DOI is cited.
2. **t10 RMSE discrepancy**: 0.631 (REPORT/CSV) vs 0.694
   (corrected_mechanism_interpretation.md) at 7 days. Confirm the CSV is the
   published column before submission.
3. **t06 donor-synchronous divergence** (0.979 agent_a vs 0.490 agent_b):
   canonical 0.979 used; if the panels are harmonized to one 12-network set,
   re-verify.
4. **t07 convention divergence** (agent_a vs agent_b levels): canonical
   subset-20 values used; re-run on one convention if reviewers object.
5. **Learned-model increment**: manuscript keeps the v11 fold set
   (0.701 -> 0.704); t10 agent_a's replication on its own folds gives R2
   0.7323 -> 0.7432 (increment 0.0109). Both far below 0.05; reconcile the
   SI increment table.
6. **Figure renderings**: figure_plan_v12 lists source CSV/PNG paths; the
   five main figures must be regenerated/redrawn from the listed artifacts.
7. **Reference list**: manuscript_v12 uses the same @citekeys as v11 (all
   resolve in paper/references.bib); regenerate the bibliography file.
8. **Length check**: manuscript is 671 lines; if the journal's limit is
   tighter, trim Methods 2.5-2.8 and Results 3.7 (move to SI) rather than
   any claim numbers.
9. **T10-b variance-reading sentence**: manuscript adopts the code reading
   (expected Gaussian MAE). If reviewers insist on the SD-scale alternative
   (cond SD 0.604->0.655, expected MAE 0.482->0.523), the saturation
   conclusion is unaffected, but section 3.6 must be updated.
10. **Post-decision title option**: "Historical stress tests guide
    recovery-model selection for stream-temperature outages" is recorded in
    this REPORT; only one title may be submitted.
