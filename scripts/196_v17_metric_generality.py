#!/usr/bin/env python3
"""Does the timing-over-length finding hold for metrics other than the peak?

The paper's title is a general claim about stream-temperature records, but the
evidence was built on one endpoint: the hottest consecutive 30-day mean. An
average over the year has no reason to behave like an extreme — for a mean, how
many days are missing should matter more than which days — and Johnson et al.
(2021) worked on the annual mean, phase and amplitude. If the axis claim is
specific to extremes, the title overclaims and must be narrowed.

Tolerances are set per metric at the same fraction of that metric's own
interannual standard deviation that 0.5 C is of the peak's (0.47), so the four
endpoints are compared on equal terms rather than in degrees.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402
from sklearn.pipeline import make_pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from stream_recoverability.experiments.v17_fitness.policies import (  # noqa: E402
    gather,
    information_conditioned_choice,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    NATURAL_SCALE_C,
    PRIMARY_TOLERANCE_C,
    RESULTS_ROOT,
    STEP3_CASES,
)

STEP17 = RESULTS_ROOT / "step17_metric_generality"
METRICS = ("hottest7", "hottest30", "annual_mean", "coldest30", "amplitude30")
RETENTION = 0.70
TOLERANCE_FRACTION = PRIMARY_TOLERANCE_C / NATURAL_SCALE_C  # 0.47 of a standard deviation

TIMING = ("peak_overlap", "warm_observed_fraction")
LENGTH = ("longest_run", "total_missing", "missing_fraction", "n_runs")
SIMPLE = ("peak_overlap", "warm_observed_fraction", "longest_run")


def natural_scale(cases: pd.DataFrame, metric: str) -> float:
    """Interannual SD of the metric itself, averaged over stations."""

    truth = cases.groupby(["network_id", "station_id", "year"])[f"truth_{metric}"].first().reset_index()
    per_station = truth.groupby(["network_id", "station_id"])[f"truth_{metric}"].agg(["std", "size"])
    per_station = per_station.loc[per_station["size"] >= 4, "std"].dropna()
    return float(per_station.mean())


def policy_error(cases: pd.DataFrame, metric: str) -> pd.Series:
    choice = information_conditioned_choice(cases)
    return pd.Series(gather(cases, choice, prefix=f"abserr_{metric}_"), index=cases.index)


def grouped_auc(X: pd.DataFrame, label: pd.Series, groups: np.ndarray, *, seed: int = 0) -> float:
    oof = np.full(len(label), np.nan)
    for train_idx, test_idx in GroupKFold(n_splits=5).split(X, label, groups):
        model = HistGradientBoostingRegressor(random_state=seed, max_depth=4, max_iter=300, learning_rate=0.06)
        model.fit(X.iloc[train_idx], label.iloc[train_idx])
        oof[test_idx] = model.predict(X.iloc[test_idx])
    return float(roc_auc_score(label, oof))


def frontier_rate(score: np.ndarray, error: np.ndarray, tolerance: float) -> float:
    good = np.isfinite(error)
    score = np.where(np.isfinite(score), score, np.inf)[good]
    error = error[good]
    order = np.argsort(score, kind="mergesort")
    k = max(1, int(round(RETENTION * len(error))))
    return float((error[order[:k]] > tolerance).mean())


def main() -> int:
    STEP17.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(STEP3_CASES / "cases.parquet")
    cases = cases.loc[cases["split_role"].eq("development")].reset_index(drop=True)
    groups = cases["network_id"].to_numpy()
    rng = np.random.default_rng(23)
    length_score = pd.to_numeric(cases["longest_run"], errors="coerce").to_numpy() + rng.random(len(cases))
    overlap_score = pd.to_numeric(cases["peak_overlap"], errors="coerce").to_numpy() + rng.random(len(cases)) * 1e-3
    random_score = rng.random(len(cases))

    sweep_rows = []
    rows = []
    contrasts = {}
    for metric in METRICS:
        scale = natural_scale(cases, metric)
        tolerance = TOLERANCE_FRACTION * scale
        error = policy_error(cases, metric)
        # Is the ordering of axes an artefact of where the tolerance is set?
        for fraction in (0.25, TOLERANCE_FRACTION, 1.0):
            tol = fraction * scale
            lab = (error > tol).astype(int)
            keep_any = error.notna()
            if lab[keep_any].nunique() < 2:
                continue
            auc_peak = float(roc_auc_score(lab[keep_any], cases.loc[keep_any, "peak_overlap"]))
            auc_warm = float(1 - roc_auc_score(lab[keep_any], cases.loc[keep_any, "warm_observed_fraction"]))
            auc_len = float(roc_auc_score(lab[keep_any], cases.loc[keep_any, "longest_run"]))
            sweep_rows.append(
                {
                    "metric": metric,
                    "tolerance_fraction_of_sd": fraction,
                    "tolerance_c": tol,
                    "base_rate": float(lab[keep_any].mean()),
                    "auc_peak_overlap": auc_peak,
                    "auc_warm_coverage": auc_warm,
                    "auc_longest_run": auc_len,
                    "winning_axis": "timing" if max(auc_peak, auc_warm) > auc_len else "length",
                }
            )
        label = (error > tolerance).astype(float)
        keep = error.notna()
        if label[keep].nunique() < 2 or int(keep.sum()) < 1000:
            continue
        X_all = cases.loc[keep, list(TIMING) + list(LENGTH)].apply(pd.to_numeric, errors="coerce")
        X_len = cases.loc[keep, list(LENGTH)].apply(pd.to_numeric, errors="coerce")
        y = label.loc[keep]
        g = groups[keep.to_numpy()]

        simple = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, random_state=0))
        Xs = cases[list(SIMPLE)].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        oof_simple = np.full(len(cases), np.nan)
        for tr, te in GroupKFold(n_splits=5).split(Xs, label.fillna(0), groups):
            simple.fit(Xs.iloc[tr], label.fillna(0).iloc[tr])
            oof_simple[te] = simple.predict_proba(Xs.iloc[te])[:, 1]

        err = error.to_numpy(dtype=float)
        row = {
            "metric": metric,
            "interannual_sd": scale,
            "tolerance_c": tolerance,
            "n": int(keep.sum()),
            "base_rate": float(label[keep].mean()),
            "auc_peak_overlap": float(roc_auc_score(y, cases.loc[keep, "peak_overlap"])),
            "auc_warm_coverage": float(1 - roc_auc_score(y, cases.loc[keep, "warm_observed_fraction"])),
            "auc_longest_run": float(roc_auc_score(y, cases.loc[keep, "longest_run"])),
            "auc_missing_fraction": float(roc_auc_score(y, cases.loc[keep, "missing_fraction"])),
            "grouped_auc_length_only": grouped_auc(X_len, y, g),
            "grouped_auc_length_plus_timing": grouped_auc(X_all, y, g),
            "rate_at_70_length_rule": frontier_rate(length_score, err, tolerance),
            "rate_at_70_peak_overlap_rule": frontier_rate(overlap_score, err, tolerance),
            "rate_at_70_three_variable_rule": frontier_rate(oof_simple, err, tolerance),
            "rate_at_70_random": frontier_rate(random_score, err, tolerance),
        }
        row["points_saved_three_variable"] = (row["rate_at_70_length_rule"] - row["rate_at_70_three_variable_rule"]) * 100
        rows.append(row)

        block = cases[["network_id"]].copy()
        block["simple"] = oof_simple
        block["length"] = length_score
        block["error"] = err
        block = block.dropna(subset=["error"])

        def contrast(sub: pd.DataFrame, tol=tolerance) -> float:
            k = max(1, int(round(RETENTION * len(sub))))
            a = sub.nsmallest(k, "simple")["error"].to_numpy()
            b = sub.nsmallest(k, "length")["error"].to_numpy()
            return float((a > tol).mean() - (b > tol).mean())

        contrasts[metric] = cluster_bootstrap(block, contrast, draws=1200, seed=0)

    table = pd.DataFrame(rows)
    table.to_csv(STEP17 / "metric_generality.csv", index=False)
    sweep = pd.DataFrame(sweep_rows)
    sweep.to_csv(STEP17 / "tolerance_sweep.csv", index=False)
    (STEP17 / "contrasts.json").write_text(json.dumps(contrasts, indent=2), encoding="utf-8")

    verdict = {
        "question": "does the timing-over-length finding hold for metrics other than the annual peak?",
        "tolerance_rule": f"{TOLERANCE_FRACTION:.3f} of each metric's own interannual standard deviation",
        "timing_beats_length_marginally": {
            str(r["metric"]): bool(max(r["auc_peak_overlap"], r["auc_warm_coverage"]) > r["auc_longest_run"])
            for r in rows
        },
        "three_variable_rule_beats_length_rule": {
            str(r["metric"]): bool(contrasts[r["metric"]]["high"] < 0) for r in rows
        },
        "points_saved": {str(r["metric"]): round(r["points_saved_three_variable"], 2) for r in rows},
        "winning_axis_is_stable_across_tolerances": {
            str(metric): sorted(set(block["winning_axis"]))
            for metric, block in sweep.groupby("metric")
        },
    }
    (STEP17 / "verdict.json").write_text(json.dumps(verdict, indent=2), encoding="utf-8")

    lines = ["# Step 17 — does the finding hold for other thermal metrics?", ""]
    lines.append(
        "Each metric is scored against a tolerance equal to "
        f"{TOLERANCE_FRACTION:.2f} of its own interannual standard deviation, so the four "
        "endpoints are compared on equal terms."
    )
    lines.append("")
    lines.append(table.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Which axis wins, across tolerances")
    lines.append("")
    lines.append(sweep.round(4).to_string(index=False))
    lines.append("")
    lines.append("## Three-variable rule minus length rule, at 70% retention, clustered by network")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(contrasts, indent=2))
    lines.append("```")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(verdict, indent=2))
    lines.append("```")
    (STEP17 / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(table.round(4).to_string(index=False))
    print()
    print(json.dumps({k: {"points": round(v["point"] * 100, 2), "ci": [round(v["low"] * 100, 2), round(v["high"] * 100, 2)]} for k, v in contrasts.items()}, indent=2))
    print()
    print(json.dumps(verdict, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
