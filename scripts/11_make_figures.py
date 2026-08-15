#!/usr/bin/env python3
"""Freeze final result inputs and generate available publication figures/tables."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.plotting import generate_publication_outputs  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daily-predictions", type=Path, default=PROJECT_ROOT / "results/experiments/daily_predictions.parquet")
    parser.add_argument("--event-metrics", type=Path, default=PROJECT_ROOT / "results/experiments/event_metrics.parquet")
    parser.add_argument("--analysis-dir", type=Path, default=PROJECT_ROOT / "results/analysis")
    parser.add_argument("--station-metadata", type=Path, default=PROJECT_ROOT / "metadata/station_metadata.csv")
    parser.add_argument("--eda-dir", type=Path, default=PROJECT_ROOT / "results/eda")
    parser.add_argument("--study-area-points", type=Path, default=PROJECT_ROOT / "results/eda/study_area_points.csv")
    parser.add_argument("--availability-image", type=Path, default=PROJECT_ROOT / "figures/eda/availability.png")
    parser.add_argument("--online-dir", type=Path, default=PROJECT_ROOT / "results/online")
    parser.add_argument("--figure-dir", type=Path, default=PROJECT_ROOT / "figures/main")
    parser.add_argument("--table-dir", type=Path, default=PROJECT_ROOT / "paper/tables")
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "results/final_results_manifest.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = generate_publication_outputs(
        daily_predictions_path=args.daily_predictions,
        event_metrics_path=args.event_metrics,
        analysis_dir=args.analysis_dir,
        station_metadata_path=args.station_metadata,
        eda_dir=args.eda_dir,
        study_area_points_path=args.study_area_points,
        availability_image_path=args.availability_image,
        online_dir=args.online_dir,
        figure_dir=args.figure_dir,
        table_dir=args.table_dir,
        manifest_path=args.manifest,
    )
    figure_counts = Counter(item["status"] for item in manifest["figures"].values())
    table_counts = Counter(item["status"] for item in manifest["tables"].values())
    print(
        "publication outputs: "
        f"figures generated={figure_counts['generated']}, skipped={figure_counts['skipped']}; "
        f"tables generated={table_counts['generated']}, skipped={table_counts['skipped']}"
    )
    print(f"manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
