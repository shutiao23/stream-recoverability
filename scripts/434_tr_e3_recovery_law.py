#!/usr/bin/env python3
"""TR-E3: does the recovery law explain and predict the plug-in H30 error?

The law (scripts/wrr_tr_law.py) predicts the signed bias, spread and failure
probability of P0 from training-period quantities only. It is compared with
the realised errors on the length x overlap x layer cells of P-mech, by
reliability and expected calibration error, and by layer to show why air-only
reconstructions fail more often.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_tr_common as T
import wrr_tr_law as L

OUT = T.OUT / "e3_recovery_law"


def chunked_law(frame: pd.DataFrame, tolerance: float, truncate: bool, version: str) -> pd.DataFrame:
    return L.apply_law(frame, tolerance, truncate, version)


def reliability(predicted: np.ndarray, observed: np.ndarray, weights: np.ndarray, bins: int = 10) -> tuple[pd.DataFrame, float]:
    edges = np.unique(np.quantile(predicted, np.linspace(0, 1, bins + 1)))
    labels = np.clip(np.searchsorted(edges, predicted, side="right") - 1, 0, len(edges) - 2)
    rows = []
    for label in np.unique(labels):
        keep = labels == label
        w = weights[keep]
        rows.append({"bin": int(label), "n": int(keep.sum()), "predicted": float(np.average(predicted[keep], weights=w)), "observed": float(np.average(observed[keep], weights=w)), "weight": float(w.sum())})
    table = pd.DataFrame(rows)
    ece = float(np.sum(table.weight * np.abs(table.predicted - table.observed)) / table.weight.sum())
    return table, ece


def auc(score: np.ndarray, label: np.ndarray, weight: np.ndarray) -> float:
    """Weighted area under the ROC curve (ties counted half)."""

    positive, negative = label > 0.5, label <= 0.5
    if not positive.any() or not negative.any():
        return float("nan")
    order = np.argsort(score, kind="mergesort")
    s, w, y = score[order], weight[order], positive[order]
    unique, inverse = np.unique(s, return_inverse=True)
    pos = np.bincount(inverse, weights=w * y)
    neg = np.bincount(inverse, weights=w * ~y)
    cum_neg = np.cumsum(neg) - neg
    return float(np.sum(pos * (cum_neg + 0.5 * neg)) / (pos.sum() * neg.sum()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(T.OUT / "e2_cases/cases.parquet"))
    parser.add_argument("--output", default=str(OUT))
    parser.add_argument("--workers", type=int, default=96)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    settings = T.settings()
    cases = pd.read_parquet(args.cases)
    cases = cases.loc[cases.policy_choice.ne("unavailable") & cases.eval_truth_h30.notna() & cases.state_h30_q50.notna()].reset_index(drop=True)
    chunks = np.array_split(cases.index.to_numpy(), args.workers * 4)
    laws = {}
    grid = [("v2", tolerance, truncate) for tolerance in settings["tolerance_sensitivity_c"] for truncate in (True, False)]
    grid += [("v1", settings["tolerance_c"], truncate) for truncate in (True, False)]
    if "law_sigma_r_peak" in cases:
        grid += [("v2p", tolerance, True) for tolerance in settings["tolerance_sensitivity_c"]]
    if "law_replay_errors" in cases:
        grid += [("v3", tolerance, True) for tolerance in settings["tolerance_sensitivity_c"]]
    for version, tolerance, truncate in grid:
        parts = Parallel(n_jobs=args.workers)(delayed(chunked_law)(cases.loc[chunk], tolerance, truncate, version) for chunk in chunks)
        laws[(version, tolerance, truncate)] = pd.concat(parts).sort_index()
    main_law = laws[("v2", settings["tolerance_c"], True)]
    predictions = cases[["station_key", "year", "realization_id", "region", "independence_group", "design_family", "policy_choice"]].copy()
    for (version, tolerance, truncate), frame in laws.items():
        prefix = {"v2": "law", "v1": "law_v1", "v3": "law_v3", "v2p": "law_v2p"}[version]
        suffix = f"_{int(tolerance * 100):03d}{'' if truncate else '_untruncated'}"
        predictions[f"{prefix}_pfail{suffix}"] = frame.law_pfail
        if tolerance == settings["tolerance_c"]:
            predictions[f"{prefix}_bias{'' if truncate else '_untruncated'}"] = frame.law_bias
            predictions[f"{prefix}_sd{'' if truncate else '_untruncated'}"] = frame.law_sd
    predictions["law_r2"] = main_law.law_r2
    predictions.to_parquet(output / "law_predictions.parquet", index=False)

    error = cases.h30__policy - cases.eval_truth_h30
    fail = (error.abs() > settings["tolerance_c"]).astype(float)
    rows, reliabilities = [], []
    for population in ("mech", "deploy"):
        weights = T.population_weights(cases, population)
        keep = (weights > 0) & main_law.law_pfail.notna()
        for version in [v for v in ("v2", "v1", "v3", "v2p") if (v, settings["tolerance_c"], True) in laws]:
            for truncate in (True, False):
                if (version, settings["tolerance_c"], truncate) not in laws:
                    continue
                law = laws[(version, settings["tolerance_c"], truncate)]
                keep = (weights > 0) & law.law_pfail.notna()
                table, ece = reliability(law.law_pfail[keep].to_numpy(), fail[keep].to_numpy(), weights[keep].to_numpy())
                table.insert(0, "population", population)
                table.insert(1, "version", version)
                table.insert(2, "truncated", truncate)
                reliabilities.append(table)
                tag = {"population": population, "version": version, "truncated": truncate}
                rows.append({**tag, "metric": "ece", "value": ece})
                brier = float(np.average((law.law_pfail[keep] - fail[keep]) ** 2, weights=weights[keep]))
                base = float(np.average(fail[keep], weights=weights[keep]))
                rows.append({**tag, "metric": "brier", "value": brier})
                rows.append({**tag, "metric": "brier_skill_vs_base_rate", "value": 1 - brier / (base * (1 - base))})
                rows.append({**tag, "metric": "mean_predicted_pfail", "value": float(np.average(law.law_pfail[keep], weights=weights[keep]))})
                rows.append({**tag, "metric": "observed_failure_rate", "value": base})
                rows.append({**tag, "metric": "mean_predicted_bias", "value": float(np.average(law.law_bias[keep], weights=weights[keep]))})
                rows.append({**tag, "metric": "observed_mean_error", "value": float(np.average(error[keep], weights=weights[keep]))})
                rows.append({**tag, "metric": "availability", "value": float(keep.sum() / (weights > 0).sum())})
                rows.append({**tag, "metric": "auc", "value": auc(law.law_pfail[keep].to_numpy(), fail[keep].to_numpy(), weights[keep].to_numpy())})
    pd.concat(reliabilities).to_csv(output / "reliability.csv", index=False)

    # Cells of the mechanism population: length x overlap x layer.
    mech = cases.design_family.eq("crossed")
    cells = pd.DataFrame({
        "gap_length": cases.gap_length, "overlap_class": cases.overlap_class, "layer": cases.policy_choice,
        "error": error, "fail": fail, "law_bias": main_law.law_bias, "law_pfail": main_law.law_pfail,
        "law_bias_untruncated": laws[("v2", settings["tolerance_c"], False)].law_bias,
        "law_v1_bias": laws[("v1", settings["tolerance_c"], True)].law_bias, "law_v1_pfail": laws[("v1", settings["tolerance_c"], True)].law_pfail,
        **({"law_v3_bias": laws[("v3", settings["tolerance_c"], True)].law_bias, "law_v3_pfail": laws[("v3", settings["tolerance_c"], True)].law_pfail} if ("v3", settings["tolerance_c"], True) in laws else {}),
        **({"law_v2p_bias": laws[("v2p", settings["tolerance_c"], True)].law_bias, "law_v2p_pfail": laws[("v2p", settings["tolerance_c"], True)].law_pfail} if ("v2p", settings["tolerance_c"], True) in laws else {}),
    }).loc[mech]
    cell = cells.groupby(["gap_length", "overlap_class", "layer"]).agg(
        n=("error", "size"), mean_error=("error", "mean"), failure_rate=("fail", "mean"), law_bias=("law_bias", "mean"),
        law_bias_untruncated=("law_bias_untruncated", "mean"), law_pfail=("law_pfail", "mean"),
        law_v1_bias=("law_v1_bias", "mean"), law_v1_pfail=("law_v1_pfail", "mean"),
        **({"law_v3_bias": ("law_v3_bias", "mean"), "law_v3_pfail": ("law_v3_pfail", "mean")} if "law_v3_bias" in cells else {}),
        **({"law_v2p_bias": ("law_v2p_bias", "mean"), "law_v2p_pfail": ("law_v2p_pfail", "mean")} if "law_v2p_bias" in cells else {}),
    ).reset_index()
    cell = cell.loc[cell.n >= 30]
    cell.to_csv(output / "cells.csv", index=False)

    def explained(actual: pd.Series, predicted: pd.Series, n: pd.Series) -> float:
        centre = np.average(actual, weights=n)
        return float(1 - np.sum(n * (actual - predicted) ** 2) / np.sum(n * (actual - centre) ** 2))

    pairs = [("law_bias", "mean_error"), ("law_bias_untruncated", "mean_error"), ("law_pfail", "failure_rate"), ("law_v1_bias", "mean_error"), ("law_v1_pfail", "failure_rate")]
    pairs += [("law_v3_bias", "mean_error"), ("law_v3_pfail", "failure_rate")] if "law_v3_bias" in cell else []
    pairs += [("law_v2p_bias", "mean_error"), ("law_v2p_pfail", "failure_rate")] if "law_v2p_bias" in cell else []
    # Hardest cells: the five with the highest observed failure rate.
    hardest = cell.nlargest(5, "failure_rate")
    for column in [c for c in ("law_pfail", "law_v1_pfail", "law_v2p_pfail", "law_v3_pfail") if c in cell]:
        rows.append({"population": "mech_hardest5_cells", "version": column, "truncated": True, "metric": "mean_predicted_minus_observed_failure", "value": float((hardest[column] - hardest.failure_rate).mean())})
    for column, target in pairs:
        rows.append({"population": "mech_cells", "version": "v1" if "v1" in column else ("v3" if "v3" in column else ("v2p" if "v2p" in column else "v2")), "truncated": column != "law_bias_untruncated", "metric": f"explained_variance_{target}_by_{column}", "value": explained(cell[target], cell[column], cell.n)})
    by_layer = pd.DataFrame({"layer": cases.policy_choice, "population": np.where(mech, "mech", "deploy"), "fail": fail, "law_pfail": main_law.law_pfail, "law_r2": main_law.law_r2, "error": error, "law_bias": main_law.law_bias})
    by_layer.groupby(["population", "layer"]).agg(n=("fail", "size"), failure_rate=("fail", "mean"), law_pfail=("law_pfail", "mean"), law_r2=("law_r2", "median"), mean_error=("error", "mean"), law_bias=("law_bias", "mean")).reset_index().to_csv(output / "by_layer.csv", index=False)
    summary = pd.DataFrame(rows)
    summary.to_csv(output / "summary.csv", index=False)
    print(summary.to_string(), flush=True)
    print(cell.sort_values(["layer", "gap_length", "overlap_class"]).to_string(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
