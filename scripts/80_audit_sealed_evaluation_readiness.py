#!/usr/bin/env python3
"""Audit T2/T7 sealed readiness without reading or unsealing sealed objects."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.experiments.sealed_evaluation_readiness import (
    DEFAULT_OUTPUT,
    build_readiness_manifest,
    write_readiness_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 2 after writing the audit when any pre-unseal gate is blocked.",
    )
    args = parser.parse_args()
    manifest = build_readiness_manifest()
    output = write_readiness_manifest(manifest, args.output)
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "ready_for_unseal": manifest["ready_for_unseal"],
                "sealed_outcomes_opened": False,
                "blockers": manifest["blockers"],
                "output": str(output),
            },
            sort_keys=True,
        )
    )
    if args.require_ready and not manifest["ready_for_unseal"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
