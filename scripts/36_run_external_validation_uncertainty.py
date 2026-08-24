#!/usr/bin/env python3
"""Run 20-seed mask-placement uncertainty on external validation data only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.external_validation_uncertainty import (
    EXTERNAL_VALIDATION_MASK_SEEDS,
    run_external_validation_uncertainty,
)
from stream_recoverability.data.confirmatory import CONFIRMATORY_DATA_VERSION
from stream_recoverability.experiments.contracts import DEFAULT_DESIGN_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=PROJECT_ROOT / "data_versions" / CONFIRMATORY_DATA_VERSION,
    )
    parser.add_argument(
        "--finalized-model-roster",
        type=Path,
        default=(
            PROJECT_ROOT
            / "results/validation_funnel/published_v2/finalized_model_roster.json"
        ),
    )
    parser.add_argument(
        "--design", type=Path, default=PROJECT_ROOT / DEFAULT_DESIGN_PATH
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
        default=(PROJECT_ROOT / "data_versions/published_v2/version_manifest.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results/revision/external_validation_uncertainty",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    manifest = run_external_validation_uncertainty(
        data_root=args.data_root,
        finalized_model_roster_path=args.finalized_model_roster,
        output_dir=args.output_dir,
        design_path=args.design,
        study_manifest_path=args.study_manifest,
        experiment_config_path=args.experiment_config,
        selection_data_version_manifest_path=args.selection_data_version_manifest,
        mask_seeds=EXTERNAL_VALIDATION_MASK_SEEDS,
    )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "evaluation_split": manifest["evaluation_split"],
                "confirmatory_outcomes_read": manifest["confirmatory_outcomes_read"],
                "once_lock_modified": manifest["once_lock_modified"],
                "mask_seed_count": len(manifest["grid"]["mask_seeds"]),
                "scenario_count": manifest["grid"]["scenario_count"],
                "output_dir": str(args.output_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
