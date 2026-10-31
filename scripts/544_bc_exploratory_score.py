#!/usr/bin/env python3
"""Score exploratory BC published daily-reference archives with fixed source models and paired masks.

Published daily means can have only 20 hourly measurements and were selected using
air-based checks. They are not strict 24-hour truth or a risk certificate.
"""
from __future__ import annotations
import gzip
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
import joblib
import requests
from joblib import Parallel, delayed
import wrr_tr_common as T
from stream_recoverability.seeds import position_index
from stream_recoverability.experiments.tr_revision.statistics import ensemble_crps, interval_score

ROOT = T.ROOT / "results/wrr_review_response_20261027"
OUT = ROOT / "external_bc_air2stream"
SOURCE = T.ROOT / "results/wrr_review_completion_20261024"


def weather(row, folder):
    site = str(row["station_number"])
    path = folder / (site + ".json.gz")
    try:
        if path.exists():
            document = json.loads(gzip.decompress(path.read_bytes()))
        else:
            params = {"parameters":"T2M", "community":"AG", "latitude":row["latitude"],
                      "longitude":row["longitude"], "start":"20090101", "end":"20231231",
                      "format":"JSON", "time-standard":"LST"}
            response = requests.get("https://power.larc.nasa.gov/api/temporal/daily/point", params=params, timeout=90)
            response.raise_for_status()
            document = response.json()
            path.write_bytes(gzip.compress(response.content))
            (folder / (site + ".request.json")).write_text(json.dumps({"url":response.url,"status":response.status_code}, indent=2) + "\n")
            time.sleep(1)
        forcing = T.load_script("bc_power_parse", T.ROOT / "scripts/501_review_completion_national_forcing.py").parse(document)
        return pd.DataFrame({"date":forcing.index, "air_temperature_c":forcing.to_numpy(),
                             "station_id":site, "network_id":"bc_" + site}), None
    except (requests.RequestException, ValueError, KeyError) as exc:
        return pd.DataFrame(columns=["date", "air_temperature_c", "station_id", "network_id"]), f"{type(exc).__name__}: {exc}"


def run_cases(job, settings, generator, pool):
    core = T.load_script("bc_case_worker", T.ROOT / "scripts/431_tr_cases.py")
    return core.station_cases(job, settings, generator, pool, False)


def main():
    status_path = OUT / "status.json"
    status = json.loads(status_path.read_text())
    roster = pd.read_csv(OUT / "qualification.csv", dtype={"station_number":str})
    eligible = roster.loc[roster.qualified_exploratory_20h_reference.fillna(False)].copy()
    if eligible.empty:
        status["reconstruction_accuracy_evaluated"] = False
        status["accuracy_reason"] = "No station met the four complete published-daily calendar-year criterion"
        status_path.write_text(json.dumps(status, indent=2) + "\n")
        print(status["accuracy_reason"], flush=True)
        return 0
    weather_dir, panels = OUT / "weather", OUT / "panels"
    weather_dir.mkdir(exist_ok=True)
    panels.mkdir(exist_ok=True)
    weather_rows, weather_status = [], []
    for row in eligible.to_dict("records"):
        frame, reason = weather(row, weather_dir)
        weather_rows.append(frame)
        weather_status.append(dict(site=str(row["station_number"]), available=reason is None, reason=reason))
    pd.DataFrame(weather_status).to_csv(OUT / "forcing_qualification.csv", index=False)
    air = pd.concat(weather_rows, ignore_index=True)
    air_path = OUT / "air_forcing.parquet"
    if len(air):
        air.to_parquet(air_path, index=False)
    else:
        air_path = OUT / "no_air_forcing_available.parquet"
    jobs = []
    for row in eligible.to_dict("records"):
        site = str(row["station_number"])
        daily = pd.read_parquet(OUT / "daily" / (site + ".parquet")).set_index("date")
        panel = daily[["temperature_c"]].rename(columns={"temperature_c":site})
        panel.index.name = "date"
        panel_path = panels / (site + ".csv")
        panel.to_csv(panel_path)
        jobs.append(dict(network_id="bc_"+site, station_id=site, station_key="bc_published|"+site,
                         provider="bc_published", independence_group="british_columbia", latitude=float(row["latitude"]),
                         input_path=str(panel_path), air_input_path=str(air_path),
                         statistic_class="published_mean_min20hours", regulation_status=str(row["regulation"]), region="british_columbia",
                         roster="independent"))
    indices = position_index(f"{j['network_id']}|{j['station_id']}" for j in jobs)
    for job in jobs:
        job["station_index"] = indices[f"{job['network_id']}|{job['station_id']}"]
    settings = json.loads((SOURCE / "independent_study/source_case_settings.json").read_text())
    settings["version"] = "review_response_bc_published_daily_external"
    generator = json.loads((SOURCE / "independent_study/source_missingness_generator.json").read_text())
    core = T.load_script("bc_case_parent", T.ROOT / "scripts/431_tr_cases.py")
    pools = core.calendar_pool("independent", jobs)
    results = Parallel(n_jobs=min(4, len(jobs)), verbose=10)(
        delayed(run_cases)(job, settings, generator, core.pool_for(job, pools)) for job in jobs)
    parts = [pd.read_parquet(r["cache"]) for r in results if r.get("cache")]
    if not parts:
        status["accuracy_reason"] = "Qualified sites produced no evaluation cases"
        status_path.write_text(json.dumps(status, indent=2) + "\n")
        return 0
    cases = pd.concat(parts, ignore_index=True)
    refit = T.load_script("bc_source_roles", T.ROOT / "scripts/466_review_completion_refit.py")
    analysis = T.load_script("bc_source_repair", T.ROOT / "scripts/467_review_completion_analysis.py")
    archive = T.load_script("bc_calibration", T.ROOT / "scripts/521_whole_archive.py")
    inference = T.load_script("bc_prediction", T.ROOT / "scripts/495_review_completion_independent_analysis.py")
    scorer = T.load_script("bc_scoring", T.ROOT / "scripts/528_review_response_annual.py")
    source = pd.read_parquet(SOURCE / "cases/leave_one_year_out/seed_00.parquet")
    source = analysis.apply_bridge_repairs(source, 0, "leave_one_year_out")
    bundle = joblib.load(SOURCE / "deployment/global_source_candidate.joblib")
    calibration = archive.classical_calibration(source, "global_source_candidate", refit)
    bundle["offsets"], groups = archive.recalibrate_d2(source, "global_source_candidate", refit, bundle)
    calibration["D2_offsets"] = bundle["offsets"]
    calibration["D2_calibration_groups"] = groups
    T.write_json(OUT / "source_calibration.json", calibration)
    result = inference.classical_predictions(inference.predict(cases, bundle), calibration)
    result.to_parquet(OUT / "predictions.parquet", index=False)
    score_rows, pairs = [], []
    levels = (.05, .10, .25, .50, .75, .90, .95)
    for family in ["calendar", "crossed"]:
        for stratum in ["all", "danger"]:
            block = result.loc[result.design_family.eq(family)]
            if stratum == "danger":
                block = block.loc[block.peak_overlap.ge(.5)]
            truth = block.eval_truth_h30.to_numpy(float)
            lower = block.observed_lower_bound__observed_days.to_numpy(float)
            for method, column, prefix in [("plug_in", "h30__policy", None),
                                            ("D2", "D2", "D2"),
                                            ("stochastic_calibrated", "stochastic_cal_q50", "stochastic_cal")]:
                point = block[column].to_numpy(float)
                valid = np.isfinite(point) & np.isfinite(truth)
                row = dict(family=family, stratum=stratum, estimator=method, n_eligible=len(block),
                           n_available=int(valid.sum()), availability=float(valid.mean()) if len(block) else np.nan,
                           stations=int(block.loc[valid, "station_key"].nunique()))
                if valid.any():
                    error = point[valid] - truth[valid]
                    row |= dict(mae=float(np.mean(abs(error))), bias=float(np.mean(error)),
                                failure_rate=float(np.mean(abs(error) > .5)))
                if prefix:
                    q = block[[f"{prefix}_q{int(100 * level):02d}" for level in levels]].to_numpy(float)
                    valid &= np.isfinite(q).all(axis=1)
                    if valid.any():
                        samples = scorer.quantile_samples(q[valid], lower[valid])
                        lo, hi = q[valid, 0], q[valid, -1]
                        row |= dict(coverage90=float(np.mean((truth[valid]>=lo-1e-8)&(truth[valid]<=hi+1e-8))),
                                    width90=float(np.mean(hi-lo)), crps=float(np.mean(ensemble_crps(samples, truth[valid]))),
                                    interval_score90=float(np.mean(interval_score(lo, hi, truth[valid]))))
                score_rows.append(row)
            if len(block):
                a, b = block.D2.to_numpy(float), block.stochastic_cal_q50.to_numpy(float)
                common = np.isfinite(a) & np.isfinite(b) & np.isfinite(truth)
                if common.any():
                    pairs.append(dict(family=family, stratum=stratum, n_common=int(common.sum()),
                                      n_sites=int(block.loc[common, "station_key"].nunique()),
                                      D2_mae=float(np.mean(abs(a[common]-truth[common]))),
                                      stochastic_mae=float(np.mean(abs(b[common]-truth[common])))))
    pd.DataFrame(score_rows).to_csv(OUT / "annual_scorecard.csv", index=False)
    pd.DataFrame(pairs).to_csv(OUT / "paired_annual.csv", index=False)
    status.update(reconstruction_accuracy_evaluated=True, n_cases=len(result),
                  n_scored_stations=int(result.station_key.nunique()),
                  inference_scope="unregistered BC offline masked-year comparison; published means may include only 20 hours per day; station-selected author QC also used water-air checks; local day/timezone unresolved; stations and climate not independent")
    status_path.write_text(json.dumps(status, indent=2) + "\n")
    print(pd.DataFrame(score_rows).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
