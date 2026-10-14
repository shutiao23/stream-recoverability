#!/usr/bin/env python3
"""P0-07 wave-2 ECCC automated freshwater temperature recruitment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.data.eccc_automated_temperature import (  # noqa: E402
    candidate_networks,
    directory_inventory,
    read_station_catalog,
    station_file_map,
    WATER_TEMPERATURE_CODE,
    get_bytes,
    file_url,
)

OUT = ROOT / "results/wrr_submission_ready/p0_07_wave2_ingest/eccc"
MIN_YEARS = 4
MIN_STATIONS = 2


def complete_years(series: pd.Series) -> list[int]:
    """Match USGS wave-2: ≥(year_length−1) observed days, all finite, plausible °C."""
    years = []
    for year, block in series.groupby(series.index.year):
        values = pd.to_numeric(block, errors="coerce")
        expected = 366 if pd.Timestamp(int(year), 12, 31).is_leap_year else 365
        if len(values) >= expected - 1 and values.notna().all() and np.isfinite(values.to_numpy(dtype=float)).all():
            if float(values.min()) < -5 or float(values.max()) > 45:
                continue
            years.append(int(year))
    return years


def load_station_daily(path: str) -> pd.Series:
    raw = get_bytes(file_url(path))
    name = path.lower()
    bio = __import__("io").BytesIO(raw)
    if name.endswith(".xlsx"):
        frame = pd.read_excel(bio)
    else:
        frame = pd.read_csv(bio, encoding="cp1252", low_memory=False)
    # Normalize common bilingual headers.
    rename = {}
    for c in frame.columns:
        key = str(c).lower()
        if key in {"date_time_heure", "datetime", "date"}:
            rename[c] = "date"
        elif key in {"value_valeur", "value", "result", "resultat"}:
            rename[c] = "value"
        elif key in {"variable", "variable_en", "variable_fr"}:
            rename[c] = "variable" if "variable" not in rename.values() else c
        elif key in {"vmv_code", "variable_code"}:
            rename[c] = "vmv_code"
    frame = frame.rename(columns=rename)
    if "date" not in frame.columns or "value" not in frame.columns:
        raise ValueError(f"unrecognized columns {list(frame.columns)[:12]}")
    work = frame.copy()
    filtered = False
    if "vmv_code" in work.columns and work["vmv_code"].notna().any():
        codes = pd.to_numeric(work["vmv_code"], errors="coerce")
        # VMV 4730 = water temperature (°C) in ECCC automated FWQ files.
        temp = work.loc[codes.eq(WATER_TEMPERATURE_CODE)]
        if not temp.empty:
            work = temp
            filtered = True
    if not filtered and "variable" in work.columns:
        var = work["variable"].astype(str).str.lower()
        work = work.loc[var.str.contains("temp") & var.str.contains("water")]
    series = pd.Series(
        pd.to_numeric(work["value"], errors="coerce").to_numpy(),
        index=pd.to_datetime(work["date"], errors="coerce", dayfirst=True),
    )
    series = series[series.index.notna()].sort_index()
    daily = series.groupby(series.index.normalize()).mean()
    daily.name = "temperature_c"
    return daily


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("ECCC inventory...", flush=True)
    inventory = directory_inventory()
    stations = read_station_catalog(inventory)
    files = station_file_map(inventory)
    cands = candidate_networks(stations, files)
    cands.to_csv(OUT / "candidate_networks.csv", index=False)
    print(f"candidates {len(cands)}", flush=True)

    ready = []
    for row in cands.head(25).itertuples(index=False):
        net_id = str(row.network_id)
        site_ids = str(row.site_ids).split("|")
        print(f"network {net_id} n_sites={len(site_ids)}", flush=True)
        series_map = {}
        elig = []
        for site_id in site_ids[:6]:
            paths = files.get(site_id) or ()
            if not paths:
                continue
            try:
                # concatenate all files for station
                parts = []
                for path in paths:
                    try:
                        parts.append(load_station_daily(path))
                    except Exception as exc:  # noqa: BLE001
                        print(f"  file fail {site_id} {path}: {exc}", flush=True)
                if not parts:
                    continue
                s = pd.concat(parts).groupby(level=0).mean().sort_index()
                years = complete_years(s)
                elig.append({"station_id": site_id, "n_complete_years": len(years)})
                print(f"  {site_id} years={len(years)}", flush=True)
                if len(years) >= MIN_YEARS:
                    series_map[site_id] = s
            except Exception as exc:  # noqa: BLE001
                print(f"  fail {site_id}: {exc}", flush=True)
        if len(series_map) < MIN_STATIONS:
            continue
        wide = pd.DataFrame(series_map).sort_index()
        net_dir = OUT / "networks" / net_id
        net_dir.mkdir(parents=True, exist_ok=True)
        wide.to_csv(net_dir / "daily_wide_temperature.csv")
        pd.DataFrame(elig).to_csv(net_dir / "station_eligibility.csv", index=False)
        ready.append({"network_id": net_id, "provider": "eccc_automated", "n_stations_ge4": len(series_map)})
        print(f"  READY {net_id}", flush=True)

    pd.DataFrame(ready).to_csv(OUT / "ready_networks.csv", index=False)
    summary = {
        "provider": "eccc_automated",
        "scored": False,
        "n_ready_networks": len(ready),
        "ready_network_ids": [r["network_id"] for r in ready],
        "note": "Wave-2 ECCC automated FWQ temperature; not scored.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
