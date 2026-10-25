#!/usr/bin/env python3
"""TR-E8: do the ways of handling incomplete years change the science?

Long-record stations (>= 20 complete years; 15 as fallback) are degraded
200 times. Each year becomes incomplete with the archive's provider share,
optionally with the archive's decline of missingness over time and with the
E1 state effects; an incomplete year receives one of its real-calendar cases
(state-weighted in the MNAR scenarios). Pipelines:

  A0  drop every incomplete year
  A1  keep incomplete years with >= 90% warm-season coverage, H30 from recorded days
  A2  keep incomplete years whose longest gap is <= 49 days (Johnson et al. 2021)
  B   keep all years, plug-in completion (P0)
  C1  keep all years, D2* median (single imputation)
  C   keep all years, D2* multiple imputation (M = 20) pooled by Rubin's rules

Estimands: station OLS and Theil-Sen trend of H30, regional mean trend, mean
H30, frequency of years above the station's complete-data 75th percentile,
H30 in regional heat-wave summers (top 10% of the region's summer air anomaly,
known without water data) and the hot-year classification.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy.special import expit, logit
from scipy.stats import t as student_t

import wrr_tr_common as T
import wrr_tr_features as F
import wrr_tr_rules as R
from stream_recoverability.seeds import plain_seed, position_index

E5 = T.load_script("tr_e5_for_e8", T.ROOT / "scripts/436_tr_e5_rules.py")

OUT = T.OUT / "e8_downstream"
PIPELINES = ("A0", "A1", "A2", "B", "C1", "C")


def ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Slope per decade and its standard error."""

    x = (x - x.mean()) / 10
    sxx = np.sum(x**2)
    slope = np.sum(x * (y - y.mean())) / sxx
    resid = y - y.mean() - slope * x
    se = np.sqrt(np.sum(resid**2) / max(len(y) - 2, 1) / sxx)
    return float(slope), float(se)


def theil_sen(x: np.ndarray, y: np.ndarray) -> float:
    i, j = np.triu_indices(len(x), 1)
    return float(np.median((y[j] - y[i]) / (x[j] - x[i])) * 10)


def inverse_cdf(quantiles: np.ndarray, levels: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Draw from piecewise-linear quantile functions, extrapolating the outer segments to 0 and 1."""

    lower = quantiles[:, 0] - (quantiles[:, 1] - quantiles[:, 0]) * levels[0] / (levels[1] - levels[0])
    upper = quantiles[:, -1] + (quantiles[:, -1] - quantiles[:, -2]) * (1 - levels[-1]) / (levels[-1] - levels[-2])
    grid = np.column_stack([lower, quantiles, upper])
    lv = np.r_[0.0, levels, 1.0]
    out = np.empty(u.shape)
    for row in range(len(grid)):
        out[row] = np.interp(u[row], lv, grid[row])
    return out


def station_replicates(job: dict, scenario: dict, replicates: int, imputations: int, seed: int) -> list[dict]:
    years = np.asarray(job["years"])
    truth = np.asarray(job["truth"])
    rng = np.random.default_rng(seed)
    full_slope, full_se = ols(years.astype(float), truth)
    full_ts = theil_sen(years.astype(float), truth)
    threshold = np.quantile(truth, 0.75)
    hot_threshold = np.quantile(truth, 0.9)
    heat = np.asarray(job["heatwave"], dtype=bool)
    z = np.nan_to_num(np.asarray(job["z_air"], dtype=float))
    trend = (years - 2000) / 10
    share = float(np.clip(job["incomplete_share"], 0.02, 0.98))
    linear = scenario["trend"] * trend + scenario["air"] * z
    # Intercept chosen so that the expected incomplete share over the record equals the provider share.
    lo, hi = -10.0, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if expit(mid + linear).mean() < share:
            lo = mid
        else:
            hi = mid
    probability = expit((lo + hi) / 2 + linear)
    rows = []
    levels = np.asarray(job["levels"])
    for replicate in range(replicates):
        incomplete = rng.random(len(years)) < probability
        values = {name: truth.copy() for name in ("A1", "A2", "B", "C1")}
        keep = {name: np.ones(len(years), dtype=bool) for name in PIPELINES}
        draws = np.repeat(truth[None, :], imputations, axis=0)
        chosen_cases = {}
        for position in np.flatnonzero(incomplete):
            cases = job["cases"][position]
            weights = np.exp(np.asarray(cases["logw"]) * scenario["within_season"]) if scenario["within_season"] else np.ones(len(cases["p0"]))
            pick = rng.choice(len(weights), p=weights / weights.sum())
            chosen_cases[position] = pick
            keep["A0"][position] = False
            p0, pobs = cases["p0"][pick], cases["pobs"][pick]
            observed_value = pobs if np.isfinite(pobs) else p0
            keep["A1"][position] = cases["warm_fraction"][pick] >= 0.9
            keep["A2"][position] = cases["longest_gap"][pick] <= 49
            values["A1"][position] = observed_value
            values["A2"][position] = observed_value
            values["B"][position] = p0
            values["C1"][position] = cases["d2_median"][pick]
            q = np.asarray(cases["d2_quantiles"][pick])[None, :]
            draws[:, position] = inverse_cdf(np.repeat(q, imputations, axis=0), levels, rng.random((imputations, 1)))[:, 0]
        for name in PIPELINES:
            if name == "C":
                slopes, ses = zip(*[ols(years.astype(float), draws[m]) for m in range(imputations)])
                slopes, ses = np.asarray(slopes), np.asarray(ses)
                qbar, within, between = slopes.mean(), np.mean(ses**2), slopes.var(ddof=1)
                total = within + (1 + 1 / imputations) * between
                # Barnard and Rubin (1999) small-sample degrees of freedom, never above the complete-data value.
                gamma = (1 + 1 / imputations) * between / max(total, 1e-12)
                complete_dof = len(years) - 2
                dof_rubin = (imputations - 1) / max(gamma, 1e-12) ** 2
                dof_observed = (complete_dof + 1) / (complete_dof + 3) * complete_dof * (1 - gamma)
                dof = 1 / (1 / dof_rubin + 1 / dof_observed)
                missing_se = np.sqrt((1 + 1 / imputations) * between)
                estimate, se, ts = qbar, np.sqrt(total), float(np.median([theil_sen(years.astype(float), draws[m]) for m in range(min(imputations, 5))]))
                tcrit = student_t.ppf(0.975, min(dof, 1e6))
                series = draws.mean(axis=0)
                hot_call = (draws > hot_threshold).mean(axis=0) >= 0.5
                exceed = float((draws > threshold).mean())
                missing_cover = bool(abs(qbar - full_slope) <= 1.96 * missing_se) if missing_se > 0 else bool(abs(qbar - full_slope) < 1e-9)
            else:
                x, y = years[keep[name]].astype(float), (truth if name == "A0" else values[name])[keep[name]]
                if len(y) < 5:
                    rows.append({"station_key": job["station_key"], "region": job["region"], "replicate": replicate, "pipeline": name, "n_years": len(y)})
                    continue
                estimate, se = ols(x, y)
                ts = theil_sen(x, y)
                tcrit = student_t.ppf(0.975, len(y) - 2)
                series = np.where(keep[name], truth if name == "A0" else values[name], np.nan)
                hot_call = series > hot_threshold
                exceed = float(np.mean(y > threshold))
                missing_cover = np.nan
            heat_kept = heat & np.isfinite(series)
            rows.append({
                "station_key": job["station_key"], "region": job["region"], "group": job["group"], "replicate": replicate, "pipeline": name,
                "n_years": int(np.isfinite(series).sum()), "n_incomplete": int(incomplete.sum()),
                "slope": estimate, "slope_se": se, "slope_ts": ts, "full_slope": full_slope, "full_slope_ts": full_ts,
                "cover_full": bool(abs(estimate - full_slope) <= tcrit * se), "cover_missing_component": missing_cover,
                "detect_warming": bool(estimate - tcrit * se > 0), "full_detect_warming": bool(full_slope - student_t.ppf(0.975, len(years) - 2) * full_se > 0),
                "mean_h30": float(np.nanmean(series)), "full_mean_h30": float(truth.mean()),
                "exceed_freq": exceed, "full_exceed_freq": float(np.mean(truth > threshold)),
                "heatwave_years": int(heat.sum()), "heatwave_delivered": int(heat_kept.sum()),
                "heatwave_abs_error": float(np.mean(np.abs(series[heat_kept] - truth[heat_kept]))) if heat_kept.any() else np.nan,
                "heatwave_signed_error": float(np.mean(series[heat_kept] - truth[heat_kept])) if heat_kept.any() else np.nan,
                "hot_years_true": int((truth > hot_threshold).sum()),
                "hot_missed_incomplete": int(((truth > hot_threshold) & incomplete & ~(hot_call & np.isfinite(series))).sum()),
                "hot_true_incomplete": int(((truth > hot_threshold) & incomplete).sum()),
                "hot_false_incomplete": int(((truth <= hot_threshold) & incomplete & hot_call & np.isfinite(series)).sum()),
                "hot_unknown_incomplete": int(((truth > hot_threshold) & incomplete & ~np.isfinite(series)).sum()),
            })
    return rows


def run_replicates(job: dict, scenario: dict, replicates: int, imputations: int, seed: int) -> list[dict]:
    """Worker entry point: re-import this script so its helpers resolve in the worker."""

    module = T.load_script("tr_e8_worker", Path(__file__))
    return module.station_replicates(job, scenario, replicates, imputations, seed)


def jobs(min_years: int) -> tuple[list[dict], dict]:
    cases = pd.read_parquet(T.OUT / "e2_cases/cases.parquet")
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    oof = pd.read_parquet(T.OUT / "e4_estimators/oof_predictions.parquet")
    d2, levels, point, quantiles = E5.d2_distribution(cases, oof)
    levels = list(levels)
    cases["d2_median"] = point
    cases["d2_quantiles"] = list(quantiles)
    calendar = cases.loc[cases.design_family.eq("calendar")].copy()
    features = R.mask_features(calendar)
    calendar["longest_gap"] = features.longest_gap
    years_table = pd.read_parquet(T.E1 / "station_years.parquet")
    core = years_table.loc[~years_table.edge_year & years_table.fully_active]
    share = core.groupby("provider").complete_year.apply(lambda s: 1 - s.mean())
    sample = pd.read_parquet(T.E1_MISSINGNESS / "station_year_sample.parquet")[["station_key", "year", "z_air", "region"]]
    region_year = sample.groupby(["region", "year"]).z_air.mean().rename("region_z").reset_index()
    region_year["heatwave"] = region_year.groupby("region").region_z.transform(lambda s: s >= s.quantile(0.9))
    z_lookup = sample.set_index(["station_key", "year"]).z_air
    heat_lookup = region_year.set_index(["region", "year"]).heatwave
    out = []
    for station, block in calendar.groupby("station_key"):
        years = sorted(block.year.unique())
        if len(years) < min_years:
            continue
        per_year = []
        truth = []
        for year in years:
            rows = block.loc[block.year.eq(year)]
            truth.append(float(rows.eval_truth_h30.iloc[0]))
            per_year.append({
                "p0": rows.h30__policy.to_numpy(), "pobs": rows.h30__observed_days.to_numpy(), "d2_median": rows.d2_median.to_numpy(),
                "d2_quantiles": np.vstack(rows.d2_quantiles.to_numpy()), "warm_fraction": rows.warm_observed_fraction.to_numpy(),
                "longest_gap": rows.longest_gap.to_numpy(), "logw": rows.mnar_logw_k1.fillna(0).to_numpy(),
            })
        region = block.region.iloc[0]
        out.append({
            "station_key": station, "region": region, "group": block.independence_group.iloc[0], "years": years, "truth": truth, "cases": per_year,
            "levels": levels, "incomplete_share": float(share.get(block.provider.iloc[0], 0.45)),
            "z_air": [float(z_lookup.get((station, year), np.nan)) for year in years],
            "heatwave": [bool(heat_lookup.get((region, year), False)) for year in years],
        })
    return out, {"d2": d2, "levels": levels}


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=96)
    parser.add_argument("--min-years", type=int, default=0, help="override the minimum number of complete years (sensitivity)")
    args = parser.parse_args()
    settings = T.settings()
    OUT.mkdir(parents=True, exist_ok=True)
    generator = json.loads((T.E1_MISSINGNESS / "mnar_generator.json").read_text())
    models = pd.read_csv(T.E1_MISSINGNESS / "missingness_models.csv")
    air_effect = float(models.loc[(models.analysis == "station_year_conditional_logit") & (models.covariate == "z_air"), "log_odds"].iloc[0])
    trend_effect = float(models.loc[(models.analysis == "station_year_conditional_logit") & (models.covariate == "trend"), "log_odds"].iloc[0])
    used_min = args.min_years or settings["trend_min_complete_years"]
    station_jobs, meta = jobs(used_min)
    if args.min_years:
        OUT = OUT / f"min_years_{used_min}"
        OUT.mkdir(parents=True, exist_ok=True)
    elif len(station_jobs) < 30:
        station_jobs, meta = jobs(settings["trend_fallback_min_complete_years"])
        used_min = settings["trend_fallback_min_complete_years"]
    scenarios = {
        "mcar": {"trend": 0.0, "air": 0.0, "within_season": 0.0},
        "realistic_trend": {"trend": trend_effect, "air": 0.0, "within_season": 0.0},
        "mnar1": {"trend": trend_effect, "air": air_effect, "within_season": 1.0},
        "mnar2": {"trend": trend_effect, "air": 2 * air_effect, "within_season": 2.0},
    }
    print(f"[440] {len(station_jobs)} stations with >= {used_min} complete years; D2* = {meta['d2']}", flush=True)
    frames = []
    stations = position_index(job["station_key"] for job in station_jobs)
    for index, (name, scenario) in enumerate(scenarios.items()):
        results = Parallel(n_jobs=args.workers)(delayed(run_replicates)(job, scenario, settings["trend_replicates"], settings["multiple_imputations"], plain_seed(index, stations[job["station_key"]])) for job in station_jobs)
        frame = pd.DataFrame([row for rows in results for row in rows])
        frame.insert(0, "scenario", name)
        frames.append(frame)
    table = pd.concat(frames, ignore_index=True)
    table.to_parquet(OUT / "replicates.parquet", index=False)
    table["slope_error"] = table.slope - table.full_slope
    table["slope_ts_error"] = table.slope_ts - table.full_slope_ts
    summary = table.groupby(["scenario", "pipeline"]).agg(
        n_station_replicates=("slope", "size"), mean_years=("n_years", "mean"), slope_bias=("slope_error", "mean"),
        slope_rmse=("slope_error", lambda s: float(np.sqrt(np.nanmean(s**2)))), slope_ts_rmse=("slope_ts_error", lambda s: float(np.sqrt(np.nanmean(s**2)))),
        cover_full=("cover_full", "mean"), cover_missing_component=("cover_missing_component", "mean"),
        detect_warming=("detect_warming", "mean"), full_detect_warming=("full_detect_warming", "mean"),
        mean_h30_bias=("mean_h30", lambda s: np.nan), heatwave_delivered=("heatwave_delivered", "sum"), heatwave_years=("heatwave_years", "sum"),
        heatwave_abs_error=("heatwave_abs_error", "mean"), heatwave_signed_error=("heatwave_signed_error", "mean"),
        hot_true_incomplete=("hot_true_incomplete", "sum"), hot_missed_incomplete=("hot_missed_incomplete", "sum"),
        hot_false_incomplete=("hot_false_incomplete", "sum"), hot_unknown_incomplete=("hot_unknown_incomplete", "sum"),
    ).reset_index()
    climatology = table.assign(err=table.mean_h30 - table.full_mean_h30, exc=table.exceed_freq - table.full_exceed_freq).groupby(["scenario", "pipeline"]).agg(mean_h30_bias=("err", "mean"), exceed_freq_bias=("exc", "mean"))
    summary = summary.drop(columns="mean_h30_bias").merge(climatology.reset_index(), on=["scenario", "pipeline"])
    summary["hot_miss_rate_incomplete"] = summary.hot_missed_incomplete / summary.hot_true_incomplete.replace(0, np.nan)
    summary.to_csv(OUT / "summary.csv", index=False)
    regional = table.groupby(["scenario", "pipeline", "replicate", "region"]).agg(slope=("slope", "mean"), full=("full_slope", "mean"), n=("slope", "size")).reset_index()
    regional = regional.loc[regional.n >= 3]
    regional["error"] = regional.slope - regional.full
    regional.groupby(["scenario", "pipeline", "region"]).agg(bias=("error", "mean"), rmse=("error", lambda s: float(np.sqrt(np.mean(s**2)))), n_stations=("n", "first")).reset_index().to_csv(OUT / "regional_trend.csv", index=False)
    # Primary endpoint P4 on the fitted state-dependent scenario, with an independence-group bootstrap.
    primary = table.loc[table.scenario.eq("mnar1") & table.pipeline.isin(["A1", "C"])]
    by_station = primary.groupby(["group", "station_key", "pipeline"]).agg(sq=("slope_error", lambda s: float(np.nanmean(s**2))), bias=("slope_error", "mean"), cover=("cover_missing_component", "mean")).reset_index()
    wide = by_station.pivot_table(index=["group", "station_key"], columns="pipeline", values=["sq", "bias", "cover"]).reset_index()
    wide.columns = ["_".join(c).strip("_") for c in wide.columns]

    def reduction(frame: pd.DataFrame) -> float:
        return float(1 - np.sqrt(frame.sq_C.mean()) / np.sqrt(frame.sq_A1.mean()))

    boot = T.group_bootstrap(wide, "group", reduction, settings["bootstrap_draws"], settings["seed"])
    endpoint = {
        "scenario": "mnar1", "n_stations": int(len(wide)), "n_groups": int(wide.group.nunique()), "min_complete_years": used_min,
        "rmse_A1": float(np.sqrt(wide.sq_A1.mean())), "rmse_C": float(np.sqrt(wide.sq_C.mean())),
        "rmse_reduction": reduction(wide), "rmse_reduction_lower95": float(np.quantile(boot, 0.025)), "rmse_reduction_upper95": float(np.quantile(boot, 0.975)),
        "bias_A1": float(wide.bias_A1.mean()), "bias_C": float(wide.bias_C.mean()), "coverage_C_missing_component": float(wide.cover_C.mean()),
        "success_rule": "rmse_reduction >= 0.20, |bias_C| <= |bias_A1| + 0.01 C/decade, coverage in [0.90, 0.97]",
    }
    endpoint["P4_success"] = bool(endpoint["rmse_reduction"] >= 0.2 and abs(endpoint["bias_C"]) <= abs(endpoint["bias_A1"]) + 0.01 and 0.90 <= endpoint["coverage_C_missing_component"] <= 0.97)
    T.write_json(OUT / "endpoint_P4.json", endpoint)
    print(summary[["scenario", "pipeline", "mean_years", "slope_bias", "slope_rmse", "cover_full", "cover_missing_component", "detect_warming", "full_detect_warming", "mean_h30_bias", "heatwave_delivered", "heatwave_signed_error", "hot_miss_rate_incomplete"]].to_string(), flush=True)
    print(endpoint, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
