#!/usr/bin/env python3
"""Claim the irreversible evaluate-once lock after preunseal readiness passes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.sealed_evaluation_readiness import (
    CLAIM_ACKNOWLEDGEMENT,
    DEFAULT_ONCE_LOCK,
    SealedReadinessError,
    build_readiness_manifest,
    claim_evaluate_once,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_ONCE_LOCK)
    parser.add_argument(
        "--acknowledgement",
        default=CLAIM_ACKNOWLEDGEMENT,
        help="Must exactly match the preregistered claim acknowledgement string.",
    )
    args = parser.parse_args()
    readiness = build_readiness_manifest()
    if readiness.get("ready_for_unseal") is not True:
        print(
            json.dumps(
                {"status": "blocked", "blockers": readiness.get("blockers", [])},
                sort_keys=True,
            )
        )
        raise SystemExit(2)
    try:
        payload = claim_evaluate_once(
            readiness,
            lock_path=args.lock,
            acknowledgement=args.acknowledgement,
        )
    except SealedReadinessError as error:
        print(json.dumps({"status": "blocked", "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from error
    print(
        json.dumps(
            {
                "status": payload.get("status"),
                "lock_path": str(args.lock.resolve()),
                "head_commit": payload.get("head_commit"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
