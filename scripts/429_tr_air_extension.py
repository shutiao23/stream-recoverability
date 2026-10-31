#!/usr/bin/env python3
"""TR-E1c: complete the station air forcing with the same NASA POWER product.

The v18 forcing covers 457 stations. USGS stations added later have
coordinates in the USGS site service but no forcing, so their reconstructions
never had an air layer. The new study gives every station with coordinates the
same T2M series; stations without coordinates keep no air layer.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T

RAW = T.ROOT / "data/external/wrr_target_recovery_20261021/power"
OUT_PATH = T.ROOT / "data/interim/tr_air_forcing.parquet"
ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M&community=AG&longitude={lon}&latitude={lat}&start=19810101&end=20260831&format=JSON"


def fetch(row: dict) -> pd.DataFrame:
    path = RAW / f"{row['station_id']}.json"
    if not path.exists():
        url = ENDPOINT.format(lat=row["latitude"], lon=row["longitude"])
        for attempt in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "stream-recoverability/1.0"}), timeout=240) as response:
                    payload = response.read()
                RAW.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
                break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(10 * (attempt + 1))
        else:
            return pd.DataFrame()
    values = json.loads(path.read_text())["properties"]["parameter"]["T2M"]
    frame = pd.DataFrame({"date": pd.to_datetime(list(values), format="%Y%m%d"), "air_temperature_c": np.asarray(list(values.values()), dtype=float)})
    frame.loc[frame.air_temperature_c <= -998, "air_temperature_c"] = np.nan
    frame["station_id"], frame["network_id"] = row["station_id"], row["network_id"]
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    # Always extend the v18 forcing, so a rerun rebuilds the same table from the cached responses.
    base = pd.read_parquet(T.AIR_V18)
    covered = set(base.station_id.astype(str).unique())
    roster = T.roster()
    lacking = roster.loc[~roster.station_id.astype(str).isin(covered)].drop_duplicates("station_id")
    sites = pd.read_csv(T.OUT / "e1_archive/usgs_site_metadata.csv", dtype={"site_no": str})
    coords = sites.rename(columns={"site_no": "station_id", "dec_lat_va": "latitude", "dec_long_va": "longitude"})[["station_id", "latitude", "longitude"]]
    jobs = lacking.merge(coords, on="station_id", how="left")
    missing_coordinates = jobs.loc[jobs.latitude.isna(), ["provider", "network_id", "station_id"]]
    jobs = jobs.dropna(subset=["latitude"])
    print(f"[429] {len(lacking)} stations lack air; {len(jobs)} have coordinates", flush=True)
    with ThreadPoolExecutor(args.workers) as pool:
        frames = list(pool.map(fetch, jobs[["station_id", "network_id", "latitude", "longitude"]].to_dict("records")))
    added = pd.concat([frame for frame in frames if len(frame)], ignore_index=True)
    merged = pd.concat([base.astype({"station_id": str, "network_id": str}), added], ignore_index=True)
    merged["air_temperature_c"] = merged.air_temperature_c.astype("float32")
    merged["station_id"] = merged.station_id.astype("category")
    merged["network_id"] = merged.network_id.astype("category")
    merged.to_parquet(OUT_PATH, index=False)
    missing_coordinates.to_csv(T.OUT / "e1_archive/air_missing_coordinates.csv", index=False)
    summary = {"n_base_stations": len(covered), "n_added_stations": int(added.station_id.nunique()), "n_without_coordinates": len(missing_coordinates), "output": str(OUT_PATH.relative_to(T.ROOT))}
    T.write_json(T.OUT / "e1_archive/air_extension_summary.json", summary)
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
