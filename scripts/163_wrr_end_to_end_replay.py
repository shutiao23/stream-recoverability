#!/usr/bin/env python3
"""Step 6: station-year replay with unused budget and zero-action allowed."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_data import (  # noqa: E402
    joint_complete_feature_rosters,
)
from stream_recoverability.experiments.development_recovery import year_split  # noqa: E402
from stream_recoverability.experiments.wrr_revision.benefit import (  # noqa: E402
    attach_component_predictors,
)
from stream_recoverability.experiments.wrr_revision.decision import adopt_mean_threshold  # noqa: E402
from stream_recoverability.experiments.wrr_revision.features import base_feature_frame  # noqa: E402
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_PLACEMENTS,
    RESULTS_ROOT,
)
from stream_recoverability.experiments.wrr_revision.recoverers import (  # noqa: E402
    fit_station_recoverers,
)
from stream_recoverability.experiments.wrr_revision.replay import (  # noqa: E402
    replay_case,
    seasonal_rule_adopt,
    select_mixed_duration_gaps,
    select_nonoverlapping_gaps,
)
from stream_recoverability.experiments.wrr_revision.score import load_panel  # noqa: E402

OUTPUT = RESULTS_ROOT / "step6_replay"
SMALL_XGB = {
    "n_estimators": 80,
    "max_depth": 3,
    "learning_rate": 0.08,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "random_state": 0,
    "n_jobs": 1,
    "objective": "reg:squarederror",
    "verbosity": 0,
}


def _replay_network(network_id: str, recoverer_name: str) -> pd.DataFrame:
    panel = load_panel(network_id, "first")
    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    train_mask, _, eval_years = year_split(daily.index)
    archived = pd.read_csv(FIRST_PLACEMENTS, parse_dates=["gap_start"])
    archived = archived.loc[
        archived["network_id"].astype(str).eq(network_id)
        & archived["information_condition"].eq("B_union_D")
    ].copy()
    if archived.empty:
        return pd.DataFrame()
    hist = archived.loc[archived["gap_start"].dt.year.isin(
        [int(y) for y in str(archived["training_years"].iloc[0]).split("|") if y]
    )]
    # History for benefit is inner placements from P0 if available; else even archive rows.
    p0 = ROOT / "results/v14/p0_differential/placement_predictions_first.csv"
    if p0.exists():
        hist = pd.read_csv(p0, parse_dates=["gap_start"])
        hist = hist.loc[hist["network_id"].astype(str).eq(network_id)]
        if "climatology_mae_deg_c" not in hist.columns and "realized_benefit" in hist.columns:
            # predictors already present; synthesize MAE columns for attach
            hist = hist.copy()
            hist["mae_deg_c"] = 1.0
            hist["climatology_mae_deg_c"] = 1.0 + hist["realized_benefit"]
    rows = []
    for station in daily.columns:
        donors, _, _ = joint_complete_feature_rosters(
            daily.loc[train_mask],
            target=station,
            donor_candidates=tuple(c for c in daily.columns if c != station),
            meteorology_candidates=(),
            hydraulics_candidates=(),
        )
        if not donors:
            continue
        features = base_feature_frame(daily, donors=donors)
        recoverers = fit_station_recoverers(
            daily,
            target_station=station,
            donors=donors,
            train_mask=train_mask,
            features=features,
            include_external=False,
            xgboost_parameters=SMALL_XGB,
        )
        if recoverer_name not in recoverers:
            continue
        default_fill = np.asarray(recoverers["doy_climatology"].extra["values"], dtype=float)
        station_gaps = archived.loc[archived["station_id"].astype(str).eq(station)]
        if station_gaps.empty:
            continue
        station_hist = hist.loc[hist["station_id"].astype(str).eq(str(station))]
        for year in eval_years:
            year_gaps = station_gaps.loc[pd.to_datetime(station_gaps["gap_start"]).dt.year == int(year)]
            if year_gaps.empty:
                continue
            year_gaps = year_gaps.copy()
            year_gaps["year"] = int(year)
            patterns: list[tuple[str, int, pd.DataFrame]] = []
            for gap_length, group in year_gaps.groupby("gap_length"):
                selected = select_nonoverlapping_gaps(group, daily.index)
                if not selected.empty:
                    patterns.append(("duration", int(gap_length), selected))
            mixed_src = year_gaps.loc[year_gaps["gap_length"].isin((30, 90, 180))]
            mixed = select_mixed_duration_gaps(
                mixed_src if not mixed_src.empty else year_gaps,
                daily.index,
            )
            if not mixed.empty:
                patterns.append(("mixed", 0, mixed))
            for pattern, stratum, selected in patterns:
                if station_hist.empty or "mae_deg_c" not in station_hist.columns:
                    pred = pd.Series(0.0, index=selected.index)
                    supported = pd.Series(False, index=selected.index)
                else:
                    attached = attach_component_predictors(station_hist, selected)
                    pred = pd.Series(attached["diff_prediction"].to_numpy(), index=selected.index)
                    supported = pd.Series(
                        attached["seasonal_empirical_supported"].to_numpy(dtype=bool),
                        index=selected.index,
                    )
                adopt = adopt_mean_threshold(pred, tau=0.0, supported=supported)
                seasonal = seasonal_rule_adopt(
                    selected, max_length=30, seasons=("DJF", "MAM", "JJA", "SON")
                )
                chosen = replay_case(
                    daily[station],
                    default_fill=default_fill,
                    recoverers=recoverers,
                    features=features,
                    gaps=selected,
                    predicted_benefit=pred,
                    adopt=adopt,
                    chosen_recoverer=recoverer_name,
                )
                seasonal_replay = replay_case(
                    daily[station],
                    default_fill=default_fill,
                    recoverers=recoverers,
                    features=features,
                    gaps=selected,
                    predicted_benefit=pred,
                    adopt=seasonal,
                    chosen_recoverer=recoverer_name,
                )
                all_on = replay_case(
                    daily[station],
                    default_fill=default_fill,
                    recoverers=recoverers,
                    features=features,
                    gaps=selected,
                    predicted_benefit=pred,
                    adopt=pd.Series(True, index=selected.index),
                    chosen_recoverer=recoverer_name,
                )
                rows.append(
                    {
                        "network_id": network_id,
                        "station_id": station,
                        "year": int(year),
                        "pattern": pattern,
                        "stratum_gap_length": int(stratum),
                        "recoverer": recoverer_name,
                        **{f"rule_{k}": v for k, v in chosen.items()},
                        "seasonal_hottest_30_benefit": seasonal_replay["hottest_30_benefit"],
                        "all_reconstruct_hottest_30_benefit": all_on["hottest_30_benefit"],
                        "all_default_hottest_30_benefit": 0.0,
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-networks", type=int, default=12)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--recoverer", default="xgb_longblock_boundary")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ids = sorted(
        pd.read_csv(FIRST_PLACEMENTS, usecols=["network_id"])["network_id"].astype(str).unique()
    )[: args.max_networks]
    frames = []
    failures = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        fmap = {pool.submit(_replay_network, n, args.recoverer): n for n in ids}
        for fut in as_completed(fmap):
            network_id = fmap[fut]
            try:
                frame = fut.result()
                if frame is not None and not frame.empty:
                    frames.append(frame)
                print(f"replay {network_id} rows={0 if frame is None else len(frame)}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({"network_id": network_id, "error": str(exc), "trace": traceback.format_exc()})
                print(f"failed {network_id}: {exc}", flush=True)
    if not frames:
        raise SystemExit("no replay rows")
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUTPUT / "station_year_replay.csv", index=False)
    pd.DataFrame(failures).to_csv(OUTPUT / "failures.csv", index=False)
    network = (
        out.groupby("network_id", as_index=False)
        .agg(
            rule_hottest_30=("rule_hottest_30_benefit", "mean"),
            seasonal=("seasonal_hottest_30_benefit", "mean"),
            all_reconstruct=("all_reconstruct_hottest_30_benefit", "mean"),
            all_default=("all_default_hottest_30_benefit", "mean"),
            adopt_rate=("rule_adopt_rate", "mean"),
            n_cases=("year", "size"),
        )
    )
    network.to_csv(OUTPUT / "network_replay.csv", index=False)
    pattern = (
        out.groupby(["pattern", "stratum_gap_length"], as_index=False)
        .agg(
            n_cases=("year", "size"),
            n_networks=("network_id", "nunique"),
            rule_hottest_30=("rule_hottest_30_benefit", "mean"),
            seasonal=("seasonal_hottest_30_benefit", "mean"),
            all_reconstruct=("all_reconstruct_hottest_30_benefit", "mean"),
            adopt_rate=("rule_adopt_rate", "mean"),
        )
    )
    pattern.to_csv(OUTPUT / "pattern_replay.csv", index=False)
    rule_mean = float(out["rule_hottest_30_benefit"].mean())
    seasonal_mean = float(out["seasonal_hottest_30_benefit"].mean())
    all_on_mean = float(out["all_reconstruct_hottest_30_benefit"].mean())
    adopt_rate = float(out["rule_adopt_rate"].mean()) if "rule_adopt_rate" in out.columns else float("nan")
    summary = {
        "n_cases": int(len(out)),
        "n_networks": int(out["network_id"].nunique()),
        "mean_rule_hottest_30": rule_mean,
        "mean_seasonal_hottest_30": seasonal_mean,
        "mean_all_reconstruct_hottest_30": all_on_mean,
        "mean_all_default_hottest_30": 0.0,
        "mean_adopt_rate": adopt_rate,
        "beats_all_default": bool(rule_mean > 0.0),
        "beats_seasonal": bool(rule_mean > seasonal_mean),
        "n_mixed_cases": int((out["pattern"] == "mixed").sum()) if "pattern" in out.columns else 0,
        "recoverer": args.recoverer,
        "n_failures": int(len(failures)),
    }
    (OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
