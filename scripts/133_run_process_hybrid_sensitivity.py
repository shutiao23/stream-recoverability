#!/usr/bin/env python3
"""Run and audit the development-only air2stream-inspired proxy sensitivity."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
)
from stream_recoverability.experiments.process_hybrid_sensitivity import (
    score_process_hybrid,
)

CORPUS = ROOT / "data_versions/global_network_corpus_v1"
INVENTORY = ROOT / "results/development_v11/network_inventory.csv"
PLACEMENTS = ROOT / "results/development_v11/recovery_scoring/placement_losses.csv"
FIRST = ROOT / "results/development_v11/route_a_confirmation/placement_losses.csv"
SECOND = ROOT / "results/development_v11/second_confirmation/readiness_roster.csv"
DEFAULT_OUTPUT = ROOT / "results/development_v11/reviewer_completion"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def correlation(frame: pd.DataFrame, left: str, right: str) -> float | None:
    usable = frame[[left, right]].dropna()
    if len(usable) < 3 or usable[left].nunique() < 2 or usable[right].nunique() < 2:
        return None
    return float(usable[left].corr(usable[right], method="spearman"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-networks", type=int)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    inventory = pd.read_csv(INVENTORY, dtype={"network_id": str})
    placements = pd.read_csv(
        PLACEMENTS, dtype={"network_id": str, "station_id": str}
    )
    scored_ids = set(placements["network_id"].astype(str))
    candidates = inventory.loc[
        inventory["qualified_open_role"]
        & inventory["auxiliary_present"]
        & inventory["network_id"].astype(str).isin(scored_ids)
    ].sort_values(["role", "network_id"], kind="mergesort")
    if args.max_networks is not None:
        candidates = candidates.head(args.max_networks)
    station_gaps: list[pd.DataFrame] = []
    failures: list[dict[str, object]] = []
    for item in candidates.itertuples(index=False):
        network = str(item.network_id)
        role = str(item.role)
        temperature_path = (
            CORPUS
            / "open_role_qc/failure_closure6"
            / role
            / "networks"
            / network
            / "daily_wide_qc.csv"
        )
        auxiliary_path = (
            CORPUS
            / "development_auxiliary/failure_closure6"
            / role
            / "networks"
            / network
            / "daily_long_auxiliary.parquet"
        )
        scored, station_failures = score_process_hybrid(
            network,
            read_temperature_panel(str(temperature_path)),
            pd.read_parquet(auxiliary_path),
            placements,
        )
        if not scored.empty:
            scored["role"] = role
            station_gaps.append(scored)
        failures.extend(station_failures)
        print(f"development process-hybrid: {network}", flush=True)
    result = pd.concat(station_gaps, ignore_index=True) if station_gaps else pd.DataFrame()
    failures_frame = pd.DataFrame(
        failures, columns=["network_id", "station_id", "reason"]
    )

    first = pd.read_csv(FIRST, dtype={"network_id": str})
    first_ready = first.loc[
        first["meteorology_feature_count"].gt(0)
        & first["hydraulics_feature_count"].gt(0),
        "network_id",
    ].nunique()
    second = pd.read_csv(SECOND, dtype={"network_id": str})
    readiness = pd.DataFrame(
        [
            {
                "phase": "open_development",
                "networks_in_scope": len(candidates),
                "networks_with_materialized_ta_f": candidates["network_id"].nunique(),
                "networks_scored": result["network_id"].nunique() if not result.empty else 0,
                "status": "development_proxy_executable",
            },
            {
                "phase": "first_confirmation",
                "networks_in_scope": first["network_id"].nunique(),
                "networks_with_materialized_ta_f": int(first_ready),
                "networks_scored": 0,
                "status": "fail_closed_no_ta_f_confirmation_inputs",
            },
            {
                "phase": "second_confirmation",
                "networks_in_scope": second.loc[
                    second["qc_status"].eq("qualified"), "network_id"
                ].nunique(),
                "networks_with_materialized_ta_f": 0,
                "networks_scored": 0,
                "status": "fail_closed_no_ta_f_confirmation_inputs",
            },
        ]
    )
    station_path = args.output / "process_hybrid_station_gaps.csv"
    failure_path = args.output / "process_hybrid_failures.csv"
    readiness_path = args.output / "process_hybrid_readiness.csv"
    manifest_path = args.output / "process_hybrid_manifest.json"
    result.to_csv(station_path, index=False)
    failures_frame.to_csv(failure_path, index=False)
    readiness.to_csv(readiness_path, index=False)
    network = (
        result.groupby("network_id", as_index=False).mean(numeric_only=True)
        if not result.empty
        else pd.DataFrame()
    )
    manifest = {
        "analysis_id": "v11_air2stream_inspired_development_proxy_v1",
        "status": "development_sensitivity_complete_confirmation_fail_closed",
        "evidence_role": "open_development_only_not_confirmatory",
        "model_identity": "ridge_Ta_logF_season_blended_with_two_sided_boundary",
        "published_air2stream_implementation": False,
        "reviewer3_air2stream_requirement_satisfied": False,
        "reasons_requirement_not_satisfied": [
            "proxy_is_not_the_published_air2stream_differential_equation_model",
            "first_confirmation_has_no_materialized_timestamp_aligned_Ta_and_F",
            "second_confirmation_has_no_materialized_timestamp_aligned_Ta_and_F",
        ],
        "results": {
            "n_development_networks_scored": int(result["network_id"].nunique())
            if not result.empty
            else 0,
            "n_development_station_gaps": len(result),
            "xgboost_vs_process_hybrid_station_gap_spearman": correlation(
                result, "xgboost_bd_mae_deg_c", "hybrid_mae_deg_c"
            )
            if not result.empty
            else None,
            "xgboost_vs_process_hybrid_network_spearman": correlation(
                network, "xgboost_bd_mae_deg_c", "hybrid_mae_deg_c"
            )
            if not network.empty
            else None,
        },
        "input_sha256": {
            str(INVENTORY.relative_to(ROOT)): sha256(INVENTORY),
            str(PLACEMENTS.relative_to(ROOT)): sha256(PLACEMENTS),
            str(FIRST.relative_to(ROOT)): sha256(FIRST),
            str(SECOND.relative_to(ROOT)): sha256(SECOND),
        },
        "output_sha256": {
            station_path.name: sha256(station_path),
            failure_path.name: sha256(failure_path),
            readiness_path.name: sha256(readiness_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
