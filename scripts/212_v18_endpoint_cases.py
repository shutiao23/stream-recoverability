#!/usr/bin/env python3
"""Build the extended endpoint table E3 and E6 both need.

Regenerates the v17 outage realizations from the same deterministic seeds and
computes, on each of them, two families of estimand the original case table
does not carry: Johnson et al.'s sine-fit mean, phase and amplitude, and the
hottest-k-day mean for k from 1 to 365. One pass, because both need the same
completed years.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v18_closure.endpoints import endpoint_rows  # noqa: E402
from stream_recoverability.experiments.v18_closure.paths import RESULTS_ROOT  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from scripts_support import endpoint_jobs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=64)
    args = parser.parse_args()

    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    work = endpoint_jobs()
    frames: list[pd.DataFrame] = []
    if args.workers <= 1:
        frames = [endpoint_rows(job) for job in work]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            frames = list(pool.map(endpoint_rows, work, chunksize=1))
    frames = [f for f in frames if not f.empty]
    table = pd.concat(frames, ignore_index=True)
    # Row order is part of reproducibility: workers return out of order.
    table = table.sort_values(
        ["network_id", "station_id", "year", "realization_id"], kind="mergesort"
    ).reset_index(drop=True)
    table.to_parquet(RESULTS_ROOT / "endpoint_cases.parquet", index=False)
    summary = {
        "n_cases": int(len(table)),
        "n_stations": int(table["station_id"].nunique()),
        "n_networks": int(table["network_id"].nunique()),
        "by_split": table["split_role"].value_counts().to_dict(),
        "by_arm": table["arm"].value_counts().to_dict(),
    }
    (RESULTS_ROOT / "endpoint_cases_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
