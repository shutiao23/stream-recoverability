#!/usr/bin/env python3
"""TR-E7a: the Australian (BoM) test inputs, prepared before the TR pipeline is frozen.

Station series are grouped into networks by conservative hydrologic block so
donors never cross blocks. Air temperature is NASA POWER T2M with the same
request as the source forcing. Only completeness is counted here: no H30,
reconstruction or prediction error is computed.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T

SOURCE = T.ROOT / "data/external/wrr_au_confirmation_20261021/qualified_daily"
METADATA = T.ROOT / "results/wrr_submission_ready/followup_20261021/au_confirmation/metadata_candidates_and_roles.csv"
BLOCKS = T.ROOT / "results/wrr_submission_ready/followup_20261021/au_dependence_audit/station_hydrologic_scope.csv"
DATA = T.ROOT / "data/external/wrr_target_recovery_20261021/au_sealed"
OUT = T.OUT / "e7_sealed"
ENDPOINT = (
    "https://power.larc.nasa.gov/api/temporal/daily/point"
    "?parameters=T2M&community=AG&longitude={lon}&latitude={lat}"
    "&start={start}&end={end}&format=JSON"
)
START, END, FILL = "19810101", "20260831", -999.0
AGENT = {"User-Agent": "stream-recoverability/1.0"}


def read_station(path: Path) -> pd.Series:
    frame = pd.read_csv(path, parse_dates=["date"])
    series = pd.to_numeric(frame.set_index("date")["temperature_C"], errors="coerce").sort_index()
    series = series.loc[~series.index.duplicated(keep="first")]
    return series.asfreq("D")


def complete_years(series: pd.Series) -> int:
    count = 0
    for year, block in series.groupby(series.index.year):
        expected = 366 if pd.Timestamp(int(year), 12, 31).is_leap_year else 365
        count += int(len(block) == expected and block.notna().all())
    return count


def fetch_power(row: dict, retries: int = 4) -> Path:
    path = DATA / "power_raw" / f"{row['station_id']}.json"
    if path.exists() and path.stat().st_size:
        return path
    url = ENDPOINT.format(lat=row["lat"], lon=row["lon"], start=START, end=END)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=240) as response:
                payload = response.read()
            json.loads(payload)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            path.with_suffix(".url").write_text(url + "\n")
            return path
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"NASA POWER failed for {row['station_id']}")


def power_frame(path: Path, station: str, network: str) -> pd.DataFrame:
    values = json.loads(path.read_text())["properties"]["parameter"]["T2M"]
    frame = pd.DataFrame({"date": pd.to_datetime(list(values), format="%Y%m%d"), "air_temperature_c": list(values.values())})
    frame.loc[frame.air_temperature_c <= FILL + 1e-6, "air_temperature_c"] = np.nan
    frame["station_id"], frame["network_id"] = station, network
    return frame


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    files = sorted(SOURCE.glob("*.csv"))
    metadata = pd.read_csv(METADATA, dtype=str).drop_duplicates("station_id").set_index("station_id")
    blocks = pd.read_csv(BLOCKS, dtype=str).drop_duplicates("station_id").set_index("station_id")
    rows, series = [], {}
    for path in files:
        station = path.stem
        values = read_station(path)
        block = blocks.hydrologic_block.get(station)
        singleton = not isinstance(block, str) or not block
        block = f"singleton_{station}" if singleton else block
        observed = values.dropna()
        rows.append(
            {
                "station_id": station, "station_no": metadata.station_no.get(station), "provider": "bom",
                "hydrologic_block": block, "singleton_block": singleton,
                "block_screen_status": blocks.hydrologic_screen_status.get(station),
                "network_id": "bom_" + block.replace("hydrologic_", ""),
                "lat": float(metadata.station_latitude[station]), "lon": float(metadata.station_longitude[station]),
                "first_date": str(observed.index.min().date()) if len(observed) else None,
                "last_date": str(observed.index.max().date()) if len(observed) else None,
                "n_complete_years": complete_years(values), "source_path": str(path.relative_to(T.ROOT)),
            }
        )
        series[station] = values
    roster = pd.DataFrame(rows)
    network_paths = {}
    for network, members in roster.groupby("network_id"):
        panel = pd.concat({station: series[station] for station in members.station_id}, axis=1).sort_index()
        panel = panel.asfreq("D")
        panel.index.name = "date"
        path = DATA / "networks" / network / "daily_wide_temperature.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        panel.reset_index().to_csv(path, index=False, date_format="%Y-%m-%d", float_format="%.4g")
        network_paths[network] = str(path.relative_to(T.ROOT))
    roster["input_path"] = roster.network_id.map(network_paths)
    jobs = roster[["station_id", "lat", "lon"]].to_dict("records")
    with ThreadPoolExecutor(min(args.workers, 6)) as pool:
        power_paths = list(pool.map(fetch_power, jobs))
    air = pd.concat(
        [power_frame(path, row.station_id, row.network_id) for path, row in zip(power_paths, roster.itertuples(index=False))],
        ignore_index=True,
    )
    air["air_temperature_c"] = air.air_temperature_c.astype("float32")
    air["station_id"] = air.station_id.astype("category")
    air["network_id"] = air.network_id.astype("category")
    air_path = DATA / "air_forcing.parquet"
    air.to_parquet(air_path, index=False)
    with_air = air.dropna(subset=["air_temperature_c"]).station_id.astype(str).unique()
    roster["has_air_forcing"] = roster.station_id.isin(with_air)
    OUT.mkdir(parents=True, exist_ok=True)
    roster.to_csv(OUT / "au_roster.csv", index=False)
    power_manifest = pd.DataFrame([{"path": str(path.relative_to(T.ROOT))} for path in power_paths])
    power_manifest.to_csv(DATA / "power_manifest.csv", index=False)
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "role": "TR-E7 transfer region, evaluated with the pipeline frozen on the source cases",
        "errors_opened": False,
        "statement": "No H30, reconstruction or prediction error was computed; only calendar completeness was counted.",
        "n_stations": len(roster), "n_networks": int(roster.network_id.nunique()),
        "n_hydrologic_blocks_resolved": int((~roster.singleton_block).groupby(roster.network_id).any().sum()),
        "n_singleton_blocks": int(roster.singleton_block.sum()),
        "n_complete_station_years": int(roster.n_complete_years.sum()),
        "n_stations_ge4_complete_years": int((roster.n_complete_years >= 4).sum()),
        "n_complete_station_years_in_ge4_stations": int(roster.loc[roster.n_complete_years >= 4, "n_complete_years"].sum()),
        "n_networks_with_ge4_station": int(roster.loc[roster.n_complete_years >= 4, "network_id"].nunique()),
        "n_stations_with_air_forcing": int(roster.has_air_forcing.sum()),
        "air_forcing": {"path": str(air_path.relative_to(T.ROOT)), "source": "NASA POWER T2M daily, same request as scripts/218_v18_air_forcing.py"},
        "network_files": dict(sorted(network_paths.items())),
        "inputs": {"metadata": str(METADATA.relative_to(T.ROOT)), "blocks": str(BLOCKS.relative_to(T.ROOT))},
    }
    T.write_json(OUT / "au_summary.json", summary)
    print({key: value for key, value in summary.items() if key.startswith("n_")}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
