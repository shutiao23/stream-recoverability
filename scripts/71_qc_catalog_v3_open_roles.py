#!/usr/bin/env python3
"""QC registered catalog-v3 development or validation raw objects.

This command performs no downloads.  All raw reads pass through the locked
HUC8 custody gate; sealed is not an accepted role.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.data.open_role_corpus_qc import (
    run_open_role_qc,
)

DEFAULT_OUTPUT = ROOT / "data_versions/global_network_corpus_v1/open_role_qc"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=["development", "validation"], required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-networks", type=int)
    args = parser.parse_args()
    manifest = run_open_role_qc(
        role=args.role,
        output_dir=args.output_dir / args.role,
        max_networks=args.max_networks,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
