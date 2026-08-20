#!/usr/bin/env python3
"""Plan or build the immutable frozen confirmatory data set (never metrics)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.data.confirmatory import (
    CONFIRMATORY_DATA_VERSION,
    build_confirmatory_data,
    build_confirmatory_request_plan,
    load_confirmatory_protocol,
    write_immutable_request_plan,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    plan = commands.add_parser(
        "plan", help="emit the frozen request plan without any network access"
    )
    plan.add_argument(
        "--design",
        type=Path,
        default=PROJECT_ROOT / "configs" / "design_freeze_v4.yaml",
    )
    plan.add_argument(
        "--output",
        type=Path,
        help="optional immutable JSON path; otherwise print the plan to stdout",
    )

    build = commands.add_parser(
        "build",
        help=(
            "execute frozen source requests and build data artifacts after validating "
            "a finalized validation-only model roster"
        ),
    )
    build.add_argument(
        "--design",
        type=Path,
        default=PROJECT_ROOT / "configs" / "design_freeze_v4.yaml",
    )
    build.add_argument(
        "--output",
        type=Path,
        default=(PROJECT_ROOT / "data_versions" / CONFIRMATORY_DATA_VERSION),
    )
    build.add_argument(
        "--finalized-model-roster",
        type=Path,
        required=True,
        help=(
            "existing finalized_model_roster_v1 JSON that authorizes opening "
            "confirmatory values"
        ),
    )
    build.add_argument(
        "--study-manifest",
        type=Path,
        default=PROJECT_ROOT / "study_manifest.yaml",
    )
    build.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs/experiments.yaml",
    )
    build.add_argument(
        "--selection-data-version",
        help="frozen validation version; defaults to data_versions.primary in --design",
    )
    build.add_argument(
        "--selection-data-version-manifest",
        type=Path,
        help="selection manifest; defaults from data_versions.primary in --design",
    )
    build.add_argument(
        "--usgs-api-key-env",
        default="USGS_API_KEY",
        help=(
            "environment variable containing an optional USGS key; the value is "
            "sent only via X-Api-Key and is never persisted"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        protocol = load_confirmatory_protocol(args.design)
        plan = build_confirmatory_request_plan(protocol)
        if args.output is None:
            print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            write_immutable_request_plan(plan, args.output)
            print(
                f"request plan ({plan['initial_request_count']} initial requests) "
                f"-> {args.output}"
            )
        return 0

    api_key = os.environ.get(args.usgs_api_key_env)
    manifest = build_confirmatory_data(
        args.design,
        args.output,
        finalized_model_roster_path=args.finalized_model_roster,
        study_manifest_path=args.study_manifest,
        experiment_config_path=args.config,
        selection_data_version=args.selection_data_version,
        selection_data_version_manifest_path=args.selection_data_version_manifest,
        usgs_api_key=api_key,
    )
    counts = manifest["output_counts"]
    print(
        f"{manifest['data_version']}: {counts['long_rows']:,} long rows, "
        f"{counts['wide_rows']:,} days -> {args.output}"
    )
    print("confirmatory performance metrics were not computed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
