#!/usr/bin/env python3
"""Write the fail-closed v9.1 Tier-2 deep-budget readiness manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_tier2_readiness import (
    READINESS_RELATIVE_PATH,
    build_tier2_deep_readiness_manifest,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / READINESS_RELATIVE_PATH)
    parser.add_argument(
        "--skip-constructor-smoke",
        action="store_true",
        help="audit sources/dependencies without initializing official SAITS/CSDI cores",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    manifest = build_tier2_deep_readiness_manifest(
        ROOT, run_constructor_smoke=not args.skip_constructor_smoke
    )
    if args.output.is_file():
        previous = json.loads(args.output.read_text(encoding="utf-8"))
        previous_sample = (previous.get("sample_lock") or {}).get("sample_sha256")
        current_sample = manifest["sample_lock"]["sample_sha256"]
        if previous_sample not in (None, current_sample):
            raise RuntimeError("refusing to overwrite readiness for a different sample")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
