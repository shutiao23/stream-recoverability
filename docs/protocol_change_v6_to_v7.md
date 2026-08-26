# Protocol change v6 to v7

Date: 2026-08-25  
Status: claim-safe overlay; does not reopen confirmatory outcomes or the national freeze

## Why

Implementation tests passed, but four headline inferences were not scientifically valid: overlapping-anchor Wilcoxon tests, a post-hoc Chattahoochee model rule used as confirmation, a defective national pooled AUC kept as the visual primary, and incomplete Jinsha source quality.

## What changed

1. Independent units are site-year or overlap components. Below five clusters, p-values and confidence intervals are withheld.
2. The title and abstract no longer claim that reservoir structure predicts recoverability.
3. Fixed-model Chattahoochee scores remain archived but are labelled post-hoc.
4. Figure 7 reports within-fold AUC. The frozen pooled AUC 0.407 is retained only as a preregistered defective diagnostic.
5. Separated national odds ratios are suppressed. A Firth unadjusted null is reported as a sensitivity.
6. Texts S3--S15 are generated as numbered SI sections.
7. `make reproduce-paper` applies this overlay from frozen artifacts and does not require overwriting the validation-uncertainty directory.

## What did not change

The 540-unit once-lock, the frozen train-only heuristic, the national-panel freeze hash, and the 2018--2020 development-test visibility label are unchanged. No new independent network was opened.
