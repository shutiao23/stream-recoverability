#!/usr/bin/env python3
"""Generate descriptive statistics, event labels, and local study figures."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.eda import run_eda  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--long-data",
        type=Path,
        default=PROJECT_ROOT / "data/processed/daily_long.parquet",
    )
    parser.add_argument(
        "--wide-data",
        type=Path,
        default=PROJECT_ROOT / "data/processed/daily_wide.parquet",
    )
    parser.add_argument(
        "--station-metadata",
        type=Path,
        default=PROJECT_ROOT / "metadata/station_metadata.csv",
    )
    parser.add_argument(
        "--candidate-metadata",
        type=Path,
        default=PROJECT_ROOT / "metadata/candidate_stations.csv",
    )
    parser.add_argument(
        "--results-dir", type=Path, default=PROJECT_ROOT / "results/eda"
    )
    parser.add_argument(
        "--eda-figures-dir", type=Path, default=PROJECT_ROOT / "figures/eda"
    )
    parser.add_argument(
        "--qc-figures-dir", type=Path, default=PROJECT_ROOT / "figures/qc"
    )
    parser.add_argument(
        "--event-output",
        type=Path,
        default=PROJECT_ROOT / "data/processed/event_labels.parquet",
    )
    parser.add_argument(
        "--study-area-output",
        type=Path,
        default=PROJECT_ROOT / "figures/study_area.png",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    outputs = run_eda(
        args.long_data,
        args.wide_data,
        args.station_metadata,
        args.candidate_metadata,
        results_dir=args.results_dir,
        eda_figures_dir=args.eda_figures_dir,
        qc_figures_dir=args.qc_figures_dir,
        event_output=args.event_output,
        study_area_output=args.study_area_output,
    )
    print(f"wrote {len(outputs)} EDA tables/artifacts")


if __name__ == "__main__":
    main()

