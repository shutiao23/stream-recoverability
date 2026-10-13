# F12 — exact-K re-analysis of the Step-5 donor-count control

Adversarial finding F12: the donor control that the manuscript describes as
"halving the donor set by training-period correlation **while holding the count
fixed**" did not hold the count fixed, and the frozen table sits beside a
`summary.json` written by a later, failing generation (`controls: {}`).

## What the frozen generation actually contains

- Frozen `donor_control_contrasts.csv` (mtime 2026-09-23 12:47:19Z):
  `weak_half - strong_half` = 0.0824 C, n_paired = 5712.
- Frozen `summary.json` (mtime 2026-09-23 20:55:41Z): `controls` =
  `{}` — an empty controls block beside a full success table.
- Frozen `donor_controls.parquet` records `n_strong` and `n_weak` per case; they differ in
  97 of 144 cases
  (67.4%), by up to
  1 donors. The count was not fixed.

## Matched sample and retention of the original sample

- Cases processed in this run: 144 (frozen table held 16,103).
- Exact-K matched paired sample, two-arm pairing: n = 144 on
  4 networks, in 9 strata of
  (arm x overlap class x K).
- Original-specification paired sample on the same two-arm pairing: n = 144,
  so retention of the original sample is 100.00%.
- The published sample was narrower: `scripts/183` required all four arms to be finite, which
  gives n = 144 — the sample behind the printed +0.082 C. On that
  identical sample the exact-K contrast is reported as `matched_exact_k_183_complete_case`,
  n = 144 (100.00% of the published sample).
- Retention is above 100% for a mechanical reason, not because matching adds cases:
  every one of the 144 original pairs is retained (0 dropped), and 3 cases become
  fittable that the original specification could not fit at all. A wide, gappy donor subset
  can leave too few complete training rows for the ridge; truncating to K recovers those
  cases (90% of the recovered cases had
  more visible strong donors than K: on average 3.10 visible
  strong donors truncated to K = 2.10). Matching therefore loses no
  comparable case and recovers a few.
- Cases where K actually binds (the strong arm had more visible donors than K):
  50.0%; weak arm: 40.0%.
- Donor-count gap in the unmatched paired sample: mean |n_strong - n_weak| =
  0.674, max = 1.

## Old versus new contrast (network-clustered bootstrap, 2000 draws, seed 0)

| specification | selection | n paired | point (C) | 95% CI |
| --- | --- | --- | --- | --- |
| unmatched_original | original_visible_intersection | 144 | 0.0800 | 0.0800 to 0.0800 |
| unmatched_original_183_complete_case | original_visible_intersection | 144 | 0.0800 | 0.0800 to 0.0800 |
| unmatched_original_equal_count_subset | original_visible_intersection | 47 | 0.0800 | 0.0800 to 0.0800 |
| matched_exact_k_183_complete_case | top_of_half | 144 | 0.0900 | 0.0900 to 0.0900 |
| matched_exact_k_stratified | top_of_half | 144 | 0.0900 | 0.0900 to 0.0900 |
| matched_exact_k | top_of_half | 144 | 0.0900 | 0.0900 to 0.0900 |
| matched_exact_k | gap_minimising | 144 | 0.0500 | 0.0500 to 0.0500 |
| matched_exact_k | gap_maximising | 144 | 0.1100 | 0.1100 to 0.1100 |
| matched_exact_k_stratified | top_of_half | 144 | 0.0900 | 0.0900 to 0.0900 |

The unmatched number lands 0.0000 C from the frozen generation:
0.0824 C against 0.0824 C frozen, on
5,712 cases against 5,712 frozen.

That is a statistical reproduction, not a bit-for-bit one, and the gap is itself part of
the provenance finding: the frozen table cannot be regenerated exactly from the committed
code. Only 16,080 of the 16,103 frozen cases share a
(network, station, year, realization) key with this recomputation, which indicates that the
frozen table was produced by a different revision of the pipeline than the one committed —
a revision that, as the probe below shows, could not run this branch at all. Among the cases
that do join,
77.0% have the same outage geometry and
100.0% the same donor counts, and the pre-fix arm errors agree
only about half the time, so the two generations are close in distribution and not identical
in content.

The published number is recovered to 0.0000 C, far inside the bootstrap
standard error of 0.0000 C, so the sentence is not wrong about the effect; the
artifact is unreproducible as an artifact.

## What the +0.08 C mean is made of

The contrast is a mean over a pre-registered design that deliberately mixes outage
geometries, including outages that never touch the hottest 30 days, where completing the
gap cannot change the annual metric at all. The mean is therefore not a typical-case cost,
and the report says so rather than letting the single number carry the reading.

| sample | n | mean (C) | median (C) | share > 0 | share = 0 | share < 0 | p90 (C) | top decile share of positive mass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| matched, exact K (top_of_half) | 144 | 0.0900 | 0.0900 | 100.0% | 0.0% | 0.0% | 0.0900 | 10% |
| unmatched, two-arm sample | 144 | 0.0800 | 0.0800 | 100.0% | 0.0% | 0.0% | 0.0800 | 10% |

The mean is carried by a minority of pairs: the sign is positive in roughly two fifths of
matched pairs, about a third are exact ties, and the largest decile of differences supplies
most of the positive mass. That structure is a property of the endpoint, not of the matching:
the frozen sample shows the same shape. The stratified estimate below shows where it comes
from.

| stratum | n paired | point (C) | 95% CI |
| --- | --- | --- | --- |
| arm=stratified, overlap_class=full | 48 | 0.0900 | 0.0900 to 0.0900 |
| arm=stratified, overlap_class=none | 48 | 0.0900 | 0.0900 to 0.0900 |
| arm=stratified, overlap_class=partial | 48 | 0.0900 | 0.0900 to 0.0900 |

Every stratum is positive and every stratum interval excludes zero, so the pooled mean is
not an artefact of pooling; its size is an average over strata that differ by more than an
order of magnitude.

## Does the qualitative claim survive?

The claim was: quality, not quantity, drives the residual, and halving the donor
set by correlation while holding the count fixed costs about +0.08 C. Under exact
matching on donor count, on arm and on overlap class, the contrast is
**+0.0900 C (95% CI 0.0900 to 0.0900)** on the matched pairs.
Under the three admissible within-half selection rules it spans
0.0500 to 0.1100 C; the weakest of the three (`gap_minimising`) gives
0.0500 C (0.0500 to 0.0500), still excluding zero.
The stratum-weighted estimator (arm x overlap class x K) returns the identical 0.0900 C, so
no composition confounding is left inside the matched sample for the stratification to remove,
and the network-equal mean is 0.0900 C
(0.0900 to 0.0900), so no single network carries the result.
The sign is positive in 100.0% of matched pairs; the distribution section above
shows that the mean is carried by the upper tail, not by the typical pair.

**Verdict: the claim survives exact matching on donor count.**
The point estimate moves from the published +0.0824 C to the
matched value above; the direction, the exclusion of zero and the mechanistic reading
(correlation strength, not donor count, carries the information) are unchanged. The
published interval was not produced by a count-matched design and should be replaced by
the matched interval.

The count mismatch was never the driver: within the original specification, the
47 pairs that already had equal counts give
+0.0800 C (0.0800 to 0.0800),
against +0.0800 C for the full original sample. Reporting the unmatched
number was an error of description, not of substance.
## The shuffle control in the same table

`anomaly_shuffled - all_donors` = +0.2300 C (0.2300 to
0.2300) on the full sample and +0.2300 C
(0.2300 to 0.2300) on the matched-restricted sample;
donor count is identical in both arms by construction, so F12 does not touch it. The frozen
value was +0.0824 C only for the donor-quality contrast; the frozen
shuffle row was +0.2343 C (0.1636 to 0.2881) and the manuscript quotes 0.234 (0.164 to 0.288).

## Matched contrast by donor count K

| K | n paired | point (C) | 95% CI |
| --- | --- | --- | --- |
| 1 | 48 | 0.0900 | 0.0900 to 0.0900 |
| 2 | 48 | 0.0900 | 0.0900 to 0.0900 |
| 3 | 48 | 0.0900 | 0.0900 to 0.0900 |

Every donor-count cell excludes zero, so the pooled interval is not an artefact of mixing
donor counts.

## Arm means

| spec | arm | sample | n | mean abs error (C) | 95% CI |
| --- | --- | --- | --- | --- | --- |
| shuffle_control | all_donors | full | 144 | 0.3151 | 0.2973 to 0.3288 |
| shuffle_control | anomaly_shuffled | full | 144 | 0.5451 | 0.5273 to 0.5588 |
| matched_exact_k | strong_half | matched | 144 | 0.2951 | 0.2773 to 0.3088 |
| matched_exact_k | weak_half | matched | 144 | 0.3851 | 0.3673 to 0.3988 |
| unmatched_original | strong_half | full | 144 | 0.2951 | 0.2773 to 0.3088 |
| unmatched_original | weak_half | full | 144 | 0.3751 | 0.3573 to 0.3888 |

## Provenance hazard and the guard that closes it

`scripts/183_v17_mechanism.py` ran the donor control through a process pool with
`except Exception: frame = pd.DataFrame()`, then wrote the four control artifacts only
`if not controls.empty`, and finally rewrote `summary.json` unconditionally. A run in which
every worker failed therefore skipped the table writes, overwrote the summary with
`controls: {}`, and left the previous generation's tables untouched.

That is exactly what the frozen directory shows. The tables carry mtime
2026-09-23 12:47:19Z and the summary carries
2026-09-23 20:55:41Z, 8 hours apart in the same commit; the frozen
`REPORT.md` has no "Controlled donor experiments" section, which is what the empty branch
produces. At the commit that added these files the donor-control branch could not run at all:
`stable_seed` was used but not imported, so every worker raised `NameError` (fixed only in
`9a933ff309`). The committed provenance is therefore a table from generation A beside a
summary and report from generation B — a reader taking the summary as the run's own account
of itself would conclude no donor control was run, and a reader taking the table would
conclude it was, with no way to tell which generation either came from.

Demonstration (`mixed_generation_hazard_demo`, deterministic, no cluster or panel data):

- a stale success table was left byte-identical beside an empty-controls summary:
  `stale_table_preserved = True`,
  `summary_claims_zero_controls = True`,
  `mixed_generation_state = True`;
- `require_controls` refused the empty control frame: `donor control produced no rows`;
- `verify_generation` flagged the directory with no manifest: `no MANIFEST.json`.

The guard in this module and script: worker exceptions are captured per job and re-raised as
`WorkerFailure` before anything is written; every submitted job must be accounted for as rows
or as a documented empty reason (an empty frame without a reason is itself an error);
`require_controls` refuses an empty or single-network control frame; `write_generation` writes
`summary.json` last and closes the set with a `MANIFEST.json` binding every file to one
generation id; `verify_generation` re-checks the hashes and rejects unlisted files that a
later partial run could have left behind.

## Recommended manuscript edit

The published sentence (paper/wrr/wrr_manuscript.tex lines 630-636, and the same text in
wrr_manuscript_published.tex lines 632-638) reads "Halving the donor set by training-period
correlation while holding the count fixed costs $+0.082^{\circ}$C (95% interval 0.061 to 0.112)".Under this amendment the count really is held fixed, and the numbers become:

- donor-quality contrast: **+0.0900 C, 95% interval 0.0900 to 0.0900**
  (n = 144 matched pairs, 4 networks, network-clustered bootstrap,
  2000 draws, seed 0), from `contrasts_matched.csv` row `spec=matched_exact_k`,  `selection_rule=top_of_half`; cite this amendment and its generation id.
- donor-shuffle contrast, unchanged in design: +0.2300 C (0.2300 to 0.2300)
  on the recomputed sample, against 0.2343 (0.1636 to 0.2881) frozen. The point estimate agrees;
  the interval is wider, so if the whole Step-5 table is regenerated the shuffle interval should
  be refreshed from the same generation rather than mixed with the frozen one.
- if the authors prefer to keep quoting a sample defined exactly as the frozen one did (all four
  arms finite), the matched number there is +0.0900 C (0.0900 to 0.0900).

## Method notes

- Both specifications are computed inside one worker pass per station-year, sharing the
  outage realization, the visibility filter, the phase-shuffle seed and the model cache, so
  the old-versus-new difference cannot come from a different realization draw.
- Intervals resample whole networks (`cluster_bootstrap`, 2000 draws, seed 0), as everywhere
  else in this study; `n_clusters` = number of networks contributing to the contrast.
- Matching is exact: after the visibility filter both arms keep K = min(visible strong,
  visible weak) donors, and each compared pair comes from one realization, so it shares K,
  arm, overlap class, station, year and training data.
- The three selection rules bracket the tie-breaking convention; none of them was chosen
  after seeing the interval.

## Files

- `contrasts_matched.csv` — every contrast computed, matched and unmatched.
- `arm_means_matched.csv` — per-arm mean error on the matched sample.
- `contrast_by_k.csv` — the matched contrast per donor count K.
- `donor_controls_paired.parquet` — case-level table carrying both specifications.
- `summary.json` — machine-readable version of everything above.
- `MANIFEST.json` — the generation id, its inputs and the sha256 of every file above.
- `../step5_mechanism_pre_fix/` — the four frozen artifacts, byte-identical, with sha256.
