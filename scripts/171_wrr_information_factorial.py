#!/usr/bin/env python3
"""Step 4: donor × right-boundary factorial and air-only recoverers.

Donor-only is scored as a negative control: hiding only the right boundary
must not change its predictions. Methods that actually need the right flank
(linear interpolation) are allowed to fail that cell and fall back to default.
"""

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
    FACTORIAL_RECOVERERS,
    best_simple_by_cell,
    donor_only_right_boundary_delta,
    score_information_cells,
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
NAMES = tuple(FACTORIAL_RECOVERERS)
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
        if not donors:
            continue
        air = air_by_station.get(station)
        features = base_feature_frame(daily, donors=donors, air=air)
        try:
            recoverers = fit_station_recoverers(
                daily,
                target_station=station,
                donors=donors,
                train_mask=train_mask,
                features=features,
                air=air,
                include_external=air is not None,
                include_names=NAMES,
            )
        except ValueError:
            continue
        if "donor_only_ridge" not in recoverers:
            continue
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
                count=4,
            )
            for task in generated:
                start = int(daily.index.get_indexer([pd.Timestamp(task["gap_start"])])[0])
                tasks.append((start, int(task["gap_length"]), "generated"))
        for start, gap_length, source in tasks:
            delta = donor_only_right_boundary_delta(
                recoverers["donor_only_ridge"],
                panel=daily,
                target_station=station,
                donors=donors,
                start=start,
                gap_length=gap_length,
                air=air,
            )
            scored = score_information_cells(
                recoverers,
                panel=daily,
                target_station=station,
                donors=donors,
                start=start,
                gap_length=gap_length,
                default_fill=default_fill,
                air=air,
                names=tuple(name for name in NAMES if name in recoverers),
            )
            for row in scored:
                row.update(
                    {
                        "network_id": network_id,
                        "station_id": station,
                        "gap_length": gap_length,
                        "gap_start": str(daily.index[start].date()),
                        "source": source,
                        "donor_only_right_delta": delta,
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
    parser.add_argument("--networks", default=None, help="comma-separated network ids")
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
                print(f"info-factorial {network_id} rows={0 if frame is None else len(frame)}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({"network_id": network_id, "error": str(exc), "trace": traceback.format_exc()})
                print(f"failed {network_id}: {exc}", flush=True)
    pd.DataFrame(failures).to_csv(STEP4_INFORMATION / "failures.csv", index=False)
    if not frames:
        raise SystemExit("no information-condition rows")
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(STEP4_INFORMATION / "cell_scores.csv", index=False)
    best = best_simple_by_cell(out)
    best.to_csv(STEP4_INFORMATION / "best_simple_by_cell.csv", index=False)
    by_length = best_simple_by_cell(out, extra_keys=("gap_length",))
    by_length.to_csv(STEP4_INFORMATION / "best_simple_by_cell_length.csv", index=False)
    donor = out.loc[out["recoverer"].eq("donor_only_ridge")]
    summary = {
        "n_rows": int(len(out)),
        "n_networks": int(out["network_id"].nunique()),
        "n_stations": int(out["station_id"].nunique()),
        "donor_only_max_right_delta": float(pd.to_numeric(out["donor_only_right_delta"], errors="coerce").max()),
        "donor_only_right_invariance_holds": bool(
            pd.to_numeric(out["donor_only_right_delta"], errors="coerce").fillna(0).max() < 1e-8
        ),
        "mean_mae_benefit_by_cell_recoverer": (
            out.groupby(["cell", "recoverer"])["mae_benefit"].mean().unstack().to_dict()
            if not out.empty
            else {}
        ),
        "best_simple_by_cell": best.to_dict(orient="records") if not best.empty else [],
        "donor_only_supported_without_right": bool(
            donor.loc[donor["cell"].eq("donors_no_right"), "supported"].all()
        )
        if not donor.empty
        else False,
    }
    (STEP4_INFORMATION / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({k: v for k, v in summary.items() if k != "mean_mae_benefit_by_cell_recoverer"}, indent=2))


if __name__ == "__main__":
    main()
