#!/usr/bin/env python3
"""Generate the frozen validation-only five-anchor-per-station catalog."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.masks import (
    AnchorAvailabilityError,
    generate_validation_anchor_catalog,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            PROJECT_ROOT
            / "data_versions"
            / "published_v1"
            / "daily_long.parquet"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "validation_anchors.csv",
    )
    parser.add_argument("--data-version", default="published_v1")
    parser.add_argument(
        "--station",
        dest="stations",
        action="append",
        help="repeatable station ID (default: B1, S2, P3)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="atomically replace an existing catalog",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.input.is_file():
        raise FileNotFoundError(args.input)
    source = pd.read_parquet(args.input)
    try:
        catalog = generate_validation_anchor_catalog(
            source,
            data_version=args.data_version,
            station_ids=tuple(args.stations or ("B1", "S2", "P3")),
        )
    except AnchorAvailabilityError as error:
        print(error.report.to_string(index=False), file=sys.stderr)
        raise
    if args.output.exists() and not args.force:
        raise FileExistsError(f"refusing to replace existing catalog: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    catalog.to_csv(temporary, index=False)
    temporary.replace(args.output)
    print(f"wrote {len(catalog)} validation anchors to {args.output}")


if __name__ == "__main__":
    main()
