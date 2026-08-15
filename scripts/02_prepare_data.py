#!/usr/bin/env python3
"""Build aligned daily Parquet files, chronological splits, and a train-only scaler."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stream_recoverability.data.prepare import prepare_daily_data, window_counts  # noqa: E402
from stream_recoverability.data.schema import (  # noqa: E402
    DEFAULT_DATA_DICTIONARY,
    DEFAULT_PROCESSED_DIR,
    DEFAULT_RAW_DIR,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--data-dictionary", type=Path, default=DEFAULT_DATA_DICTIONARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_PROCESSED_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    long_data, wide_data, _ = prepare_daily_data(
        raw_dir=args.raw_dir,
        data_dictionary=args.data_dictionary,
        output_dir=args.output_dir,
    )
    print(f"Wrote {len(long_data):,} long rows and {len(wide_data):,} daily wide rows to {args.output_dir}")
    print(window_counts(wide_data).to_string(index=False))


if __name__ == "__main__":
    main()
