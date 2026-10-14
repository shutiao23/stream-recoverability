#!/usr/bin/env python3
"""P0-07 wave-2 UK EA: recruit unused spatial clusters as primary networks.

Skips clusters already emitted under multi_agency_ingest/uk_ea (s50_001/002).
Downloads derived daily means via uk_ea_daily; does not score.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.data.uk_ea_temperature import uk_ea_daily  # noqa: E402

OUT = ROOT / "results/wrr_submission_ready/p0_07_wave2_ingest/uk_ea"
CLUSTERS = ROOT / "results/framework/public_catalog/uk_ea_spatial_clusters.csv"
PRIOR_EMITTED = {
    "uk_ea_s50_001",
    "uk_ea_s50_002",
}
MIN_YEARS = 4
MIN_STATIONS = 2
MAX_NETWORKS = 10
SITES_PER_NET = 8


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


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "raw_cache"
    cache.mkdir(parents=True, exist_ok=True)
    clusters = pd.read_csv(CLUSTERS)
    clusters = clusters.loc[~clusters["cluster_id"].astype(str).isin(PRIOR_EMITTED)].copy()
    clusters = clusters.sort_values("n_stations", ascending=False).head(MAX_NETWORKS)
    print(f"wave2 uk_ea targets {len(clusters)}", flush=True)

    ready = []
    for row in clusters.itertuples(index=False):
        net_id = f"uk_ea_wave2_{str(row.cluster_id).replace('uk_ea_', '')}"
        site_ids = [s.strip() for s in str(row.site_ids).split(",") if s.strip()][:SITES_PER_NET]
        print(f"download {net_id} sites={site_ids}", flush=True)
        series_map: dict[str, pd.Series] = {}
        elig = []
        for site_id in site_ids:
            try:
                daily = uk_ea_daily(site_id, cache_dir=cache, start="2005-01-01", end="2024-12-31")
            except Exception as exc:  # noqa: BLE001
                print(f"  fail {site_id}: {exc}", flush=True)
                continue
            if daily is None or daily.empty:
                print(f"  empty {site_id}", flush=True)
                continue
            s = daily.set_index(pd.to_datetime(daily["date"]))["temperature_c"].astype(float)
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
                "provider": "uk_ea",
                "n_stations_ge4": len(series_map),
                "station_ids": ";".join(series_map),
            }
        )
        print(f"  READY {net_id}", flush=True)

    pd.DataFrame(ready).to_csv(OUT / "ready_networks.csv", index=False)
    summary = {
        "provider": "uk_ea",
        "scored": False,
        "n_ready_networks": len(ready),
        "ready_network_ids": [r["network_id"] for r in ready],
        "source": "uk_ea_spatial_clusters.csv excluding prior-emitted s50_001/002",
        "note": "Wave-2 UK EA primary derived-daily panels; not scored.",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
