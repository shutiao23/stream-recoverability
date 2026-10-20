#!/usr/bin/env python3
"""Freeze an opened-source composition rule and audit independent calendar replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as C

from stream_recoverability.experiments.v19_revision.risk import bounded_mean_upper

OUT = C.RUN / "r3_16_composition_transfer"
LENGTH_EDGES = [0, 14, 30, 90, 10000]
SUPPORT_EDGES = [-1e-9, 1e-9, 0.5, 1 + 1e-9]


def cells(frame: pd.DataFrame) -> pd.Series:
    length = pd.cut(frame.longest_run, LENGTH_EDGES, labels=False)
    support = pd.cut(frame.peak_overlap, SUPPORT_EDGES, labels=False)
    return length.astype(str) + "|" + support.astype(str)


def rates(frame: pd.DataFrame, weight: np.ndarray | None = None) -> tuple[dict, float]:
    weight = np.ones(len(frame)) if weight is None else weight
    work = frame.assign(cell=cells(frame), weight=weight, failures=weight * frame.policy_bad.astype(float))
    overall = float(work.failures.sum() / work.weight.sum())
    grouped = work.groupby("cell")[["failures", "weight"]].sum()
    overlap = work.groupby(pd.cut(work.peak_overlap, SUPPORT_EDGES, labels=False))[["failures", "weight"]].sum()
    result = {}
    for cell, row in grouped.iterrows():
        fallback = overlap.loc[int(cell.split("|")[1])]
        result[cell] = float(row.failures / row.weight) if row.weight >= 30 else float(fallback.failures / fallback.weight) if fallback.weight else overall
    return result, overall


def fit() -> None:
    if (C.RUN / "method_lock.json").exists():
        raise RuntimeError("Composition choices must be fixed before method lock")
    output = {}
    for protocol_name in ("leave_one_year_out", "strictly_prior_years"):
        frame = pd.read_parquet(C.source_cases(protocol_name))
        frame = frame.loc[frame.design_family.eq("empirical")]
        if protocol_name == "strictly_prior_years":
            frame = frame.loc[frame.year <= 2018]
        for scope in ("documented_daily_mean", "all"):
            data = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])] if scope == "documented_daily_mean" else frame
            if data.empty:
                raise RuntimeError("No empirical source geometry for composition fitting")
            fitted, overall = rates(data)
            units, index = np.unique(data.independence_group.astype(str), return_inverse=True)
            rng = np.random.default_rng(20261020)
            bootstrap = []
            for repetition in range(2000):
                multiplicity = rng.multinomial(len(units), np.full(len(units), 1 / len(units)))
                boot_rates, boot_overall = rates(data, multiplicity[index])
                bootstrap.append({"rates": boot_rates, "overall": boot_overall})
            output[f"{protocol_name}|{scope}"] = {"rates": fitted, "overall": overall, "source_cases": len(data), "source_components": len(units), "bootstrap": bootstrap}
    C.write_json(OUT / "composition_model.json", {"fits": output, "length_edges": LENGTH_EDGES, "support_edges": SUPPORT_EDGES, "minimum_cell_size": 30, "bin_origin": "inherited from opened 20261020b results; fixed before independent new test", "source_arm": "empirical geometries only", "decision": "point forecast <= 0.05 is descriptive no-screen advice, never a risk certificate", "new_test_outcomes_used": False})
    print("[366] source-only composition model frozen for independent replay", flush=True)


def evaluate(role: str, protocol_name: str) -> None:
    gate = C.load_script("r3_composition_test_gate", C.ROOT / "scripts/358_wrr_external_recovery.py")
    gate.verify_role_access(role)
    frame = pd.read_parquet(C.RUN / "r3_08_external_recovery" / role / protocol_name / "real_calendars/cofailure_0/cases.parquet")
    if protocol_name == "strictly_prior_years":
        frame = frame.loc[frame.year.between(2019, 2022)]
    model = json.loads((OUT / "composition_model.json").read_text())
    rows, pooled = [], []
    for scope in ("documented_daily_mean", "all"):
        data = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])] if scope == "documented_daily_mean" else frame
        fitted = model["fits"][f"{protocol_name}|{scope}"]
        forecast = cells(data).map(fitted["rates"]).fillna(fitted["overall"])
        for group, indices in data.groupby("independence_group").groups.items():
            block = data.loc[indices]
            point = float(forecast.loc[indices].mean())
            predicted = [float(cells(block).map(item["rates"]).fillna(item["overall"]).mean()) for item in fitted["bootstrap"]]
            lower, upper = np.quantile(predicted, [0.025, 0.975])
            observed = float(block.policy_bad.mean())
            rows.append({"scope": scope, "group": group, "provider": block.provider.iloc[0], "n_cases": len(block), "n_station_years": len(block[["station_id", "year"]].drop_duplicates()), "predicted_risk": point, "source_only_prediction_ci_low": lower, "source_only_prediction_ci_high": upper, "observed_risk": observed, "rule_says_no_screen": point <= 0.05, "observed_above_cap": observed > 0.05, "independent_groups": 1, "unseen_group_risk_upper": bounded_mean_upper(observed, 1, alpha=0.05), "risk_certification": "insufficient_component_level_evidence"})
        if len(data):
            means = data.groupby("independence_group").policy_bad.mean()
            pooled.append({"scope": scope, "n_cases": len(data), "n_groups": len(means), "predicted_case_weighted_risk": float(forecast.mean()), "observed_case_weighted_risk": float(data.policy_bad.mean()), "observed_equal_group_risk": float(means.mean()), "equal_group_risk_upper": bounded_mean_upper(float(means.mean()), len(means), alpha=0.05), "formal_assumption": "independent deployment-representative groups; not valid under arbitrary domain shift"})
    output = OUT / role / protocol_name
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(output / "group_predictions.csv", index=False)
    pd.DataFrame(pooled).to_csv(output / "pooled.csv", index=False)
    print(f"[366] independent real-calendar composition audit: {len(rows)} group-scope rows", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluate", choices=["development", "calibration", "test"])
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    args = parser.parse_args()
    C.protocol()
    evaluate(args.evaluate, args.protocol) if args.evaluate else fit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
