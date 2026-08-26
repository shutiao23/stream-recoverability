#!/usr/bin/env python3
"""Build the complete outcome-blind T2 v4 pre-score eligibility audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stream_recoverability.experiments.t2_pre_score_eligibility import (
    build_pre_score_eligibility,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--workload",
        type=Path,
        default=ROOT / "results/framework/t2_recovery_benchmark_v4/workload_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results/framework/t2_recovery_benchmark_v4/pre_score_eligibility",
    )
    args = parser.parse_args()
    manifest = build_pre_score_eligibility(
        repo_root=args.repo_root,
        workload_manifest_path=args.workload,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
