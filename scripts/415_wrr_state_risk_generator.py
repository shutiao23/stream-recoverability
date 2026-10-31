#!/usr/bin/env python3
"""Replay old Swiss cases under matched air-only and flow-enhanced H30 laws."""
from __future__ import annotations

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from functools import lru_cache
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed

import wrr_r3_common as C
from stream_recoverability.experiments.development_recovery import read_temperature_panel
from stream_recoverability.experiments.v17_fitness.estimators import StationModels
from stream_recoverability.experiments.v19_revision.data import station_air_series
from stream_recoverability.experiments.v19_revision.state_trajectory import sample_crps
from stream_recoverability.experiments.v19_revision.target_risk_laws import (
    RESIDUAL_LAWS, adjust_neural_draws, residual_law_draws, restore_neural_draws, tolerance_features,
)
from stream_recoverability.experiments.v19_revision.trajectory import trajectory_features, window_means
from stream_recoverability.seeds import plain_seed, position_index

CONFIG = C.ROOT / "configs/wrr_state_risk_completion_20261021.json"
OUT = C.READY / "followup_20261021/state_risk_completion"
PROB = OUT.parent / "probability_development"
KEYS = ["network_id", "station_id", "year", "realization_id"]
LAWS = RESIDUAL_LAWS + ("neural_air32", "neural_air32_visible_adjustment")


@lru_cache(maxsize=16)
def neural_chunk(role, start):
    path = PROB / role / "sampling_chunks" / f"case_{start:05d}.npz"
    with np.load(path) as stored:
        return stored["samples"]


def record_distribution(case, law, draws, mask):
    point, truth = float(case.policy_metric), float(case.truth_hottest30)
    visible = ~mask
    if not np.isfinite(draws).all():
        raise ValueError("Nonfinite conditional paths")
    h30 = window_means(draws).max(axis=1)
    record = {key: getattr(case, key) for key in KEYS}
    record.update(independence_group=case.independence_group, law=law, status="available",
                  information_tier="air_and_flow" if law == "seasonal_air_flow_slow" else "available_air",
                  fixed_point=point, truth_h30=truth, n_generated_draws=len(h30), h30_samples_C=h30,
                  n_visible_days=int(visible.sum()), local_hot_threshold_C=case.local_hot_threshold_C,
                  warm_anomaly=bool(case.warm_anomaly), air_available=bool(case.air_available))
    primary = h30[:32]
    record.update(tolerance_features(primary, point))
    for name, value in trajectory_features(draws[:32], mask, point).items():
        record[name + "_CDF"] = value
    for count in (32, 128, 512):
        if count > len(h30):
            continue
        selected = h30[:count]
        lower, upper = np.quantile(selected, [.05, .95])
        record.update({f"median_{count}": float(np.median(selected)), f"CRPS_{count}": sample_crps(selected, truth),
                       f"coverage90_{count}": bool(lower <= truth <= upper), f"width90_{count}": float(upper - lower),
                       f"hot_probability_{count}": float((selected > case.local_hot_threshold_C).mean())})
    return record


def station(job, cases, neural, role):
    output = OUT / "trajectories" / role / "station_cache" / (job["station_id"] + ".parquet")
    # The cache is reused only for the same role, station, laws and case count.
    stamp = output.with_suffix(".inputs.json")
    key = {"role": role, "network_id": job["network_id"], "station_id": job["station_id"],
           "laws": list(LAWS), "cases": len(cases)}
    if output.exists() and stamp.exists() and json.loads(stamp.read_text()) == key:
        return pd.read_parquet(output)
    core = C.load_script("state_risk_recovery_core", C.ROOT / "scripts/351_wrr_representative_recovery.py")
    helper = C.load_script("state_risk_flow_core", C.ROOT / "scripts/362_wrr_process_reference.py")
    panel = read_temperature_panel(job["input_path"]).asfreq("D")
    panel.columns = panel.columns.astype(str)
    target, donors = panel[job["station_id"]], panel.drop(columns=job["station_id"])
    air = station_air_series(Path(job["air_input_path"]), job["network_id"], job["station_id"], panel.index)
    flow_table = helper.forcing_table(C.ROOT / "data/external/wrr_revision_20261020c/hydroshare/MEAS_Qt")
    flow = flow_table[job["station_id"]].reindex(target.index).where(lambda value: value >= 0) if job["station_id"] in flow_table else pd.Series(np.nan, index=target.index)
    neural_of = {tuple(row[key] for key in KEYS): row for row in neural.to_dict("records")}
    rows = []
    for year, annual in cases.groupby("year"):
        allowed = pd.Series(target.index.year != year, index=target.index)
        train_years = [value for value in core.complete_years(target) if value != year]
        index = target.index[target.index.year == year]
        truth = target.reindex(index).to_numpy(dtype=float)
        model = StationModels(target=target, donors=donors, air=air, train_mask=allowed)
        states = []
        for series in (air if air is not None else pd.Series(np.nan, index=target.index), flow):
            climate = series.loc[allowed].groupby(series.loc[allowed].index.month).mean()
            scale = max(float(series.loc[allowed].std()), .1)
            states.append((series - pd.Series(series.index.month, index=series.index).map(climate)).to_numpy(dtype=float) / scale)
        history_states = np.column_stack(states)
        current_states = history_states[target.index.year == year]
        residual_cache = {}
        for case in annual.itertuples(index=False):
            mask = np.zeros(len(index), dtype=bool)
            for run in case.mask_runs.split(";"):
                start, length = map(int, run.split(":"))
                mask[start:start + length] = True
            observed = truth.copy(); observed[mask] = np.nan
            visible_donors = tuple(filter(None, case.visible_donor_ids.split(";")))
            fills = core.predictions(model, observed, index, visible_donors)
            method = case.policy_choice
            center = fills.get(method, np.full(len(index), np.nan))
            completed = observed.copy(); completed[mask] = center[mask]
            if np.isfinite(completed).all() and not np.isclose(window_means(completed).max(), case.policy_metric, rtol=0, atol=1e-9):
                raise RuntimeError("The fixed delivered priority point changed")
            missing_days = tuple(index.dayofyear.to_numpy()[mask]) if method == "linear_interp" else ()
            key = (method, visible_donors if method == "donor_ridge" else (), missing_days)
            if key not in residual_cache:
                residual_cache[key] = core.residual_history(target, donors, air, allowed, train_years, method, visible_donors, missing_days)
            residuals = residual_cache[key]
            seed = plain_seed(case.station_position, int(year), case.realization_position)
            for law in LAWS:
                identity = {key: getattr(case, key) for key in KEYS}
                try:
                    if law in RESIDUAL_LAWS:
                        draws = residual_law_draws(law, observed, center, index, residuals, target.index,
                                                   history_states=history_states, target_states=current_states, seed=seed)
                    else:
                        reference = neural_of[tuple(getattr(case, key) for key in KEYS)]
                        position = int(reference["sample_position"])
                        start = position // 4 * 4
                        normalized = neural_chunk(role, start)[position - start]
                        draws = restore_neural_draws(normalized, observed, reference["mean"], reference["scale"], reference["h30_samples_C"])
                        if law.endswith("visible_adjustment"):
                            draws = adjust_neural_draws(draws, observed, center)
                    if not np.array_equal(draws[:, ~mask], np.broadcast_to(truth[~mask], draws[:, ~mask].shape)):
                        raise RuntimeError("A law changed an observed target value")
                    rows.append(record_distribution(case, law, draws, mask))
                except ValueError as error:
                    # Unsupported local residual support remains a candidate.
                    # A neural cache identity mismatch is a custody error.
                    if "reproduce" in str(error) or "cached neural" in str(error):
                        raise RuntimeError(str(error)) from error
                    rows.append({**identity, "independence_group": case.independence_group, "law": law,
                                 "status": str(error), "fixed_point": case.policy_metric,
                                 "truth_h30": case.truth_hottest30, "h30_samples_C": None, "n_generated_draws": 0,
                                 "information_tier": "air_and_flow" if law == "seasonal_air_flow_slow" else "available_air"})
    result = pd.DataFrame(rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output, index=False)
    C.write_json(stamp, key)
    print(f"[415] {role}/{job['station_id']}: {len(cases)} cases under {len(LAWS)} laws", flush=True)
    return result


def station_worker(*arguments):
    # Import the module in the worker so the cached chunk reader has a real
    # module identity instead of an unpicklable __main__ cache wrapper.
    return importlib.import_module("415_wrr_state_risk_generator").station(*arguments)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["development", "calibration", "test"], required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    role = args.role
    source = C.RUN / "r3_08_external_recovery" / role / "leave_one_year_out/crossed/cofailure_0"
    frame = pd.read_parquet(source / "cases.parquet")
    frame = frame.loc[frame.replicate.eq(0) & frame.design_family.eq("crossed_contiguous") & frame.statistic_class.eq("daily_mean")].copy()
    jobs = json.loads((source / "jobs.json").read_text())["jobs"]
    neural = pd.read_parquet(PROB / role / "cases.parquet").reset_index(drop=True)
    neural["sample_position"] = np.arange(len(neural))
    if set(map(tuple, frame[KEYS].to_numpy())) != set(map(tuple, neural[KEYS].to_numpy())):
        raise RuntimeError("The fixed original candidate pools differ")
    # Residual-law seeds are those of script 378, so its existing laws are reproduced:
    # positions in this case table's sorted station and realization rosters.
    stations, realizations = position_index(frame.station_id), position_index(frame.realization_id)
    frame = frame.assign(station_position=frame.station_id.map(stations), realization_position=frame.realization_id.map(realizations))
    tasks = [(job, frame.loc[frame.station_id.eq(job["station_id"])], neural.loc[neural.station_id.eq(job["station_id"])]) for job in jobs]
    results = Parallel(n_jobs=args.workers, verbose=10)(delayed(station_worker)(job, cases, probability, role) for job, cases, probability in tasks if len(cases))
    result = pd.concat(results, ignore_index=True)
    if len(result) != len(frame) * len(LAWS) or result.duplicated(KEYS + ["law"]).any():
        raise RuntimeError("An original candidate or declared law was lost or duplicated")
    output = OUT / "trajectories" / role
    output.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output / "cases.parquet", index=False)
    result.groupby(["law", "status"]).size().rename("cases").reset_index().to_csv(output / "availability.csv", index=False)
    old = pd.read_parquet(OUT.parent / "trajectory/leave_one_year_out" / role / "cases.parquet")
    old = old.loc[old.n_draws.eq(32) & old.status.eq("available")]
    mapping = {"raw_block14": "raw_block14", "visible_adjustment": "visible_adjustment", "seasonal_state_slow_short": "seasonal_air_flow_slow"}
    replay = []
    for variant, law in mapping.items():
        matched = old.loc[old.variant.eq(variant), KEYS + ["h30_point"]].merge(
            result.loc[result.law.eq(law) & result.status.eq("available"), KEYS + ["median_32"]], on=KEYS, validate="one_to_one")
        difference = float(np.abs(matched.h30_point - matched.median_32).max()) if len(matched) else None
        if len(matched) != int((old.variant == variant).sum()) or difference is None or difference > 1e-9:
            raise RuntimeError("The new supplement did not reproduce an existing residual law")
        replay.append({"law": law, "matched_cases": len(matched), "maximum_point_difference_C": difference})
    pd.DataFrame(replay).to_csv(output / "old_law_replay.csv", index=False)
    print(f"[415] {role}: all {len(frame)} original candidates retained; old-law and neural-cache replay verified", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
