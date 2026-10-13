#!/usr/bin/env python3
"""Exploratory (scratch): complete-year count of three waterinfo.be daily-mean WT
series that were fetched before the provider's per-IP credit quota was exhausted.

URLs used (identical KiWIS request template as scripts/260_..., only the date
range differs: from=1980-01-01):

  https://download.waterinfo.be/tsmdownload/KiWIS/KiWIS?service=kisters
    &type=queryServices&datasource=0&request=getTimeseriesValues
    &ts_id=<ts_id>&from=1980-01-01&to=2026-12-31&format=json

Output: scratch/be_manual_probe_complete_years.csv
"""

import glob
import json
import pathlib

import pandas as pd

STATIONS = {
    "0139050042": "Mere/Molenbeek",
    "0139146042": "Sint-Pieters-Leeuw/Zuunbeek",
    "0139194042": "Zoutleeuw/Dormaalbeek",
}


def complete_years(series: pd.Series) -> list[int]:
    years = []
    for year, block in series.groupby(series.index.year):
        leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
        if len(block) >= (366 if leap else 365):
            years.append(int(year))
    return years


def main() -> None:
    rows = []
    for path in sorted(glob.glob("/tmp/be_v_*.json")):
        document = json.load(open(path))[0]
        ts_id = str(document["ts_id"])
        series = pd.Series({stamp[:10]: value for stamp, value in document["data"] if value is not None})
        series.index = pd.to_datetime(series.index)
        series = series.sort_index()
        years = complete_years(series)
        rows.append(
            {
                "raw_file": path,
                "ts_id": ts_id,
                "station_name": STATIONS.get(ts_id, ""),
                "n_rows_returned": document.get("rows"),
                "n_non_null_values": int(len(series)),
                "first_date": str(series.index.min().date()),
                "last_date": str(series.index.max().date()),
                "n_complete_years": len(years),
                "complete_years": ";".join(map(str, years)),
            }
        )
    frame = pd.DataFrame(rows)
    target = pathlib.Path("scratch/be_manual_probe_complete_years.csv")
    frame.to_csv(target, index=False)
    print(frame.to_string())
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
