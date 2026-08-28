#!/usr/bin/env python3
"""Build the ordinary v11 open-network work inventory."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data_versions/global_network_corpus_v1"
OUTPUT = ROOT / "results/development_v11/network_inventory.csv"


def main() -> None:
    split = yaml.safe_load(
        (ROOT / "configs/network_catalog_v3_split.yaml").read_text(encoding="utf-8")
    )
    strata = {
        row["network_id"]: row
        for row in split["networks"]
        if row["role"] in {"development", "validation"}
    }
    qualified_catalog = pd.read_parquet(
        CORPUS / "qualified_corpus_v1/network_catalog_v3_qualified.parquet"
    )
    qualified_open = set(
        qualified_catalog.loc[
            qualified_catalog["role"].isin(("development", "validation")),
            "network_id",
        ].astype(str)
    )
    scored = pd.read_parquet(
        ROOT
        / "results/framework/t2_recovery_benchmark_v1/w7_open_role_bd_combined"
        / "joined_first_layer_complete.parquet",
        columns=["network_id", "station_id", "gap_length"],
    ).drop_duplicates()
    rows = []
    for role in ("development", "validation"):
        network_root = (
            CORPUS / "open_role_qc/failure_closure6" / role / "networks"
        )
        current_auxiliary_root = (
            CORPUS / "development_auxiliary/failure_closure6" / role / "networks"
        )
        legacy_auxiliary_root = (
            CORPUS / "open_role_auxiliary/failure_closure6" / role / "networks"
        )
        for path in sorted(network_root.glob("*/daily_wide_qc.csv")):
            network = path.parent.name
            content = path.read_text(encoding="utf-8").strip()
            if content in {"", '""'}:
                temperature = pd.DataFrame(columns=["date"])
                temperature["date"] = pd.to_datetime(temperature["date"])
                stations = []
            else:
                temperature = pd.read_csv(path, parse_dates=["date"])
                stations = list(temperature.columns[1:].astype(str))
            current_auxiliary_path = (
                current_auxiliary_root / network / "daily_long_auxiliary.parquet"
            )
            legacy_auxiliary_path = (
                legacy_auxiliary_root / network / "daily_long_auxiliary.parquet"
            )
            auxiliary_path = (
                current_auxiliary_path
                if current_auxiliary_path.exists()
                else legacy_auxiliary_path
            )
            if auxiliary_path.exists():
                auxiliary = pd.read_parquet(
                    auxiliary_path, columns=["site_id", "variable"]
                )
                auxiliary_sites = int(auxiliary["site_id"].astype(str).nunique())
                auxiliary_variables = "|".join(
                    sorted(auxiliary["variable"].astype(str).unique())
                )
            else:
                auxiliary_sites = 0
                auxiliary_variables = ""
            network_scores = scored.loc[scored["network_id"].eq(network)]
            stratum = strata[network]
            rows.append(
                {
                    "network_id": network,
                    "role": role,
                    "climate_band": stratum["climate_band"],
                    "size_tertile": stratum["size_tertile"],
                    "regulation_stratum": stratum["regulation_stratum"],
                    "n_stations": len(stations),
                    "three_station_eligible": len(stations) >= 3,
                    "qualified_open_role": network in qualified_open,
                    "station_ids": "|".join(stations),
                    "temperature_start": (
                        "" if temperature.empty else str(temperature["date"].min().date())
                    ),
                    "temperature_end": (
                        "" if temperature.empty else str(temperature["date"].max().date())
                    ),
                    "n_temperature_days": len(temperature),
                    "n_temperature_values": int(
                        temperature.iloc[:, 1:].notna().sum().sum()
                    ),
                    "auxiliary_present": auxiliary_path.exists(),
                    "auxiliary_source": (
                        "development_auxiliary"
                        if current_auxiliary_path.exists()
                        else "legacy_open_auxiliary"
                        if legacy_auxiliary_path.exists()
                        else ""
                    ),
                    "n_auxiliary_sites": auxiliary_sites,
                    "auxiliary_variables": auxiliary_variables,
                    "scored_outcomes_present": not network_scores.empty,
                    "n_scored_station_gaps": len(network_scores),
                }
            )
    inventory = pd.DataFrame(rows).sort_values(["role", "network_id"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(OUTPUT, index=False)
    print(
        inventory.groupby("role").agg(
            networks=("network_id", "size"),
            stations=("n_stations", "sum"),
            auxiliary=("auxiliary_present", "sum"),
            scored=("scored_outcomes_present", "sum"),
        )
    )


if __name__ == "__main__":
    main()
