#!/usr/bin/env python3
"""Download NASA POWER T2M for first-panel stations that have coordinates.

External-information recoverers are scored only where this file is present.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (  # noqa: E402
    read_temperature_panel,
)
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_PANEL_ROOT,
    FIRST_PLACEMENTS,
    RESULTS_ROOT,
)

POWER_ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
OUTPUT = RESULTS_ROOT / "forcing" / "nasa_power_t2m.parquet"
USGS_LOC = ROOT / "results/framework/public_catalog/usgs_long_temperature_locations.csv"


def power_url(lat: float, lon: float, start: str, end: str) -> str:
    query = urllib.parse.urlencode(
        {
            "parameters": "T2M",
            "community": "AG",
            "longitude": lon,
            "latitude": lat,
            "start": start.replace("-", ""),
            "end": end.replace("-", ""),
            "format": "JSON",
            "time-standard": "LST",
        }
    )
    return f"{POWER_ENDPOINT}?{query}"


def fetch_t2m(lat: float, lon: float, start: str, end: str) -> pd.Series:
    with urllib.request.urlopen(power_url(lat, lon, start, end), timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    values = payload["properties"]["parameter"]["T2M"]
    index = pd.to_datetime(list(values), format="%Y%m%d")
    series = pd.to_numeric(pd.Series(list(values.values()), index=index), errors="coerce")
    return series.where(series > -900)


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    loc = pd.read_csv(USGS_LOC, dtype={"site_id": str})
    loc["site_id"] = loc["site_id"].str.zfill(8)
    loc_map = loc.set_index("site_id")[["latitude", "longitude"]]
    networks = sorted(
        pd.read_csv(FIRST_PLACEMENTS, usecols=["network_id"])["network_id"].astype(str).unique()
    )
    rows = []
    failures = []
    for network_id in networks:
        panel = read_temperature_panel(
            str(FIRST_PANEL_ROOT / network_id / "daily_wide_temperature.csv")
        )
        start = str(panel.index.min().date())
        end = str(panel.index.max().date())
        for station in panel.columns:
            key = str(station).zfill(8) if str(station).isdigit() else str(station)
            if key not in loc_map.index:
                continue
            lat = float(loc_map.loc[key, "latitude"])
            lon = float(loc_map.loc[key, "longitude"])
            try:
                series = fetch_t2m(lat, lon, start, end)
            except Exception as exc:  # noqa: BLE001
                failures.append({"network_id": network_id, "station_id": station, "error": str(exc)})
                continue
            part = series.rename("air_temperature_c").to_frame()
            part["network_id"] = network_id
            part["station_id"] = str(station)
            part["date"] = part.index
            rows.append(part.reset_index(drop=True))
            print(f"power {network_id} {station} n={len(series)}", flush=True)
    if rows:
        out = pd.concat(rows, ignore_index=True)
        out.to_parquet(OUTPUT, index=False)
        print("wrote", OUTPUT, "rows", len(out))
    pd.DataFrame(failures).to_csv(OUTPUT.with_suffix(".failures.csv"), index=False)


if __name__ == "__main__":
    main()
