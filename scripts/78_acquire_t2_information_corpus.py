#!/usr/bin/env python3
"""Plan or sequentially acquire M/H for the 67-network open T2 corpus."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.t2_information_corpus_acquisition import (
    run_corpus_acquisition,
)

DEFAULT_EXECUTE_OUTPUT = (
    ROOT
    / "data_versions/global_network_corpus_v1/open_role_auxiliary"
    / "failure_closure6"
)
DEFAULT_DRY_RUN_OUTPUT = (
    ROOT
    / "results/framework/t2_information_adapters_v1"
    / "corpus_acquisition_dry_run"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--network-id", action="append", default=[])
    selection.add_argument("--max-networks", type=int)
    selection.add_argument("--all", action="store_true", dest="all_networks")
    parser.add_argument("--acknowledge-network-count", type=int)
    parser.add_argument("--acknowledge-all-network-count", type=int)
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=1.0,
        help="Minimum start-to-start delay for every provider HTTP request.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Refuse rather than integrity-check and skip terminal networks.",
    )
    parser.set_defaults(resume=True)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    output = args.output_root or (
        DEFAULT_EXECUTE_OUTPUT if args.execute else DEFAULT_DRY_RUN_OUTPUT
    )
    manifest = run_corpus_acquisition(
        ROOT,
        output,
        execute=args.execute,
        network_ids=args.network_id,
        max_networks=args.max_networks,
        all_networks=args.all_networks,
        acknowledged_network_count=args.acknowledge_network_count,
        acknowledge_all_network_count=args.acknowledge_all_network_count,
        resume=args.resume,
        request_interval_seconds=args.request_interval_seconds,
        usgs_api_key=os.environ.get("USGS_API_KEY"),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
