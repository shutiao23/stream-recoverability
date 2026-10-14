#!/usr/bin/env python3
"""P0-07 wave-2 SMHI recruitment into a new root (not opened transport ingest)."""

from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.data.smhi_water_temperature import (  # noqa: E402
    DATA_URL,
    PARAMETER_URL,
    station_catalog,
)

OUT = ROOT / "results/wrr_submission_ready/p0_07_wave2_ingest/smhi"
# Accept G (good) and O (as in transport ingest QC contract); quarantine implausible °C.
ACCEPT_Q = {"G", "O"}
TEMP_MIN, TEMP_MAX = -5.0, 45.0  # 45 keeps room under SMHI 80289-class failures
MIN_YEARS = 4
MIN_STATIONS = 2


def get_bytes(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "stream-recoverability-wave2-smhi/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_daily(payload: bytes, site_id: str) -> pd.DataFrame:
    lines = payload.decode("utf-8-sig").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Datum"))
    rows = []
    for values in csv.reader(lines[start + 1 :], delimiter=";"):
        if len(values) < 3:
            continue
        quality = (values[2] or "").strip()
        if quality not in ACCEPT_Q:
            continue
        try:
            temp = float(values[1])
        except ValueError:
            continue
        if not (TEMP_MIN <= temp <= TEMP_MAX):
            continue
        rows.append({"date": pd.to_datetime(values[0]), "temperature_c": temp, "q": quality})
    return pd.DataFrame(rows)


def complete_years(series: pd.Series) -> list[int]:
    years = []
    for year in sorted({int(y) for y in series.index.year}):
        idx = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
        vals = series.reindex(idx).to_numpy(dtype=float)
        if len(vals) >= 365 and np.isfinite(vals).all():
            years.append(year)
    return years


def used_station_ids() -> set[str]:
    used: set[str] = set()
    for path in [
        ROOT / "results/wrr_submission_ready/multi_agency_ingest/smhi/stations_all.csv",
        ROOT / "results/wrr_submission_ready/multi_agency_ingest/smhi/stations.csv",
        ROOT / "results/v17_fitness/step1_panel/station_roster.csv",
    ]:
        if not path.is_file():
            continue
        frame = pd.read_csv(path)
        col = "station_id" if "station_id" in frame.columns else "site_id"
        if col in frame.columns:
            used |= set(frame[col].astype(str))
    # quarantined
    used.add("80289")
    return used


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = station_catalog()
    used = used_station_ids()
    fresh = catalog.loc[~catalog["site_id"].astype(str).isin(used)].copy()
    print(f"smhi catalog {len(catalog)} fresh {len(fresh)}", flush=True)
    fresh.to_csv(OUT / "fresh_catalog.csv", index=False)

    # Prefer catchments that could reach ≥2 stations
    counts = fresh.groupby("catchment_number")["site_id"].nunique()
    catchments = counts[counts >= MIN_STATIONS].index.astype(str)
    target = fresh.loc[fresh["catchment_number"].astype(str).isin(set(catchments))]
    # Cap for runtime: top catchments by station count
    top = (
        target.groupby("catchment_number")
        .size()
        .sort_values(ascending=False)
        .head(40)
        .index.astype(str)
    )
    target = target.loc[target["catchment_number"].astype(str).isin(set(top))]
    print(f"download targets {len(target)} stations in {len(top)} catchments", flush=True)

    daily_root = OUT / "station_daily"
    daily_root.mkdir(parents=True, exist_ok=True)

    def one(site_id: str) -> tuple[str, int]:
        try:
            payload = get_bytes(DATA_URL.format(site_id=site_id))
            frame = parse_daily(payload, site_id)
            path = daily_root / f"{site_id}.csv"
            frame.to_csv(path, index=False)
            return site_id, len(frame)
        except Exception as exc:  # noqa: BLE001
            return site_id, -1

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(one, target["site_id"].astype(str).tolist()))
    print("downloaded", sum(1 for _, n in results if n > 0), "failed", sum(1 for _, n in results if n < 0), flush=True)

    station_rows = []
    for row in target.itertuples(index=False):
        site_id = str(row.site_id)
        path = daily_root / f"{site_id}.csv"
        if not path.is_file():
            continue
        frame = pd.read_csv(path, parse_dates=["date"])
        if frame.empty:
            continue
        series = frame.set_index("date")["temperature_c"]
        years = complete_years(series)
        station_rows.append(
            {
                "network_id": f"smhi_wave2_{row.catchment_number}",
                "station_id": site_id,
                "catchment_number": row.catchment_number,
                "catchment_name": row.catchment_name,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "n_complete_years": len(years),
                "complete_years": ";".join(map(str, years)),
                "n_days": int(len(frame)),
            }
        )
    stations = pd.DataFrame(station_rows)
    if len(stations):
        stations.to_csv(OUT / "stations_all.csv", index=False)
    else:
        stations = pd.DataFrame(
            columns=[
                "network_id",
                "station_id",
                "catchment_number",
                "catchment_name",
                "latitude",
                "longitude",
                "n_complete_years",
                "complete_years",
                "n_days",
            ]
        )
        stations.to_csv(OUT / "stations_all.csv", index=False)

    ready_nets = []
    if len(stations) and "network_id" in stations.columns:
        for net_id, group in stations.groupby("network_id"):
            ge4 = group.loc[group["n_complete_years"] >= MIN_YEARS]
            if len(ge4) < MIN_STATIONS:
                continue
            wide = {}
            for site_id in ge4["station_id"].astype(str):
                frame = pd.read_csv(daily_root / f"{site_id}.csv", parse_dates=["date"])
                wide[site_id] = frame.set_index("date")["temperature_c"]
            panel = pd.DataFrame(wide).sort_index()
            net_dir = OUT / "networks" / str(net_id)
            net_dir.mkdir(parents=True, exist_ok=True)
            panel.to_csv(net_dir / "daily_wide_temperature.csv")
            ge4.to_csv(net_dir / "stations.csv", index=False)
            ready_nets.append(
                {
                    "network_id": net_id,
                    "provider": "smhi",
                    "n_stations_ge4": int(len(ge4)),
                    "station_ids_ge4": ";".join(ge4["station_id"].astype(str)),
                    "path": str((net_dir / "daily_wide_temperature.csv").relative_to(ROOT)),
                }
            )
    ready = pd.DataFrame(ready_nets)
    ready.to_csv(OUT / "ready_networks.csv", index=False)
    summary = {
        "provider": "smhi",
        "scored": False,
        "n_ready_networks": int(len(ready)),
        "min_stations": MIN_STATIONS,
        "min_complete_years": MIN_YEARS,
        "accept_quality": sorted(ACCEPT_Q),
        "temp_bounds_C": [TEMP_MIN, TEMP_MAX],
        "excluded_prior_stations": len(used),
        "n_fresh_catalog_stations": int(len(fresh)),
        "ready_network_ids": ready["network_id"].tolist() if len(ready) else [],
        "note": (
            "Wave-2 SMHI primary-candidate panels; not scored; unit bounds enforced. "
            "If n_fresh_catalog_stations=0, the HydroObs catalog is exhausted relative "
            "to multi_agency_ingest/smhi/stations_all.csv — need another primary provider."
        ),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
