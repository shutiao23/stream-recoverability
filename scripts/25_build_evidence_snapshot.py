#!/usr/bin/env python3
"""Write the machine-readable evidence snapshot for the current commit."""

from __future__ import annotations

import argparse
from pathlib import Path

from stream_recoverability.governance import evidence_snapshot, write_json

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results/audits/evidence_snapshot.json",
    )
    args = parser.parse_args()
    write_json(args.output, evidence_snapshot(PROJECT_ROOT))
    print(args.output)


if __name__ == "__main__":
    main()
