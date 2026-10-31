#!/usr/bin/env python3
"""Run the sealed temperature QC pass over every registered object."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.sealed_evaluator_scaffold import (
    DEFAULT_SEALED_QC_OUTPUT,
    SealedEvaluatorError,
    run_sealed_qc,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_SEALED_QC_OUTPUT)
    parser.add_argument("--sealed-absolute-floor", type=int, default=40)
    args = parser.parse_args()
    try:
        manifest = run_sealed_qc(
            output_dir=args.output,
            sealed_absolute_floor=args.sealed_absolute_floor,
        )
    except SealedEvaluatorError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from error
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
