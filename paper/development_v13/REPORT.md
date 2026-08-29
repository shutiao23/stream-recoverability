# REPORT — revision v13 manuscript package (merged, adversarial pairs)

Status: complete. This package responds to the simulated WRR review
(Major Revision at the Reject-and-Resubmit boundary) returned on the v12
manuscript (`paper/development_v12/`). It was produced by 7 adversarial
pairs (14 Agent Manager sessions, model DeepSeek V4 Flash / variant max):
each pair produced two independent versions; the canonical values below
were re-verified by the senior reviewer directly against the artifacts and
the pairs were merged into the final files.

## Deliverables (final, in `paper/development_v13/`)

| File | Status | Notes |
| --- | --- | --- |
| `manuscript_v13.md` | final | 975 lines; abstract 249 words; intro 5 paragraphs / 3 RQs; results reordered (strongest baseline → support/duration → within-network stability → decision → downstream → model boundaries → missingness); discussion with 4 judgments; conclusions without "strongest screen"; figure captions; editorial note listing artifact-vs-review discrepancies |
| `aux_text_v13.md` | final | 3 Key Points (≤140 chars each); Plain Language Summary with corrected wording |
| `figure_plan_v13.md` | final | 5 main figures (Fig2 = strongest-baseline comparison with r6 as primary comparator; Fig4 = coverage–regret; Fig5 = downstream multi-baseline) + SI list; evidence-provenance conventions; sources incl. `results/revision_v13/` outputs |
| `claim_matrix_v13.md` | final | 3 top-level claims (C1 predictive validity; C2 applicability boundaries; C3 decision utility at prespecified coverage), evidence mapping, "NOT made" list, reporting order |
| `terminology_v13.md` | final | frozen labels incl. `station x horizon historical mean`, `cross-instance transfer`, `loss-targeting utility`, `coverage floor`, `interpolation-capable support-aware risk surface` |
| `protocol_v4.md` | final | 998 lines; replaces v3; primary endpoint = fixed-coverage network-balanced selection-regret difference vs deployable nested-CV selector; coverage floors ≥50% units / ≥60% networks (70% target); simulation-based power on the regret endpoint; registration workflow; appendices |
| `response_letter_v13.md` | final | point-by-point responses to Major Comments 1–10 + writing/figure/data comments + requirement→deliverable mapping + open items |
| `evidence_ledger_v13.md` | final | every headline number with source artifact, v13 value, status (retained/corrected/re-verified/demoted/removed/relabeled), evidence role, and location |
| `manuscript_v13_{a,b}.md` etc. | pair raw outputs | independent adversarial versions, kept as pair records |

## New analyses (in `results/revision_v13/`)

### 1. Strongest-baseline harmonization (`strongest_baseline/agent_{a,b}/`)

The definitive empirical-vs-station×horizon-mean (r6) comparison on
identical units. Both implementations agree **bit-for-bit** and match the
senior reviewer's independent computation:

- Direct 874 units (second panel): empirical pooled 0.9453 / network
  0.8049 / slope 0.9383 vs r6 pooled 0.9424 / network 0.7632 / slope
  0.9235; predictor Pearson correlation 0.9917 (Spearman 0.9959).
- Paired network bootstrap Δρ = +0.0412, 95% CI [-0.0004, +0.1140]
  (seed-42 run; seed-0 matches the t03 canonical artifact +0.0417
  [-0.0006, +0.1154]); win fraction 0.97. Pooled-level Δρ = +0.0028.
- First panel direct 858: network Δρ +0.0024 (CI [-0.0237, +0.0274]);
  pooled Δρ +0.0002 — indistinguishable.
- Per horizon (empirical vs r6 network Spearman): 0.932 vs 0.938 (7 d),
  0.916 vs 0.915 (30 d), 0.865 vs 0.843 (90 d), 0.659 vs 0.603 (180 d):
  the increment is concentrated at 90–180 d; r6 is equal or better at
  7–30 d.
- Within-network: empirical 0.9359/0.9650 vs r6 0.9298/0.9676
  (network-demeaned pooled / median within-network) — not separable.
- Panel composition verified: second = 57 (US 32 / CZ 15 / NO 10; 224
  stations, 1,446 units, 874 direct); first = 42 (1,440 units, 858
  direct). The v12 "35 US" statement is confirmed as a bug and corrected.

### 2. Decision + downstream harmonization (`decision_harmonization/agent_{a,b}/`)

- **Coverage–regret curves** (Part A): reproduced the t09 anchors
  exactly (no-abstention proposed 0.0850 vs best fixed/global CV 0.0815,
  per-network CV 0.0383; support-any+ambiguity abstention 0.0067 at 8.5%
  coverage, 123 units, 8 networks). New fixed-coverage curves over
  c = 0.1–0.9 (+0.5/0.7) under three confidence criteria (ambiguity
  margin, mean width, support completeness) for proposed / best fixed /
  global CV / per-network CV / gap rule / random / oracle, with
  network-balanced and pooled regret, selection accuracy, top-2 hit,
  abstention cost. Finding: at 50–70% coverage the proposed selector is
  only marginally better than best-fixed/global CV (e.g., 70% ambiguity
  margin: 0.098 vs 0.108) and per-network CV remains stronger; the 8.5%
  result does not generalize — consistent with the review's position.
- **Downstream multi-baseline** (Part B): verified both implementations.
  vs no-fill: reconstruction error ratios 0.124 (annual mean), 0.138
  (degree days), 0.126 (trend), 0.30 (p90), 0.33 (amplitude), 0.34
  (days>20C). vs climatology: reconstruction ≈ climatology for annual
  mean (0.889 ratio), degree days (0.925) and days>20C (0.995), WORSE for
  days>25C (1.255) and summer max (1.319). Budget vs climatology default:
  risk policy negative for summer mean (-0.23), amplitude (-0.34), phase
  (-0.11); only annual mean positive (+0.022). Both-baseline reporting
  implemented in the manuscript (3.5); interpolation default noted as not
  computable from existing artifacts (flagged in the divergence note).

## How the review's 10 Major Comments are addressed (summary)

1. **Strongest baseline**: r6 (station×horizon historical mean) is now
   the primary comparator in Abstract, Key Points, Fig 2, claim matrix,
   and protocol v4; the +0.55-vs-simple result is demoted to secondary.
2. **Second panel provenance**: evidence-role labels (frozen / post-hoc
   v12 / v13 harmonization / preregistered) appear in Methods, Fig 1,
   and every results section.
3. **Triage**: reported as a negative diagnostic ("loss-targeting
   utility"), not end-to-end decision utility; empirical predictor stays
   the worst non-random policy.
4. **Model selection**: coverage floors (≥50% units / ≥60% networks;
   70% target) in protocol v4; the 8.5% result is labeled a proof of
   concept on non-random networks.
5. **Downstream baseline dependence**: both no-fill and climatology
   defaults reported; incremental-benefit framing B = D(default) −
   D(model) − λC adopted.
6. **BiLSTM**: relabeled "cross-instance BiLSTM-family transfer";
   common-panel requirement in protocol v4 (same-instance source=target
   rule).
7. **Missingness matrix**: demoted to SI with the implementation
   divergence documented (0.979 vs 0.490; 5/12 shared networks; uniform
   0.531 vs 0.944 as a second conflict); neither value is cited as
   evidence in the manuscript.
8. **Surface**: labeled "interpolation-capable"; 365-day extrapolation
   flagged and abstained (46.8% coverage); extrapolation abstention is
   the required policy.
9. **Persistence law**: the headline claim is restated as persistence of
   local recovery difficulty, with modest seasonal increment; the Design
   is defined as a framework (stress → support-aware risk → selection →
   incremental benefit).
10. **Hydrologic significance**: downstream section restructured around
    multiple untreated baselines and incremental benefit.

## Verified corrections vs v12

- Second-panel composition corrected to US 32 / CZ 15 / NO 10 (= 57).
- Paired Δρ vs r6 CI corrected to [-0.0006, +0.1154] (straddles zero;
  the v12 text [0.0001, 0.1117] implied exclusion).
- Triage point estimate harmonized to the bootstrap values
  (0.337/0.512; paired -0.174 [-0.198, -0.140]).
- Missingness shared-panel count verified at 5 networks (manuscript
  merged version uses 5; one agent draft said 6 — corrected).
- Abstract trimmed to 249 words; Key Points ≤140 chars; plain-language
  wording fixed ("held-out artificial gaps in later years"; "57 networks
  that were not used to develop the original frozen predictor").

## TODO before submission (carried from v12 + v13)

1. Archival DOI (Zenodo/OSF) — mandatory; date-gated deposit workflow in
   Open Research and the response letter.
2. t10 RMSE transcription: 0.631 (canonical CSV) vs 0.694 (one
   interpretation note) at 7 d — confirm against the published column.
3. t06 missingness harmonization: re-run one 12-network panel with one
   forcing definition before any matched-transfer value can be evidence.
4. t07 convention divergence: canonical subset-20 values used; document
   the pooling difference if reviewers object.
5. Learned-model increment reconciliation (0.701→0.704 vs 0.7323→0.7432).
6. Figure renderings from `figure_plan_v13.md` sources (none drawn yet).
7. Bibliography regeneration (same citekeys as v12, all in
   `paper/references.bib`).
8. Length check (975 lines; trim Methods/SI if the journal limit binds).
9. Protocol v4 external registration (pre-outcome commit + OSF/Zenodo)
   before any third-panel outcome.
10. Interpolation-default downstream leg: not computable from existing
    artifacts; must be scored in the harmonized panel.

## Session records

14 Agent Manager sessions (7 pairs, model DeepSeek V4 Flash / variant
max, local mode): manu_a/b, fig_a/b, claim_a/b, proto_a/b, sbase_a/b,
dec_a/b, resp_a/b. Pair outputs retained under `paper/development_v13/*_{a,b}.md`
and `results/revision_v13/*/agent_{a,b}/`.
