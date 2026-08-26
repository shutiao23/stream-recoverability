#!/usr/bin/env python3
"""Dry-run the sealed evaluator gate; never claim a lock or open a vault."""

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
    DEFAULT_PREFLIGHT_OUTPUT,
    build_evaluator_preflight,
    write_preflight,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_PREFLIGHT_OUTPUT)
    parser.add_argument("--require-authorized", action="store_true")
    args = parser.parse_args()
    manifest = build_evaluator_preflight()
    output = write_preflight(manifest, args.output)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "authorized_for_object_reads": manifest["authorized_for_object_reads"],
                "evaluate_once_lock_claimed": False,
                "sealed_objects_read": 0,
                "output": str(output),
                "blockers": manifest["blockers"],
            },
            sort_keys=True,
        )
    )
    if args.require_authorized and not manifest["authorized_for_object_reads"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
