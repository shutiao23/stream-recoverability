#!/usr/bin/env python3
"""Run the frozen-sample Tier-2 development subsample (SAITS/CSDI, passed: false)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_tier2_development_subsample import (
    write_tier2_development_subsample,
)

DEFAULT_OUTPUT = ROOT / "results/framework/t2_recovery_benchmark_v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--max-networks", type=int)
    args = parser.parse_args()
    manifest = write_tier2_development_subsample(
        ROOT,
        args.output,
        epochs=int(args.epochs),
        max_networks=args.max_networks,
    )
    print(json.dumps({k: v for k, v in manifest.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
