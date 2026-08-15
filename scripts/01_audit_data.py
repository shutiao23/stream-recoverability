#!/usr/bin/env python3
"""Create the targeted first-stage data audit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stream_recoverability.data.audit import audit_raw_data  # noqa: E402
from stream_recoverability.data.schema import (  # noqa: E402
    DEFAULT_AUDIT_DIR,
    DEFAULT_DATA_DICTIONARY,
    DEFAULT_RAW_DIR,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--data-dictionary", type=Path, default=DEFAULT_DATA_DICTIONARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--minimum-constant-run", type=int, default=7)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tables = audit_raw_data(
        raw_dir=args.raw_dir,
        data_dictionary=args.data_dictionary,
        output_dir=args.output_dir,
        minimum_constant_run=args.minimum_constant_run,
    )
    print(f"Wrote {len(tables)} audit tables and data_quality_report.md to {args.output_dir}")


if __name__ == "__main__":
    main()
