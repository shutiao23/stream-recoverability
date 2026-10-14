#!/usr/bin/env python3
"""P0-07 wave-2 Hub'Eau: download beyond-cap rivers never emitted as transport panels."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import importlib.util  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

OUT = ROOT / "results/wrr_submission_ready/p0_07_wave2_ingest/hubeau"
BEYOND = ROOT / "results/wrr_submission_ready/multi_agency_ingest/hubeau/networks_beyond_cap.csv"
EXISTING = ROOT / "results/wrr_submission_ready/multi_agency_ingest/hubeau/networks"
CODE = "4"  # same disclosed Non-qualifié contract as transport ingest
MIN_OBS = 4
MIN_YEARS = 4
MIN_STATIONS = 2


def load_242():
    spec = importlib.util.spec_from_file_location("hubeau242", ROOT / "scripts/242_multi_agency_hubeau_ingest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def download_station(h, hub, site_id: str, *, max_years: int = 25) -> pd.Series | None:
    # Use span endpoints from Hub'Eau API
    import time

    from stream_recoverability.data.hubeau_temperature import hubeau_chronicle_span

    span = None
    for attempt in range(4):
        try:
            span = hubeau_chronicle_span(site_id)
            break
        except Exception as exc:  # noqa: BLE001
            print(f"    span fail {site_id} attempt={attempt+1}: {exc}", flush=True)
            time.sleep(2.0 * (attempt + 1))
    if not span:
        return None
    begin, end = span.get("daily_begin"), span.get("daily_end")
    if not begin or not end:
        return None
    start_y = pd.Timestamp(str(begin)[:10]).year
    end_y = min(pd.Timestamp(str(end)[:10]).year, 2025)
    years = list(range(start_y, end_y + 1))
    if len(years) > max_years:
        years = years[-max_years:]
    parts = []
    for year in years:
        ok = False
        for attempt in range(3):
            try:
                rows = h.fetch_window(
                    hub,
                    site_id,
                    pd.Timestamp(year=year, month=1, day=1),
                    pd.Timestamp(year=year, month=12, day=31),
                    CODE,
                )
                day, _ = h.per_day_table(rows)
                parts.append(day)
                ok = True
                break
            except Exception as exc:  # noqa: BLE001
                print(f"    year fail {site_id} {year} attempt={attempt+1}: {exc}", flush=True)
                time.sleep(1.5 * (attempt + 1))
        if not ok:
            continue
    if not parts:
        return None
    per_day = h.merge_per_day(parts)
    daily = h.daily_values(per_day, min_obs_per_day=MIN_OBS)
    if daily.empty:
        return None
    return daily.set_index(pd.to_datetime(daily["date"]))["temperature_c"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "raw_cache").mkdir(parents=True, exist_ok=True)
    (OUT / "networks").mkdir(parents=True, exist_ok=True)
    h = load_242()
    hub = h.CachedHub(OUT / "raw_cache", workers=1, timeout=120, retries=6, pause=0.4, outer_retries=3)

    beyond = pd.read_csv(BEYOND)
    existing = {p.name for p in EXISTING.iterdir()} if EXISTING.is_dir() else set()
    beyond = beyond.loc[~beyond["network_id"].astype(str).isin(existing)].copy()
    # Prefer metropolitan France (skip Reunion/DOM river keys that stall / return empty).
    beyond = beyond.loc[
        ~beyond["river_name"].astype(str).str.contains(
            r"Rivi[eè]re|cirque|Langevin|Marsouins|Salazie|Tavignano",
            case=False,
            regex=True,
        )
    ]
    # Resume: skip networks already marked ready from a prior partial run.
    ready: list[dict] = []
    ready_csv = OUT / "ready_networks.csv"
    if ready_csv.is_file() and ready_csv.stat().st_size > 0:
        prev = pd.read_csv(ready_csv)
        if not prev.empty:
            ready = prev.to_dict(orient="records")
    prior_ready = {str(r["network_id"]) for r in ready}
    # Also treat on-disk network panels as ready.
    net_root = OUT / "networks"
    if net_root.is_dir():
        for p in net_root.iterdir():
            if (p / "daily_wide_temperature.csv").is_file():
                prior_ready.add(p.name)
                if p.name not in {str(r["network_id"]) for r in ready}:
                    ready.append(
                        {
                            "network_id": p.name,
                            "provider": "hubeau",
                            "n_stations_ge4": None,
                            "station_ids": "",
                        }
                    )
    beyond = beyond.loc[~beyond["network_id"].astype(str).isin(prior_ready)]
    beyond = beyond.sort_values("candidate_observations", ascending=False).head(20)
    print(f"wave2 hubeau targets {len(beyond)} (prior_ready={len(prior_ready)})", flush=True)
    for row in beyond.itertuples(index=False):
        net_id = str(row.network_id)
        site_ids = [s.strip() for s in str(row.station_ids).split(";") if s.strip()][:4]
        print(f"download {net_id} sites={site_ids}", flush=True)
        series_map: dict[str, pd.Series] = {}
        elig = []
        for site_id in site_ids:
            try:
                s = download_station(h, hub, site_id)
            except Exception as exc:  # noqa: BLE001
                print(f"  fail {site_id}: {exc}", flush=True)
                continue
            if s is None or s.empty:
                print(f"  empty {site_id}", flush=True)
                continue
            years = complete_years(s)
            elig.append(
                {
                    "station_id": site_id,
                    "n_complete_years": len(years),
                    "complete_years": ";".join(map(str, years)),
                }
            )
            print(f"  {site_id} ge4_years={len(years)}", flush=True)
            if len(years) >= MIN_YEARS:
                series_map[site_id] = s
        if len(series_map) < MIN_STATIONS:
            print(f"  skip {net_id}: {len(series_map)} ge4 stations", flush=True)
            continue
        wide = pd.DataFrame(series_map).sort_index()
        net_dir = OUT / "networks" / net_id
        net_dir.mkdir(parents=True, exist_ok=True)
        wide.to_csv(net_dir / "daily_wide_temperature.csv")
        pd.DataFrame(elig).to_csv(net_dir / "station_eligibility.csv", index=False)
        ready.append(
            {
                "network_id": net_id,
                "provider": "hubeau",
                "n_stations_ge4": len(series_map),
                "station_ids": ";".join(series_map),
            }
        )
        print(f"  READY {net_id}", flush=True)

    pd.DataFrame(ready).to_csv(OUT / "ready_networks.csv", index=False)
    summary = {
        "provider": "hubeau",
        "scored": False,
        "n_ready_networks": len(ready),
        "ready_network_ids": [r["network_id"] for r in ready],
        "quality_code": CODE,
        "min_obs_per_day": MIN_OBS,
        "source": "networks_beyond_cap.csv",
        "note": "Daily series newly downloaded for wave-2; not scored.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
