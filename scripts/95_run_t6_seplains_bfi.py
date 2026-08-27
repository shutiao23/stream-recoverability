#!/usr/bin/env python3
"""Run the post-hoc T6 SEPlains × BFI mechanism slice."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t6_seplains_bfi import run_t6_seplains_bfi_analysis

DEFAULT_OUTPUT = ROOT / "results/framework/t6_seplains_bfi_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--station-metrics",
        type=Path,
        default=ROOT
        / "results/regulation_panel_v1_legacy_transport/station_metrics.csv",
    )
    parser.add_argument(
        "--frozen-predictions",
        type=Path,
        default=ROOT
        / "results/regulation_panel_v1_legacy_transport/leave_ecoregion_out_predictions.csv",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/regulation_panel_freeze_v1.yaml",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=ROOT / "data/cache/regulation_panel_v1",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = run_t6_seplains_bfi_analysis(
        station_metrics_path=args.station_metrics,
        frozen_predictions_path=args.frozen_predictions,
        config_path=args.config,
        cache_dir=args.cache_dir,
        output_dir=args.output,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
