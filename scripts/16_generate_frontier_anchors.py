#!/usr/bin/env python3
"""Generate the fixed, season-balanced nested-frontier anchor catalog."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stream_recoverability.masks import (
    FRONTIER_SEASONS,
    AnchorAvailabilityError,
    generate_frontier_anchor_catalog,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "data_versions" / "published_v1" / "daily_long.parquet",
        help="versioned daily_long.parquet",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "frontier_anchors.csv",
    )
    parser.add_argument(
        "--evaluation-split",
        default="development_test",
        help="evidence-facing split label (2018-2020 is development_test)",
    )
    parser.add_argument(
        "--source-split",
        help="stored data split when it differs from the evidence label",
    )
    parser.add_argument("--data-version", default="published_v1")
    parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        help="target variable; repeat as needed (default: T, F, L)",
    )
    parser.add_argument(
        "--station",
        dest="station_ids",
        action="append",
        help="station ID; repeat as needed (default: every station)",
    )
    parser.add_argument("--max-supported-length", type=int, default=365)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frame = pd.read_parquet(args.input)
    try:
        anchors = generate_frontier_anchor_catalog(
            frame,
            evaluation_split=args.evaluation_split,
            data_version=args.data_version,
            source_split=args.source_split,
            targets=tuple(args.targets or ("T", "F", "L")),
            station_ids=args.station_ids,
            max_supported_length=args.max_supported_length,
        )
    except AnchorAvailabilityError as error:
        print(error.report.to_string(index=False), file=sys.stderr)
        raise

    args.output.parent.mkdir(parents=True, exist_ok=True)
    anchors.to_csv(args.output, index=False, mode="x")
    group_count = anchors[["station_id", "target"]].drop_duplicates().shape[0]
    print(
        f"wrote {len(anchors):,} anchors for {group_count} station-target groups "
        f"({', '.join(FRONTIER_SEASONS)}) to {args.output}"
    )


if __name__ == "__main__":
    main()
