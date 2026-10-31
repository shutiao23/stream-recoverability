#!/usr/bin/env python3
"""Qualify actual logger gaps against independent backup sensor records."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

import wrr_r3_common as C

RAW = C.ROOT / "data/external/wrr_followup_backup"
OUT = C.READY / "followup_20261021/natural_backup"
CONFIG = C.ROOT / "configs/wrr_natural_backup_20261021_v2.json"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def qualified_daily(frame, settings):
    data = frame.copy()
    data["time"] = pd.to_datetime(data.Time_UTC, utc=True, errors="coerce", format="mixed")
    data["temperature"] = pd.to_numeric(data.WaterTemperature_Celsius, errors="coerce")
    low, high = settings["gross_water_temperature_range_C"]
    data.loc[~data.temperature.between(low, high), "temperature"] = np.nan
    data = data.dropna(subset=["time"]).drop_duplicates(["time", "temperature"])
    conflicts = data.groupby("time").temperature.nunique(dropna=True)
    data.loc[data.time.isin(conflicts.index[conflicts > 1]), "temperature"] = np.nan
    # first() selects the available value when an exact duplicate also has NaN.
    series = data.groupby("time").temperature.first().sort_index()
    finite = series.dropna().rename("temperature").to_frame()
    if finite.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    finite["hour"] = finite.index.hour
    grouped = finite.groupby(finite.index.floor("D"))
    daily = grouped.temperature.mean()
    hours = grouped.hour.nunique()
    span = grouped.apply(lambda block: (block.index.max() - block.index.min()).total_seconds() / 3600)
    valid = (hours >= settings["coverage"]["minimum_distinct_hours"]) & (span >= settings["coverage"]["minimum_span_hours"])
    daily = daily.where(valid)
    daily.index = daily.index.tz_convert(None)
    return daily


def daily_path(row, serial):
    """Readable, filesystem-safe daily file name from river, station, coordinates and serial."""
    parts = [row["river"], row["station"], row["latitude"], row["longitude"], serial]
    return OUT / "daily" / ("__".join(re.sub(r"[^A-Za-z0-9_.-]+", "-", str(part)) for part in parts) + ".csv")


def complete_years(series):
    found = []
    for year in sorted(series.index.year.unique()):
        dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
        if series.reindex(dates).notna().all():
            found.append(int(year))
    return found


def qualify():
    settings = json.loads(CONFIG.read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    protocol_record = OUT / "analysis_protocol.json"
    if not protocol_record.exists():
        # Written once, before any temperature column is opened.
        C.write_json(protocol_record, run_record({"protocol_v2": CONFIG, "metadata_protocol": OUT / "metadata_protocol.json", "metadata_pairs": OUT / "potential_backup_pairs.csv", "archive": RAW / "CSV_EN.7z"}, temperature_values_inspected=False, recovery_outcomes_inspected=False, amendment_before_temperature_inspection=True))
    pairs = pd.read_csv(OUT / "potential_backup_pairs.csv", dtype={"primary_serial": str, "backup_serial": str})
    pairs = pairs.loc[pairs.metadata_pair_eligible].drop_duplicates(["file", "station", "primary_serial", "backup_serial"])
    cache = OUT / "daily"
    cache.mkdir(exist_ok=True)
    eligible, exclusions, pair_quality = [], [], []
    for filename, candidate_pairs in pairs.groupby("file"):
        source = pd.read_csv(RAW / filename, dtype={"Station": str, "Serial": str}, encoding="utf-8-sig")
        source["latitude_key"] = pd.to_numeric(source.Latitude, errors="coerce").round(6)
        source["longitude_key"] = pd.to_numeric(source.Longitude, errors="coerce").round(6)
        daily_of = {}
        for row in candidate_pairs.to_dict("records"):
            for serial in (row["primary_serial"], row["backup_serial"]):
                key = (row["station"], serial, row["latitude"], row["longitude"])
                if key not in daily_of:
                    chosen = source.loc[source.Station.eq(key[0]) & source.Serial.eq(key[1]) & source.latitude_key.eq(key[2]) & source.longitude_key.eq(key[3])]
                    daily_of[key] = qualified_daily(chosen, settings)
                    daily_of[key].rename("temperature_C").to_csv(daily_path(row, serial), index_label="date")
            for primary_id, backup_id in ((row["primary_serial"], row["backup_serial"]), (row["backup_serial"], row["primary_serial"])):
                primary, backup = daily_of[(row["station"], primary_id, row["latitude"], row["longitude"])], daily_of[(row["station"], backup_id, row["latitude"], row["longitude"])]
                joined = pd.concat([primary.rename("primary"), backup.rename("backup")], axis=1).sort_index().asfreq("D")
                primary_years = complete_years(primary)
                for year, block in joined.groupby(joined.index.year):
                    dates = pd.date_range(f"{year}-01-01", f"{year}-12-31")
                    block = block.reindex(dates)
                    missing = block.primary.isna()
                    overlap = block.primary.notna() & block.backup.notna()
                    difference = (block.primary - block.backup).loc[overlap].abs()
                    identity = {"river": row["river"], "station": row["station"], "primary_serial": primary_id, "backup_serial": backup_id, "year": int(year), "latitude": row["latitude"], "longitude": row["longitude"], "file": filename,
                                "primary_daily_path": str(daily_path(row, primary_id)), "backup_daily_path": str(daily_path(row, backup_id))}
                    quality = {**identity, "missing_primary_days": int(missing.sum()), "visible_overlap_days": int(overlap.sum()), "visible_pair_MAE_C": float(difference.mean()) if len(difference) else np.nan,
                               "visible_pair_abs95_C": float(difference.quantile(.95)) if len(difference) else np.nan,
                               "n_complete_prior_primary_years": sum(value < year for value in primary_years)}
                    pair_quality.append(quality)
                    reason = None
                    if not missing.any():
                        reason = "primary_year_already_complete"
                    elif not np.isfinite(block.primary.iloc[[0, -1]]).all():
                        reason = "annual_boundary_outside_verified_primary_support"
                    elif block.backup.loc[missing].isna().any():
                        reason = "backup_does_not_cover_every_actual_missing_day"
                    elif overlap.sum() < settings["reference_QC"]["minimum_visible_overlap_days"]:
                        reason = "insufficient_visible_sensor_overlap"
                    elif difference.mean() > settings["reference_QC"]["maximum_visible_daily_MAE_C"] or difference.quantile(.95) > settings["reference_QC"]["maximum_visible_daily_abs95_C"]:
                        reason = "sensor_records_not_comparable_under_prespecified_QC"
                    elif sum(value < year for value in primary_years) < 3:
                        reason = "fewer_than_three_complete_prior_primary_years"
                    if reason:
                        exclusions.append({**quality, "reason": reason})
                        continue
                    runs = []
                    values = missing.to_numpy()
                    starts = np.flatnonzero(values & ~np.r_[False, values[:-1]])
                    ends = np.flatnonzero(values & ~np.r_[values[1:], False]) + 1
                    for start, end in zip(starts, ends):
                        runs.append(f"{start}:{end-start}")
                    eligible.append({**quality, "mask_runs": ";".join(runs), "n_runs": len(starts), "longest_run": int((ends-starts).max()),
                                     "independence_group": "dfo_NL_dependent_resource", "reference": "independent_backup_plus_visible_primary"})
    pd.DataFrame(pair_quality).to_csv(OUT / "pair_year_quality.csv", index=False)
    pd.DataFrame(exclusions).to_csv(OUT / "qualification_exclusions.csv", index=False)
    pd.DataFrame(eligible).to_csv(OUT / "eligible_natural_gaps.csv", index=False)
    C.write_json(OUT / "qualification_summary.json", {"n_pair_year_candidates": len(pair_quality), "n_qualified_pair_years": len(eligible),
                 "n_distinct_primary_years": len({(row["station"], row["primary_serial"], row["year"]) for row in eligible}),
                 "reasons": pd.Series([row["reason"] for row in exclusions]).value_counts().to_dict(),
                 "recovery_errors_used_for_selection": False, "actual_masks_not_synthetic": True, "provider_certified_daily_mean_claim": False})
    print(f"[388] {len(eligible)} qualified actual-gap pair-years from {len(pair_quality)} candidates; errors remain unevaluated", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["qualify"])
    args = parser.parse_args()
    qualify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
