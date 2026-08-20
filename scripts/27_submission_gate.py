#!/usr/bin/env python3
"""Fail-closed WRR submission gate. Passing requires complete P0 evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

from stream_recoverability.governance import submission_gate, write_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results/audits/submission_gate.json",
    )
    parser.add_argument(
        "--allow-no-go",
        action="store_true",
        help="Write the report and exit 0 even when the gate is no-go.",
    )
    args = parser.parse_args()
    report = submission_gate(PROJECT_ROOT)
    write_json(args.output, report)
    print(args.output)
    print(report["decision"])
    if report["blockers"]:
        for item in report["blockers"]:
            print(f"- {item}")
    if not report["passed"] and not args.allow_no_go:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
