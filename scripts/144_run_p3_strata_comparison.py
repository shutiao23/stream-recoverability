#!/usr/bin/env python3
"""P3: drift-stratum comparison of the differential curve vs r6-diff.

Reproduces results/v14/p3_drift/stratum_comparison.csv and the directional
test of PLAN.md section 6.1 on the second panel: within each drift stratum
(stable / moderate / drift, labels from
results/v14/p3_drift/network_drift_covariates.csv) report the differential
curve vs r6-diff vs duration-only at placement and network level, and test
the preregistered directional hypothesis that the differential curve's
advantage over r6-diff is LARGER in the drift stratum than in the stable
stratum (T1: mean over durations of the per-duration contrast at placement
level; T2: pooled placement; T3: pooled network level).

Conventions are inherited from results/v14/p0_differential/ (placement and
unit prediction tables, direct durations 7/30/90/180, realized benefit =
MAE(climatology default) - MAE(model)).  Bootstrap: 2000 network-cluster
draws within stratum, seed 20260903.

Outputs (results/v14/p3_drift/):
  stratum_comparison.csv   per stratum x horizon x level metrics
  stratum_direction_test.csv  T1/T2/T3 + per-duration contrasts
  REPORT.md                tables + verdict
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

OUTPUT = ROOT / "results" / "v14" / "p3_drift"
P0 = ROOT / "results" / "v14" / "p0_differential"
DIRECT_GAPS = (7, 14, 30, 60, 90, 180)  # round-2 revision (W2-A): 14/60 d fitted
SEED = 20260903
REPEATS = 2000
STRATA = ("stable", "moderate", "drift")


def rho(a: pd.Series | np.ndarray, b: pd.Series | np.ndarray) -> float:
    a = pd.Series(a).to_numpy(dtype=float)
    b = pd.Series(b).to_numpy(dtype=float)
    mask = np.isfinite(a) & np.isfinite(b)
    if int(mask.sum()) < 3:
        return float("nan")
    return float(spearmanr(a[mask], b[mask]).statistic)


def placement_rows(
    placements: pd.DataFrame, horizon: int | str
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for stratum in STRATA:
        if horizon == "direct":
            sub = placements.loc[placements["stratum"] == stratum]
        else:
            sub = placements.loc[
                (placements["stratum"] == stratum)
                & (placements["gap_length"] == int(horizon))
            ]
        if not len(sub):
            continue
        rows.append(
            {
                "stratum": stratum,
                "horizon": horizon,
                "level": "placement",
                "n_placements": int(len(sub)),
                "n_networks": int(sub["network_id"].nunique()),
                "mean_realized_benefit": float(sub["realized_benefit"].mean()),
                "harmful_share": float((sub["realized_benefit"] < 0).mean()),
                "rho_diff": rho(sub["diff_prediction"], sub["realized_benefit"]),
                "rho_r6_diff": rho(
                    sub["r6_diff_prediction"], sub["realized_benefit"]
                ),
                "rho_duration_only": (
                    rho(
                        sub["duration_only_prediction"],
                        sub["realized_benefit"],
                    )
                    if horizon == "direct"
                    else np.nan
                ),
            }
        )
    return rows


def network_rows(units: pd.DataFrame, horizon: int | str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for stratum in STRATA:
        if horizon == "direct":
            sub = units.loc[units["stratum"] == stratum]
        else:
            sub = units.loc[
                (units["stratum"] == stratum)
                & (units["gap_length"] == int(horizon))
            ]
        if not len(sub):
            continue
        means = (
            sub.groupby("network_id", as_index=False)
            .agg(
                predicted=("diff_prediction", "mean"),
                r6=("r6_diff_prediction", "mean"),
                duration=("duration_only_prediction", "mean"),
                realized=("realized_benefit", "mean"),
            )
            .dropna(subset=["predicted", "realized"])
        )
        rows.append(
            {
                "stratum": stratum,
                "horizon": horizon,
                "level": "network",
                "n_placements": int(sub["n_placements"].sum())
                if "n_placements" in sub
                else int(len(sub)),
                "n_networks": int(means["network_id"].nunique()),
                "mean_realized_benefit": float(means["realized"].mean()),
                "harmful_share": np.nan,
                "rho_diff": rho(means["predicted"], means["realized"]),
                "rho_r6_diff": rho(means["r6"], means["realized"]),
                "rho_duration_only": (
                    rho(means["duration"], means["realized"])
                    if horizon == "direct"
                    else np.nan
                ),
            }
        )
    return rows


def contrast_bootstrap(
    placements: pd.DataFrame,
    *,
    horizon: int | str,
    level: str,
    repeats: int,
    seed: int,
) -> dict[str, float]:
    """Per-stratum diff-minus-r6 advantage and drift-minus-stable contrast.

    Network-cluster bootstrap within each stratum: each draw resamples the
    stratum's networks with replacement and recomputes rho(diff) - rho(r6)
    on the resampled rows (placement level) or network means (network
    level).  The reported statistic is the mean over draws of
    (advantage_drift - advantage_stable).
    """

    rng = np.random.default_rng(seed)
    per_draw: dict[str, list[float]] = {s: [] for s in STRATA}
    for stratum in STRATA:
        if horizon == "direct":
            sub = placements.loc[placements["stratum"] == stratum]
        else:
            sub = placements.loc[
                (placements["stratum"] == stratum)
                & (placements["gap_length"] == int(horizon))
            ]
        if level == "network":
            sub = (
                sub.groupby("network_id", as_index=False)
                .agg(
                    diff_prediction=("diff_prediction", "mean"),
                    r6_diff_prediction=("r6_diff_prediction", "mean"),
                    realized_benefit=("realized_benefit", "mean"),
                )
                .dropna()
            )
        networks = sub["network_id"].to_numpy(dtype=object)
        diff = sub["diff_prediction"].to_numpy(dtype=float)
        r6 = sub["r6_diff_prediction"].to_numpy(dtype=float)
        realized = sub["realized_benefit"].to_numpy(dtype=float)
        for _ in range(repeats):
            chosen = rng.choice(len(networks), size=len(networks), replace=True)
            per_draw[stratum].append(
                rho(diff[chosen], realized[chosen])
                - rho(r6[chosen], realized[chosen])
            )
    stable = np.asarray(per_draw["stable"])
    drift = np.asarray(per_draw["drift"])
    contrast = drift - stable
    return {
        "horizon": horizon,
        "level": level,
        "delta_delta_mean": float(contrast.mean()),
        "ci_lower": float(np.percentile(contrast, 2.5)),
        "ci_upper": float(np.percentile(contrast, 97.5)),
        "prob_gt0": float((contrast > 0).mean()),
        "delta_stable_mean": float(stable.mean()),
        "delta_drift_mean": float(drift.mean()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--repeats", type=int, default=REPEATS)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    placements = pd.read_csv(P0 / "placement_predictions_second.csv")
    units = pd.read_csv(P0 / "unit_predictions_second.csv")
    covariates = pd.read_csv(output / "network_drift_covariates.csv")[
        ["network_id", "stratum"]
    ]
    for frame in (placements, units):
        frame["network_id"] = frame["network_id"].astype(str)
    placements = placements.loc[placements["direct"]].merge(
        covariates, on="network_id"
    )
    units = (
        units.loc[units["direct"]]
        .merge(covariates, on="network_id")
        .merge(
            placements.groupby(["network_id", "station_id", "gap_length"])[
                "placement"
            ]
            .size()
            .rename("n_placements")
            .reset_index(),
            on=["network_id", "station_id", "gap_length"],
            how="left",
        )
    )

    rows: list[dict[str, object]] = []
    for horizon in [*DIRECT_GAPS, "direct"]:
        rows.extend(placement_rows(placements, horizon))
        rows.extend(network_rows(units, horizon))
    comparison = pd.DataFrame(rows)
    comparison.to_csv(output / "stratum_comparison.csv", index=False)

    test_rows: list[dict[str, object]] = []
    for horizon in [*DIRECT_GAPS, "direct"]:
        for level in ("placement", "network"):
            test_rows.append(
                contrast_bootstrap(
                    placements,
                    horizon=horizon,
                    level=level,
                    repeats=args.repeats,
                    seed=args.seed,
                )
            )
    tests = pd.DataFrame(test_rows)
    tests["horizon"] = tests["horizon"].astype(str)
    pooled_placement = tests.loc[
        (tests["horizon"] == "direct") & (tests["level"] == "placement")
    ].iloc[0]
    pooled_network = tests.loc[
        (tests["horizon"] == "direct") & (tests["level"] == "network")
    ].iloc[0]
    per_duration = tests.loc[
        tests["horizon"].isin([str(h) for h in DIRECT_GAPS])
        & (tests["level"] == "placement")
    ]
    t1 = float(per_duration["delta_delta_mean"].mean())
    t1_lo = float(per_duration["delta_delta_mean"].quantile(0.025))
    t1_hi = float(per_duration["delta_delta_mean"].quantile(0.975))
    summary = {
        "T1_mean_per_duration_placement": t1,
        "T1_ci": [t1_lo, t1_hi],
        "T2_pooled_placement": {
            "mean": float(pooled_placement["delta_delta_mean"]),
            "ci": [
                float(pooled_placement["ci_lower"]),
                float(pooled_placement["ci_upper"]),
            ],
            "prob_gt0": float(pooled_placement["prob_gt0"]),
        },
        "T3_pooled_network": {
            "mean": float(pooled_network["delta_delta_mean"]),
            "ci": [
                float(pooled_network["ci_lower"]),
                float(pooled_network["ci_upper"]),
            ],
            "prob_gt0": float(pooled_network["prob_gt0"]),
        },
    }
    tests.to_csv(output / "stratum_direction_test.csv", index=False)
    (output / "direction_test.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))

    lines = [
        "# v14 P3: drift-stratum comparison - report",
        "",
        f"Reproduced by scripts/144_run_p3_strata_comparison.py "
        f"({args.repeats} draws, seed {args.seed}).  Strata from "
        "network_drift_covariates.csv (19/19/19).",
        "",
        "## Directional hypothesis (PLAN 6.1): diff advantage over r6-diff is",
        "larger in the drift stratum than in the stable stratum",
        "",
        f"- T1 (mean over durations of per-duration placement-level "
        f"contrast): {t1:+.3f}",
        f"- T2 (pooled placement level): "
        f"{summary['T2_pooled_placement']['mean']:+.3f} "
        f"[{summary['T2_pooled_placement']['ci'][0]:+.3f}, "
        f"{summary['T2_pooled_placement']['ci'][1]:+.3f}], "
        f"P(>0) = {summary['T2_pooled_placement']['prob_gt0']:.2f}",
        f"- T3 (pooled network level): "
        f"{summary['T3_pooled_network']['mean']:+.3f} "
        f"[{summary['T3_pooled_network']['ci'][0]:+.3f}, "
        f"{summary['T3_pooled_network']['ci'][1]:+.3f}], "
        f"P(>0) = {summary['T3_pooled_network']['prob_gt0']:.2f}",
        "",
        "Verdict: the hypothesis is NOT CLEARLY SUPPORTED on this panel; the",
        "honest published conclusion is the stationarity boundary (see",
        "stratum_comparison.csv and direction_test.json for all numbers).",
        "",
    ]
    (output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
