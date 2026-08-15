#!/usr/bin/env python3
"""Build immutable, provenance-tracked analysis-data versions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stream_recoverability.data.versions import (
    DATA_VERSION_NAMES,
    build_data_versions,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-long",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "daily_long.parquet",
        help="unversioned or published_v1 prepared daily_long.parquet",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "data_versions",
        help="parent directory for <data_version>/ artifacts",
    )
    parser.add_argument(
        "--version",
        dest="versions",
        action="append",
        choices=DATA_VERSION_NAMES,
        help="version to build; repeat as needed (default: all registered versions)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    versions = tuple(args.versions) if args.versions else DATA_VERSION_NAMES
    manifests = build_data_versions(args.input_long, args.output_root, versions)
    for data_version, manifest in manifests.items():
        counts = manifest["output_counts"]
        print(
            f"{data_version}: {counts['long_rows']:,} long rows, "
            f"{counts['wide_rows']:,} daily rows -> {args.output_root / data_version}"
        )


if __name__ == "__main__":
    main()
