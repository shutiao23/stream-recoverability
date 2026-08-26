#!/usr/bin/env python3
"""Download public daily temperature for rivers used to build the method.

Does not download rivers saved for the last check. Does not write a paper
headline. Writes overlap, real missing blocks, and a first leave-one-river
score if at least three rivers have enough overlapping years.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.network_catalog import load_network_catalog
from stream_recoverability.data.nwis_temperature import nwis_daily_temperature
from stream_recoverability.data.public_temperature import (
    missing_gap_catalog,
    overlap_report,
    river_wide_panel,
)
from stream_recoverability.experiments.real_river_checks import (
    leave_one_river_out,
    real_river_sensor_check,
    score_rivers,
    simple_baseline_errors,
)

OUTPUT = ROOT / "results/framework/public_rivers"
CACHE = ROOT / "data/public_rivers"
START = "2000-01-01"
END = "2024-12-31"
BUILD_USES = {"build", "development", "lock", "validation"}
# Last-check sites. Do not download even if a name-cluster mixed them in.
DO_NOT_DOWNLOAD = {
    "09379500",
    "09380000",
    "09402500",
    "09404120",
    "09404200",
    "12399500",
    "12424000",
    "14105700",
    "14127100",
    "14128870",
    "03216600",
    "03277200",
    "03294500",
    "03303280",
    "03612500",
    "14050000",
    "14064500",
    "14070500",
    "14076500",
    "14092500",
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    catalog = load_network_catalog()
    catalog_sites = ROOT / "results/framework/public_catalog/usgs_station_catalog.csv"
    usable = {}
    if catalog_sites.is_file():
        stations = pd.read_csv(catalog_sites, dtype={"site_id": str})
        good = stations.loc[
            stations["has_daily_temperature"].fillna(False)
            & stations["span_years"].ge(8)
        ]
        for network_id, group in good.groupby("network_id"):
            usable[str(network_id)] = [str(item) for item in group["site_id"]]
    overlap_rows = []
    panels = {}
    gap_frames = []
    for network in catalog["networks"]:
        use = str(network.get("use") or network.get("split_role"))
        network_id = str(network["network_id"])
        if use not in BUILD_USES:
            continue
        site_ids = usable.get(network_id)
        if not site_ids:
            site_ids = [
                str(item)
                for item in network.get("candidate_station_ids") or []
                if str(item).isdigit()
            ]
        site_ids = [item for item in site_ids if item not in DO_NOT_DOWNLOAD]
        frames = []
        for site_id in site_ids:
            try:
                frames.append(
                    nwis_daily_temperature(
                        site_id, START, END, cache_dir=CACHE
                    )
                )
            except Exception as error:
                print(f"{network_id} {site_id}: {error}")
            time.sleep(0.8)
        wide = river_wide_panel(frames)
        if wide.empty:
            overlap_rows.append(
                {"network_id": network_id, "name": network.get("display_name"), "ok": False}
            )
            continue
        wide.to_csv(OUTPUT / f"{network_id}_daily_wide.csv")
        report = overlap_report(wide, min_stations=min(4, wide.shape[1]))
        report.update(
            {
                "network_id": network_id,
                "name": network.get("display_name"),
                "use": use,
                "ok": report["complete_enough"],
            }
        )
        overlap_rows.append(report)
        gaps = missing_gap_catalog(wide)
        if not gaps.empty:
            gaps["network_id"] = network_id
            gap_frames.append(gaps)
        if report["days_with_min_stations"] >= 365 * 4 and wide.shape[1] >= 3:
            # Keep only days with at least two stations so donor fill is defined.
            keep = wide.notna().sum(axis=1).ge(2)
            panels[network_id] = wide.loc[keep]
    overlap = pd.DataFrame(overlap_rows)
    overlap.to_csv(OUTPUT / "overlap.csv", index=False)
    if gap_frames:
        pd.concat(gap_frames, ignore_index=True).to_csv(
            OUTPUT / "real_missing_blocks.csv", index=False
        )
    scores = score_rivers(panels) if panels else pd.DataFrame()
    if not scores.empty:
        scores.to_csv(OUTPUT / "leave_one_year_scores.csv", index=False)
        baselines = simple_baseline_errors(scores)
        if not baselines.empty:
            baselines.to_csv(OUTPUT / "simple_baseline_errors.csv", index=False)
    sensor = real_river_sensor_check(panels) if panels else pd.DataFrame()
    if not sensor.empty:
        sensor.to_csv(OUTPUT / "real_river_sensor_check.csv", index=False)
    confirmation = leave_one_river_out(scores) if not scores.empty else {
        "passed": False,
        "reason": "no_scored_rivers",
    }
    if isinstance(confirmation.get("leave_one_network_out"), pd.DataFrame):
        confirmation["leave_one_network_out"].to_csv(
            OUTPUT / "leave_one_river_out.csv", index=False
        )
        confirmation = {
            key: value
            for key, value in confirmation.items()
            if key != "leave_one_network_out"
        }
    manifest = {
        "what_this_is": (
            "Public daily temperature for rivers used to build the method, "
            "plus overlap, real missing blocks, and a first whole-river check."
        ),
        "what_this_is_not": (
            "Not the last check. Not a reservoir-cause result. "
            "Not a paper headline."
        ),
        "n_rivers_downloaded": int(len(overlap)),
        "n_rivers_scored": int(scores["network_id"].nunique()) if not scores.empty else 0,
        "n_rivers_sensor_checked": int(sensor["network_id"].nunique()) if not sensor.empty else 0,
        "last_check_temperatures_used_to_score": False,
        "reservoir_operations_used": False,
        "leave_one_river": confirmation,
    }
    (OUTPUT / "public_river_check.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(overlap.to_string(index=False))
    print(json.dumps({k: manifest[k] for k in ("n_rivers_downloaded", "n_rivers_scored", "leave_one_river")}, indent=2, default=str))


if __name__ == "__main__":
    main()
