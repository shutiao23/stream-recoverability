#!/usr/bin/env python3
"""Write the Twin E hold-out publishable negative result record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.twin_e import write_twin_e_holdout_negative_result

DEFAULT_HOLDOUT = (
    ROOT
    / "results/framework/synthetic_v2/twin_e_holdout/twin_e_holdout_manifest.json"
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout-manifest", type=Path, default=DEFAULT_HOLDOUT)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    record = write_twin_e_holdout_negative_result(
        holdout_manifest_path=args.holdout_manifest,
        output_path=args.output,
    )
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
