# Attribution round, 2026-10-20b

This round answers the second simulated review of 2026-10-20 (commit
`e7fc9050df3d215afa7aa60d0c1410bbadc4c83f`). That review accepted the aligned-policy
chain of `major_revision_20261020/` and asked a different question: *which design
element earns the result, and does the mechanism the paper names explain the error?*
The point-by-point answer is `paper/wrr/RESPONSE_TO_REVIEW.md`.

Nothing here refits or overwrites an earlier artifact. Panels, thresholds and
cross-fitted scores are read from `major_revision_20261020/`; the only earlier script
edited is `scripts/335` (Figure 3: see "Errors in our own text" below).

Run the whole round with `make wrr-round-20261020b` (a few minutes on a 128-core
machine; the ladder runs 66 cross-fit tasks in a process pool).

## What was done

| step | script | output |
|---|---|---|
| what each design contains and identifies | `scripts/340_wrr_design_audit.py` | `r2_01_design_audit/` |
| one learner, information added in layers; oracle bound | `scripts/341_wrr_same_capacity_ablation.py` | `r2_02_same_capacity_ablation/` |
| three windows, exact error identity, interventions | `scripts/342_wrr_three_window_decomposition.py` | `r2_03_three_windows/` |
| hot-year refusal against a hot-year-blind null; abstention cost | `scripts/343_wrr_hot_year_selection_null.py` | `r2_04_hot_year_null/` |
| does the gap calendar say whether to screen? | `scripts/344_wrr_screening_need_rule.py` | `r2_05_screening_need/` |
| Figures 4 and 5 | `scripts/345_wrr_figures_r2.py` | `r2_06_figures/` |
| supporting-information tables (no hand-typed cell) | `scripts/346_wrr_si_tables_r2.py` | `paper/wrr/si_r2_tables.tex` |
| claim registry, bound to artifacts and to the manuscript text | `scripts/347_wrr_claim_registry_r2.py` | `claim_registry.csv`, `claim_binding_check.json` |

## What the round found

1. **The designs are not the factorial the text described.** Of the 53,721 outages,
   33,749 are single contiguous runs of 14 to 270 days placed at a requested overlap
   with the *climatological* window and 19,972 are transplanted real geometries; no
   scattered days exist. Gap length and the true hidden share correlate at +0.52 in
   them, +0.71 in the real replay, and +0.14 (0.00 against the climatological overlap)
   only in the separately generated crossed panel (1,899 outages, 211 station-years,
   12 networks, all nine cells in every station-year). The 418 replay groups rest on
   59 recorded gaps and 67 target station-years.
2. **The fitted score does not need the support feature.** One learner, nested
   cross-fit, three seeds, two panels; the full specification reproduces the aligned
   round's score bit for bit. External retention at the 5 % cap:

   | model | external | development |
   |---|---:|---:|
   | gap and season | 63.2 % | 58.7 % |
   | + donor information | 68.7 % | 62.4 % |
   | + reconstruction diagnostics | 74.0 % | 70.2 % |
   | + station history (generic) | 73.4 % | 70.4 % |
   | + peak-window share (fitted score) | 73.9 % | 70.5 % |
   | peak-window rule | 66.6 % | 60.4 % |

   The share adds +0.3 to +0.8 points externally (every interval includes zero). A small
   logistic model does need it (+6.2 to +6.8 external, +11.4 to +16.3 development). An
   oracle that reads the true hidden share adds only 0.6 to 1.8 points to the fitted
   model, but 5.0 to 5.9 points to the transparent rule.
3. **The error splits exactly.** `H30(completed) − H30(truth) = ē_S + F`, `F ≥ 0`
   (verified to 2×10⁻¹³ °C on 9,449 cases): a hiding channel and a false-peak channel
   of opposite sign. The "misaligned minus aligned" contrast falls from 0.66 to 0.19 °C
   (climatology) once the true hidden share is held fixed; residual persistence is
   12 to 27 % of the error, the gap-mean offset 49 to 59 %.
4. **Refusing hot years is not a hot-year harm.** The fitted score refuses 24.5 % of true
   hot years and 25.5 % of all records (excess −1.0 point [−1.6, −0.3]). A screen
   pays only if an abstention costs under about 0.046 of a wrong judgement.
5. **Most real networks need no screen, and the pooled rate hides which.** Two to four
   of 14 networks fail at 7 to 83 %. A composition rule built on designed outages
   predicts the pooled 3.5 % (observed 2.6 to 4.1 %) and never says "no screen" for a
   failing network, but it rests on 3 to 6 station-years per failing network and is
   reported as a description.

## Errors in our own text, found while answering the review

The abstract, §2.3 and the intro said the 53,721 outages vary length and support
independently with scattered extra days and lengths {30, 60, 90, 180}; the generator
does none of this. §2.3's "+0.45 observed in real records" was the pooled designed
value. Figure 3b used a different estimator from the text's numbers, and the two
disagree about whether climatology has a length effect (the station-year-paired
estimate is 0.12 °C [0.06, 0.18] at a true share of at least 0.9). Figure 3c dropped
the exact-zero hidden-share class and listed a reconstructor with no series on the
external panel. A sentence the 2026-10-20 audit had recorded as fixed (the ordering of
the five methods at 90 days) was still in the text and false. The peak-window rule's
external retention is 66.6 %, not 66.7 %. All are corrected; `scripts/335` carries the
Figure 3 fixes.

## Evidence identity

Nothing here is a sealed confirmation. The external panel is opened and every
comparison is a local cross-fit; the real replay is a development-period probe on 59
recorded gaps; the crossed panel is 211 station-years from development networks; the
residual interventions are numerical experiments on recorded residuals; the
composition rule's cell edges were fixed after the replay's per-network summaries had
been seen.

## Not done

Frozen-model transfer to another agency, risk control by hydrological type and in
anomalous years, an anomalous-event replay, and an implementation of the
uncertain-support design all need data or a sealed panel the archive does not contain.
The manuscript says so in its limitations.

## Verification

* `python -m pytest tests -k wrr` exit 0 (including `tests/test_wrr_attribution_round.py`).
* `python scripts/223_wrr_build.py` builds the article (37 pages double-spaced, 20
  pages in the published layout), the SI (23 pages), and passes the AGU desk checks
  (3 key points <= 140 characters, abstract 249 words, plain-language summary 196
  words, 92 headline numbers present, 27 references all cited and rendered).
* `scripts/347` binds 35 numbers in the text to the artifacts that produce them.
* The build stays `NOT submission-ready` until the author block is filled by a human.
