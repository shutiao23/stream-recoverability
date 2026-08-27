#!/usr/bin/env python3
"""Bind complete T2 v4 scores to the frozen lattice. Not confirmatory T2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_primary_aggregation_v2 import (
    bind_complete_v4_primary_results,
)

DEFAULT_RUN = ROOT / "results/framework/t2_recovery_benchmark_v4"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workload",
        type=Path,
        default=DEFAULT_RUN / "workload_manifest_v3.json",
        help="v3 workload SHA-bound to aggregation_v3",
    )
    parser.add_argument(
        "--aggregation",
        type=Path,
        default=DEFAULT_RUN / "aggregation_v3/aggregation_manifest.json",
    )
    parser.add_argument(
        "--lattice-freeze",
        type=Path,
        default=DEFAULT_RUN / "primary_aggregation_v2/lattice_freeze_manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RUN / "primary_aggregation_v2",
        help="writes post_t2_input_binding.json next to the frozen lattice",
    )
    parser.add_argument(
        "--development-exclude-data-ineligible",
        action="store_true",
        help="drop lattice rows scored data_ineligible; not confirmatory T2",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    binding = bind_complete_v4_primary_results(
        workload_manifest_path=args.workload,
        aggregation_manifest_path=args.aggregation,
        lattice_freeze_manifest_path=args.lattice_freeze,
        output_dir=args.output,
        development_exclude_data_ineligible=bool(
            args.development_exclude_data_ineligible
        ),
    )
    print(json.dumps(binding, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
