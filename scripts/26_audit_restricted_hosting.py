#!/usr/bin/env python3
"""Record whether restricted observation bytes are still on the public tip."""

from __future__ import annotations

import argparse
from pathlib import Path

from stream_recoverability.governance import audit_restricted_hosting, write_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results/audits/restricted_hosting_audit.json",
    )
    parser.add_argument(
        "--fail-if-present",
        action="store_true",
        help="Exit 2 if restricted bytes remain tracked. Default is record-only.",
    )
    args = parser.parse_args()
    report = audit_restricted_hosting(PROJECT_ROOT)
    write_json(args.output, report)
    print(args.output)
    if args.fail_if_present and report["public_hosting_defect"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
