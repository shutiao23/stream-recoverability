# Aligned-policy round, 2026-10-20

This round answers the review of 2026-10-19 (commit `bfc797ef43`) by repairing the
object mismatch it identified and re-deriving every downstream number. The
point-by-point response is `paper/wrr/RESPONSE_TO_REVIEW.md`.

## What was wrong

The accepted object was the stored `policy` reconstruction, but the failure event
used for threshold calibration was `certificate_abs_error`. On the external panel
the two events disagree on 898 of 13,017 cases (6.90 %; 408 policy-only, 490
certificate-only). A second defect made the tie rule differ between calibration
and deployment.

## What was done

| step | script | output |
|---|---|---|
| one object, one event, whole tie blocks | `scripts/330_wrr_aligned_policy_admission.py` | `p0_01_aligned_policy_admission/` |
| population risk vs finite-batch error | `scripts/332_wrr_selection_calibration_v2.py` | `p0_02_selection_calibration/` |
| the rule on real calendars, including no screen | `scripts/331_wrr_aligned_real_calendar.py` | `p0_03_real_calendar_adoption/` |
| hot-year closure, all seeds, confusion matrix | `scripts/333_wrr_aligned_hot_year_closure.py` | `p0_04_hot_year_closure/` |
| how much of the change is which repair | `scripts/334_wrr_repair_attribution.py` | `p0_05_repair_attribution/` |
| does the ranking survive the measurement stratum | `scripts/336_wrr_measurement_subset.py` | `p1_measurement_subset/` |
| four data figures and their source tables | `scripts/335_wrr_figures_v2.py` | `p0_06_figures/` |
| two draw.io schematics (Figure 2, Figure S1) | `scripts/337_wrr_drawio_figures.py` | `figures/wrr/drawio/` |

Run the whole round with `make wrr-round-20261020`.

## The result in one table

Retention at the pre-registered 5 % cap on the admitted reconstruction's error,
mean of three fold seeds (range in brackets):

| rule | external panel | development panel |
|---|---|---|
| gap-length | 39.6 % | 30.5 % |
| peak-window (support) | 66.7 % | 60.4 % |
| certificate bound | 72.9 % | 72.7 % |
| fitted risk | 74.0 % | 70.4 % |
| reconstruct everything | 100 % at 15.3 % risk | 100 % at 14.9 % risk |

* The fitted score beats the peak-window rule by 7.0–8.3 points on the external
  panel and 9.7–10.3 on development, and clears the pre-specified five-point
  margin at every seed.
* It does not beat the certificate bound (+1.6 points external, −1.7 to −2.6
  development).
* On the 418 real calendars, admitting everything already sits at 2.6–4.1 % risk,
  under the cap; the screens keep 93–96 % and cut the risk to 0.5–1.7 %.
* At a 20 °C hot-year threshold the screens refuse 25 % (fitted) to 60 %
  (gap-length) of true hot years; the fitted score's composition bias is
  +0.7 points [−0.3, +1.6].
* Restricted to the documented-daily-mean subset (74.4 % of development, 94.4 %
  of external cases) and with thresholds re-selected inside it, the fitted-vs-peak
  advantage is 8.0/7.3/7.3 points on the external panel and 8.8/8.7/10.4 on
  development, so the ranking does not depend on the mixed-measurement providers.

## Claim registry

`claim_registry.csv` binds each headline number in the article (C01–C25) to the
artifact and the column that produces it. It is the audit trail for the claim set
the article is allowed to make; the build separately checks 61 literal headline
numbers and refuses to build the PDF when one is missing from the text.

## Evidence identity

Nothing here is a sealed confirmation. The external panel is already opened and
every comparison is a cross-fit within it; the development panel was used for
method selection; the real-calendar replay is a development-period probe. This is
stated in the manuscript's abstract, limitations and open-research statement.

## Verification

* `python -m pytest tests/` exit 0 on this tree.
* `python scripts/223_wrr_build.py` builds the article (28 pages double-spaced,
  15 pages published layout), the SI (13 pages) and passes the AGU desk checks
  (3 key points ≤ 140 characters, abstract 248 words, PLS 200 words, 61 headline
  numbers present, 27 references all cited and rendered).
* The build stays `NOT submission-ready` until the author block is filled by a
  human.
