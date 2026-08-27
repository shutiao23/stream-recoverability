#!/usr/bin/env python3
"""Write the W2 toy demo (and optional six-river planted scores) under scratch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

W2 = Path(__file__).resolve().parent
REPO = W2.parents[2]
SRC = REPO / "src"
if str(W2) not in sys.path:
    sys.path.insert(0, str(W2))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gap_specific_scorer import (
    REQUIRED_SIX,
    later_year_station_rows,
    planted_station_rows,
    shock_toy_wide,
    w2_manifest,
    write_w2_artifacts,
)
from stream_recoverability.experiments.public_river_operator_ablation import (
    _jsonable,
    load_public_river_panels,
)

DEMO_DIR = W2 / "demo"
PUBLIC = REPO / "results/framework/public_rivers"
COMPARE_COLS = [
    "method",
    "network_id",
    "station_id",
    "gap_length",
    "achieved_skill",
    "fill_or_donor_mae",
    "climate_mae",
    "start_date",
    "y_kind",
]


def _demo_rows(method: str, rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=COMPARE_COLS)
    mae = frame["fill_mae"] if "fill_mae" in frame.columns else frame.get("donor_mae")
    out = pd.DataFrame(
        {
            "method": method,
            "network_id": frame.get("network_id"),
            "station_id": frame.get("station_id"),
            "gap_length": pd.to_numeric(frame.get("gap_length"), errors="coerce"),
            "achieved_skill": pd.to_numeric(frame.get("achieved_skill"), errors="coerce"),
            "fill_or_donor_mae": pd.to_numeric(mae, errors="coerce"),
            "climate_mae": pd.to_numeric(frame.get("climate_mae"), errors="coerce"),
            "start_date": frame["start_date"] if "start_date" in frame.columns else "",
            "y_kind": frame.get("y_kind"),
        }
    )
    out = out.loc[out["achieved_skill"].notna() & out["station_id"].notna()].copy()
    return out.sort_values(["method", "station_id", "gap_length"]).reset_index(drop=True)


def write_toy_demo() -> dict[str, object]:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    wide = shock_toy_wide(seed=11)
    later = _demo_rows("later_year", later_year_station_rows("toy", wide, gap_lengths=(30, 90)))
    planted = _demo_rows("planted_gap", planted_station_rows("toy", wide, gap_lengths=(30, 90)))
    combined = pd.concat([later, planted], ignore_index=True)
    csv_path = DEMO_DIR / "later_year_vs_gap_specific.csv"
    json_path = DEMO_DIR / "later_year_vs_gap_specific.json"
    combined.to_csv(csv_path, index=False)

    def first_pair(frame: pd.DataFrame) -> list[dict]:
        if frame.empty:
            return []
        station = str(frame["station_id"].iloc[0])
        pair = frame.loc[frame["station_id"].eq(station)].head(2)
        return pair.to_dict(orient="records")

    later_first = first_pair(later)
    planted_first = first_pair(planted)
    later_same = (
        len(later_first) == 2
        and later_first[0]["achieved_skill"] == later_first[1]["achieved_skill"]
        and later_first[0]["gap_length"] != later_first[1]["gap_length"]
    )
    planted_diff = (
        len(planted_first) == 2
        and planted_first[0]["achieved_skill"] != planted_first[1]["achieved_skill"]
        and planted_first[0]["gap_length"] != planted_first[1]["gap_length"]
    )
    payload = {
        "note": (
            "First L=30 vs L=90 rows match under later-year y and differ under "
            "planted gap-specific y."
        ),
        "later_year_first_rows_match": later_same,
        "planted_first_rows_differ": planted_diff,
        "later_year_first_rows": later_first,
        "planted_gap_first_rows": planted_first,
        "rows": _jsonable(combined),
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {
        "csv": str(csv_path),
        "json": str(json_path),
        "later_year_first_rows_match": later_same,
        "planted_first_rows_differ": planted_diff,
        "later_year_first_rows": later_first,
        "planted_gap_first_rows": planted_first,
    }


def score_six_rivers() -> dict[str, object]:
    panels = load_public_river_panels(PUBLIC)
    six = {key: panels[key] for key in REQUIRED_SIX if key in panels}
    missing_files = [key for key in REQUIRED_SIX if key not in six]
    rows: list[dict] = []
    for name, wide in six.items():
        rows.extend(planted_station_rows(name, wide, gap_lengths=(30, 90)))
    scores = pd.DataFrame(rows)
    manifest = w2_manifest(scores, roster=REQUIRED_SIX)
    manifest["wide_csvs_missing"] = missing_files
    manifest["new_temperatures_downloaded"] = False
    out = W2 / "outputs"
    paths = write_w2_artifacts(scores, manifest, out)
    return {
        "n_rows": int(len(scores)),
        "scored_networks": manifest["scored_networks"],
        "delaware_scored": manifest["delaware_scored"],
        "requested_primary_missing": manifest["requested_primary_missing"],
        "paths": {key: str(path) for key, path in paths.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--six-rivers",
        action="store_true",
        help="Score the six overlap-complete wides already on disk. Scratch only.",
    )
    args = parser.parse_args()
    demo = write_toy_demo()
    print(json.dumps({"demo": demo}, indent=2, default=str))
    if args.six_rivers:
        six = score_six_rivers()
        print(json.dumps({"six_rivers": six}, indent=2, default=str))


if __name__ == "__main__":
    main()
