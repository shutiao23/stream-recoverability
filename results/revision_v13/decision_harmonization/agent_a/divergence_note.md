# Divergence note: t08 agent_a vs agent_b implementations

Both agents of `results/revision_v12/t08_downstream_metrics/` measure downstream
thermal-regime distortion of the XGBoost gap reconstruction and run a 20%
budget experiment. The two runs agree on the core reconstruction pipeline and
on per-placement error magnitudes for the shared networks, but they differ in
panel, baselines, and budget semantics, which explains the different headline
numbers (and the review's quoted ranges). This note reconciles them.

## 1. Panels and scale

| aspect | agent_a | agent_b |
|---|---|---|
| networks | 15 first-confirmation networks with most scored station-gaps | 15 reviewer-completion empirical-roster networks |
| placements | 1,965 (655 per horizon; horizons 7/30/90) | 1,755 (585 per horizon; horizons 7/30/90) |
| stations | 131 | 117 |
| overlap | 11 networks shared | 11 networks shared |
| agent-only | huc8_02040104, huc8_03110206, huc8_10020007, huc8_17090001 (USGS) | arso_bistrica (SI), lubw_rhein (DE-BW), rws_rijn_lek_nederrijn (NL), usgs_snake_river_huc4_1706 (US) |

Shared: gkd_bayern_donau, gkd_bayern_isar, gkd_bayern_main, lubw_neckar,
arso_sava, arso_savinja, foen_aare_aaregebiet, huc8_02040101, huc8_05030103,
huc8_17090004, usgs_missouri_river_huc10.

## 2. Reconstruction pipeline (identical by design)

Fixed XGBoost B_union_D (300 trees, depth 4, lr 0.05), 70%-of-years train /
30% evaluation split, information condition B_union_D. agent_a verified parity
against the stored confirmation empirical MAEs: mean absolute difference 0.0000
on the 808 exactly-matched placements. On the 11 shared networks the
per-horizon mean reconstruction MAE is identical to 3 decimals in both runs
(7 d: 0.395, 30 d: 0.753, 90 d: 1.076 °C). The full-panel means differ only
because of the 8 non-shared networks (agent_a 0.405/0.725/1.091; agent_b
0.391/0.736/1.126).

## 2b. Metric evaluation window: dominant cause of absolute-error differences

| | agent_a | agent_b |
|---|---|---|
| window | **whole evaluation record** (mean 3,136 days; 224–5,695) | **365 days centred on the gap**, clipped to the panel range (191–365 d; `n_window_days`) |

agent_a inserts the reconstruction into the full evaluation record and
recomputes each metric over it; agent_b recomputes each metric over a 365-day
window centred on the gap. The gap therefore carries ~9× more weight in
agent_b's window than in agent_a's multi-year record. This explains why the
per-placement absolute distortions differ by roughly an order of magnitude for
record-average metrics even on the same networks (e.g., annual-mean |err|:
agent_a 0.011 vs agent_b 0.093; trend slope 0.006 vs 0.083), while
gap-concentrated metrics agree better (degree days 19.98 vs 21.72).
Ratios against the untreated baseline are less affected than the absolute
levels because the baseline is computed on the same window in each run.

## 3. Untreated baseline: the key divergence

| | agent_a | agent_b |
|---|---|---|
| "no recovery" default | **climatology fill** (day-of-year medians from the training period) | **no-fill** (gap days dropped from the record) |
| reconstruction effect | replaces climatology-filled days with XGBoost predictions | inserts predictions into an otherwise complete record |
| budget reduction = | 1 − agg(policy)/agg(climatology baseline) | 1 − agg(policy)/agg(no-fill baseline) |

Consequences for the budget experiment (top 20% of units, reduction of
aggregate absolute distortion):

- Under the **no-fill default** (agent_b, 270 station-gaps, 54 treated),
  reconstruction always helps: reductions +0.095…+0.395 (risk policy), +0.021…
  +0.522 (gap-length policy), +0.033…+0.173 (random). This answers: "does
  recovery beat doing nothing (leaving the gap empty)?" — yes.
- Under the **climatology default** (agent_a, 393 of 1,965 placements treated),
  the risk and gap-length policies concentrate on long summer gaps where the
  reconstruction's cold peak bias flips more threshold crossings than the
  climatology fill removes: risk-policy reductions are NEGATIVE for degree days
  (−17.9%), days>20 °C (−22.2%), days>25 °C (−42.5%), amplitude (−33.8%),
  summer mean (−23.0%), trend slope (−15.7%); only annual mean is slightly
  positive (+2.2%). This answers: "does recovery beat filling the gap with
  climatology?" — for mean/percentile metrics yes, for threshold/single-event
  metrics on long gaps no.

The two defaults are complements, not contradictions: dropping a 90-day gap
destroys the record (huge no-fill distortion), while climatology filling is a
non-trivial opponent. The manuscript must label the default explicitly in every
reduction figure.

## 4. Budget semantics

| | agent_a | agent_b |
|---|---|---|
| unit | placement (top 20% of 1,965 = 393) | station-gap (top 20% of 270 risk-scored = 54; 53 for amplitude) |
| random policy | 200 draws, mean | 20 draws, mean ± SD |
| oracle policies | per-metric oracles + oracle_combined | none |
| overlap of treated sets | can treat multiple placements of the same station-gap | exactly one per station-gap |

agent_b's budget is restricted to the 270 station-gaps carrying the
reviewer-roster risk scores so that all policies are compared on identical
units; agent_a's budget covers every placement (risk scores are matched per
placement with an exact-start/station-gap-season fallback chain).

## 5. Risk-score definitions

- agent_a: `empirical_transfer_prediction` (fitting-period empirical loss
  transferred to each outer placement, °C MAE), matched by exact gap start
  (808) else station-gap-season (1,157).
- agent_b: `risk_transfer` (same source, averaged to station-gap level) and
  `risk_fit_loss` (mean inner-period fit MAE per station-gap), 270 of 351
  station-gaps.

Network-level risk-distortion Spearman therefore differs partly by panel and
partly by aggregation (agent_a p90 +0.77, degree days +0.76, exceed_20 +0.74;
agent_b annual mean +0.76, degree days +0.74, phase +0.73).

## 6. Metric definitions and aggregation

- Identical metric set and formulas (annual/summer mean, Jul−Jan amplitude,
  phase DOY, p90, summer max, days>20/25 °C, degree days>10 °C, trend slope),
  different column names: agent_a `exceed_20_days`/`exceed_25_days`/
  `degree_days_10` vs agent_b `exceed_days_20`/`exceed_days_25`/`cdd10`.
- agent_a reports per-placement distortion on the full evaluation record
  (n = 1,965; 1,950 for summer/amplitude/trend where windows are clipped).
- agent_b reports per-placement errors computed on a 365-day window centred on
  the gap plus station-gap means computed on the *common support* (placements
  where the metric is defined under every scenario). This matters for
  amplitude: no-fill amplitude is undefined for 584/1,755 placements (gap
  swallowing July or January) and reconstruction itself is undefined for 217
  (window without both July and January); on the 3-way common support
  (n = 1,171) mean |err| amplitude is 0.031 °C (recon), while on the
  reconstruction-only support it is 0.229 °C — the undefined placements are
  exactly the high-distortion ones (see `downstream_baseline_comparison.csv`
  and REPORT.md).

## 7. Bottom line for harmonization

1. Per-placement reconstruction MAE is identical across the two runs on the
   shared networks; panel composition (1,965 vs 1,755) explains the small
   aggregate MAE differences.
2. Absolute per-metric distortions differ by ~an order of magnitude for
   record-average metrics because of the metric window (whole evaluation
   record in agent_a vs 365-day gap-centred window in agent_b); ratios against
   each run's own untreated baseline remain the comparable quantity.
3. The budget results are not directly comparable unless the untreated
   baseline is stated: no-fill (agent_b) shows recovery is always beneficial;
   climatology (agent_a) shows recovery is not always beneficial on long
   summer gaps. Both are true simultaneously.
4. Recommended manuscript practice: report both defaults with explicit labels,
   quote per-metric ratios (recon/no-fill and recon/climatology) rather than a
   single "reduction" number, and state the metric window used.
