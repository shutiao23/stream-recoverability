#!/usr/bin/env python3
"""Qualify acquired native-day records, then generate supported target cases."""

from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["TR_CONFIG"] = str(ROOT / "configs/wrr_target_recovery_20261022.json")
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[variable] = "1"
import argparse
from datetime import datetime, timezone
import gzip
import json
import time
import pandas as pd
import requests
from joblib import Parallel, delayed
import wrr_tr_common as T
from stream_recoverability.experiments.tr_revision.independent import (
    load_acquisition_plan,
)
from stream_recoverability.experiments.tr_revision.native_temperature import NZST
from stream_recoverability.seeds import position_index

STUDY = ROOT / "results/wrr_review_completion_20261024/independent_study"
AIR_SPEC = {
    "provider": "Open-Meteo ERA5-Land",
    "model": "era5_land",
    "variable": "hourly temperature_2m",
    "aggregation": "24 finite hourly temperatures per fixed NZST day; no interpolation",
}


def native_air_daily(document):
    if document.get("hourly_units", {}).get("temperature_2m") != "°C":
        raise ValueError("Unexpected forcing units")
    hourly = document["hourly"]
    dates = pd.to_datetime(hourly["time"], utc=True).tz_convert(NZST).tz_localize(None)
    values = pd.to_numeric(
        pd.Series(hourly["temperature_2m"]), errors="coerce"
    ).to_numpy()
    series = pd.Series(values, index=dates)
    if series.index.has_duplicates:
        raise ValueError("Duplicate forcing hours")
    group = series.groupby(series.index.normalize())
    return group.mean().where(group.count().eq(24))


def weather_parameters(row, year, end_exclusive):
    end = min(pd.Timestamp(row["to"]), pd.Timestamp(end_exclusive))
    utc_end = end.tz_localize(NZST).tz_convert("UTC").normalize().tz_localize(None)
    return {
        "latitude": float(row.latitude),
        "longitude": float(row.longitude),
        "start_date": f"{year - 1}-12-31",
        "end_date": min(pd.Timestamp(f"{year}-12-31"), utc_end).date().isoformat(),
        "hourly": "temperature_2m",
        "models": "era5_land",
        "timezone": "UTC",
        "temperature_unit": "celsius",
    }


def weather(study, roster, plan):
    if plan.get("air_forcing") != AIR_SPEC:
        raise ValueError("This adapter uses the specified ERA5-Land hourly product")
    folder = study / "acquired/air"
    folder.mkdir(parents=True, exist_ok=True)
    parts = []
    for _, row in roster.iterrows():
        first = pd.Timestamp(row["from"]).year
        last = min(
            pd.Timestamp(row["to"]), pd.Timestamp(plan["observation_end_exclusive"])
        ).year
        for year in range(first, last + 1):
            path = folder / f"{row.station_id}__{year}.json.gz"
            provenance = path.with_suffix(".request.json")
            if path.exists():
                document = json.loads(gzip.decompress(path.read_bytes()))
            else:
                parameters = weather_parameters(
                    row, year, plan["observation_end_exclusive"]
                )
                response = requests.get(
                    "https://archive-api.open-meteo.com/v1/archive",
                    params=parameters,
                    timeout=180,
                )
                response.raise_for_status()
                document = response.json()
                native_air_daily(document)
                path.write_bytes(gzip.compress(response.content))
                T.write_json(
                    provenance,
                    {
                        "url": response.url,
                        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                        "river_temperature_requested": False,
                    },
                )
                time.sleep(0.5)
            daily = native_air_daily(document)
            daily = daily.loc[
                (daily.index.year == year)
                & (
                    daily.index
                    < pd.Timestamp(plan["observation_end_exclusive"]).normalize()
                )
            ]
            parts.append(
                pd.DataFrame(
                    {
                        "date": daily.index,
                        "air_temperature_c": daily.to_numpy(),
                        "station_id": str(row.station_id),
                        "network_id": str(row.network_id),
                    }
                )
            )
    result = pd.concat(parts, ignore_index=True)
    result.to_parquet(study / "acquired/air_forcing.parquet", index=False)


def worker(job, settings, generator, pool, resume):
    module = T.load_script(
        "registered_independent_case_worker", ROOT / "scripts/431_tr_cases.py"
    )
    return module.station_cases(job, settings, generator, pool, resume)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, default=STUDY)
    parser.add_argument("--prepare-cases", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    plan = load_acquisition_plan(args.study)
    if not args.prepare_cases:
        print("Measurement plan loaded.")
        return 0
    receipt_path = args.study / "acquisition_receipt.json"
    receipt = json.loads(receipt_path.read_text())
    roster = pd.read_csv(
        args.study / plan["metadata_roster_file"],
        dtype={
            "station_id": str,
            "station_key": str,
            "network_id": str,
            "independence_group": str,
        },
    )
    if {
        "station_id",
        "station_key",
        "network_id",
        "provider",
        "independence_group",
        "latitude",
        "longitude",
    } - set(roster):
        raise ValueError("Incomplete station and network roster")
    daily = {}
    qualification = []
    for item in receipt["daily_files"]:
        path = args.study / item["file"]
        observations = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        block = observations.water_c
        daily[item["station_key"]] = block
        complete_years = []
        for year in range(block.index.min().year, block.index.max().year):
            dates = pd.date_range(f"{year}-07-01", f"{year + 1}-06-30")
            if block.reindex(dates).notna().all():
                complete_years.append(year)
        qualification.append(
            {
                "station_key": item["station_key"],
                "n_days": len(block),
                "n_quality_complete_days": int(block.notna().sum()),
                "n_raw_samples": int(observations.n_raw.sum()),
                "quality_codes_returned": ";".join(
                    sorted(
                        set(
                            ";".join(
                                observations.quality_codes.fillna("").astype(str)
                            ).split(";")
                        )
                    )
                ),
                "n_complete_hot_years": len(complete_years),
                "eligible": len(complete_years) >= 4,
            }
        )
    table = (
        pd.DataFrame(qualification)
        .set_index("station_key")
        .reindex(roster.station_key)
        .reset_index()
    )
    table["eligible"] = table.eligible.fillna(False)
    table.to_csv(args.study / "observed_qualification.csv", index=False)
    T.write_json(
        args.study / "observed_qualification.json",
        {
            "n_metadata_candidates": len(roster),
            "n_acquired_daily_files": len(daily),
            "n_eligible_stations": int(table.eligible.sum()),
            "accepted_quality_codes": plan["qc_specification"][
                "accepted_quality_codes"
            ],
            "interpretation": "Actual observation-quality qualification; unknown legacy codes are not silently relabeled as approved",
        },
    )
    qualified = roster.loc[
        roster.station_key.isin(table.loc[table.eligible, "station_key"])
    ]
    if qualified.empty:
        columns = [
            "station_key",
            "independence_group",
            "design_family",
            "h30__policy",
            "eval_truth_h30",
            "peak_overlap",
        ]
        pd.DataFrame(columns=columns).to_parquet(
            args.study / "acquired/cases.parquet", index=False
        )
        print(
            f"Qualified 0/{len(roster)} stations: no recoverability errors scored; all qualification outcomes recorded."
        )
        return 0
    weather(args.study, qualified, plan)
    panel_dir = args.study / "acquired/panels"
    panel_dir.mkdir(exist_ok=True)
    jobs = []
    for network, block in qualified.groupby("network_id"):
        panel = pd.concat(
            [
                daily[row.station_key].rename(row.station_id)
                for row in block.itertuples(index=False)
            ],
            axis=1,
        )
        panel.index.name = "date"
        path = panel_dir / (str(network) + ".csv")
        panel.to_csv(path)
        for row in block.itertuples(index=False):
            jobs.append(
                {
                    "network_id": str(network),
                    "station_id": str(row.station_id),
                    "station_key": row.station_key,
                    "provider": row.provider,
                    "independence_group": row.independence_group,
                    "latitude": float(row.latitude),
                    "input_path": str(path),
                    "air_input_path": str(args.study / "acquired/air_forcing.parquet"),
                    "statistic_class": "daily_mean",
                    "regulation_status": "unknown",
                    "region": "registered_greater_wellington",
                    "roster": "independent",
                }
            )
    positions = position_index(
        (f"{job['network_id']}|{job['station_id']}" for job in jobs)
    )
    for job in jobs:
        job["station_index"] = positions[f"{job['network_id']}|{job['station_id']}"]
    settings = json.loads((args.study / "source_case_settings.json").read_text())
    settings["version"] = "review_completion_independent"
    generator = json.loads(
        (args.study / "source_missingness_generator.json").read_text()
    )
    core = T.load_script(
        "registered_independent_case_parent", ROOT / "scripts/431_tr_cases.py"
    )
    pools = core.calendar_pool("independent", jobs)
    results = Parallel(n_jobs=args.workers)(
        (
            delayed(worker)(
                job, settings, generator, core.pool_for(job, pools), args.resume
            )
            for job in jobs
        )
    )
    parts = [pd.read_parquet(r["cache"]) for r in results if r.get("cache")]
    empty_columns = [
        "station_key",
        "independence_group",
        "design_family",
        "h30__policy",
        "eval_truth_h30",
        "peak_overlap",
    ]
    cases = (
        pd.concat(parts, ignore_index=True)
        if parts
        else pd.DataFrame(columns=empty_columns)
    )
    path = args.study / "acquired/cases.parquet"
    cases.to_parquet(path, index=False)
    receipt["source_generator_settings"] = settings
    receipt["station_qualification_and_outputs"] = results
    receipt["n_selected_stations"] = len(roster)
    receipt["n_cases"] = len(cases)
    T.write_json(receipt_path, receipt)
    print(f"Prepared {len(cases)} cases using the source annual model and calibration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
