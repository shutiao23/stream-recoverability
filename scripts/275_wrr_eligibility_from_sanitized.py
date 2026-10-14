#!/usr/bin/env python3
"""P0-02: rebuild complete-year eligibility from sanitized confirmation panels."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
SAN = READY / "amendments" / "p0_02_sanitized_panels" / "panels"
OUT = READY / "amendments" / "p0_02_eligibility_rebuild"
TEMP_MIN, TEMP_MAX = -5.0, 50.0
MIN_YEARS = 4


def complete_years(series) -> list[int]:
    import numpy as np
    import pandas as pd

    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    values = np.where(np.isfinite(values) & ((values < TEMP_MIN) | (values > TEMP_MAX)), np.nan, values)
    s = pd.Series(values, index=series.index)
    years = []
    for year, block in s.groupby(s.index.year):
        need = 366 if ((year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)) else 365
        if int(np.isfinite(block.to_numpy(dtype=float)).sum()) >= need:
            years.append(int(year))
    return years


def scan(root: Path, provider_label: str) -> list[dict]:
    import pandas as pd

    rows = []
    for path in sorted(root.glob("**/daily_wide_temperature.csv")):
        panel = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        panel = panel.apply(pd.to_numeric, errors="coerce")
        network_id = path.parent.name
        for station in panel.columns:
            years = complete_years(panel[station])
            rows.append(
                {
                    "provider_label": provider_label,
                    "network_id": network_id,
                    "station_id": str(station),
                    "n_complete_years": len(years),
                    "complete_years": ";".join(map(str, years)),
                    "eligible_ge4": len(years) >= MIN_YEARS,
                    "panel_path": str(path.relative_to(ROOT)),
                }
            )
    return rows


def main() -> int:
    import pandas as pd

    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    usgs = SAN / "confirmation_ingest"
    if usgs.is_dir():
        rows += scan(usgs, "usgs_confirmation")
    for provider in ("smhi", "uk_ea", "hubeau", "nve"):
        root = SAN / "multi_agency_ingest" / provider / "networks"
        if root.is_dir():
            rows += scan(root, provider)

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "station_year_eligibility.csv", index=False)

    summary = {"providers": {}}
    for label, block in table.groupby("provider_label"):
        eligible_stations = block.loc[block["eligible_ge4"]]
        nets = eligible_stations.groupby("network_id").filter(lambda g: len(g) >= 2)
        summary["providers"][str(label)] = {
            "n_stations_total": int(block["station_id"].nunique()),
            "n_stations_ge4_complete_years": int(eligible_stations["station_id"].nunique()),
            "n_networks_with_ge2_eligible_stations": int(nets["network_id"].nunique()),
            "n_complete_station_years": int(eligible_stations["n_complete_years"].sum()),
        }
    summary["policy"] = (
        "Eligibility after sentinel/implausible quarantine; SMHI coding failures "
        "remove most complete years until source units are verified."
    )
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
