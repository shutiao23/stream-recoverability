#!/usr/bin/env python3
"""TR-E4: target-aware estimators against the plug-in, cross-fitted leave-one-region-out.

Estimators of each annual target:
  P0     plug-in of the information-priority completion (the old delivered point)
  Pobs   computed from recorded days only (common practice)
  P1     Air2stream-3 plug-in, where air forcing allows a fit
  P2     functional debiasing: P0 plus a cross-fitted regression of the signed error
  P3     median of the seasonal air-state conditional simulation (P3raw: raw blocks)
  P5a    direct distribution regression (quantile boosting) without simulation inputs
  P5b    the same with the conditional-simulation summaries as inputs
Models never see the held-out region. Estimators are compared by quantile CRPS,
signed bias, coverage and MAE; RMSE is not a selection criterion.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse

import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_tr_common as T
import wrr_tr_features as F
from stream_recoverability.seeds import plain_seed

OUT = T.OUT / "e4_estimators"
QUANTILES = F.QUANTILES
TARGET_QUANTILES = {"h30": QUANTILES}
SHORT_QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=50, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, n_jobs=2)


def fit_fold(train: pd.DataFrame, test: pd.DataFrame, target: str, seed: int) -> pd.DataFrame:
    y = train[f"eval_truth_{target}"] - train[f"{target}__policy"]
    out = pd.DataFrame(index=test.index)
    quantiles = TARGET_QUANTILES.get(target, SHORT_QUANTILES)
    plain_train, plain_test = F.design_matrix(train, target, simulation=False), F.design_matrix(test, target, simulation=False)
    simulated_train, simulated_test = F.design_matrix(train, target, simulation=True), F.design_matrix(test, target, simulation=True)
    point = test[f"{target}__policy"]
    model = lgb.LGBMRegressor(objective="l2", random_state=seed, **PARAMS).fit(plain_train, y)
    out[f"{target}__P2"] = point + model.predict(plain_test)
    for name, (xtr, xte) in {"P5a": (plain_train, plain_test), "P5b": (simulated_train, simulated_test)}.items():
        predictions = []
        for q in quantiles:
            quantile_model = lgb.LGBMRegressor(objective="quantile", alpha=q, random_state=seed, **PARAMS).fit(xtr, y)
            predictions.append(quantile_model.predict(xte))
        predictions = np.sort(np.column_stack(predictions), axis=1)
        for q, values in zip(quantiles, predictions.T):
            out[f"{target}__{name}_q{int(q * 100):02d}"] = point + values
    return out


def quantile_crps(quantiles: np.ndarray, levels: tuple[float, ...], truth: np.ndarray) -> np.ndarray:
    """Twice the mean pinball loss over the stored levels (a CRPS approximation)."""

    loss = []
    for q, values in zip(levels, quantiles.T):
        diff = truth - values
        loss.append(np.maximum(q * diff, (q - 1) * diff))
    return 2 * np.mean(loss, axis=0)


def estimator_table(cases: pd.DataFrame, oof: pd.DataFrame, target: str) -> dict[str, dict]:
    """Point and (optional) quantiles per estimator, aligned to the case index."""

    quantiles = TARGET_QUANTILES.get(target, SHORT_QUANTILES)
    table = {
        "P0": {"point": cases[f"{target}__policy"]},
        "Pobs": {"point": cases.get(f"{target}__observed_days")},
        "P1": {"point": cases.get(f"{target}__air2stream3")},
        "P2": {"point": oof[f"{target}__P2"]},
    }
    if target == "h30":
        levels = QUANTILES
        table["P3"] = {"point": cases.state_h30_q50, "levels": levels, "quantiles": cases[[f"state_h30_q{int(q * 100):02d}" for q in levels]].to_numpy()}
        table["P3raw"] = {"point": cases.raw_h30_q50, "levels": levels, "quantiles": cases[[f"raw_h30_q{int(q * 100):02d}" for q in levels]].to_numpy()}
    else:
        levels = (0.05, 0.5, 0.95)
        table["P3"] = {"point": cases[f"state_{target}_q50"], "levels": levels, "quantiles": cases[[f"state_{target}_q05", f"state_{target}_q50", f"state_{target}_q95"]].to_numpy()}
    for name in ("P5a", "P5b"):
        columns = [f"{target}__{name}_q{int(q * 100):02d}" for q in quantiles]
        table[name] = {"point": oof[f"{target}__{name}_q50"], "levels": quantiles, "quantiles": oof[columns].to_numpy()}
    return table


def level_value(quantiles: np.ndarray, levels: tuple[float, ...], level: float) -> np.ndarray:
    """Vectorised linear interpolation of every case's quantile function at one level."""

    levels = np.asarray(levels)
    i = int(np.clip(np.searchsorted(levels, level) - 1, 0, len(levels) - 2))
    share = (level - levels[i]) / (levels[i + 1] - levels[i])
    return quantiles[:, i] + share * (quantiles[:, i + 1] - quantiles[:, i])


def interval(entry: dict, coverage: float) -> tuple[np.ndarray, np.ndarray] | None:
    levels = entry.get("levels")
    if levels is None:
        return None
    key = f"bounds{coverage}"
    if key not in entry:
        lower, upper = (1 - coverage) / 2, 1 - (1 - coverage) / 2
        entry[key] = (level_value(entry["quantiles"], levels, lower), level_value(entry["quantiles"], levels, upper))
    return entry[key]


def strata(cases: pd.DataFrame) -> dict[str, pd.Series]:
    hidden = cases.eval_true_peak_hidden_fraction
    warm_anomaly = (cases.eval_truth_h30 - cases.train_h30_mean) >= 1.0
    return {
        "all": pd.Series(True, index=cases.index),
        "peak_not_hidden": hidden.eq(0), "peak_partly_hidden": hidden.gt(0) & hidden.lt(0.5), "peak_half_hidden": hidden.ge(0.5),
        "air_layer_half_hidden": hidden.ge(0.5) & cases.policy_choice.eq("air_ridge"),
        "donor_layer_half_hidden": hidden.ge(0.5) & cases.policy_choice.eq("donor_ridge"),
        "climatology_layer_half_hidden": hidden.ge(0.5) & cases.policy_choice.isin(["smooth_climatology", "doy_climatology"]),
        "warm_anomaly_year": warm_anomaly, "warm_anomaly_half_hidden": warm_anomaly & hidden.ge(0.5),
        **{f"layer_{layer}": cases.policy_choice.eq(layer) for layer in F.LAYERS},
    }


def metrics(cases: pd.DataFrame, table: dict, target: str, weights: pd.Series, tolerance: float) -> pd.DataFrame:
    truth = cases[f"eval_truth_{target}"].to_numpy()
    rows = []
    for stratum, selected in strata(cases).items():
        base = selected.to_numpy() & (weights.to_numpy() > 0)
        for name, entry in table.items():
            point = entry["point"]
            if point is None:
                continue
            point = point.to_numpy(dtype=float)
            keep = base & np.isfinite(point)
            if keep.sum() < 20:
                continue
            w = weights.to_numpy()[keep]
            error = point[keep] - truth[keep]
            row = {
                "target": target, "stratum": stratum, "estimator": name, "n": int(keep.sum()), "availability": float(keep.sum() / max(base.sum(), 1)),
                "bias": float(np.average(error, weights=w)), "mae": float(np.average(np.abs(error), weights=w)),
                "failure_rate": float(np.average(np.abs(error) > tolerance, weights=w)), "share_under": float(np.average(error < 0, weights=w)),
            }
            if "levels" in entry:
                q = entry["quantiles"][keep]
                row["crps_q"] = float(np.average(quantile_crps(q, entry["levels"], truth[keep]), weights=w))
                for coverage in (0.5, 0.8, 0.9):
                    bounds = interval(entry, coverage)
                    if bounds is None or coverage > entry["levels"][-1] - entry["levels"][0] + 1e-9:
                        continue
                    lower, upper = bounds[0][keep], bounds[1][keep]
                    row[f"coverage{int(coverage * 100)}"] = float(np.average((truth[keep] >= lower) & (truth[keep] <= upper), weights=w))
                    row[f"width{int(coverage * 100)}"] = float(np.average(upper - lower, weights=w))
            if target == "h30" and name == "P3":
                row["crps_exact_draws"] = float(np.average(cases.loc[keep, "eval_state_h30_crps"], weights=w))
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", nargs="+", default=["h30", "h7", "annual_mean", "c30", T.DEGREE_DAYS, "days_above_20"])
    parser.add_argument("--workers", type=int, default=48)
    parser.add_argument("--cases", default=str(T.OUT / "e2_cases/cases.parquet"))
    parser.add_argument("--reuse", action="store_true", help="reuse saved out-of-fold predictions and only recompute metrics")
    args = parser.parse_args()
    settings = T.settings()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(args.cases)
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    regions = sorted(cases.region.unique())
    print(f"[432] {len(cases)} cases, {len(regions)} regions", flush=True)
    jobs = [(target, region) for target in args.targets for region in regions]
    cached = OUT / "oof_predictions.parquet"
    if args.reuse and cached.exists():
        oof = pd.read_parquet(cached)
        if len(oof) != len(cases) or not (oof.realization_id.to_numpy() == cases.realization_id.to_numpy()).all():
            raise RuntimeError("Cached out-of-fold predictions do not match the case table")
        oof = oof[[c for c in oof.columns if "__" in c]]
        return report(cases, oof, args, settings)
    folds = Parallel(n_jobs=args.workers, verbose=5)(
        delayed(fit_fold)(cases.loc[cases.region.ne(region)], cases.loc[cases.region.eq(region)], target, plain_seed(T.TARGETS.index(target), regions.index(region)))
        for target, region in jobs
    )
    oof = pd.concat([pd.concat([f for (t, _), f in zip(jobs, folds) if t == target]) for target in args.targets], axis=1).sort_index()
    keys = cases[["station_key", "year", "realization_id", "region", "independence_group", "design_family", "policy_choice"]]
    pd.concat([keys, oof], axis=1).to_parquet(OUT / "oof_predictions.parquet", index=False)
    return report(cases, oof, args, settings)


def report(cases: pd.DataFrame, oof: pd.DataFrame, args, settings: dict) -> int:
    tolerances = T.target_tolerances() if hasattr(T, "target_tolerances") else {}
    all_metrics = []
    for population in ("mech", "deploy", "mnar1", "mnar2"):
        weights = T.population_weights(cases, population)
        for target in args.targets:
            table = estimator_table(cases, oof, target)
            frame = metrics(cases, table, target, weights, tolerances.get(target, settings["tolerance_c"]))
            frame.insert(0, "population", population)
            all_metrics.append(frame)
    result = pd.concat(all_metrics, ignore_index=True)
    result.to_csv(OUT / "estimator_metrics.csv", index=False)
    view = result.loc[(result.target == "h30") & result.stratum.isin(["all", "peak_half_hidden", "air_layer_half_hidden", "warm_anomaly_half_hidden"])]
    print(view[["population", "stratum", "estimator", "n", "bias", "mae", "crps_q", "coverage90"]].to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
