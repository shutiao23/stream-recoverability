#!/usr/bin/env python3
"""Write the W8 failure-closure retitle record. Not confirmatory T2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.w8_failure_closure import (
    write_w8_failure_closure_from_w7_path,
)

DEFAULT_W7 = (
    ROOT
    / "results/framework/t2_recovery_benchmark_v1/w7_open_role_bd_slice"
    / "w7_open_role_bd_slice_manifest.json"
)
DEFAULT_OUTPUT = ROOT / "results/framework/w8_failure_closure_v1"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w7-manifest", type=Path, default=DEFAULT_W7)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    manifest = write_w8_failure_closure_from_w7_path(
        repo_root=ROOT,
        output_dir=args.output,
        w7_manifest_path=args.w7_manifest,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
