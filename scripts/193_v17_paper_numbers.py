#!/usr/bin/env python3
"""Emit every headline number the manuscript quotes, from the artifacts.

Written after a self-audit found a stale hardcoded case count in a figure
caption. Numbers in the text are checked against this file by
`tests/test_v17_fitness.py`, so a rerun that moves a result cannot leave the
prose behind.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import (  # noqa: E402
    RESULTS_ROOT,
    STEP10_CONFIRM,
    STEP1_PANEL,
    STEP3_CASES,
    STEP4_CEILING,
    STEP5_MECHANISM,
    STEP6_SCREEN,
    STEP7_FRONTIER,
    STEP8_DOWNSTREAM,
    STEP9_FREEZE,
)

OUT = RESULTS_ROOT / "paper_numbers.json"


def main() -> int:
    panel = json.loads((STEP1_PANEL / "summary.json").read_text())
    case_frame = pd.read_parquet(STEP3_CASES / "cases.parquet", columns=["split_role", "network_id", "station_id", "year"])
    cases = {
        "n_cases": int(len(case_frame)),
        "by_split": case_frame.groupby("split_role").size().to_dict(),
        "n_station_years": int(case_frame.groupby(["network_id", "station_id", "year"]).ngroups),
    }
    gate = json.loads((STEP4_CEILING / "gate.json").read_text())
    verdict = json.loads((STEP10_CONFIRM / "verdict.json").read_text())
    freeze = json.loads((STEP9_FREEZE / "SUCCESS_CRITERION_v17.json").read_text())
    tolerances = pd.read_csv(STEP4_CEILING / "estimator_tolerances.csv").set_index("estimator")
    nested = pd.read_csv(STEP5_MECHANISM / "nested_feature_sets.csv").set_index("feature_set")
    importance = pd.read_csv(STEP5_MECHANISM / "permutation_importance.csv").set_index("feature")
    contrasts = pd.read_csv(STEP5_MECHANISM / "donor_control_contrasts.csv")
    dev_front = pd.read_csv(STEP7_FRONTIER / "frontiers.csv")
    res_front = pd.read_csv(STEP10_CONFIRM / "frontiers.csv")
    dev_inc = pd.read_csv(STEP7_FRONTIER / "incumbent_operating_points.csv")
    res_inc = pd.read_csv(STEP10_CONFIRM / "incumbent_operating_points.csv")
    per_year = pd.read_csv(STEP10_CONFIRM / "per_year_threshold.csv")
    downstream = pd.read_csv(STEP8_DOWNSTREAM / "summary.csv").set_index("treatment")
    self_point = json.loads((STEP6_SCREEN / "self_selected_operating_point.json").read_text())

    def at70(frame: pd.DataFrame, screen: str) -> float:
        row = frame.loc[frame["retention"].eq(0.70) & frame["screen"].eq(screen)]
        return float(row["rate_above_0.5"].iloc[0])

    numbers = {
        "panel": {
            "networks": panel["n_eligible_networks"],
            "stations": panel["n_eligible_stations"],
            "station_years": panel["n_eligible_station_years"],
            "development_networks": panel["n_development_networks"],
            "reserved_networks": panel["n_reserved_networks"],
            "natural_scale_mean_sd_c": round(panel["natural_scale_interannual_sd"]["mean_sd_c"], 4),
        },
        "cases": {
            "total": cases["n_cases"],
            "development": cases["by_split"]["development"],
            "reserved": cases["by_split"]["reserved"],
            "station_years": cases["n_station_years"],
        },
        "gate": gate,
        "practice": {
            name: {
                "mean_abs_error_c": round(float(tolerances.loc[name, "mean_abs_error_c"]), 4),
                "rate_above_0.5": round(float(tolerances.loc[name, "rate_above_0.5"]), 4),
                "rate_above_1.0": round(float(tolerances.loc[name, "rate_above_1.0"]), 4),
                "mean_error_in_natural_sd": round(float(tolerances.loc[name, "mean_error_in_natural_sd"]), 4),
            }
            for name in ("observed_days", "doy_climatology", "policy", "oracle_method")
        },
        "mechanism": {
            "nested_auc": {k: round(float(v), 4) for k, v in nested["grouped_cv_auc"].items()},
            "importance_peak_overlap": round(float(importance.loc["peak_overlap", "permutation_r2_drop"]), 4),
            "importance_longest_run": round(float(importance.loc["longest_run", "permutation_r2_drop"]), 4),
            "donor_quality_contrast": contrasts.round(4).to_dict("records"),
        },
        "frontier_at_70": {
            "development": {s: round(at70(dev_front, s), 4) for s in ("certificate", "length_rule", "peak_overlap_rule", "random")},
            "reserved": {s: round(at70(res_front, s), 4) for s in ("certificate", "length_rule", "peak_overlap_rule", "random")},
        },
        "incumbent": {
            "development": dev_inc.round(4).to_dict("records"),
            "reserved": res_inc.round(4).to_dict("records"),
        },
        "confirmation": verdict,
        "precision": freeze["precision"],
        "self_selected_operating_point": self_point,
        "per_year_20C": per_year.loc[per_year["threshold_c"].eq(20.0)].round(4).to_dict("records"),
        "downstream_slope_rmse": {k: round(float(v), 4) for k, v in downstream["slope_rmse_c_per_year"].items()},
        "downstream_exceed20_bias": {k: round(float(v), 4) for k, v in downstream["exceed20_bias_years"].items()},
    }
    for optional, path in (("arm_robustness", RESULTS_ROOT / "step11_arm_robustness" / "arm_contrasts.csv"),
                           ("ablations", RESULTS_ROOT / "step12_ablations" / "ablations.csv"),
                           ("prior_years", RESULTS_ROOT / "step13_prior_years" / "protocol_comparison.csv"),
                           ("metric_generality", RESULTS_ROOT / "step17_metric_generality" / "metric_generality.csv"),
                           ("weighting", RESULTS_ROOT / "step19_weighting" / "weighting.csv")):
        if path.exists():
            numbers[optional] = pd.read_csv(path).round(4).to_dict("records")
    for optional, path in (("ablation_summary", RESULTS_ROOT / "step12_ablations" / "summary.json"),
                           ("metric_generality_verdict", RESULTS_ROOT / "step17_metric_generality" / "verdict.json"),
                           ("cluster_conformal", RESULTS_ROOT / "step18_cluster_conformal" / "summary.json")):
        if path.exists():
            numbers[optional] = json.loads(path.read_text())

    OUT.write_text(json.dumps(numbers, indent=2), encoding="utf-8")
    print(json.dumps({k: numbers[k] for k in ("panel", "cases", "frontier_at_70")}, indent=2))
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
