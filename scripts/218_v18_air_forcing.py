#!/usr/bin/env python3
"""E5b — daily air temperature for every station in the panel.

NASA POWER, one request per station, 2 m air temperature at the native MERRA-2
resolution. The product is global, free and daily from 1981, which is why the
v17 air branch being supported on 0.85% of confirmation cases was never a data
problem: it was that station coordinates had not been carried into the
pipeline.

Written to the same schema the v17 loader expects, so the sensitivity analysis
can rerun the existing pipeline against it rather than forking one.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    AIR_FORCING_V18,
    E5_AIR,
    STATION_COORDINATES,
)

ENDPOINT = (
    "https://power.larc.nasa.gov/api/temporal/daily/point"
    "?parameters=T2M&community=AG&longitude={lon}&latitude={lat}"
    "&start={start}&end={end}&format=JSON"
)
START = "19810101"
END = "20260831"
FILL_VALUE = -999.0
TIMEOUT = 180
RETRIES = 3
WORKERS = 8


def fetch_station(row: dict) -> pd.DataFrame:
    url = ENDPOINT.format(lat=row["latitude"], lon=row["longitude"], start=START, end=END)
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "stream-recoverability/1.0"})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))
            values = payload["properties"]["parameter"]["T2M"]
            frame = pd.DataFrame(
                {
                    "date": pd.to_datetime(list(values.keys()), format="%Y%m%d"),
                    "air_temperature_c": list(values.values()),
                }
            )
            frame = frame.loc[frame["air_temperature_c"] > FILL_VALUE + 1]
            frame["station_id"] = str(row["station_id"])
            frame["network_id"] = str(row["network_id"])
            return frame
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TimeoutError) as error:
            if attempt == RETRIES - 1:
                print(f"  {row['provider']}/{row['station_id']}: {error}", file=sys.stderr)
                return pd.DataFrame()
            time.sleep(3 * (attempt + 1))
    return pd.DataFrame()


def main() -> int:
    E5_AIR.mkdir(parents=True, exist_ok=True)
    AIR_FORCING_V18.parent.mkdir(parents=True, exist_ok=True)
    coordinates = pd.read_csv(STATION_COORDINATES, dtype={"station_id": str, "network_id": str})
    coordinates = coordinates.dropna(subset=["latitude", "longitude"])
    rows = coordinates.to_dict(orient="records")
    print(f"fetching NASA POWER for {len(rows)} stations")

    frames: list[pd.DataFrame] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for index, frame in enumerate(pool.map(fetch_station, rows)):
            if not frame.empty:
                frames.append(frame)
            if (index + 1) % 50 == 0:
                print(f"  {index + 1}/{len(rows)} done, {len(frames)} with data", flush=True)

    if not frames:
        raise SystemExit("no air forcing retrieved")
    forcing = pd.concat(frames, ignore_index=True)
    forcing = forcing.sort_values(["network_id", "station_id", "date"]).reset_index(drop=True)
    forcing.to_parquet(AIR_FORCING_V18, index=False)

    coverage = (
        forcing.groupby("station_id")
        .agg(days=("date", "size"), first=("date", "min"), last=("date", "max"))
        .reset_index()
    )
    coverage.to_csv(E5_AIR / "air_forcing_coverage.csv", index=False)
    summary = {
        "n_stations_requested": int(len(rows)),
        "n_stations_with_forcing": int(forcing["station_id"].nunique()),
        "n_daily_values": int(len(forcing)),
        "median_days_per_station": float(coverage["days"].median()),
        "source": "NASA POWER daily T2M (MERRA-2), 1981-2026",
        "output": str(AIR_FORCING_V18.relative_to(ROOT)),
    }
    (E5_AIR / "air_forcing_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
