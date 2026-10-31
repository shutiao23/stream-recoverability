#!/usr/bin/env python3
"""Common-denominator and truth-assisted nested-gap mechanism experiments."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.estimators import StationModels, usable_donors
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.v19_revision.trajectory import window_means

OUT = C.READY / "followup_20261021/mechanism"
KEYS = ["independence_group", "network_id", "station_id", "year"]
METHODS = ("doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge")


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def nested_station(job, eligible):
    core = C.load_script("followup_nested_core", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    panel = read_temperature_panel(job["input_path"]).asfreq("D")
    panel.columns = panel.columns.astype(str)
    target, donors = panel[job["station_id"]], panel.drop(columns=job["station_id"])
    air = station_air_series(C.ROOT / "data/interim/v18_air_forcing.parquet", job["network_id"], job["station_id"], panel.index)
    rows = []
    for year in eligible:
        allowed = pd.Series(target.index.year < year if job["fit_protocol"] == "strictly_prior_years" else target.index.year != year, index=target.index)
        index = target.index[target.index.year == year]
        truth = target.reindex(index).to_numpy(dtype=float)
        truth_windows = window_means(truth)
        true_start = int(np.argmax(truth_windows))
        model = StationModels(target=target, donors=donors, air=air, train_mask=allowed)
        # Choose a nonoverlapping control by a fixed temporal displacement, never its outcome.
        controls = [start for start in (true_start - 90, true_start + 90) if 0 <= start and start + 30 <= len(truth)]
        for direction in ("left", "balanced", "right"):
            starts = {length: true_start - (length - 30 if direction == "left" else (length - 30) // 2 if direction == "balanced" else 0) for length in (30, 60, 90)}
            feasible = min(starts.values()) >= 0 and max(start + length for length, start in starts.items()) <= len(truth)
            if not feasible or not controls:
                continue
            designs = [(f"nested_{length}", starts[length], length) for length in (30, 60, 90)] + [("outside_30", controls[0], 30)]
            previous = None
            for label, start, length in designs:
                mask = np.zeros(len(truth), dtype=bool)
                mask[start:start + length] = True
                if label.startswith("nested"):
                    if not mask[true_start:true_start + 30].all() or (previous is not None and (previous & ~mask).any()):
                        raise RuntimeError("Nested gap lost hidden true support")
                    previous = mask
                observed = truth.copy()
                observed[mask] = np.nan
                visible = usable_donors(donors, index, mask)
                fills = core.predictions(model, observed, index, visible)
                for method, fill in fills.items():
                    completed = observed.copy()
                    completed[mask] = fill[mask]
                    point = float(window_means(completed).max()) if np.isfinite(completed).all() else np.nan
                    rows.append({**{key: job[key] for key in KEYS if key != "year"}, "year": int(year), "direction": direction,
                                 "design": label, "gap_start": start, "gap_length": length, "left_boundary_distance": start,
                                 "right_boundary_distance": len(truth) - start - length, "true_hidden_fraction": float(mask[true_start:true_start + 30].mean()),
                                 "method": method, "absolute_error_C": abs(point - truth_windows.max())})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    output = OUT / args.protocol
    output.mkdir(parents=True, exist_ok=True)
    core = C.load_script("followup_mechanism_source", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    evaluate = C.load_script("followup_mechanism_evaluation", C.ROOT / "scripts/355_wrr_mechanism_summary.py")
    source = C.source_cases(args.protocol, "controlled")
    frame = pd.read_parquet(source)
    frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
    group_map = pd.read_csv(C.RUN / "r3_06_independence_risk/complete_network_independence.csv").set_index("network_id").independence_group
    frame = frame.assign(independence_group=frame.network_id.map(group_map))
    crossed = frame.loc[frame.design_family.eq("crossed_contiguous")]
    full = crossed.loc[crossed.true_peak_hidden_fraction >= 0.999]
    length = full.groupby(KEYS + ["total_missing"]).abserr_smooth_climatology.mean().unstack("total_missing").dropna(subset=[30, 90])
    common = length.index.to_frame(index=False)
    matched = frame.merge(common, on=KEYS, validate="many_to_one")
    evaluate.position_contrasts(matched, 2000).to_csv(output / "common_population_position.csv", index=False)
    a, b = evaluate.length_and_fragmentation(matched, 2000)
    a.to_csv(output / "common_population_length.csv", index=False)
    b.to_csv(output / "common_population_fragmentation.csv", index=False)
    population = []
    for name, block in (("original", frame), ("common_length_feasible", matched)):
        annual = block.drop_duplicates(KEYS)
        population.append({"population": name, "n_station_years": len(annual[["station_id", "year"]].drop_duplicates()),
                           "n_network_target_years": len(annual), "n_groups": annual.independence_group.nunique(),
                           "n_stations": annual.station_id.nunique(), "mean_history_years": annual.n_complete_years.mean(),
                           "mean_truth_h30_C": annual.truth_hottest30.mean(), "warm_anomaly_share": annual.warm_anomaly.mean()})
    pd.DataFrame(population).to_csv(output / "population_comparison.csv", index=False)
    destination = output / "nested_cases.parquet"
    jobs, _ = core.source_jobs(args.protocol, False)
    annual = frame[KEYS].drop_duplicates()
    selected = []
    for job in jobs:
        years = annual.loc[annual.network_id.eq(job["network_id"]) & annual.station_id.eq(job["station_id"]), "year"].tolist()
        if years:
            job["independence_group"] = group_map[job["network_id"]]
            selected.append((job, years))
    if not destination.exists():
        results = Parallel(n_jobs=args.workers, verbose=10)(delayed(nested_station)(job, years) for job, years in selected)
        nested = pd.concat(results, ignore_index=True)
        nested.to_parquet(destination, index=False)
    else:
        nested = pd.read_parquet(destination)
    rows = []
    for method in METHODS:
        for direction in ("left", "balanced", "right"):
            paired = nested.loc[nested.method.eq(method) & nested.direction.eq(direction)].pivot(index=KEYS, columns="design", values="absolute_error_C").dropna()
            for label, left, right in (("length_90_minus_30_full_support", "nested_90", "nested_30"), ("position_30_full_minus_none", "nested_30", "outside_30")):
                diff = paired.index.to_frame(index=False)
                diff["difference"] = (paired[left] - paired[right]).to_numpy()
                rows.append({"method": method, "direction": direction, "contrast": label,
                             **evaluate.cluster_mean(diff, "difference", 2000, 20261021)})
    pd.DataFrame(rows).to_csv(output / "nested_contrasts.csv", index=False)
    C.write_json(output / "run_record.json", run_record({"controlled_cases": source, "core": Path(core.__file__)}, truth_assisted_mechanism=True, deployment_peak_oracle=False, original_common_subset_station_years=len(common[["station_id", "year"]].drop_duplicates())))
    print(f"[376] {args.protocol}: {len(common)} common years; {len(nested)} nested method cases", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
