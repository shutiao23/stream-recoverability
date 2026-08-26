#!/usr/bin/env python3
"""Plan or execute the bounded huc8_01070004 T2 M/H acquisition pilot."""

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

from stream_recoverability.data.t2_information_acquisition import run_bounded_pilot

DEFAULT_EXECUTE_OUTPUT = (
    ROOT
    / "data_versions/global_network_corpus_v1/open_role_auxiliary_pilot"
    / "development/networks/huc8_01070004"
)
DEFAULT_DRY_RUN_OUTPUT = (
    ROOT / "results/framework/t2_information_adapters_v1/acquisition_pilot_dry_run"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or (
        DEFAULT_EXECUTE_OUTPUT if args.execute else DEFAULT_DRY_RUN_OUTPUT
    )
    manifest = run_bounded_pilot(
        ROOT,
        output_dir,
        execute=args.execute,
        usgs_api_key=os.environ.get("USGS_API_KEY"),
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
