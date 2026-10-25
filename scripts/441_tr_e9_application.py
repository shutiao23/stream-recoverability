#!/usr/bin/env python3
"""TR-E9: the frozen pipeline on the archive's real incomplete years (no truth).

An application, not a validation: how many real incomplete station-years each
rule keeps, how many the frozen target-aware rule admits, and how station and
regional H30 trends and the ranking of hot summers change when incomplete
years enter through multiple imputation rather than being dropped.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import json

import numpy as np
import pandas as pd

import wrr_tr_common as T
import wrr_tr_law as L
import wrr_tr_rules as R

OUT = T.OUT / "e9_application"
BUNDLE = T.load_script("tr2_bundle_for_e9", T.ROOT / "scripts/455_tr2_final_models.py")
SEALED = T.load_script("tr_sealed_for_e9", T.ROOT / "scripts/439_tr_e7_sealed.py")
E8 = T.load_script("tr_e8_for_e9", T.ROOT / "scripts/440_tr_e8_downstream.py")


def score_round1(real: pd.DataFrame) -> tuple[np.ndarray, tuple]:
    """Round 1: the frozen D2* distribution and its target-aware score, admitted by the layer thresholds of script 438."""

    pipeline = json.loads(SEALED.PIPELINE.read_text())
    oof, _ = SEALED.predict(real, pipeline)
    d2, levels = pipeline["d2"], tuple(pipeline["levels"])
    names = [f"q{int(level * 100):02d}" for level in levels]
    quantiles = real[[f"state_h30_{n}" for n in names]].to_numpy() if d2 == "P3" else oof[[f"h30__{d2}_{n}" for n in names]].to_numpy()
    real["d2_point"] = quantiles[:, list(levels).index(0.5)]
    real["score"] = SEALED.E5.predictive_pfail(quantiles, levels, real.d2_point.to_numpy(), pipeline["tolerance_c"])
    real["layer_group"] = real.policy_choice.where(real.policy_choice.isin(["donor_ridge", "air_ridge"]), "other")
    real["admitted"] = SEALED.E7.apply(real, "score", pipeline["thresholds"]["R7a_target_aware"], True)
    return quantiles, levels


def score_round2(real: pd.DataFrame) -> tuple[np.ndarray, tuple]:
    """Round 2: calibrated D2* quantiles and label-free expected-risk admission (R7b) within each region."""

    meta = json.loads((BUNDLE.BUNDLE / "bundle.json").read_text())
    scored = BUNDLE.apply_bundle(real)
    levels = tuple(meta["levels"])
    quantiles = scored[[f"d2_q{int(level * 100):02d}" for level in levels]].to_numpy()
    real["d2_point"] = scored.d2_point.to_numpy()
    real["score"] = scored.R7b.to_numpy()
    factor = meta["expected_risk"]["factor_k"]["R7b"]
    real["admitted"] = False
    for region, block in real.groupby("region"):
        accept = BUNDLE.expected_risk_admission(block.score.to_numpy(), np.ones(len(block)), meta["expected_risk"]["alpha"], factor)
        real.loc[block.index, "admitted"] = accept
    return quantiles, levels


def main() -> int:
    settings = T.settings()
    real = pd.read_parquet(OUT / "cases.parquet")
    real = real.loc[real.policy_choice.ne("unavailable") & real.state_h30_q50.notna()].reset_index(drop=True)
    # A station-year can appear in two networks; keep the first so each year counts once.
    real = real.drop_duplicates(["station_key", "year"]).reset_index(drop=True)
    quantiles, levels = score_round2(real) if settings.get("round", 1) == 2 else score_round1(real)
    real["d2_lower90"] = quantiles[:, 0]
    real["d2_upper90"] = quantiles[:, -1]
    features = R.mask_features(real)
    fixed = R.fixed_rules(features, real)
    for name, accept in fixed.items():
        real[f"rule::{name}"] = accept.to_numpy()
    real.drop(columns=[c for c in real if c.startswith("eval_")]).to_parquet(OUT / "real_year_estimates.parquet", index=False)
    rows = []
    for provider, block in [("all", real)] + list(real.groupby("provider")):
        row = {"provider": provider, "n_incomplete_station_years": len(block), "target_aware_admitted": float(block.admitted.mean()), "interval_reported": 1.0}
        for name in fixed:
            row[name] = float(block[f"rule::{name}"].mean())
        rows.append(row)
    usage = pd.DataFrame(rows)
    usage.to_csv(OUT / "usable_station_years.csv", index=False)

    # Station series: complete-year truths plus each pipeline's treatment of the real incomplete years.
    years = pd.read_parquet(T.E1 / "station_years.parquet")
    complete = years.loc[years.complete_year & years.truth_h30.notna(), ["station_key", "year", "truth_h30"]]
    rng = np.random.default_rng(settings["seed"])
    trend_rows, series_rows = [], []
    for station, block in real.groupby("station_key"):
        base = complete.loc[complete.station_key.eq(station)]
        if len(base) + len(block) < 15:
            continue
        x_complete = base.year.to_numpy(dtype=float)
        y_complete = base.truth_h30.to_numpy()
        a1 = block.loc[block.warm_observed_fraction >= 0.9]
        a1_values = np.where(a1.h30__observed_days.notna(), a1.h30__observed_days, a1.h30__policy)
        x_a1, y_a1 = np.r_[x_complete, a1.year.to_numpy(dtype=float)], np.r_[y_complete, a1_values]
        draws = E8.inverse_cdf(np.repeat(quantiles[block.index.to_numpy()][None], settings["multiple_imputations"], axis=0).reshape(-1, len(levels)), np.asarray(levels), rng.random((settings["multiple_imputations"] * len(block), 1))).reshape(settings["multiple_imputations"], len(block))
        slopes = [E8.ols(np.r_[x_complete, block.year.to_numpy(dtype=float)], np.r_[y_complete, draws[m]])[0] for m in range(settings["multiple_imputations"])]
        a0 = E8.ols(x_complete, y_complete) if len(base) >= 5 else (np.nan, np.nan)
        trend_rows.append({"station_key": station, "provider": block.provider.iloc[0], "region": block.region.iloc[0], "n_complete": len(base), "n_incomplete": len(block), "n_a1": len(x_a1), "slope_A0": a0[0], "slope_A1": E8.ols(x_a1, y_a1)[0], "slope_B": E8.ols(np.r_[x_complete, block.year.to_numpy(dtype=float)], np.r_[y_complete, block.h30__policy.to_numpy()])[0], "slope_C": float(np.mean(slopes))})
        for (year, value), lower, upper, admitted in zip(block[["year", "d2_point"]].itertuples(index=False), block.d2_lower90, block.d2_upper90, block.admitted):
            series_rows.append({"station_key": station, "region": block.region.iloc[0], "year": int(year), "kind": "incomplete", "h30": value, "lower90": lower, "upper90": upper, "admitted": bool(admitted)})
        for year, value in zip(base.year, base.truth_h30):
            series_rows.append({"station_key": station, "region": block.region.iloc[0], "year": int(year), "kind": "complete", "h30": value})
    trends = pd.DataFrame(trend_rows)
    trends.to_csv(OUT / "station_trends.csv", index=False)
    series = pd.DataFrame(series_rows)
    series.to_parquet(OUT / "station_series.parquet", index=False)
    regional = trends.groupby("region").agg(n_stations=("station_key", "size"), slope_A0=("slope_A0", "mean"), slope_A1=("slope_A1", "mean"), slope_B=("slope_B", "mean"), slope_C=("slope_C", "mean"), n_incomplete=("n_incomplete", "sum")).reset_index()
    regional.to_csv(OUT / "regional_trends.csv", index=False)
    # Hot-summer ranking: regional mean H30 anomaly with complete years only versus all years.
    series["anomaly"] = series.h30 - series.groupby("station_key").h30.transform("mean")
    rank_rows = []
    for region, block in series.groupby("region"):
        complete_only = block.loc[block.kind.eq("complete")].groupby("year").anomaly.mean()
        all_years = block.groupby("year").anomaly.mean()
        counts = block.groupby("year").station_key.nunique()
        top_all = all_years.loc[counts.reindex(all_years.index) >= 3].sort_values(ascending=False).head(5)
        top_complete = complete_only.sort_values(ascending=False).head(5)
        rank_rows.append({"region": region, "top5_all_years": ";".join(map(str, top_all.index)), "top5_complete_only": ";".join(map(str, top_complete.index)), "n_top5_changed": int(len(set(top_all.index) ^ set(top_complete.index)) // 2)})
    pd.DataFrame(rank_rows).to_csv(OUT / "hot_summer_ranking.csv", index=False)
    summary = {
        "n_real_incomplete_station_years": len(real), "n_stations": int(real.station_key.nunique()),
        "target_aware_admitted_share": float(real.admitted.mean()),
        "best_rule_share": float(usage.loc[usage.provider.eq("all"), list(fixed)].max(axis=1).iloc[0]),
        "regional_mean_slope_change_C_minus_A1": float((trends.slope_C - trends.slope_A1).mean()),
        "regional_mean_slope_change_B_minus_A1": float((trends.slope_B - trends.slope_A1).mean()),
        "n_trend_stations": len(trends), "role": "application without truth; not a validation",
    }
    T.write_json(OUT / "summary.json", summary)
    print(usage.to_string(), flush=True)
    print(regional.to_string(), flush=True)
    print(pd.DataFrame(rank_rows).to_string(), flush=True)
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
