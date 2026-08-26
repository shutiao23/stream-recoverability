#!/usr/bin/env python3
"""Lock metadata-only Swiss candidates before any FOEN temperature values.

The GraphQL selection is deliberately station metadata only. Candidate
membership is restricted to the pre-existing FOEN water-temperature station
inventory, grouped by accent-normalized river name and catchment. No coverage
date is requested or used. Station 2016, whose WT timestamps were probed during
W6, burns its entire Aare network and can never be sealed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.http_json import USER_AGENT

FOEN_GRAPHQL = "https://data.bafu.admin.ch/api"
SOURCE_INVENTORY = ROOT / "results/framework/public_catalog/foen_existenz_locations.csv"
OUTPUT = ROOT / "results/framework/public_catalog"
METADATA_CSV = OUTPUT / "foen_temperature_station_metadata_20260826.csv"
SPLIT_CSV = OUTPUT / "foen_prospective_split_v1.csv"
SHA_PATH = OUTPUT / "foen_prospective_split_v1.sha256"
MANIFEST = OUTPUT / "foen_prospective_lock_manifest.json"
CATALOG_YAML = ROOT / "configs/foen_prospective_catalog_v1.yaml"
SPLIT_YAML = ROOT / "configs/foen_prospective_split_v1.yaml"
FUTURE_QUERY_TEMPLATE = ROOT / "configs/foen_daily_value_query_v1.graphql"

SPLIT_SEED = 20260826
REQUIRED_NON_NA_SEALED = 10
PROBED_STATION_IDS = frozenset({"2016"})
MIN_STATIONS = 3
FUTURE_REQUEST_START = "1974-01-01T00:00:00Z"
FUTURE_REQUEST_END_EXCLUSIVE = "2026-01-01T00:00:00Z"
STATION_QUERY = """
{ water { observations { stations(limit: 10000) {
  no name riverName catchmentName status latitude longitude elevation
} } } }
"""
CANONICAL_COLUMNS = (
    "network_id",
    "role",
    "seed",
    "river_key",
    "catchment_key",
    "n_stations",
    "station_ids",
    "never_sealed",
    "development_burned",
    "metadata_only",
    "temperature_values_queried",
    "qualified_8yr_status",
)


def _post_station_metadata() -> list[dict[str, Any]]:
    body = json.dumps({"query": STATION_QUERY}).encode("utf-8")
    request = urllib.request.Request(
        FOEN_GRAPHQL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"]))
    return payload["data"]["water"]["observations"]["stations"]


def _key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(
        character for character in text if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")


def _haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(a)))


def _max_pair_km(group: pd.DataFrame) -> float:
    points = list(
        zip(group["latitude"].astype(float), group["longitude"].astype(float))
    )
    return max(
        [0.0]
        + [
            _haversine_km(points[index], points[other])
            for index in range(len(points))
            for other in range(index)
        ]
    )


def eligible_station_metadata(
    station_rows: list[dict[str, Any]], inventory: pd.DataFrame
) -> pd.DataFrame:
    """Intersect current metadata with the prior water-temperature location list."""

    current = pd.DataFrame(station_rows).rename(
        columns={
            "no": "site_id",
            "riverName": "river_name",
            "catchmentName": "catchment_name",
        }
    )
    current["site_id"] = current["site_id"].astype(str).str.zfill(4)
    prior = inventory.copy()
    prior["site_id"] = prior["site_id"].astype(str).str.zfill(4)
    prior = prior[["site_id", "water_body_type"]].drop_duplicates("site_id")
    frame = current.merge(prior, on="site_id", how="inner", validate="one_to_one")
    frame = frame.loc[frame["water_body_type"].astype(str).str.casefold().eq("river")]
    frame = frame.dropna(
        subset=["site_id", "river_name", "catchment_name", "latitude", "longitude"]
    ).copy()
    frame["river_key"] = frame["river_name"].map(_key)
    frame["catchment_key"] = frame["catchment_name"].map(_key)
    frame = frame.loc[frame["river_key"].ne("") & frame["catchment_key"].ne("")]
    frame["temperature_values_queried"] = False
    frame["coverage_fields_used_for_eligibility"] = False
    return frame.sort_values("site_id").reset_index(drop=True)


def build_candidates(stations: pd.DataFrame) -> list[dict[str, Any]]:
    """One prospective network per normalized river/catchment pair."""

    candidates: list[dict[str, Any]] = []
    grouped = stations.groupby(["river_key", "catchment_key"], sort=True)
    for (river_key, catchment_key), group in grouped:
        group = group.drop_duplicates("site_id").sort_values("site_id")
        if len(group) < MIN_STATIONS:
            continue
        site_ids = group["site_id"].astype(str).tolist()
        burned = bool(PROBED_STATION_IDS.intersection(site_ids))
        candidates.append(
            {
                "network_id": f"foen_{river_key}_{catchment_key}",
                "river_key": river_key,
                "catchment_key": catchment_key,
                "river_labels": sorted(set(group["river_name"].astype(str))),
                "catchment_labels": sorted(set(group["catchment_name"].astype(str))),
                "n_stations": len(site_ids),
                "candidate_station_ids": site_ids,
                "max_pair_km": _max_pair_km(group),
                "never_sealed": burned,
                "development_burned": burned,
                "probe_station_ids": sorted(PROBED_STATION_IDS.intersection(site_ids)),
                "metadata_only": True,
                "temperature_values_queried": False,
                "qualified_8yr_status": "unknown_until_post_download_qc",
                "flow_connectivity_status": "unverified_metadata_only",
                "coverage_fields_used_for_eligibility": False,
                "stations": [
                    {
                        "site_id": str(row.site_id),
                        "name": str(row.name),
                        "status": str(row.status),
                        "latitude": float(row.latitude),
                        "longitude": float(row.longitude),
                    }
                    for row in group.itertuples(index=False)
                ],
            }
        )
    ids = [str(item["network_id"]) for item in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("normalized FOEN network IDs are not unique")
    return candidates


def assign_roles(
    candidates: list[dict[str, Any]],
    *,
    seed: int = SPLIT_SEED,
    required_sealed: int = REQUIRED_NON_NA_SEALED,
) -> list[dict[str, Any]]:
    pool = [item for item in candidates if not item["never_sealed"]]
    if len(pool) < int(required_sealed):
        raise ValueError("fewer than ten unburned FOEN metadata candidates")
    ranked = sorted(
        pool,
        key=lambda item: hashlib.sha256(
            f"{seed}:{item['network_id']}".encode()
        ).hexdigest(),
    )
    sealed_ids = {str(item["network_id"]) for item in ranked[: int(required_sealed)]}
    rows: list[dict[str, Any]] = []
    for item in candidates:
        network_id = str(item["network_id"])
        if item["never_sealed"]:
            role = "never_sealed"
        elif network_id in sealed_ids:
            role = "sealed"
        else:
            digest = hashlib.sha256(f"remainder:{seed}:{network_id}".encode()).digest()
            role = "validation" if digest[0] < 73 else "development"
        rows.append({**item, "role": role, "seed": int(seed)})
    return sorted(rows, key=lambda item: str(item["network_id"]))


def canonical_split_bytes(rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CANONICAL_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for item in sorted(rows, key=lambda row: str(row["network_id"])):
        writer.writerow(
            {
                "network_id": item["network_id"],
                "role": item["role"],
                "seed": item["seed"],
                "river_key": item["river_key"],
                "catchment_key": item["catchment_key"],
                "n_stations": item["n_stations"],
                "station_ids": ",".join(item["candidate_station_ids"]),
                "never_sealed": str(bool(item["never_sealed"])).lower(),
                "development_burned": str(bool(item["development_burned"])).lower(),
                "metadata_only": "true",
                "temperature_values_queried": "false",
                "qualified_8yr_status": item["qualified_8yr_status"],
            }
        )
    return buffer.getvalue().encode("utf-8")


def write_lock(stations: pd.DataFrame, rows: list[dict[str, Any]]) -> dict[str, Any]:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CATALOG_YAML.parent.mkdir(parents=True, exist_ok=True)
    metadata_columns = [
        "site_id",
        "name",
        "river_name",
        "catchment_name",
        "status",
        "latitude",
        "longitude",
        "elevation",
        "water_body_type",
        "river_key",
        "catchment_key",
        "temperature_values_queried",
        "coverage_fields_used_for_eligibility",
    ]
    stations[metadata_columns].to_csv(METADATA_CSV, index=False)

    canonical = canonical_split_bytes(rows)
    split_sha = hashlib.sha256(canonical).hexdigest()
    query_template_sha = hashlib.sha256(FUTURE_QUERY_TEMPLATE.read_bytes()).hexdigest()
    SPLIT_CSV.write_bytes(canonical)
    SHA_PATH.write_text(split_sha + "\n", encoding="utf-8")

    catalog = {
        "catalog_id": "foen_prospective_catalog_v1",
        "status": "metadata_only_locked_before_temperature_value_query",
        "source": "foen_public_graphql_plus_prior_temperature_station_inventory",
        "station_metadata_endpoint": FOEN_GRAPHQL,
        "station_query_contains_temperature_value": False,
        "coverage_fields_requested": False,
        "coverage_fields_used_for_eligibility": False,
        "temperature_values_queried": False,
        "daily_years_claimed": 0,
        "candidate_rule": (
            "FOEN temperature-location inventory intersection; river water-body type; "
            "accent-normalized riverName x catchmentName; >=3 distinct station IDs"
        ),
        "network_independence_warning": (
            "Same-name/catchment metadata is prospective only; flow connectivity and "
            "eight concurrent qualified years remain unverified."
        ),
        "networks": rows,
    }
    CATALOG_YAML.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    catalog_sha = hashlib.sha256(CATALOG_YAML.read_bytes()).hexdigest()

    split = {
        "split_id": "foen_prospective_split_v1",
        "status": "locked_before_temperature_value_query",
        "frozen_on": "2026-08-26",
        "seed": SPLIT_SEED,
        "sha256": split_sha,
        "catalog_sha256": catalog_sha,
        "canonical_split_table": str(SPLIT_CSV.relative_to(ROOT)),
        "catalog": str(CATALOG_YAML.relative_to(ROOT)),
        "required_non_north_america_sealed": REQUIRED_NON_NA_SEALED,
        "source_specific_assignment": (
            "Fill the locked absolute non-NA sealed quota after burning any timestamp-probed "
            "network; existing North-American development/validation roles are unchanged."
        ),
        "temperature_values_queried": False,
        "sealed_outcomes_opened": False,
        "coverage_fields_used_for_eligibility": False,
        "qualified_networks_claimed": 0,
        "future_request_contract": {
            "status": "template_locked_not_executed",
            "query_template": str(FUTURE_QUERY_TEMPLATE.relative_to(ROOT)),
            "query_template_sha256": query_template_sha,
            "endpoint": FOEN_GRAPHQL,
            "aggregation": "data_1day_mean",
            "parameter": "WT",
            "release_states": ["2", "3"],
            "request_start": FUTURE_REQUEST_START,
            "request_end_exclusive": FUTURE_REQUEST_END_EXCLUSIVE,
            "partition": "disjoint_calendar_year_windows",
            "response_handling_for_sealed": "stream_raw_http_response_bytes_without_json_decode",
            "template_executed": False,
        },
        "networks": [
            {
                "network_id": item["network_id"],
                "role": item["role"],
                "seed": item["seed"],
                "n_stations": item["n_stations"],
                "station_ids": item["candidate_station_ids"],
                "never_sealed": item["never_sealed"],
                "development_burned": item["development_burned"],
                "qualified_8yr_status": item["qualified_8yr_status"],
            }
            for item in rows
        ],
    }
    SPLIT_YAML.write_text(
        yaml.safe_dump(split, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )

    sealed = [item for item in rows if item["role"] == "sealed"]
    burned = [item for item in rows if item["role"] == "never_sealed"]
    manifest = {
        "what_this_is": "Prospective Swiss metadata-only split lock.",
        "what_this_is_not": (
            "Not a qualified-network count, not T8 evidence, and not a temperature download."
        ),
        "split_seed": SPLIT_SEED,
        "split_sha256": split_sha,
        "catalog_sha256": catalog_sha,
        "future_query_template_sha256": query_template_sha,
        "n_temperature_station_metadata_rows": len(stations),
        "n_candidate_networks": len(rows),
        "n_prospective_non_na_sealed": len(sealed),
        "n_never_sealed_development_burned": len(burned),
        "burned_station_ids": sorted(PROBED_STATION_IDS),
        "burned_network_ids": [item["network_id"] for item in burned],
        "sealed_network_ids": [item["network_id"] for item in sealed],
        "temperature_values_queried": False,
        "sealed_outcomes_opened": False,
        "coverage_fields_requested": False,
        "coverage_fields_used_for_eligibility": False,
        "qualified_8yr_networks": 0,
        "countable_toward_t8_now": False,
        "lock_ready_for_future_byte_custody": len(sealed) >= REQUIRED_NON_NA_SEALED,
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-csv", type=Path)
    args = parser.parse_args()
    inventory = pd.read_csv(SOURCE_INVENTORY, dtype={"site_id": str})
    if args.metadata_csv:
        station_rows = pd.read_csv(args.metadata_csv, dtype={"no": str}).to_dict(
            "records"
        )
    else:
        station_rows = _post_station_metadata()
    stations = eligible_station_metadata(station_rows, inventory)
    rows = assign_roles(build_candidates(stations))
    manifest = write_lock(stations, rows)
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
