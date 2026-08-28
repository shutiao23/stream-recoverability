#!/usr/bin/env python3
"""Score fixed XGBoost recovery models on open development networks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    GAP_LENGTHS,
    XGBOOST_PARAMETERS,
    read_temperature_panel,
    score_network,
)

DEFAULT_TEMPERATURE_ROOT = (
    ROOT / "data_versions/global_network_corpus_v1/open_role_qc/failure_closure6"
)
DEFAULT_AUXILIARY_ROOT = (
    ROOT
    / "data_versions/global_network_corpus_v1/development_auxiliary/failure_closure6"
)
DEFAULT_OUTPUT = ROOT / "results/development_v11/recovery_scoring"
DEFAULT_INVENTORY = ROOT / "results/development_v11/network_inventory.csv"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temperature-root", type=Path, default=DEFAULT_TEMPERATURE_ROOT)
    parser.add_argument("--auxiliary-root", type=Path, default=DEFAULT_AUXILIARY_ROOT)
    parser.add_argument("--role", default="all")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--networks", help="comma-separated network ids")
    parser.add_argument("--max-networks", type=int)
    parser.add_argument("--placements", type=int, default=20)
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def temperature_input_paths(networks_root: Path) -> list[Path]:
    """List daily panels that contain a date plus at least one station."""

    paths = []
    for path in sorted(networks_root.glob("*/daily_wide_qc.csv")):
        columns = pd.read_csv(path, nrows=0).columns.astype(str).tolist()
        if "date" in columns and any(column != "date" for column in columns):
            paths.append(path)
    return paths


def main() -> None:
    args = arguments()
    roles = ("development", "validation") if args.role == "all" else (args.role,)
    qualified = pd.read_csv(args.inventory)
    qualified_ids = set(
        qualified.loc[qualified["qualified_open_role"], "network_id"].astype(str)
    )
    requested = (
        None
        if args.networks is None
        else {value.strip() for value in args.networks.split(",") if value.strip()}
    )
    paths = [
        (role, path)
        for role in roles
        for path in temperature_input_paths(
            args.temperature_root / role / "networks"
        )
        if path.parent.name in qualified_ids
    ]
    if requested is not None:
        paths = [item for item in paths if item[1].parent.name in requested]
    if args.max_networks is not None:
        paths = paths[: args.max_networks]

    model_parameters = {**XGBOOST_PARAMETERS, "n_jobs": args.n_jobs}
    placement_tables = []
    station_gap_tables = []
    eligibility_tables = []
    for role, path in paths:
        network_id = path.parent.name
        auxiliary_path = (
            args.auxiliary_root
            / role
            / "networks"
            / network_id
            / "daily_long_auxiliary.parquet"
        )
        auxiliary = pd.read_parquet(auxiliary_path) if auxiliary_path.is_file() else None
        scored = score_network(
            network_id,
            read_temperature_panel(path),
            auxiliary,
            gap_lengths=GAP_LENGTHS,
            placements_per_gap=args.placements,
            xgboost_parameters=model_parameters,
        )
        placement_tables.append(scored["placement_losses"].assign(role=role))
        station_gap_tables.append(scored["station_gap_summary"].assign(role=role))
        eligibility_tables.append(scored["eligibility"].assign(role=role))

    placements = pd.concat(placement_tables, ignore_index=True)
    station_gaps = pd.concat(station_gap_tables, ignore_index=True)
    eligibility = pd.concat(eligibility_tables, ignore_index=True)
    args.output.mkdir(parents=True, exist_ok=True)
    placements.to_parquet(args.output / "placement_losses.parquet", index=False)
    placements.to_csv(args.output / "placement_losses.csv", index=False)
    station_gaps.to_csv(args.output / "station_gap_summary.csv", index=False)
    eligibility.to_csv(args.output / "eligibility.csv", index=False)

    summary = {
        "model": "xgboost",
        "information_conditions": [
            "B_union_D",
            "B_union_D_union_M_union_H",
        ],
        "training_year_fraction": 0.7,
        "evaluation_year_fraction": 0.3,
        "gap_lengths": list(GAP_LENGTHS),
        "placements_requested_per_station_gap": args.placements,
        "n_temperature_networks": len(paths),
        "n_networks_scored": int(placements["network_id"].nunique()),
        "n_stations_scored": int(
            placements[["network_id", "station_id"]].drop_duplicates().shape[0]
        ),
        "n_placement_losses": len(placements),
        "n_station_gaps": len(station_gaps),
        "n_full_information_networks": int(
            placements.loc[
                placements["information_condition"].eq(
                    "B_union_D_union_M_union_H"
                ),
                "network_id",
            ].nunique()
        ),
        "output_dir": str(args.output),
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
