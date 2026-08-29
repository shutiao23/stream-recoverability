# Agent B — Downstream Thermal-Regime Metrics (v12 revision, t08)

**Namespace:** `results/revision_v12/t08_downstream_metrics/agent_b/`
**Script:** `scripts/rev_v12_t08_downstream_metrics_b.py` (run 2026-08-28, ~3 min, no GPU)
**Branch:** main. No repository files were modified; all outputs are in the namespace above.

---

## 1. Purpose

Reviews of the stream-temperature gap-recoverability manuscript demand downstream,
ecologically relevant thermal-regime metrics rather than MAE alone. This analysis:

1. quantifies how XGBoost gap reconstruction distorts ten thermal-regime metrics
   relative to truth, and relative to the no-fill alternative (gap days dropped,
   the status quo for downstream users);
2. correlates the fitting-period empirical risk score with per-metric distortion
   (network-level Spearman);
3. runs a budget experiment (protect top 20% of gaps by risk vs by gap length vs
   random) and reports reductions in aggregate distortion vs treating no gaps;
4. identifies which metrics are most/least protected and why.

## 2. Setup

- **Networks (15):** arso_bistrica, arso_sava, arso_savinja (SI), foen_aare_aaregebiet (CH),
  gkd_bayern_donau, gkd_bayern_isar, gkd_bayern_main (DE-Bavaria), huc8_02040101,
  huc8_05030103, huc8_17090004 (US), lubw_neckar, lubw_rhein (DE-BW), rws_rijn_lek_nederrijn (NL),
  usgs_missouri_river_huc10, usgs_snake_river_huc4_1706 (US).
- **Inputs:** `results/development_v11/confirmation_daily_qc/networks/<id>/daily_wide_temperature.csv`
  (all 15 networks are in the reviewer-completion empirical roster).
- **Pipeline:** identical to scripts 106/108/115 — fixed XGBoost (300 trees, depth 4, lr 0.05),
  information condition `B_union_D` (boundary + donor stations; no auxiliary M/H for these
  networks, same as script 115), 70%-first-years / 30%-last-years split
  (`year_split`, min 365 training days, min 365 donor pairs), horizons **7/30/90 days**,
  **≤5 placements** per station-gap (evenly spaced across eligible evaluation windows).
- **Scale:** 15 networks scored (no attrition), 117 stations, 351 station-gaps (117 per horizon),
  1,755 placements. Mean reconstruction MAE: 0.39 °C (7 d), 0.74 °C (30 d), 1.13 °C (90 d).
- **Metric window:** 365 days centred on the gap centre (gap always fully inside the window;
  windows clipped to the panel range). Metrics are computed on the truth series, the
  reconstructed series (gap days replaced by XGBoost predictions), the no-fill series
  (gap days dropped), and a climatology-fill reference (day-of-year medians from training).
- **Metrics (per window):** annual mean; summer (JJA) mean; annual amplitude
  (mean July − mean January); phase (day-of-year of the 15-day-smoothed peak); 90th
  percentile; summer maximum; days >20 °C; days >25 °C; degree days >10 °C base;
  OLS trend slope (°C/yr). Distortion = |truth − alternative|; phase error is the circular
  day difference.
- **Risk scores:** `empirical_transfer_prediction` (fitting-period gap-by-season empirical
  loss transferred to evaluation placements; °C) and `risk_fit_loss` (mean inner-period fit
  MAE per station-gap, °C), both from
  `results/development_v11/reviewer_completion/confirmation_empirical_predictions.csv` and
  `confirmation_empirical_fit_losses.csv`, averaged to the station-gap level (same units as
  recovery loss). 270 of 351 station-gaps carry a risk score (the reviewer roster scored a
  subset of stations in gkd/huc8/lubw networks); the budget experiment uses the common
  pool of 270 units so all policies are compared on identical units.
- **Aggregation:** station-gap distortions are means over placements computed on the
  *common support* (placements where the metric is computable under every scenario);
  otherwise comparing recon vs no-fill mixes different placement subsets.

## 3. Metric-error tables

`metric_error_summary.csv` (mean/median absolute distortion per station-gap, n = 351 units):

| metric | units | mean recon | median recon | mean no-fill | median no-fill | recon/no-fill | mean climatology |
|---|---|---|---|---|---|---|---|
| annual mean | °C | 0.093 | 0.036 | 0.753 | 0.544 | **0.12** | 0.105 |
| summer (JJA) mean | °C | 0.098 | 0.027 | 0.165 | 0.075 | 0.60 | 0.117 |
| amplitude (Jul−Jan) | °C | 0.039 | 0.009 | 0.103 | 0.057 | 0.37 | 0.078 |
| phase (day of peak) | days | 2.36 | 0.00 | 3.42 | 0.20 | 0.69 | 2.77 |
| 90th percentile | °C | 0.141 | 0.025 | 0.469 | 0.170 | 0.30 | 0.143 |
| summer maximum | °C | 0.124 | 0.000 | 0.148 | 0.000 | 0.84 | 0.096 |
| days >20 °C | days | 2.23 | 0.00 | 6.55 | 1.40 | 0.34 | 2.24 |
| days >25 °C | days | 0.52 | 0.00 | 0.63 | 0.00 | 0.82 | 0.41 |
| degree days >10 °C | °C·d | 21.7 | 6.1 | 157.7 | 69.3 | **0.14** | 23.5 |
| trend slope | °C/yr | 0.083 | 0.032 | 0.660 | 0.270 | **0.13** | 0.124 |

Notes:

- Integrated/accumulated metrics are the most distorted by gaps and the most repaired by
  reconstruction: degree days and annual mean recover to ~13 % of the no-fill error,
  trend slope to ~13 %, 90th percentile to 30 %, days >20 °C to 34 %.
- Single-event metrics are barely distorted at all: 95.3 % of placements have zero
  reconstruction error on days >25 °C and 88.9 % on summer maximum; phase has zero error
  in 88.4 % of placements (the peak day is usually outside the gap). Reconstruction errors
  exceed no-fill errors in only 0–8 % of placements for all metrics.
- Recovery also restores *computability*: under no-fill the amplitude is undefined for
  367/1,755 placements (20.9 %, a gap swallowing all of July or January) and the summer
  metrics for 51 placements (2.9 %); reconstruction always returns a value
  (`uncomputable_no_fill.csv`).

## 4. Risk → distortion correlations

`risk_correlation.csv` — Spearman between mean empirical risk and mean reconstructed
distortion per metric. **Network-level (n = 15 networks; primary):**

| metric | ρ (transfer risk) | p | ρ (fit loss) | p |
|---|---|---|---|---|
| annual mean | **0.764** | 0.0009 | 0.757 | 0.0011 |
| degree days >10 °C | **0.743** | 0.0015 | 0.754 | 0.0012 |
| phase | 0.729 | 0.0021 | 0.707 | 0.0032 |
| 90th percentile | 0.668 | 0.0065 | 0.689 | 0.0045 |
| days >25 °C | 0.496 | 0.060 | 0.540 | 0.038 |
| days >20 °C | 0.471 | 0.076 | 0.521 | 0.046 |
| summer mean | 0.336 | 0.221 | 0.393 | 0.147 |
| trend slope | 0.329 | 0.232 | 0.261 | 0.348 |
| summer maximum | 0.250 | 0.369 | 0.218 | 0.435 |
| amplitude | 0.089 | 0.752 | 0.079 | 0.781 |

Pooled station-gap-level Spearman (descriptive; units are not independent): annual mean
0.82, degree days 0.79, 90th percentile 0.78, summer mean 0.69, phase 0.65, days >20 °C
0.59, trend slope 0.59, summer maximum 0.43, days >25 °C 0.38, amplitude −0.14 (all
p < 1e−10 except amplitude, which is slightly negative).

**Reading:** the empirical risk score (fitting-period, in °C, same units as recovery loss)
is a strong predictor of downstream distortion for integrated metrics (annual mean,
degree days, p90, phase) at the network level; it is *not* predictive of amplitude or
summer-maximum distortion, which are governed by gap geometry rather than reconstruction
error.

## 5. Budget experiment

`budget_comparison.csv` + `budget_reduction.png`. Units: 270 station-gaps with risk
scores (261 for amplitude); budget = top 20 % (54 units, 53 for amplitude) filled by the
XGBoost reconstruction; untreated gaps remain unfilled (no-fill). Reduction = 1 −
aggregate distortion(treated)/aggregate distortion(no treatment). Random = mean over 20
draws ± SD.

| metric | top-20 risk | top-20 length | random (mean ± SD) |
|---|---|---|---|
| annual mean | 0.377 | 0.386 | 0.173 ± 0.022 |
| degree days >10 °C | **0.395** | 0.344 | 0.171 ± 0.023 |
| trend slope | 0.348 | **0.522** | 0.173 ± 0.045 |
| days >20 °C | 0.308 | 0.240 | 0.124 ± 0.034 |
| 90th percentile | 0.307 | 0.290 | 0.133 ± 0.022 |
| summer mean | 0.188 | 0.182 | 0.084 ± 0.024 |
| summer maximum | 0.133 | 0.119 | 0.033 ± 0.027 |
| phase | 0.117 | 0.109 | 0.053 ± 0.023 |
| days >25 °C | 0.109 | 0.021 | 0.036 ± 0.024 |
| amplitude | 0.095 | 0.159 | 0.119 ± 0.032 |

- Risk targeting beats random by **1.9–4.0×** on every metric except amplitude, where
  random (0.119) slightly beats risk (0.095) and gap-length targeting is best (0.159).
- Gap-length targeting (protect the 90-day gaps) is competitive with risk for annual
  mean, amplitude, and trend slope, but clearly worse for days >25 °C (0.021 vs 0.109)
  and days >20 °C (0.240 vs 0.308) and degree days (0.344 vs 0.395): long gaps are not
  necessarily the ones with the largest regime impact.
- Aggregate numbers (e.g. degree days): no treatment = 41,343 °C·d error across the
  panel; top-20 risk = 25,030 °C·d (39 % reduction); random = 34,292 °C·d (17 %).

## 6. Most/least protected — and why

**Most protected:** degree days >10 °C, annual mean, trend slope, 90th percentile,
days >20 °C. These metrics *integrate or average* the daily signal, so their distortion
grows roughly with gap length × local MAE; the fitting-period empirical risk (an MAE-type
score) is therefore strongly correlated with their distortion (network ρ = 0.67–0.76)
and risk-based budgets cut their aggregate error 2–2.5× more than random.

**Least protected:**
- **Amplitude (Jul−Jan)** — network ρ ≈ 0.09 (n.s.), risk budget no better than random.
  Amplitude error is set by whether the gap swallows a whole month (undefined under
  no-fill in 20.9 % of placements), not by reconstruction MAE; no MAE-type risk score can
  rank that.
- **Summer maximum** — ρ = 0.25 (n.s.); distortion is non-zero only when the gap covers
  the single hottest JJA day (zero error in 88.9 % of placements); event-day geometry
  dominates.
- **Phase (day of peak)** — strong network correlation (ρ = 0.73) but small absolute
  distortion (median 0 days; error only when the gap covers the peak day); well predicted
  but low impact — it is "protected" in the sense of rarely damaged.
- **Days >25 °C and summer mean** — weak network correlation (0.34–0.50); distortion is
  concentrated in warm-climate networks and summer placements, diluting network-level
  risk ranking.

Bottom line for the manuscript: recovery reduces distortion for **every** thermal metric
versus no-fill (mean errors 12–84 % of the no-fill baseline) and the empirical risk score
is a valid instrument for protecting integrated ecological metrics (degree days, annual
mean, trend), while single-event metrics (amplitude, summer max) are governed by gap
geometry and are best protected simply by filling long gaps.

## 7. Caveats

- No-fill "truth" for amplitude/summer metrics is undefined when a gap swallows July or
  January; those placements are excluded from the paired comparisons and counted in
  `uncomputable_no_fill.csv` (this favours no-fill, yet recon still wins on all metrics).
- Risk scores exist for 270/351 station-gaps (reviewer roster coverage); all policy
  comparisons use the common 270-unit pool.
- Pooled Spearman p-values treat units as independent; network-level (n = 15) is the
  primary evidence.
- Horizon set (7/30/90) and 5 placements per station-gap keep the run bounded; results
  reflect artificial gaps in the last 30 % of years only.

## 8. Deliverables (all in this namespace)

| file | content |
|---|---|
| `placement_metrics.csv` | 1,755 placements × truth/recon/no-fill/climatology metrics + errors |
| `station_gap_metrics.csv` | 351 station-gaps, aggregated distortions + risk scores |
| `metric_error_summary.csv` | Table of Section 3 |
| `risk_correlation.csv` | Table of Section 4 (network + pooled) |
| `network_metric_distortion.csv` | per-network mean distortions and risks |
| `budget_comparison.csv` | Table of Section 5 (with raw aggregates) |
| `budget_reduction.png` | grouped-bar budget comparison |
| `uncomputable_no_fill.csv` | placements where no-fill metrics are undefined |
| `summary.json` / `run_log.txt` | machine-readable summary and log |
