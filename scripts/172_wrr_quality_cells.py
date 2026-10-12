#!/usr/bin/env python3
"""Step 4 leftover: partial-donor and poor-correlation donor cells."""

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
from stream_recoverability.experiments.wrr_revision.features import base_feature_frame  # noqa: E402
from stream_recoverability.experiments.wrr_revision.information import (  # noqa: E402
    best_simple_by_cell,
    quality_kept_sets,
    score_quality_cells,
)
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    FIRST_PLACEMENTS,
    STEP1_UNIVERSE,
    STEP4_INFORMATION,
)
from stream_recoverability.experiments.wrr_revision.recoverers import (  # noqa: E402
    fit_station_recoverers,
)
from stream_recoverability.experiments.wrr_revision.score import (  # noqa: E402
    archived_placements,
    generated_placements,
    load_panel,
)

POWER = ROOT / "results/wrr_revision/forcing/nasa_power_t2m.parquet"
BASE_NAMES = (
    "doy_climatology",
    "smooth_climatology",
    "linear_interp",
    "donor_only_ridge",
    "air_ridge",
)
GAP_LENGTHS = (30, 90, 180)


def _air_map(network_id: str) -> dict[str, pd.Series]:
    if not POWER.exists():
        return {}
    frame = pd.read_parquet(POWER)
    frame["date"] = pd.to_datetime(frame["date"])
    sub = frame.loc[frame["network_id"].astype(str).eq(network_id)]
    out: dict[str, pd.Series] = {}
    for station, group in sub.groupby("station_id"):
        out[str(station)] = group.set_index("date")["air_temperature_c"]
    return out


def _score_network(network_id: str) -> pd.DataFrame:
    panel = load_panel(network_id, "first")
    daily = panel.copy().sort_index().asfreq("D")
    daily.columns = daily.columns.astype(str)
    train_mask, _, eval_years = year_split(daily.index)
    evaluation_mask = pd.Series(daily.index.year.isin(eval_years), index=daily.index)
    air_by_station = _air_map(network_id)
    archived = archived_placements(network_id)
    rows: list[dict[str, object]] = []
    for station in daily.columns:
        donors, _, _ = joint_complete_feature_rosters(
            daily.loc[train_mask],
            target=station,
            donor_candidates=tuple(col for col in daily.columns if col != station),
            meteorology_candidates=(),
            hydraulics_candidates=(),
        )
        donors = tuple(
            donor for donor in donors if int((evaluation_mask & daily[donor].notna()).sum()) >= 60
        )
        if len(donors) < 2:
            continue
        air = air_by_station.get(station)
        features = base_feature_frame(daily, donors=donors, air=air)
        include = tuple(name for name in BASE_NAMES if name != "air_ridge" or air is not None)
        try:
            recoverers = fit_station_recoverers(
                daily,
                target_station=station,
                donors=donors,
                train_mask=train_mask,
                features=features,
                air=air,
                include_external=air is not None,
                include_names=include,
            )
        except ValueError:
            continue
        if "donor_only_ridge" not in recoverers:
            continue
        kept_by_cell = quality_kept_sets(
            daily,
            target_station=station,
            donors=donors,
            train_mask=train_mask,
        )
        subset_by_cell = {}
        for cell, kept in kept_by_cell.items():
            if cell == "all_donors" or not kept:
                continue
            subset_features = base_feature_frame(daily, donors=kept, air=air)
            try:
                subset_fit = fit_station_recoverers(
                    daily,
                    target_station=station,
                    donors=kept,
                    train_mask=train_mask,
                    features=subset_features,
                    air=air,
                    include_external=False,
                    include_names=("donor_only_ridge", "doy_climatology"),
                )
            except ValueError:
                continue
            if "donor_only_ridge" in subset_fit:
                subset_by_cell[cell] = subset_fit["donor_only_ridge"]
        default_fill = np.asarray(recoverers["doy_climatology"].extra["values"], dtype=float)
        station_archive = archived.loc[archived["station_id"].astype(str).eq(station)]
        tasks = []
        for item in station_archive.itertuples(index=False):
            if int(item.gap_length) not in GAP_LENGTHS:
                continue
            start = int(daily.index.get_indexer([pd.Timestamp(item.gap_start)])[0])
            if start < 1 or start + int(item.gap_length) >= len(daily):
                continue
            tasks.append((start, int(item.gap_length), "archived"))
        if not tasks:
            generated = generated_placements(
                daily,
                target_station=station,
                donors=donors,
                evaluation_mask=evaluation_mask,
                gap_lengths=GAP_LENGTHS,
                count=3,
            )
            for task in generated:
                start = int(daily.index.get_indexer([pd.Timestamp(task["gap_start"])])[0])
                tasks.append((start, int(task["gap_length"]), "generated"))
        for start, gap_length, source in tasks:
            scored = score_quality_cells(
                recoverers,
                panel=daily,
                target_station=station,
                donors=donors,
                start=start,
                gap_length=gap_length,
                default_fill=default_fill,
                kept_by_cell={k: v for k, v in kept_by_cell.items() if k != "all_donors" and v},
                air=air,
                subset_by_cell=subset_by_cell,
                names=tuple(name for name in (*BASE_NAMES, "donor_subset_ridge") if name in recoverers or name == "donor_subset_ridge"),
            )
            for row in scored:
                row.update(
                    {
                        "network_id": network_id,
                        "station_id": station,
                        "gap_length": gap_length,
                        "gap_start": str(daily.index[start].date()),
                        "source": source,
                        "n_donors": len(donors),
                        "air_available": air is not None,
                    }
                )
                rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-networks", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--networks", default=None)
    args = parser.parse_args()
    STEP4_INFORMATION.mkdir(parents=True, exist_ok=True)
    roster = pd.read_csv(STEP1_UNIVERSE / "network_roster.csv")
    first = set(pd.read_csv(FIRST_PLACEMENTS, usecols=["network_id"])["network_id"].astype(str))
    ids = sorted(
        roster.loc[
            roster["v16_role"].eq("first_panel_development")
            & roster["in_river_main"]
            & roster["network_id"].isin(first),
            "network_id",
        ]
        .astype(str)
        .tolist()
    )
    if args.networks:
        requested = {item.strip() for item in args.networks.split(",") if item.strip()}
        ids = [item for item in ids if item in requested]
    if args.max_networks is not None:
        ids = ids[: args.max_networks]
    frames = []
    failures = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        fmap = {pool.submit(_score_network, network_id): network_id for network_id in ids}
        for fut in as_completed(fmap):
            network_id = fmap[fut]
            try:
                frame = fut.result()
                if frame is not None and not frame.empty:
                    frames.append(frame)
                print(f"quality {network_id} rows={0 if frame is None else len(frame)}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({"network_id": network_id, "error": str(exc), "trace": traceback.format_exc()})
                print(f"failed {network_id}: {exc}", flush=True)
    pd.DataFrame(failures).to_csv(STEP4_INFORMATION / "quality_failures.csv", index=False)
    if not frames:
        raise SystemExit("no quality-cell rows")
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(STEP4_INFORMATION / "quality_cell_scores.csv", index=False)
    best = best_simple_by_cell(out)
    best.to_csv(STEP4_INFORMATION / "best_simple_by_quality_cell.csv", index=False)
    by_length = best_simple_by_cell(out, extra_keys=("gap_length",))
    by_length.to_csv(STEP4_INFORMATION / "best_simple_by_quality_cell_length.csv", index=False)
    contrast = (
        out.loc[out["recoverer"].isin(["donor_only_ridge", "donor_subset_ridge"]) & out["action"].eq("predict")]
        .groupby(["cell", "recoverer"], as_index=False)
        .agg(n=("mae_benefit", "size"), mae_benefit_mean=("mae_benefit", "mean"))
    )
    contrast.to_csv(STEP4_INFORMATION / "quality_impute_vs_subset.csv", index=False)
    summary = {
        "n_rows": int(len(out)),
        "n_networks": int(out["network_id"].nunique()),
        "n_stations": int(out["station_id"].nunique()),
        "best_simple_by_quality_cell": best.to_dict(orient="records") if not best.empty else [],
        "impute_vs_subset": contrast.to_dict(orient="records"),
    }
    (STEP4_INFORMATION / "quality_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary, indent=2, default=str)[:4000])


if __name__ == "__main__":
    main()
