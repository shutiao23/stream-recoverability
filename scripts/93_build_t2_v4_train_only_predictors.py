#!/usr/bin/env python3
"""Build the create-once, full-gap train-only predictor sidecar for T2 v4."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stream_recoverability.experiments.t2_train_only_predictors_v4 import (
    build_v4_train_only_predictor_sidecar,
)

DEFAULT_RUN = ROOT / "results/framework/t2_recovery_benchmark_v4"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--index-draft-manifest",
        type=Path,
        default=DEFAULT_RUN / "index_draft_manifest.json",
    )
    parser.add_argument(
        "--design", type=Path, default=ROOT / "configs/design_freeze_v9.yaml"
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_RUN / "train_only_predictors_v2"
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    manifest = build_v4_train_only_predictor_sidecar(
        repo_root=args.repo_root,
        index_draft_manifest_path=args.index_draft_manifest,
        design_path=args.design,
        output_dir=args.output,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
