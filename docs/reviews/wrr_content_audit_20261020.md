# Adversarial self-audit of the manuscript, 2026-10-20

The brief for this round was to attack our own product: find what is wrong, fix it,
and re-verify. This note records the defects found, not the things that survived.

Method: the built PDF was read page by page against the artifacts; every quoted
number was re-derived from its table; each caption was checked against the figure
it describes; the class file was compared byte for byte with the official AGU
repository; and the bibliography was checked field by field against the publisher
deposits (separate report: `wrr_reference_audit_20261020.md`).

## Defects found and fixed

| id | severity | where | defect | fix |
|---|---|---|---|---|
| D1 | Major, factual | §1, §2.3 | "gap length and the share of the target window hidden correlate at −0.86". The −0.86 is the correlation between gap length and the **warm-season fraction observed**; the correlation with hidden support is **+0.45** (development) and +0.47 (external). | both correlations now stated with the right quantities |
| D2 | Major, factual | §4.2 | "the ordering of the five methods at 90 days is the same as at 30". It is not: interpolation costs 0.34 °C at 30 days and 1.31 °C at 90, moving from second cheapest to most expensive. | the instability is now reported, and it strengthens the conditional claim |
| D3 | Major, factual | §4.2 | air regression was grouped with methods whose length effect is "not distinguishable from zero"; its interval is 0.13 °C [0.03, 0.22], which excludes zero. | climatology and smoothing only; air regression reported separately as small but distinguishable |
| D4 | Major, factual | §4.4 | "the interval includes zero at two of three seeds" for fitted minus bound on development. All three intervals include zero. | corrected to all three |
| D5 | Major, overclaim | abstract, §4.4, conclusions | "no better than a calibrated certificate bound". On the external panel seed 101 the fitted score is +1.6 points [0.2, 3.1], i.e. better, and the other two seeds cross zero; on development it is worse. | "not reliably better", with both panels stated |
| D6 | Major, overclaim | key point 3, abstract, §4.4, §5.3 | "real calendars need no screen" and "already under the cap". The point estimates are 2.6–4.1 %, but the intervals are wide and no cap is certified for a new archive. | "may need no screen"; "under the cap at every point estimate, although the intervals are wide" |
| D7 | Minor, scope | §1 | the 1.31 °C error was attributed to "the complete station-years", but it is measured on the designed outages placed on them. | attributed to the designed outages |
| D8 | Major, missing | §3.1 | the admitted object is a per-case policy over five reconstructors, but the paper never said what the policy chooses or where it fails. | added: donor 69 %, smoothed climatology 24 %, interpolation 6 %; the fallback fails at 38 % against 8 % for donor regression |
| D9 | Minor, metadata | Figure captions | source-table paths were stale (the reconstructor caption pointed at `fig2_source.csv` after the figures were renumbered). | corrected to fig1/3/4/5 and the directory named once in the Open Research statement |
| D10 | Minor, consistency | Figure 3 caption | "only linear interpolation retains a length effect" contradicted the air-regression interval. | caption now distinguishes the large interpolation effect from the small air effect |
| D11 | Minor, stale | §5.2 | the refused tail was still quoted as "35 to 55 % against 1 to 22 %" from an earlier binning. | 40–55 % against 0.7–15 % |
| D12 | Minor, vague | §5.3 | "the retention differences are 7 to 30 points" mixed two contrasts. | fitted minus support 7–8 points; support minus length about 27 |
| D13 | Minor, contradiction | §5.2 | "on the external panel the difference is small and interval-crossing" contradicted the +1.6 point interval quoted two paragraphs earlier. | "at most 1.6 points and crosses zero at two of the three seeds" |
| D14 | Minor, cross-reference | SI | "Figure 4c" after the figure renumbering; contents said "Tables S1 to S7" when there are eight; page count stale. | Figure 5c; Tables S1 to S8; counts updated |
| D15 | Presentation | `paper/wrr/figures/` | nineteen legacy figure PDFs from earlier rounds were still in the include directory, triggering QA warnings and confusing the submission package. | only the six included files remain |
| D16 | Presentation, brief | Figures 2 and S1 | architecture/system-design schematics were matplotlib drawings, against the brief that they must be draw.io. | rebuilt as draw.io sources (`figures/wrr/drawio/`) and exported with the official draw.io desktop exporter (32.5.5, headless); the system design is now a main-text figure |
| D17 | Integrity | bibliography | eight entries were duplicated across two `.bib` files, and seven entries had wrong fields (see the reference report). | one source of truth; fields corrected and re-verified |

## What the audit confirmed as correct

* Every retention, risk and hot-year number quoted in the text re-derived from its
  CSV: 39.6 / 66.7 / 72.9 / 74.0 % external; 30.5 / 60.4 / 72.7 / 70.4 %
  development; 2.6–4.1 % unscreened on real calendars; refusal 24.5–59.5 %.
* Every contrast quoted with an interval (fitted minus peak 8.0/7.3/7.0 and
  10.3/10.1/9.7; fitted minus bound +1.6 and −2.6/−1.7/−2.5; subset contrasts).
* The effect sizes behind the mechanism: misalignment 0.28–0.70 °C, persistence
  0.16–0.36 °C, within-support separation 0.7–15 % vs 40–55 %.
* The AGU class and its three supporting files are byte-identical to the official
  repository at the recorded commit (`PROVENANCE.md`).
* Figure fonts are embedded, no text outside the page, no line below 4.5 pt; the
  remaining QA warnings are box-model artifacts (superscripts, padding) verified
  against the renders.

## What this audit does not establish

* We did not re-run every analysis from raw daily observations; the numbers are
  re-derived from the versioned case tables, not from the providers' servers.
* The external panel is not a sealed confirmation; the cross-fit statement is
  checked, not the independence of the original archive.
* The author block is still a placeholder, and the manuscript is correctly
  reported as not submission-ready.
