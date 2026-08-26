#!/usr/bin/env python3
"""Create the executable v4 workload after the pre-score freeze is committed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stream_recoverability.experiments.t2_workload_v4 import finalize_v4_workload

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "results/framework/t2_recovery_benchmark_v4"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", type=Path, default=RUN / "index_draft_manifest.json")
    parser.add_argument(
        "--pre-score-freeze", type=Path, default=RUN / "pre_score_freeze_manifest.json"
    )
    parser.add_argument("--output", type=Path, default=RUN / "workload_manifest.json")
    args = parser.parse_args()
    manifest = finalize_v4_workload(
        ROOT,
        index_draft_manifest_path=args.draft,
        pre_score_freeze_manifest_path=args.pre_score_freeze,
        output_path=args.output,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
