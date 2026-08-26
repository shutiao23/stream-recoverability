#!/usr/bin/env python3
"""Run the executable next-paper framework on synthetic systems only."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.analysis.development_power import (
    power_curve,
    recommended_network_count,
)
from stream_recoverability.analysis.hierarchical_confirmation import (
    evaluate_success,
    simulate_confirmation_panel,
)
from stream_recoverability.analysis.study_freeze import load_study_freeze
from stream_recoverability.data.network_catalog import (
    catalog_frame,
    load_network_catalog,
    validate_catalog,
)
from stream_recoverability.experiments.recoverability_baselines import run_baseline_suite
from stream_recoverability.experiments.sensor_policy import budget_curve, policy_success
from stream_recoverability.experiments.synthetic_identifiability import run_e0
from stream_recoverability.experiments.synthetic_river import catalog
from stream_recoverability.experiments.topology_falsification import run_topology_suite

OUTPUT = ROOT / "results/framework"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    freeze = load_study_freeze()
    e0 = run_e0(include_coverage=False)
    rivers = catalog()
    baselines = run_baseline_suite(rivers)
    topology = run_topology_suite()
    curve = budget_curve()
    success = policy_success(curve)
    catalog_document = load_network_catalog()
    violations = validate_catalog(catalog_document)
    networks = catalog_frame(catalog_document)
    power = power_curve()
    confirmation = evaluate_success(simulate_confirmation_panel())

    (OUTPUT / "synthetic_identifiability").mkdir(exist_ok=True)
    e0["identifiability"].to_csv(
        OUTPUT / "synthetic_identifiability/identifiability.csv", index=False
    )
    e0["finite_sample"].to_csv(
        OUTPUT / "synthetic_identifiability/finite_sample.csv", index=False
    )
    e0["degeneration"]["jensen_ar1"].to_csv(
        OUTPUT / "synthetic_identifiability/jensen_acf_gap.csv", index=False
    )
    e0["degeneration"]["donor_count_inflation"].to_csv(
        OUTPUT / "synthetic_identifiability/donor_count_inflation.csv", index=False
    )
    baselines["predictions"].to_csv(OUTPUT / "baseline_predictions.csv", index=False)
    baselines["nested_r2"].to_csv(OUTPUT / "baseline_nested_r2.csv", index=False)
    baselines["residual_gain"].to_csv(OUTPUT / "baseline_residual_gain.csv", index=False)
    topology["matched_subsets"].to_csv(OUTPUT / "topology_matched_subsets.csv", index=False)
    topology["endpoint_audit"].to_csv(OUTPUT / "topology_endpoint_audit.csv", index=False)
    curve.to_csv(OUTPUT / "sensor_policy_budget_curve.csv", index=False)
    success.to_csv(OUTPUT / "sensor_policy_success.csv", index=False)
    networks.to_csv(OUTPUT / "network_catalog.csv", index=False)
    power.to_csv(OUTPUT / "development_power_curve.csv", index=False)
    confirmation["leave_one_network_out"].to_csv(
        OUTPUT / "confirmation_leave_one_network_out.csv", index=False
    )

    manifest = {
        "status": "complete",
        "design_id": freeze["design_id"],
        "formal_evidence": False,
        "sealed_outcomes_opened": False,
        "real_network_outcomes_used": False,
        "e0_pass": e0["pass"],
        "baseline_residual_gain": baselines["residual_gain"].iloc[0].to_dict(),
        "topology_stability": topology["stability"],
        "sensor_policy_success": success.to_dict(orient="records"),
        "catalog_violations": violations,
        "recommended_network_count_for_this_simulation": recommended_network_count(power),
        "synthetic_confirmation_passed": confirmation["passed"],
        "note": (
            "Synthetic machinery only. No sealed river-network temperature "
            "outcomes were opened."
        ),
    }
    (OUTPUT / "framework_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: manifest[key] for key in ("e0_pass", "catalog_violations")}, indent=2))


if __name__ == "__main__":
    main()
