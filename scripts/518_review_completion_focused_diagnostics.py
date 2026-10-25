#!/usr/bin/env python3
"""Requested influential-station profiles and named hot-year illustrations.

Uses completed source refits only. US illustration years are selected by air
anomaly, before extracting their prediction errors; every result is exploratory.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.statistics import event_metrics

OUT = T.ROOT / "results/wrr_review_completion_20261024/focused_diagnostics"
BASE = OUT.parent
STATIONS = ["usgs|13342500", "usgs|06054500"]


def outlier_profiles():
    cases = pd.read_parquet(BASE / "cases/leave_one_year_out/seed_00.parquet",
        columns=["station_key", "year", "design_family", "gap_length", "peak_overlap", "policy_choice"])
    cases = cases.loc[cases.station_key.isin(STATIONS)]
    metadata = pd.read_csv(BASE / "failure_map/station_failures_and_metadata.csv")
    metadata = metadata.drop_duplicates("station_key").set_index("station_key")
    names = pd.read_csv(T.E1 / "usgs_site_metadata.csv", dtype={"site_no": str}).set_index("site_no").station_nm
    profiles = []
    for (station, family), block in cases.groupby(["station_key", "design_family"]):
        row = metadata.loc[station]
        profiles.append({"station_key": station, "station_name": names.loc[station.split('|')[1]], "family": family,
            "n_evaluation_complete_years": block.year.nunique(), "first_evaluation_year": int(block.year.min()),
            "last_evaluation_year": int(block.year.max()), "n_cases": len(block), "median_missing_days": float(block.gap_length.median()),
            "danger_fraction": float(block.peak_overlap.ge(.5).mean()),
            "donor_layer_fraction": float(block.policy_choice.eq("donor_ridge").mean()),
            "air_layer_fraction": float(block.policy_choice.eq("air_ridge").mean()),
            "major_upstream_dams_2009": row.MAJ_NDAMS_2009,
            "zero_flow_days_available_record": row.zero_flow_days_in_available_record,
            "lake_outlet_status": row.lake_outlet_status})
    pd.DataFrame(profiles).to_csv(OUT / "prespecified_station_profiles.csv", index=False)
    effects = []
    for seed in range(20):
        path = BASE / f"analyses/leave_one_year_out/seed_{seed:02d}/trends.parquet"
        data = pd.read_parquet(path, columns=["station", "scenario", "pipeline", "error", "n_years"])
        data = data.loc[data.pipeline.isin(["A1", "D2_multiple_imputation"])]
        for scenario, block in data.groupby("scenario"):
            b = block.assign(squared_error=block.error**2).groupby(["station", "pipeline"]).agg(
                rmse=("squared_error", lambda x: np.sqrt(x.mean())), squared_error=("squared_error", "sum"),
                median_used_years=("n_years", "median")).reset_index()
            reference = b.loc[b.pipeline.eq("A1")].set_index("station")
            ranks = reference.squared_error.rank(ascending=False, method="min")
            for station in STATIONS:
                d2 = b.loc[b.station.eq(station) & b.pipeline.eq("D2_multiple_imputation")]
                if station not in reference.index or d2.empty:
                    continue
                old, new = reference.loc[station], d2.iloc[0]
                effects.append({"seed": seed, "station_key": station, "scenario": scenario,
                    "A1_rmse": old.rmse, "D2_rmse": new.rmse,
                    "D2_to_A1_rmse_ratio": new.rmse/old.rmse if old.rmse else np.nan,
                    "A1_squared_error_share": old.squared_error/reference.squared_error.sum(),
                    "A1_error_rank_of_42": ranks.loc[station], "A1_median_used_years": old.median_used_years})
    effects = pd.DataFrame(effects)
    effects.to_csv(OUT / "prespecified_station_trends_per_seed.csv", index=False)
    effects.groupby(["station_key", "scenario"]).median(numeric_only=True).drop(columns="seed").reset_index().to_csv(
        OUT / "prespecified_station_trend_summary.csv", index=False)


def predictions(seed, columns):
    return pd.concat([pd.read_parquet(p, columns=columns) for p in sorted(
        (BASE / f"refits/leave_one_year_out/seed_{seed:02d}").glob("*.parquet"))], ignore_index=True)


def hot_year_examples():
    keys = ["provider", "region", "station_key", "year", "design_family", "peak_overlap", "air_warm_z_mean"]
    source = predictions(0, keys)
    us = source.loc[source.provider.eq("usgs")]
    station_year = us.groupby(["region", "station_key", "year"]).air_warm_z_mean.median().reset_index()
    air = station_year.groupby(["region", "year"]).agg(n_stations=("station_key", "nunique"),
        median_air_anomaly=("air_warm_z_mean", "median")).reset_index()
    air = air.loc[air.n_stations.ge(3) & np.isfinite(air.median_air_anomaly) & air.median_air_anomaly.gt(0)]
    selected = air.sort_values(["region", "median_air_anomaly", "year"], ascending=[True, False, True]).drop_duplicates("region")
    selected.to_csv(OUT / "US_air_selected_years.csv", index=False)
    qualification = pd.DataFrame({"region": sorted(us.region.unique())}).merge(selected, on="region", how="left")
    qualification["qualified"] = qualification.year.notna()
    qualification["unavailable_reason"] = np.where(qualification.qualified, "",
        "no complete-water source year with >=3 physical stations and positive median air anomaly")
    qualification.to_csv(OUT / "US_year_qualification.csv", index=False)
    selection = selected.set_index("region").year.to_dict()
    methods = {"plug_in": "h30__policy", "MOVE1_warm": "h30__move1_warm", "P2": "P2", "D2": "D2"}
    columns = keys + ["eval_truth_h30", "train_h30_q90"] + list(methods.values())
    rows = []
    for seed in range(20):
        data = predictions(seed, columns)
        data = data.loc[data.peak_overlap.ge(.5)].copy()
        data["illustration"] = None
        europe = ~data.provider.eq("usgs") & data.year.isin([2003, 2018, 2022])
        data.loc[europe, "illustration"] = data.loc[europe, "year"].map(lambda y: f"Europe_{y}")
        chosen = data.provider.eq("usgs") & data.year.eq(data.region.map(selection))
        data.loc[chosen, "illustration"] = data.loc[chosen, "region"].map(lambda r: f"{r}_{selection[r]}")
        data = data.loc[data.illustration.notna()]
        for (example, family), block in data.groupby(["illustration", "design_family"]):
            common = np.isfinite(block[list(methods.values()) + ["eval_truth_h30", "train_h30_q90"]]).all(axis=1)
            valid = block.loc[common]
            for method, column in methods.items():
                error = valid[column]-valid.eval_truth_h30
                rows.append({"seed": seed, "illustration": example, "family": family, "method": method,
                    "n_eligible": len(block), "n_common": len(valid), "n_stations": valid.station_key.nunique(),
                    "common_availability": float(common.mean()), "bias": error.mean(), "mae": error.abs().mean(),
                    "failure_rate": float(error.abs().gt(.5).mean()) if len(valid) else np.nan,
                    **event_metrics(valid.eval_truth_h30.gt(valid.train_h30_q90), valid[column].gt(valid.train_h30_q90))})
    result = pd.DataFrame(rows)
    result.to_csv(OUT / "hot_year_examples_per_seed.csv", index=False)
    result.groupby(["illustration", "family", "method"]).agg(
        seeds=("seed", "nunique"), n_common=("n_common", "median"), n_stations=("n_stations", "median"),
        availability=("common_availability", "median"), bias=("bias", "median"), mae=("mae", "median"),
        failure_rate=("failure_rate", "median"), hit_rate=("hit_rate", "median"),
        false_alarm_rate=("false_alarm_rate", "median"), sedi=("sedi", "median")).reset_index().to_csv(
            OUT / "hot_year_examples_summary.csv", index=False)
    return len(selected), len(result)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    outlier_profiles()
    regions, rows = hot_year_examples()
    T.write_json(OUT / "status.json", {"complete": True, "source_seeds": list(range(20)),
        "profile_stations_fixed_by_original_plan": STATIONS, "European_years_fixed_by_original_plan": [2003, 2018, 2022],
        "n_US_regions_with_qualified_warm_year": regions, "n_US_source_regions": len(pd.read_csv(OUT / "US_year_qualification.csv")), "n_example_score_rows": rows,
        "US_year_selection": "largest positive source-seed0 median decision-time air anomaly, >=3 physical stations per region-year; fixed before extracting example errors; unavailable regions retained",
        "scope": "opened archive illustrations, not independent heatwaves or additional refits; station weather support varies; every estimator uses the same finite example cases",
        "new_NZ_water_values_requested": False})
    print(json.dumps({"complete": True, "US_regions": regions, "score_rows": rows}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
