#!/usr/bin/env python3
"""Step 5: design ablations and realistic fault geometry on first-panel networks."""

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
from stream_recoverability.experiments.wrr_revision.failures import (  # noqa: E402
    heatwave_mask,
    hide_donors,
    natural_gap_geometry,
    right_boundary_missing_fill,
    transplant_geometry,
)
from stream_recoverability.experiments.wrr_revision.features import base_feature_frame  # noqa: E402
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_PLACEMENTS,
    RESULTS_ROOT,
)
from stream_recoverability.experiments.wrr_revision.recoverers import (  # noqa: E402
    fit_station_recoverers,
)
from stream_recoverability.experiments.wrr_revision.score import load_panel, score_gap  # noqa: E402
from stream_recoverability.experiments.wrr_revision.thermal import daily_mae  # noqa: E402

OUTPUT = RESULTS_ROOT / "step5_failures"
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


def _score_faults(network_id: str) -> pd.DataFrame:
    panel = load_panel(network_id, "first")
    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    train_mask, _, _ = year_split(daily.index)
    archived = pd.read_csv(FIRST_PLACEMENTS, parse_dates=["gap_start"])
    archived = archived.loc[
        archived["network_id"].astype(str).eq(network_id)
        & archived["information_condition"].eq("B_union_D")
        & archived["gap_length"].isin((30, 90, 180))
    ]
    rows: list[dict[str, object]] = []
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
        default_fill = np.asarray(recoverers["doy_climatology"].extra["values"], dtype=float)
        station_rows = archived.loc[archived["station_id"].astype(str).eq(station)]
        heat = heatwave_mask(daily[station], train_mask)
        geometry = natural_gap_geometry(daily.loc[train_mask, station])
        transplanted = transplant_geometry(
            daily.index[~train_mask],
            geometry,
            position_index=daily.index,
        )
        tasks = []
        n = len(daily)
        for item in station_rows.itertuples(index=False):
            start = int(daily.index.get_indexer([pd.Timestamp(item.gap_start)])[0])
            if start < 1 or start + int(item.gap_length) > n:
                continue
            tasks.append((start, int(item.gap_length), "archived", int(item.placement)))
        for i, (start, length) in enumerate(transplanted[:8]):
            if start < 1 or start + int(length) > n:
                continue
            tasks.append((int(start), int(length), "transplanted", i))
        for start, gap_length, source, placement in tasks:
            truth = daily[station].iloc[start : start + gap_length].to_numpy(dtype=float)
            if len(truth) != int(gap_length) or not np.isfinite(truth).all():
                continue
            overlap_heat = float(heat.iloc[start : start + gap_length].mean())
            persist = right_boundary_missing_fill(daily[station], start, gap_length)
            persist_mae = daily_mae(truth, persist)
            hidden = hide_donors(daily, donors=donors, start=start, gap_length=gap_length)
            hidden_features = base_feature_frame(hidden, donors=donors)
            for recoverer_name in (
                "xgb_neighbor_boundary",
                "xgb_longblock_boundary",
                "donor_only_ridge",
                "linear_interp",
            ):
                if recoverer_name not in recoverers:
                    continue
                rec = recoverers[recoverer_name]
                baseline = score_gap(
                    rec,
                    features=features,
                    target=daily[station],
                    start=start,
                    gap_length=gap_length,
                    default_fill=default_fill,
                )
                if baseline is None:
                    continue
                donor_sync = score_gap(
                    rec,
                    features=hidden_features,
                    target=daily[station],
                    start=start,
                    gap_length=gap_length,
                    default_fill=default_fill,
                )
                rows.append(
                    {
                        "network_id": network_id,
                        "station_id": station,
                        "recoverer": recoverer_name,
                        "gap_length": gap_length,
                        "placement": placement,
                        "source": source,
                        "mae_benefit": baseline["mae_benefit"],
                        "hottest_30_benefit": baseline["hottest_30_benefit"],
                        "donor_sync_mae_benefit": (
                            None if donor_sync is None else donor_sync["mae_benefit"]
                        ),
                        "donor_sync_hottest_30_benefit": (
                            None if donor_sync is None else donor_sync["hottest_30_benefit"]
                        ),
                        "missing_right_persistence_mae": persist_mae,
                        "missing_right_benefit_vs_clim": baseline["climatology_mae_deg_c"]
                        - persist_mae,
                        "heatwave_fraction": overlap_heat,
                    }
                )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-networks", type=int, default=12)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ids = sorted(
        pd.read_csv(FIRST_PLACEMENTS, usecols=["network_id"])["network_id"].astype(str).unique()
    )[: args.max_networks]
    frames = []
    failures = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        fmap = {pool.submit(_score_faults, n): n for n in ids}
        for fut in as_completed(fmap):
            network_id = fmap[fut]
            try:
                frame = fut.result()
                if frame is not None and not frame.empty:
                    frames.append(frame)
                print(f"faults {network_id} rows={0 if frame is None else len(frame)}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({"network_id": network_id, "error": str(exc), "trace": traceback.format_exc()})
                print(f"failed {network_id}: {exc}", flush=True)
    if not frames:
        raise SystemExit("no fault scores")
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(OUTPUT / "fault_scores.csv", index=False)
    summary = (
        out.groupby(["recoverer", "source", "gap_length"], as_index=False)
        .agg(
            n=("mae_benefit", "size"),
            mae_benefit=("mae_benefit", "mean"),
            hottest_30_benefit=("hottest_30_benefit", "mean"),
            donor_sync=("donor_sync_mae_benefit", "mean"),
            donor_sync_hottest_30=("donor_sync_hottest_30_benefit", "mean"),
            missing_right=("missing_right_benefit_vs_clim", "mean"),
            heatwave_frac=("heatwave_fraction", "mean"),
        )
    )
    summary.to_csv(OUTPUT / "fault_summary.csv", index=False)
    pd.DataFrame(failures).to_csv(OUTPUT / "failures.csv", index=False)
    (OUTPUT / "summary.json").write_text(
        json.dumps({"n_rows": int(len(out)), "n_networks": int(out["network_id"].nunique())}, indent=2)
    )


if __name__ == "__main__":
    main()
