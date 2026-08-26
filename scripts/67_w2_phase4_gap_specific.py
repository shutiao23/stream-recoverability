#!/usr/bin/env python3
"""W2 Phase-4 stop-loss with gap-specific planted-gap skill.

Loads already-downloaded public_rivers daily wide CSVs. Does not download
temperatures, open sealed rivers, or overwrite the later-year audit files in
results/framework/public_rivers/.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.public_river_operator_ablation import (
    ACHIEVED_SKILL_GAP_SPECIFIC,
    W2_PRIMARY_NETWORKS,
    W2_PURPOSE,
    concurrent_enough_ids,
    load_public_river_panels,
    run_public_river_operator_ablation,
    write_operator_ablation_artifacts,
)

SOURCE = ROOT / "results/framework/public_rivers"
OUTPUT = SOURCE / "w2_phase4_gap_specific"


def main() -> None:
    complete_enough = concurrent_enough_ids(SOURCE)
    if complete_enough is None:
        raise RuntimeError("W2 requires the frozen complete_enough overlap roster")
    if complete_enough != set(W2_PRIMARY_NETWORKS):
        raise RuntimeError(
            "complete_enough roster does not equal the frozen six-river W2 roster: "
            f"got {sorted(complete_enough)}"
        )
    panels = load_public_river_panels(SOURCE)
    selected = {
        name: panels[name] for name in W2_PRIMARY_NETWORKS if name in panels
    }
    missing_files = [name for name in W2_PRIMARY_NETWORKS if name not in selected]
    result = run_public_river_operator_ablation(
        selected,
        primary_networks=list(W2_PRIMARY_NETWORKS),
        achieved_skill_mode=ACHIEVED_SKILL_GAP_SPECIFIC,
    )
    if missing_files:
        manifest = dict(result["manifest"])
        extra = sorted(set(manifest.get("requested_primary_missing", [])) | set(missing_files))
        manifest["requested_primary_missing"] = extra
        result = dict(result)
        result["manifest"] = manifest
    manifest = result["manifest"]
    expected = len(W2_PRIMARY_NETWORKS)
    gate_failures = []
    if manifest.get("n_networks") != expected:
        gate_failures.append(f"n_networks={manifest.get('n_networks')} (expected {expected})")
    if manifest.get("n_networks_attempted") != expected:
        gate_failures.append(
            f"n_networks_attempted={manifest.get('n_networks_attempted')} "
            f"(expected {expected})"
        )
    if manifest.get("requested_primary_missing"):
        gate_failures.append(
            f"requested_primary_missing={manifest.get('requested_primary_missing')}"
        )
    if manifest.get("delaware_scored") is not True:
        gate_failures.append("Delaware was not scored")
    if manifest.get("pipeline_gap_length_delta_r2_nonzero") is not True:
        gate_failures.append("pooled gap_length delta R2 is zero or undefined")
    if manifest.get("pipeline_gap_rows_differ") is not True:
        gate_failures.append("30-day and 90-day gap outcomes are still identical")
    if manifest.get("passed") is not False or manifest.get("purpose") != W2_PURPOSE:
        gate_failures.append("manifest evidence status is not the locked W2 status")
    inference = (manifest.get("evaluate_success") or {}).get(
        "spearman_inference_status"
    )
    if inference != "withheld_n_lt_100_network_interval":
        gate_failures.append(f"network inference status is {inference!r}")
    if gate_failures:
        raise RuntimeError("W2 pipeline verification failed: " + "; ".join(gate_failures))
    write_operator_ablation_artifacts(
        result, OUTPUT, include_station_scores=True
    )
    if (OUTPUT / "leave_one_river_out.csv").exists():
        raise RuntimeError("W2 writer must not create leave_one_river_out.csv")
    nested = result["nested"]
    pooled = nested.loc[
        nested["scope"].eq("pooled_gaps") & nested["level"].eq("station")
    ] if not nested.empty else nested
    print(pooled.to_string(index=False) if not pooled.empty else nested.to_string(index=False))
    print(
        json.dumps(
            {
                "passed": manifest.get("passed"),
                "purpose": manifest.get("purpose"),
                "n_networks": manifest.get("n_networks"),
                "delaware_scored": manifest.get("delaware_scored"),
                "requested_primary_networks": manifest.get("requested_primary_networks"),
                "requested_primary_missing": manifest.get("requested_primary_missing"),
                "pipeline_gap_length_delta_r2": manifest.get(
                    "pipeline_gap_length_delta_r2"
                ),
                "pipeline_gap_length_delta_r2_nonzero": manifest.get(
                    "pipeline_gap_length_delta_r2_nonzero"
                ),
                "pipeline_gap_rows_differ": manifest.get("pipeline_gap_rows_differ"),
                "achieved_skill_is_later_year_not_gap_specific": manifest.get(
                    "achieved_skill_is_later_year_not_gap_specific"
                ),
                "evaluate_success": manifest.get("evaluate_success"),
                "operator_incremental_r2_station": manifest.get(
                    "operator_incremental_r2_station"
                ),
                "new_temperatures_downloaded": manifest.get(
                    "new_temperatures_downloaded"
                ),
                "output_dir": str(OUTPUT),
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
