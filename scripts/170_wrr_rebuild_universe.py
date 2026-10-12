#!/usr/bin/env python3
"""Step 1: rebuild the evaluation universe and complete-year thermal-truth roster.

Also writes the Step 2 diagnostic that recomputes existing simple-method replay
on the trusted river complete-year panel. No recoverer is retrained.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.wrr_revision.headroom import (  # noqa: E402
    run_headroom,
    write_headroom,
)
from stream_recoverability.experiments.wrr_revision.paths import (  # noqa: E402
    STEP1_UNIVERSE,
    STEP2_HEADROOM,
    UNIVERSE_AS_OF,
)
from stream_recoverability.experiments.wrr_revision.universe import (  # noqa: E402
    build_universe,
    write_universe,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=UNIVERSE_AS_OF)
    parser.add_argument("--skip-headroom", action="store_true")
    args = parser.parse_args()
    bundle = build_universe(as_of=args.as_of)
    write_universe(bundle, STEP1_UNIVERSE)
    summary = bundle["summary"]
    assert isinstance(summary, dict)
    print(json.dumps(summary, indent=2), flush=True)
    if args.skip_headroom:
        return
    station_years = bundle["station_years"]
    assert hasattr(station_years, "empty")
    headroom = run_headroom(station_years)
    write_headroom(headroom, STEP2_HEADROOM)
    print(json.dumps(headroom["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()
