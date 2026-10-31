#!/usr/bin/env python3
"""Evaluate an experimental slow/short residual model on opened external cases."""
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
from stream_recoverability.experiments.v17_fitness.estimators import StationModels
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.v19_revision.state_trajectory import state_conditioned_draws, sample_crps
from stream_recoverability.experiments.v19_revision.trajectory import conditional_trajectories, historical_location_adjustment, window_means, trajectory_features
from stream_recoverability.seeds import plain_seed, position_index

OUT = C.READY / "followup_20261021/trajectory"
RAW = C.ROOT / "data/external/wrr_revision_20261020c/hydroshare"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def station(job, cases, protocol, role):
    core = C.load_script("followup_state_core", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    helper = C.load_script("followup_state_flow", C.ROOT / "scripts/362_wrr_process_reference.py")
    flow_table = helper.forcing_table(RAW / "MEAS_Qt")
    panel = read_temperature_panel(job["input_path"]).asfreq("D")
    panel.columns = panel.columns.astype(str)
    target, donors = panel[job["station_id"]], panel.drop(columns=job["station_id"])
    air = station_air_series(Path(job["air_input_path"]), job["network_id"], job["station_id"], panel.index)
    flow = flow_table[job["station_id"]].reindex(target.index).where(lambda x: x >= 0) if job["station_id"] in flow_table else pd.Series(np.nan, index=target.index)
    rows = []
    for year, annual in cases.groupby("year"):
        allowed = pd.Series(target.index.year < year if protocol == "strictly_prior_years" else target.index.year != year, index=target.index)
        train_years = [value for value in core.complete_years(target) if (value < year if protocol == "strictly_prior_years" else value != year)]
        index = target.index[target.index.year == year]
        truth = target.reindex(index).to_numpy(dtype=float)
        model = StationModels(target=target, donors=donors, air=air, train_mask=allowed)
        # Forcing anomalies are computed with permitted training history only.
        states = []
        for series in (air if air is not None else pd.Series(np.nan, index=target.index), flow):
            climate = series.loc[allowed].groupby(series.loc[allowed].index.month).mean()
            scale = max(float(series.loc[allowed].std()), 0.1)
            states.append((series - pd.Series(series.index.month, index=series.index).map(climate)).to_numpy(dtype=float) / scale)
        history_states = np.column_stack(states)
        current_states = history_states[target.index.year == year]
        q20 = flow.loc[allowed].groupby(flow.loc[allowed].index.month).quantile(0.2)
        current_q = flow.reindex(index).to_numpy(dtype=float)
        current_q20 = pd.Series(index.month).map(q20).to_numpy(dtype=float)
        residual_cache = {}
        for case in annual.itertuples(index=False):
            mask = np.zeros(len(index), dtype=bool)
            for run in case.mask_runs.split(";"):
                start, length = map(int, run.split(":"))
                mask[start:start + length] = True
            observed = truth.copy()
            observed[mask] = np.nan
            method = case.policy_choice
            visible_donors = tuple(filter(None, case.visible_donor_ids.split(";")))
            fills = core.predictions(model, observed, index, visible_donors)
            center = fills[method]
            missing_days = tuple(index.dayofyear.to_numpy()[mask]) if method == "linear_interp" else ()
            key = (method, visible_donors if method == "donor_ridge" else (), missing_days)
            if key not in residual_cache:
                residual_cache[key] = core.residual_history(target, donors, air, allowed, train_years, method, visible_donors, missing_days)
            residuals = residual_cache[key]
            random_seed = plain_seed(case.station_position, int(year), case.realization_position)
            for variant in ("raw_block14", "visible_adjustment", "seasonal_state_slow_short"):
                try:
                    if variant == "seasonal_state_slow_short":
                        samples = state_conditioned_draws(observed, center, index, residuals, target.index, seed=random_seed,
                                                          history_states=history_states, target_states=current_states)
                    else:
                        adjustment = historical_location_adjustment(observed, center) if variant == "visible_adjustment" else 0
                        samples = conditional_trajectories(observed, center, residuals, seed=random_seed, n_draws=512, location_adjustment=adjustment)
                    if not np.array_equal(samples[:, ~mask], np.broadcast_to(truth[~mask], samples[:, ~mask].shape)):
                        raise RuntimeError("A residual scenario changed an observed value")
                    h30 = window_means(samples).max(axis=1)
                    for n_draws in (32, 128, 512):
                        selected = h30[:n_draws]
                        lower, upper = np.quantile(selected, [0.05, 0.95])
                        point = float(np.median(selected))
                        row = {"role": role, "protocol": protocol, "network_id": case.network_id, "station_id": case.station_id,
                               "independence_group": case.independence_group, "year": int(year), "realization_id": case.realization_id,
                               "variant": variant, "n_draws": n_draws, "status": "available", "truth_h30": case.truth_hottest30,
                               "h30_point": point, "signed_error_C": point - case.truth_hottest30, "absolute_error_C": abs(point - case.truth_hottest30),
                               "covered90": lower <= case.truth_hottest30 <= upper, "interval_width_C": upper - lower,
                               "lower_C": lower, "upper_C": upper, "crps_C": sample_crps(selected, case.truth_hottest30),
                               "warm_anomaly": case.warm_anomaly, "gap_length": case.longest_run,
                               "flow_coverage": np.isfinite(current_q[mask]).mean(),
                               "gap_lowflow_fraction": float(((current_q <= current_q20) & mask).sum() / np.isfinite(current_q[mask]).sum()) if np.isfinite(current_q[mask]).any() else np.nan}
                        for name, threshold in (("local", case.local_hot_threshold_C), ("18", 18), ("20", 20)):
                            probability = float((selected > threshold).mean())
                            row[f"hot_probability_{name}"] = probability
                            row[f"hot_truth_{name}"] = case.truth_hottest30 > threshold
                            row[f"brier_{name}"] = (probability - row[f"hot_truth_{name}"]) ** 2
                        if n_draws == 128:
                            row.update(trajectory_features(samples[:n_draws], mask, point))
                        rows.append(row)
                except ValueError as error:
                    rows.append({"role": role, "protocol": protocol, "network_id": case.network_id, "station_id": case.station_id,
                                 "independence_group": case.independence_group, "year": int(year), "realization_id": case.realization_id,
                                 "variant": variant, "n_draws": 0, "status": str(error)})
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["development", "calibration", "test"], required=True)
    parser.add_argument("--protocol", choices=["leave_one_year_out", "strictly_prior_years"], default="leave_one_year_out")
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    source = C.RUN / "r3_08_external_recovery" / args.role / args.protocol / "crossed/cofailure_0"
    frame = pd.read_parquet(source / "cases.parquet")
    frame = frame.loc[frame.replicate.eq(0) & frame.design_family.eq("crossed_contiguous") & frame.statistic_class.eq("daily_mean")]
    if args.protocol == "strictly_prior_years":
        frame = frame.loc[frame.year.between(2019, 2022)]
    # Scenario seeds: positions in this case table's sorted station and realization rosters.
    stations, realizations = position_index(frame.station_id), position_index(frame.realization_id)
    frame = frame.assign(station_position=frame.station_id.map(stations), realization_position=frame.realization_id.map(realizations))
    jobs = json.loads((source / "jobs.json").read_text())["jobs"]
    selected = [(job, frame.loc[frame.station_id.eq(job["station_id"])]) for job in jobs]
    selected = [(job, block) for job, block in selected if len(block)]
    gathered = Parallel(n_jobs=args.workers, verbose=10)(delayed(station)(job, block, args.protocol, args.role) for job, block in selected)
    result = pd.concat(gathered, ignore_index=True)
    # Mixed unavailable rows make booleans object-typed; numeric aggregation is explicit.
    for name in ("covered90", "warm_anomaly", "hot_truth_local", "hot_truth_18", "hot_truth_20"):
        result[name] = result[name].astype(float)
    output = OUT / args.protocol / args.role
    output.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output / "cases.parquet", index=False)
    result.groupby(["variant", "n_draws", "status"]).size().to_csv(output / "availability.csv")
    result.loc[result.status.eq("available")].groupby(["variant", "n_draws"]).agg(n=("year", "size"), groups=("independence_group", "nunique"),
        mae_C=("absolute_error_C", "mean"), bias_C=("signed_error_C", "mean"), coverage90=("covered90", "mean"),
        width_C=("interval_width_C", "mean"), crps_C=("crps_C", "mean"), brier_local=("brier_local", "mean")).to_csv(output / "summary.csv")
    available = result.loc[result.status.eq("available") & result.n_draws.eq(128)].copy()
    available["condition"] = np.where(available.gap_lowflow_fraction >= 0.5, "majority_lowflow_gap", np.where(available.flow_coverage.eq(1), "not_majority_lowflow_gap", "flow_incomplete"))
    available.groupby(["variant", "warm_anomaly", "condition"]).agg(n=("year", "size"), groups=("independence_group", "nunique"), coverage90=("covered90", "mean"), bias_C=("signed_error_C", "mean"), mae_C=("absolute_error_C", "mean"), crps_C=("crps_C", "mean"), brier_local=("brier_local", "mean")).to_csv(output / "conditional_quality.csv")
    available["probability_bin"] = np.minimum((available.hot_probability_local * 10).astype(int), 9)
    available.groupby(["variant", "probability_bin"]).agg(n=("year", "size"), mean_probability=("hot_probability_local", "mean"), observed_fraction=("hot_truth_local", "mean")).to_csv(output / "probability_reliability.csv")
    C.write_json(output / "run_record.json", run_record({"cases": source / "cases.parquet", "generator": C.ROOT / "src/stream_recoverability/experiments/v19_revision/state_trajectory.py"}, supplementary_development=True, new_confirmation=False, history_excludes_target=True, current_hidden_water_used_as_model_input=False))
    print(f"[378] {args.role}: {len(result)} trajectory evaluations", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
