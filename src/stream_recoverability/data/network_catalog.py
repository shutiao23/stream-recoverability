"""Metadata-only multi-network inventory. Sealed outcomes are not loaded."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG = REPOSITORY_ROOT / "configs/network_catalog_v1.yaml"
FORBIDDEN_OUTCOME_KEYS = (
    "temperature_series_path",
    "recovery_outcomes_path",
    "skill_table_path",
    "opened_outcomes",
)


def load_network_catalog(path: str | Path = DEFAULT_CATALOG) -> dict[str, Any]:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("network catalog must be a mapping")
    networks = document.get("networks")
    if not isinstance(networks, list) or not networks:
        raise ValueError("network catalog requires a non-empty networks list")
    return document


def validate_catalog(document: Mapping[str, Any]) -> list[str]:
    """Return violations. Sealed networks may not point at temperature outcomes."""

    violations: list[str] = []
    roles = {"development": 0, "validation": 0, "sealed": 0, "historical": 0}
    regimes: set[str] = set()
    climates: set[str] = set()
    for network in document.get("networks", []):
        if not isinstance(network, Mapping):
            violations.append("network entry is not a mapping")
            continue
        network_id = str(network.get("network_id", "<missing>"))
        role = str(network.get("split_role", ""))
        if role not in roles:
            violations.append(f"{network_id}: unknown split_role {role!r}")
        else:
            roles[role] += 1
        if network.get("temperature_record_unverified") is not True:
            if role == "sealed":
                violations.append(
                    f"{network_id}: sealed networks must remain temperature-unverified"
                )
        if role == "sealed" and network.get("sealed_outcomes_opened") is True:
            violations.append(f"{network_id}: sealed outcomes opened")
        for key in FORBIDDEN_OUTCOME_KEYS:
            if key in network and network[key] not in {None, False, ""}:
                violations.append(f"{network_id}: forbidden outcome key {key}")
        if network.get("historical_seen") and role == "sealed":
            violations.append(f"{network_id}: historical network cannot be sealed")
        stations = network.get("candidate_station_ids") or []
        if len(stations) < 4 and role != "historical":
            violations.append(f"{network_id}: fewer than four candidate stations")
        if network.get("regime"):
            regimes.add(str(network["regime"]))
        if network.get("climate_or_ecoregion"):
            climates.add(str(network["climate_or_ecoregion"]))
    if roles["sealed"] < 1:
        violations.append("catalog has no sealed networks")
    if roles["development"] < 1:
        violations.append("catalog has no development networks")
    required_regimes = {
        "regulated",
        "groundwater_dominated",
        "atmospheric",
        "large_river",
    }
    missing_regimes = required_regimes.difference(regimes)
    if missing_regimes:
        violations.append(f"missing regimes {sorted(missing_regimes)}")
    if len(climates) < 4:
        violations.append(f"only {len(climates)} climate/ecoregion classes")
    return violations


def catalog_frame(document: Mapping[str, Any] | None = None) -> pd.DataFrame:
    catalog = document if document is not None else load_network_catalog()
    rows = []
    for network in catalog["networks"]:
        rows.append(
            {
                "network_id": network["network_id"],
                "display_name": network.get("display_name"),
                "split_role": network.get("split_role"),
                "regime": network.get("regime"),
                "climate_or_ecoregion": network.get("climate_or_ecoregion"),
                "n_candidate_stations": len(network.get("candidate_station_ids") or []),
                "candidate_station_ids": ",".join(
                    str(item) for item in network.get("candidate_station_ids") or []
                ),
                "historical_seen": bool(network.get("historical_seen", False)),
                "temperature_record_unverified": bool(
                    network.get("temperature_record_unverified", True)
                ),
                "sealed_outcomes_opened": bool(
                    network.get("sealed_outcomes_opened", False)
                ),
                "feasibility_status": network.get("feasibility_status"),
                "notes": network.get("notes"),
            }
        )
    return pd.DataFrame(rows)


def split_counts(frame: pd.DataFrame) -> dict[str, int]:
    return frame["split_role"].value_counts().to_dict()


__all__ = [
    "DEFAULT_CATALOG",
    "FORBIDDEN_OUTCOME_KEYS",
    "catalog_frame",
    "load_network_catalog",
    "split_counts",
    "validate_catalog",
]
