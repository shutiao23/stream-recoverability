#!/usr/bin/env python3
"""Create one immutable formal-suite registry from explicit completed runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.formal_registry import (
    DEFAULT_FRONTIER_ANCHOR_PATH,
    build_formal_suite_registry,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        dest="manifests",
        action="append",
        type=Path,
        required=True,
        help=(
            "explicit completed suite run_manifest.json; repeat once per run "
            "directory (no historical-tree discovery is performed)"
        ),
    )
    parser.add_argument(
        "--finalized-model-roster",
        type=Path,
        required=True,
        help="finalized_model_roster_v1 from validation only",
    )
    parser.add_argument(
        "--formal-root",
        type=Path,
        required=True,
        help="canonical version/design/split root containing every listed run",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-version", required=True)
    parser.add_argument("--evaluation-split", required=True)
    parser.add_argument("--design-hash", default="")
    parser.add_argument(
        "--data-version-manifest",
        type=Path,
        required=True,
        help=(
            "target version_manifest.json for the requested data version"
        ),
    )
    parser.add_argument(
        "--design", type=Path, default=PROJECT_ROOT / "configs/design_freeze_v4.yaml"
    )
    parser.add_argument(
        "--study-manifest", type=Path, default=PROJECT_ROOT / "study_manifest.yaml"
    )
    parser.add_argument(
        "--experiment-config",
        type=Path,
        default=PROJECT_ROOT / "configs/experiments.yaml",
    )
    parser.add_argument(
        "--selection-data-version-manifest",
        type=Path,
        help="selection manifest; defaults from data_versions.primary in --design",
    )
    parser.add_argument(
        "--frontier-anchor-catalog",
        type=Path,
        default=PROJECT_ROOT / "metadata/frontier_anchors_v2.csv",
        help="canonical primary-version development-test frontier anchor catalog",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    registry = build_formal_suite_registry(
        manifest_paths=args.manifests,
        finalized_model_roster_path=args.finalized_model_roster,
        formal_root=args.formal_root,
        output_path=args.output,
        data_version=args.data_version,
        evaluation_split=args.evaluation_split,
        design_hash=args.design_hash,
        design_path=args.design,
        study_manifest_path=args.study_manifest,
        experiment_config_path=args.experiment_config,
        data_version_manifest_path=args.data_version_manifest,
        selection_data_version_manifest_path=args.selection_data_version_manifest,
        frontier_anchor_catalog_path=args.frontier_anchor_catalog,
    )
    print(json.dumps(registry, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
