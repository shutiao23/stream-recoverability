#!/usr/bin/env python3
"""Acquire a public resource with source checksums and metadata-only inspection."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

import wrr_r3_common as C

OUT = C.RUN / "r3_02_external_resource"
RAW = C.ROOT / "data" / "external" / "wrr_revision_20261020c" / "hydroshare"
METADATA_FILES = {"ReadME.txt", "Selected_stations.csv", "Selected_catchments.dbf", "Selected_catchments.prj"}


def fetch_file(item: dict) -> dict:
    destination = RAW / item["file_name"]
    expected = item.get("checksum")
    if destination.exists():
        measured = hashlib.md5(destination.read_bytes()).hexdigest()
        if expected and measured != expected:
            raise RuntimeError(f"Existing download checksum mismatch: {destination}")
        return {"file_name": item["file_name"], "bytes": destination.stat().st_size, "sha256": C.digest(destination), "cached": True}
    response = requests.get(item["url"].replace("http://", "https://", 1), timeout=(15, 180), stream=True)
    response.raise_for_status()
    temporary = destination.with_name(destination.name + ".partial")
    checksum = hashlib.md5()
    with temporary.open("wb") as handle:
        for chunk in response.iter_content(1 << 20):
            if chunk:
                handle.write(chunk)
                checksum.update(chunk)
    if expected and checksum.hexdigest() != expected:
        raise RuntimeError(f"Downloaded source checksum mismatch: {destination}")
    temporary.replace(destination)
    return {"file_name": item["file_name"], "bytes": destination.stat().st_size, "sha256": C.digest(destination), "cached": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-files", action="store_true")
    args = parser.parse_args()
    settings = C.protocol()
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    resource = settings["new_external_resource"]
    base = f"https://www.hydroshare.org/hsapi/resource/{resource}"
    catalog_response = requests.get(f"{base}/files/", timeout=30)
    catalog_response.raise_for_status()
    catalog = catalog_response.json()
    if catalog.get("next"):
        raise RuntimeError("Resource listing is paginated; acquire every page before interpreting it")
    C.write_json(OUT / "file_catalog.json", catalog)
    system_response = requests.get(f"{base}/sysmeta/", timeout=30)
    system_response.raise_for_status()
    C.write_json(OUT / "source_metadata.json", system_response.json())
    items = [item for item in catalog["results"] if args.all_files or item["file_name"] in METADATA_FILES]
    with ThreadPoolExecutor(max_workers=4) as pool:
        downloads = list(pool.map(fetch_file, items))
    C.write_json(OUT / "download_manifest.json", {"resource": resource, "files": downloads, "performance_outcomes_inspected": False})
    stations = pd.read_csv(RAW / "Selected_stations.csv", sep=None, engine="python")
    stations.to_csv(OUT / "source_station_metadata.csv", index=False)
    names = [item["file_name"] for item in catalog["results"]]
    summary = {
        "source": f"https://www.hydroshare.org/resource/{resource}/",
        "n_files": len(names),
        "n_station_metadata_rows": len(stations),
        "station_metadata_columns": stations.columns.tolist(),
        "resource_contains_extreme_values_and_events": any("ExtremeEvents" in name for name in names),
        "continuous_daily_water_temperature_verified": False,
        "event_only_file_may_be_used_as_continuous_truth": False,
        "next_action": "match station identities and acquire continuous temperature from original agencies",
        "files_downloaded": [item["file_name"] for item in downloads],
    }
    C.write_json(OUT / "summary.json", summary)
    C.write_json(OUT / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"catalog": OUT / "file_catalog.json", "source_metadata": OUT / "source_metadata.json"}))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
