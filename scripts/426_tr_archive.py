#!/usr/bin/env python3
"""TR-E1a: the full opened archive as days, gaps and station-years, complete or not.

Every station of the final analysis panel contributes its whole active span,
from the first to the last observed day. Air temperature comes from the
station forcing already used by the reconstructors. Nothing here reads a
sealed vault or a reconstruction error.
"""

from __future__ import annotations

import os

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_tr_common as T
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v19_revision.data import station_air_series

OUT = T.OUT / "e1_archive"


def smooth_doy_anomaly(series: pd.Series) -> pd.Series:
    """Departure from a 31-day circular day-of-year climatology."""

    values = series.dropna()
    if len(values) < 365:
        return pd.Series(np.nan, index=series.index)
    climate = values.groupby(values.index.dayofyear).mean().reindex(range(1, 367)).interpolate(limit_direction="both")
    padded = np.r_[climate.to_numpy()[-15:], climate.to_numpy(), climate.to_numpy()[:15]]
    smooth = np.convolve(padded, np.ones(31) / 31, mode="valid")
    return series - smooth[series.index.dayofyear.to_numpy() - 1]


def runs(missing: np.ndarray) -> list[tuple[int, int]]:
    starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
    ends = np.flatnonzero(missing & ~np.r_[missing[1:], False]) + 1
    return [(int(s), int(e - s)) for s, e in zip(starts, ends)]


def station_tables(job: dict, warm_months: list[int], summer_months: list[int]) -> dict:
    panel = read_temperature_panel(job["input_path"])
    panel.columns = panel.columns.astype(str)
    if job["station_id"] not in panel:
        return {"station_key": job["station_key"], "status": "station_missing"}
    water = pd.to_numeric(panel[job["station_id"]], errors="coerce").asfreq("D")
    observed = water.dropna()
    if observed.empty:
        return {"station_key": job["station_key"], "status": "no_observation"}
    first, last = observed.index.min(), observed.index.max()
    index = pd.date_range(pd.Timestamp(first.year, 1, 1), pd.Timestamp(last.year, 12, 31), freq="D")
    water = water.reindex(index)
    active = (index >= first) & (index <= last)
    air = station_air_series(T.AIR, job["network_id"], job["station_id"], index)
    if air is None:
        air = pd.Series(np.nan, index=index)
    air_anomaly = smooth_doy_anomaly(air)
    air_week = air_anomaly.rolling(7, min_periods=4).mean()
    water_anomaly = smooth_doy_anomaly(water)
    daily = pd.DataFrame(
        {
            "station_key": job["station_key"], "date": index, "water_c": water.to_numpy(dtype=np.float32),
            "active": active, "air_c": air.to_numpy(dtype=np.float32), "air_anomaly_c": air_anomaly.to_numpy(dtype=np.float32),
            "air_week_anomaly_c": air_week.to_numpy(dtype=np.float32), "water_anomaly_c": water_anomaly.to_numpy(dtype=np.float32),
        }
    )
    month = index.month.to_numpy()
    missing = ~np.isfinite(water.to_numpy(dtype=float))
    years, gaps = [], []
    for year in range(first.year, last.year + 1):
        in_year = index.year == year
        year_index = index[in_year]
        miss = missing[in_year]
        act = active[in_year]
        warm = np.isin(year_index.month.to_numpy(), warm_months)
        summer = np.isin(year_index.month.to_numpy(), summer_months)
        values = water.to_numpy(dtype=float)[in_year]
        year_runs = runs(miss & act)
        warm_runs = runs(miss & act & warm)
        complete_warm = not miss[warm].any()
        row = {
            "station_key": job["station_key"], "year": year, "n_days": int(in_year.sum()), "n_active_days": int(act.sum()),
            "n_observed": int((~miss).sum()), "observed_fraction": float((~miss).mean()),
            "warm_observed_fraction": float((~miss[warm]).mean()), "summer_observed_fraction": float((~miss[summer]).mean()),
            "jas_observed_fraction": float((~miss[np.isin(year_index.month.to_numpy(), [7, 8, 9])]).mean()),
            "aug_observed_fraction": float((~miss[year_index.month.to_numpy() == 8]).mean()),
            "julaug_complete": bool(not miss[np.isin(year_index.month.to_numpy(), [7, 8])].any()),
            "complete_year": bool(not miss.any()), "complete_warm": bool(complete_warm),
            "edge_year": bool(year in (first.year, last.year)), "fully_active": bool(act.all()),
            "n_runs": len(year_runs), "longest_run": max([length for _, length in year_runs], default=0),
            "longest_warm_run": max([length for _, length in warm_runs], default=0),
            "air_summer_mean_c": float(np.nanmean(air.to_numpy(dtype=float)[in_year][summer])) if np.isfinite(air.to_numpy(dtype=float)[in_year][summer]).any() else np.nan,
            "air_warm_mean_c": float(np.nanmean(air.to_numpy(dtype=float)[in_year][warm])) if np.isfinite(air.to_numpy(dtype=float)[in_year][warm]).any() else np.nan,
            "air_h30_c": float(np.nanmax(T.window_means(air.to_numpy(dtype=float)[in_year], 30))) if np.isfinite(air.to_numpy(dtype=float)[in_year]).all() else np.nan,
            "truth_h30": float(T.window_means(values, 30).max()) if complete_warm and np.isfinite(values[warm]).all() and np.isfinite(values).all() else np.nan,
            "warm_h30": float(T.window_means(values[warm], 30).max()) if complete_warm else np.nan,
        }
        years.append(row)
        for start, length in year_runs:
            onset = year_index[start]
            position = int(np.flatnonzero(index == onset)[0])
            gaps.append(
                {
                    "station_key": job["station_key"], "year": year, "start_doy": int(onset.dayofyear), "start_month": int(onset.month),
                    "length": length, "interior": bool(position > 0 and position + length < len(index) and active[position - 1] and active[min(position + length, len(index) - 1)]),
                    "crosses_year_end": bool(start + length == len(year_index) and position + length < len(index) and missing[position + length]),
                    "onset_air_anomaly_c": float(air_anomaly.iloc[position]) if np.isfinite(air_anomaly.iloc[position]) else np.nan,
                    "onset_air_week_anomaly_c": float(air_week.iloc[position - 1]) if position > 0 and np.isfinite(air_week.iloc[position - 1]) else np.nan,
                    "pre_water_anomaly_c": float(water_anomaly.iloc[max(0, position - 7) : position].mean()) if position > 0 else np.nan,
                }
            )
    cache = T.SCRATCH / "e1_archive_daily" / f"{job['station_key'].replace('|', '__')}.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    daily.to_parquet(cache, index=False)
    return {"station_key": job["station_key"], "status": "ok", "years": years, "gaps": gaps, "daily": str(cache), "first": str(first.date()), "last": str(last.date())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=64)
    args = parser.parse_args()
    settings = T.settings()
    roster = T.roster()
    stations = roster.drop_duplicates("station_key").copy()
    jobs = stations[["station_key", "station_id", "network_id", "provider", "input_path", "independence_group", "statistic_class", "regulation_status", "split_role"]].to_dict("records")
    print(f"[426] {len(jobs)} stations", flush=True)
    results = Parallel(n_jobs=args.workers, verbose=5)(delayed(station_tables)(job, settings["warm_months"], settings["summer_months"]) for job in jobs)
    OUT.mkdir(parents=True, exist_ok=True)
    meta = stations.set_index("station_key")[["station_id", "network_id", "provider", "independence_group", "statistic_class", "regulation_status", "split_role"]]
    years = pd.DataFrame([row for result in results if result["status"] == "ok" for row in result["years"]]).join(meta, on="station_key")
    gaps = pd.DataFrame([row for result in results if result["status"] == "ok" for row in result["gaps"]]).join(meta, on="station_key")
    daily = pd.concat([pd.read_parquet(result["daily"]) for result in results if result["status"] == "ok"], ignore_index=True)
    daily["station_key"] = daily.station_key.astype("category")
    years.to_parquet(OUT / "station_years.parquet", index=False)
    gaps.to_parquet(OUT / "gaps.parquet", index=False)
    daily.to_parquet(T.SCRATCH / "archive_daily.parquet", index=False)
    status = pd.DataFrame([{"station_key": r["station_key"], "status": r["status"], "first": r.get("first"), "last": r.get("last")} for r in results])
    status.to_csv(OUT / "station_status.csv", index=False)
    summary = {
        "n_stations": int(status.status.eq("ok").sum()), "n_station_years": len(years),
        "n_complete_years": int(years.complete_year.sum()), "n_complete_warm": int(years.complete_warm.sum()),
        "n_gaps": len(gaps), "n_daily_rows": len(daily), "status_counts": status.status.value_counts().to_dict(),
    }
    T.write_json(OUT / "summary.json", summary)
    print(summary, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
