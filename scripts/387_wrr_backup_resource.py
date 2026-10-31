#!/usr/bin/env python3
"""Stage a public redundant-logger resource without inspecting temperatures."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import itertools
import json
from pathlib import Path
import subprocess
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_followup_backup"
OUT = C.READY / "followup_20261021/natural_backup"
CONFIG = C.ROOT / "configs/wrr_natural_backup_20261021.json"
CATALOG = "https://open.canada.ca/data/api/action/package_show?id=bef00bd7-255e-461c-a08b-09f81977170c"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def stage():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    metadata = RAW / "canada_catalog.json"
    if not metadata.exists():
        response = requests.get(CATALOG, timeout=60)
        response.raise_for_status()
        metadata.write_bytes(response.content)
    catalog = json.loads(metadata.read_text())["result"]
    resource = next(item for item in catalog["resources"] if item.get("name") == "CSV_EN.7z")
    # Written once, before the archive is staged and before any temperature is read.
    protocol_record = OUT / "metadata_protocol.json"
    if not protocol_record.exists():
        bank = C.RUN / "r3_09_frozen_transfer/head_bank.json"
        selected_heads = [item for item in json.loads(bank.read_text())["heads"] if item["protocol"] == "strictly_prior_years" and item["scope"] == "all" and item["regime"] == "source_only" and item["name"] in {"uncertain_support", "generic_direct_h30_uncertainty", "generic_target_disagreement"}]
        C.write_json(protocol_record, run_record({"protocol": CONFIG, "catalog": metadata, "original_head_bank": bank}, archive_url=resource["url"], license=catalog.get("license_url"), temperature_values_inspected=False, selected_original_heads=[item["identity"] for item in selected_heads]))
    archive = RAW / "CSV_EN.7z"
    if not archive.exists():
        if not urlparse(resource["url"]).hostname.endswith("dfo-mpo.gc.ca"):
            raise RuntimeError("Archive URL no longer points to the government provider")
        response = requests.get(resource["url"], stream=True, timeout=120)
        response.raise_for_status()
        temporary = archive.with_suffix(".partial")
        count = 0
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(1 << 20):
                count += len(chunk)
                if count > 1 << 30:
                    raise RuntimeError("Archive exceeds the declared one-GiB staging limit")
                handle.write(chunk)
        temporary.replace(archive)
    paths = subprocess.run(["bsdtar", "-tf", str(archive)], capture_output=True, text=True, check=True).stdout.splitlines()
    if any(Path(name).is_absolute() or ".." in Path(name).parts for name in paths):
        raise RuntimeError("Unsafe archive entry")
    destination = RAW / "csv"
    destination.mkdir(exist_ok=True)
    if not list(destination.rglob("*.csv")):
        subprocess.run(["bsdtar", "-xf", str(archive), "-C", str(destination), "--no-same-owner", "--no-same-permissions"], check=True)
    acquisition = {"catalog_url": CATALOG, "archive_url": resource["url"], "archive_bytes": archive.stat().st_size,
                 "files": paths, "temperature_values_inspected": False,
                 "metadata_scope": "historical staging event only; this does not describe later analysis state"}
    # The first staging event is kept rather than overwritten.
    if not (OUT / "acquisition.json").exists():
        C.write_json(OUT / "acquisition.json", acquisition)
    print(f"[387] staged {len(paths)} entries, {archive.stat().st_size} bytes; temperatures remain uninspected", flush=True)


def metadata_audit():
    if not (OUT / "acquisition.json").exists():
        raise RuntimeError("Stage the provider resource first")
    records = []
    allowed = ["Station", "Serial", "Time_UTC", "Latitude", "Longitude", "Logger_Type"]
    for path in sorted((RAW / "csv").rglob("*.csv")):
        summary = {}
        # WaterTemperature_Celsius and WaterLevel_meters are deliberately absent.
        for block in pd.read_csv(path, usecols=allowed, dtype={"Station": str, "Serial": str}, chunksize=100000, encoding="utf-8-sig"):
            block["time"] = pd.to_datetime(block.Time_UTC, utc=True, errors="coerce", format="mixed")
            block["Latitude"] = pd.to_numeric(block.Latitude, errors="coerce").round(6)
            block["Longitude"] = pd.to_numeric(block.Longitude, errors="coerce").round(6)
            for key, group in block.groupby(["Station", "Serial", "Latitude", "Longitude", "Logger_Type"], dropna=False):
                entry = summary.setdefault(key, {"first": group.time.min(), "last": group.time.max(), "rows": 0})
                entry["first"], entry["last"] = min(entry["first"], group.time.min()), max(entry["last"], group.time.max())
                entry["rows"] += len(group)
        for (station, serial, lat, lon, logger_type), item in summary.items():
            records.append({"file": str(path.relative_to(RAW)), "river": path.stem, "station": station, "serial": serial, "latitude": lat, "longitude": lon,
                            "logger_type": logger_type, "first_timestamp": str(item["first"]), "last_timestamp": str(item["last"]), "timestamp_rows": item["rows"]})
    stations = pd.DataFrame(records)
    stations.to_csv(OUT / "logger_metadata.csv", index=False)
    pairs = []
    for key, group in stations.groupby(["river", "station", "latitude", "longitude"], dropna=False):
        for first, second in itertools.combinations(group.to_dict("records"), 2):
            if first["serial"] == second["serial"]:
                continue
            a, b = sorted((first, second), key=lambda item: item["serial"])
            overlap_first = max(pd.Timestamp(a["first_timestamp"]), pd.Timestamp(b["first_timestamp"]))
            overlap_last = min(pd.Timestamp(a["last_timestamp"]), pd.Timestamp(b["last_timestamp"]))
            days = max((overlap_last - overlap_first).total_seconds() / 86400, 0)
            pairs.append({"river": key[0], "station": key[1], "latitude": key[2], "longitude": key[3], "primary_serial": a["serial"], "backup_serial": b["serial"],
                          "potential_concurrent_days": days, "metadata_pair_eligible": days >= 90, "file": a["file"],
                          "qualification": "bounding timestamps only; simultaneous coverage and water quality remain unverified"})
    paired = pd.DataFrame(pairs)
    paired.to_csv(OUT / "potential_backup_pairs.csv", index=False)
    # This does not open any new temperature or performance data.
    coordinates = pd.read_csv(C.ROOT / "data/interim/v18_station_coordinates.csv")
    old_lat = pd.to_numeric(coordinates.latitude, errors="coerce").to_numpy()
    old_lon = pd.to_numeric(coordinates.longitude, errors="coerce").to_numpy()
    distance_rows = []
    for row in stations.itertuples(index=False):
        phi1, phi2 = np.deg2rad(row.latitude), np.deg2rad(old_lat)
        delta_phi, delta_lam = phi2 - phi1, np.deg2rad(old_lon - row.longitude)
        a = np.sin(delta_phi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lam / 2) ** 2
        distance = 6371 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        distance_rows.append({"river": row.river, "station": row.station, "serial": row.serial, "nearest_known_old_coordinate_km": float(np.nanmin(distance))})
    pd.DataFrame(distance_rows).to_csv(OUT / "prior_coordinate_audit.csv", index=False)
    C.write_json(OUT / "metadata_audit.json", run_record({"catalog": RAW / "canada_catalog.json", "protocol": CONFIG, "archive": RAW / "CSV_EN.7z", "old_coordinates": C.ROOT / "data/interim/v18_station_coordinates.csv"},
                 n_files=stations.file.nunique(), n_logger_deployments=len(stations), n_potential_pairs=len(paired), n_potential_90day_pairs=int(paired.metadata_pair_eligible.sum()) if len(paired) else 0,
                 temperature_columns_read=False, thermal_errors_inspected=False, new_independence_proved=False))
    print(f"[387] {len(stations)} logger deployments, {len(paired)} candidate colocated pairs; temperature values remain unopened", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["stage", "metadata"])
    args = parser.parse_args()
    stage() if args.action == "stage" else metadata_audit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
