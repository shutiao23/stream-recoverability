#!/usr/bin/env python3
"""TR2: target tolerances under the round-2 definitions, by the round-1 rule.

Same rule as scripts/433_tr_prereg.py: each target's tolerance is the share of
its median within-station interannual standard deviation that 0.5 C is of
H30's, with floors of 0.2 C and one day. Degree-days are now summed over each
station's four climatologically hottest months (all source stations are in the
Northern Hemisphere, so their hot years are calendar years). Only complete-year
truths are used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import wrr_tr_common as T

OUT = T.OUT / "e2_prereg"
FLOORS = {"h30": 0.0, "h7": 0.2, "annual_mean": 0.2, "c30": 0.2, T.DEGREE_DAYS: 0.0, "days_above_20": 1.0}


def main() -> int:
    settings = T.settings()
    daily = pd.read_parquet(T.SCRATCH / "archive_daily.parquet", columns=["station_key", "date", "water_c"])
    daily["station_key"] = daily.station_key.astype(str)
    rows = []
    for station, block in daily.groupby("station_key"):
        series = block.set_index("date").water_c.astype(float)
        complete = [year for year, values in series.groupby(series.index.year) if len(values) == (366 if pd.Timestamp(int(year), 12, 31).is_leap_year else 365) and values.notna().all()]
        if len(complete) < 4:
            continue
        kept = series.loc[series.index.year.isin(complete)]
        climate = kept.groupby(kept.index.dayofyear).mean().reindex(range(1, 367)).interpolate(limit_direction="both").to_numpy()[:365]
        months = T.hottest_months(climate, np.arange(1, 366), settings["degree_day_months"])
        for year in complete:
            values = kept.loc[str(year)]
            rows.append({"station_key": station, "year": int(year), **T.target_statistics(values.to_numpy(), values.index, settings["exceedance_threshold_c"], months)})
    frame = pd.DataFrame(rows)
    sd = frame.groupby("station_key")[[name for name in T.TARGETS if name != "peak_doy"]].std(ddof=1).median()
    scale = 0.5 / sd["h30"]
    tolerance = {name: float(max(FLOORS[name], scale * sd[name])) for name in sd.index}
    tolerance["h30"] = 0.5
    tolerance["peak_doy"] = 7.0
    payload = {"median_interannual_sd": sd.to_dict(), "tolerance": tolerance, "n_stations": int(frame.station_key.nunique()), "n_station_years": len(frame), "degree_days": "sum of daily means above 0 C over the station's four climatologically hottest consecutive months"}
    T.write_json(OUT / "target_tolerances.json", payload)
    print(payload, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
