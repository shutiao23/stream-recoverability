#!/usr/bin/env python3
"""Audit validation-anchor window overlap from the frozen catalog.

This script does not run the validation funnel and does not rank models.
Leave-one-out and bootstrap ranking CSVs are explicit pending placeholders.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.anchor_independence import (
    load_validation_anchors_for_audit,
    write_anchor_independence_audit,
)
from stream_recoverability.experiments.contracts import file_sha256


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "validation_anchors.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "audits",
    )
    parser.add_argument(
        "--frontier-catalog",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "frontier_anchors.csv",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    catalog = load_validation_anchors_for_audit(args.catalog)
    frontier = None
    if args.frontier_catalog.is_file():
        frontier = load_validation_anchors_for_audit(args.frontier_catalog)
    audit = write_anchor_independence_audit(
        catalog, args.output_dir, frontier_catalog=frontier
    )
    payload = {
        **audit.summary,
        "catalog_path": str(args.catalog),
        "catalog_sha256": file_sha256(args.catalog),
        "output_dir": str(args.output_dir),
        "artifacts": sorted(audit.artifact_frames()),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
