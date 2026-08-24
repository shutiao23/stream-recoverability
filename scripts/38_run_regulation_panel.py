#!/usr/bin/env python3
"""Run the independently frozen nationwide regulation-panel analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.regulation_panel import run_regulation_panel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs/regulation_panel_freeze_v1.yaml",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PROJECT_ROOT / "data/cache/regulation_panel_v1",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results/regulation_panel_v1",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Require complete existing caches and make no network requests.",
    )
    parser.add_argument(
        "--legacy-transport",
        action="store_true",
        help=(
            "Use the separately frozen official /dv fallback for stations with "
            "exactly one primary modern time series."
        ),
    )
    parser.add_argument(
        "--bootstrap-equivalence-batches",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Populate or verify the first N frozen modern-API batches required "
            "for the legacy transport equivalence audit (26 reproduces this run)."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_regulation_panel(
        project_root=PROJECT_ROOT,
        config_path=args.config.resolve(),
        cache_dir=args.cache_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        offline=args.offline,
        transport=("legacy_single_series" if args.legacy_transport else "modern"),
        equivalence_bootstrap_batches=args.bootstrap_equivalence_batches,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
