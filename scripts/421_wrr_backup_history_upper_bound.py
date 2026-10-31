#!/usr/bin/env python3
"""Bound available historical coverage without fitting or inventing temperatures."""
from __future__ import annotations

import importlib
import json

import pandas as pd

import wrr_r3_common as C

G = importlib.import_module("388_wrr_natural_backup_validation")
OUT = G.OUT / "history_coverage_bound"


def optimistic_complete_years(series):
    if not series:
        return []
    covered = pd.concat([value.notna() for value in series], axis=1).fillna(False).any(axis=1)
    return G.complete_years(covered.where(covered))


def prior_years(years, target):
    return [int(year) for year in years if int(year) < int(target)]


def optimistic_hourly_years(frame, settings):
    """Allow complementary hours, ignoring sensor agreement for an upper bound."""
    time = pd.to_datetime(frame.Time_UTC, utc=True, errors="coerce", format="mixed")
    temperature = pd.to_numeric(frame.WaterTemperature_Celsius, errors="coerce")
    low, high = settings["gross_water_temperature_range_C"]
    valid = time.notna() & temperature.between(low, high)
    times = pd.DatetimeIndex(time.loc[valid]).unique().sort_values()
    if times.empty:
        return []
    observed = pd.DataFrame({"time": times, "day": times.floor("D"), "hour": times.hour})
    grouped = observed.groupby("day")
    hours = grouped.hour.nunique()
    span = (grouped.time.max() - grouped.time.min()).dt.total_seconds() / 3600
    covered = (hours >= settings["coverage"]["minimum_distinct_hours"]) & (span >= settings["coverage"]["minimum_span_hours"])
    covered.index = covered.index.tz_convert(None)
    return G.complete_years(covered.where(covered))


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    settings = json.loads(G.CONFIG.read_text())
    original = G.OUT / "pair_year_quality.csv"
    cases = pd.read_csv(original, dtype={"primary_serial": str, "backup_serial": str})
    points = cases[["river", "station", "latitude", "longitude", "file"]].drop_duplicates()
    records = []
    for filename, group in points.groupby("file"):
        path = G.RAW / filename
        source = pd.read_csv(path, dtype={"Station": str, "Serial": str}, encoding="utf-8-sig")
        source["lat"] = pd.to_numeric(source.Latitude, errors="coerce").round(6)
        source["lon"] = pd.to_numeric(source.Longitude, errors="coerce").round(6)
        for point in group.to_dict("records"):
            named = source.loc[source.Station.eq(point["station"])]
            local = named.loc[named.lat.eq(point["latitude"]) & named.lon.eq(point["longitude"])]
            # Every serial/type is admitted for this optimistic bound. No
            # cross-sensor agreement or historical primary assignment is assumed.
            local_series = [G.qualified_daily(block, settings) for _, block in local.groupby("Serial")]
            named_series = [G.qualified_daily(block, settings) for _, block in named.groupby(["Serial", "lat", "lon"], dropna=False)]
            local_years = optimistic_complete_years(local_series)
            named_years = optimistic_complete_years(named_series)
            local_hour_years = optimistic_hourly_years(local, settings)
            named_hour_years = optimistic_hourly_years(named, settings)
            years = cases.loc[cases.file.eq(filename) & cases.station.eq(point["station"]) & cases.latitude.eq(point["latitude"]) & cases.longitude.eq(point["longitude"]), "year"].unique()
            for year in sorted(years):
                local_prior, named_prior = prior_years(local_years, year), prior_years(named_years, year)
                local_hours, named_hours = prior_years(local_hour_years, year), prior_years(named_hour_years, year)
                if len(local_prior) > len(named_prior):
                    raise RuntimeError("The looser station-name coverage bound became smaller")
                records.append({**point, "target_year": int(year), "candidate_serials_at_point": local.Serial.nunique(),
                                "complete_prior_years_if_any_point_sensor_sufficed": ";".join(map(str, local_prior)),
                                "optimistic_prior_years_at_point": len(local_prior),
                                "complete_prior_years_if_any_named_station_sensor_sufficed": ";".join(map(str, named_prior)),
                                "optimistic_prior_years_same_station_name": len(named_prior),
                                "optimistic_prior_years_point_hour_union": len(local_hours),
                                "complete_prior_years_point_hour_union": ";".join(map(str, local_hours)),
                                "optimistic_prior_years_named_station_hour_union": len(named_hours),
                                "complete_prior_years_named_station_hour_union": ";".join(map(str, named_hours)),
                                "sensor_compatibility_assumed_for_upper_bound_only": True,
                                "usable_combined_temperature_record_created": False})
    frame = pd.DataFrame(records)
    frame.to_csv(OUT / "point_year_coverage_bounds.csv", index=False)
    maximum = int(frame.optimistic_prior_years_at_point.max())
    named_maximum = int(frame.optimistic_prior_years_same_station_name.max())
    C.write_json(OUT / "summary.json", {
        "scope": "all_metadata_qualified_backup_pair_points_and_years_in_the_existing_180_pair_year_cohort",
        "original_pair_year_candidates": len(cases), "physical_point_definitions": len(points),
        "point_target_year_rows": len(frame), "maximum_complete_prior_years_even_if_any_point_sensor_sufficed": maximum,
        "maximum_complete_prior_years_even_if_any_same_named_station_sensor_sufficed": named_maximum,
        "maximum_complete_prior_years_point_hour_union": int(frame.optimistic_prior_years_point_hour_union.max()),
        "maximum_complete_prior_years_named_station_hour_union": int(frame.optimistic_prior_years_named_station_hour_union.max()),
        "point_years_with_optimistic_three_year_support": int(frame.optimistic_prior_years_at_point.ge(3).sum()),
        "named_station_years_with_optimistic_three_year_support": int(frame.optimistic_prior_years_same_station_name.ge(3).sum()),
        "point_years_with_three_year_support_under_hour_union": int(frame.optimistic_prior_years_point_hour_union.ge(3).sum()),
        "named_station_years_with_three_year_support_under_hour_union": int(frame.optimistic_prior_years_named_station_hour_union.ge(3).sum()),
        "coverage_rules_unchanged": True, "no_interpolation_or_H30_prediction_errors_computed": True,
        "daily_means_only_used_to_determine_original_coverage": True,
        "all_sensors_and_types_included_regardless_of_agreement": True,
        "same_name_bound_also_ignores_reported_coordinate_differences": True,
        "hour_union_bound_ignores_sensor_identity_agreement_and_duplicate_value_conflicts": True,
        "bound_is_not_a_usable_composite_reference_or_input": True,
        "original_history_requirement_or_eligibility_changed": False,
        "new_recovery_or_H30_prediction_errors_opened": False})
    print(f"[421] {len(points)} pair-candidate points: even optimistic same-point/same-name prior-year maxima are {maximum}/{named_maximum}; original qualification unchanged", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
