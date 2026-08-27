#!/usr/bin/env python3
"""Run the single authorized sealed temperature QC pass."""

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
    DEFAULT_MODEL_FREEZE,
    DEFAULT_ONCE_LOCK,
    DEFAULT_READINESS,
    DEFAULT_SEALED_QC_OUTPUT,
    SealedEvaluatorError,
    evaluate_production_sealed_once,
)

DEFAULT_READINESS_PATH = DEFAULT_READINESS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS_PATH)
    parser.add_argument("--lock", type=Path, default=DEFAULT_ONCE_LOCK)
    parser.add_argument("--model-freeze", type=Path, default=DEFAULT_MODEL_FREEZE)
    parser.add_argument("--output", type=Path, default=DEFAULT_SEALED_QC_OUTPUT)
    parser.add_argument("--sealed-absolute-floor", type=int, default=40)
    args = parser.parse_args()
    try:
        manifest = evaluate_production_sealed_once(
            readiness_path=args.readiness,
            once_lock_path=args.lock,
            model_freeze_path=args.model_freeze,
            output_dir=args.output,
            sealed_absolute_floor=args.sealed_absolute_floor,
        )
    except SealedEvaluatorError as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from error
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
