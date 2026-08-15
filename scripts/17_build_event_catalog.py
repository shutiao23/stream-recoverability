#!/usr/bin/env python3
"""Build or audit the deterministic M7b event/control episode catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.experiments.contracts import file_sha256
from stream_recoverability.masks import (
    audit_event_episode_catalog,
    generate_event_episode_catalog,
    load_event_episode_catalog,
)


def _atomic_json(value: dict[str, Any], path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite immutable audit artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _atomic_catalog(frame: pd.DataFrame, path: Path, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite immutable event catalog: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    frame.to_csv(temporary, index=False, float_format="%.17g")
    temporary.replace(path)


def _file_bytes_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _portable_path(path: Path) -> str:
    """Prefer repository-relative provenance paths for clone-stable audits."""

    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(resolved)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            PROJECT_ROOT / "data_versions" / "published_v1" / "daily_long.parquet"
        ),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=PROJECT_ROOT / "metadata/event_episode_catalog.csv",
    )
    parser.add_argument(
        "--audit-output",
        type=Path,
        default=PROJECT_ROOT / "metadata/event_episode_catalog.audit.json",
    )
    parser.add_argument(
        "--overwrite", action=argparse.BooleanOptionalAction, default=False
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build", help="build and immediately audit a catalog")
    _common(build)
    build.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "configs/experiments.yaml",
    )
    build.add_argument("--data-version", default="published_v1")
    build.add_argument("--evaluation-split", default="development_test")
    build.add_argument("--source-split")
    build.add_argument("--station", dest="station_ids", action="append")
    build.add_argument("--minimum-training-samples", type=int, default=30)
    build.add_argument("--control-context-days", type=int, default=1)

    audit = commands.add_parser(
        "audit", help="regenerate and compare an existing catalog"
    )
    _common(audit)
    return parser


def _declared_events(config_path: Path) -> dict[str, str]:
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or not isinstance(config.get("M7"), dict):
        raise TypeError("experiment config must contain an M7 mapping")
    events = config["M7"].get("events")
    if not isinstance(events, dict) or not events:
        raise ValueError("experiment config must declare M7.events")
    return {str(name): str(target) for name, target in events.items()}


def _audit_report(
    catalog: pd.DataFrame,
    source: pd.DataFrame,
    *,
    input_path: Path,
    catalog_path: Path,
    config_path: Path | None,
) -> dict[str, Any]:
    report = audit_event_episode_catalog(catalog, source)
    report.update(
        {
            "input_path": _portable_path(input_path),
            "input_sha256": file_sha256(input_path),
            "catalog_path": _portable_path(catalog_path),
            "catalog_file_sha256": (
                _file_bytes_sha256(catalog_path) if catalog_path.is_file() else None
            ),
            "config_path": (
                _portable_path(config_path) if config_path is not None else None
            ),
            "config_sha256": (
                file_sha256(config_path) if config_path is not None else None
            ),
            "evidence_role": "event_design_catalog",
            "formal_evidence": False,
        }
    )
    return report


def _build(args: argparse.Namespace) -> dict[str, Any]:
    source = pd.read_parquet(args.input)
    catalog = generate_event_episode_catalog(
        source,
        data_version=args.data_version,
        evaluation_split=args.evaluation_split,
        source_split=args.source_split,
        declared_events=_declared_events(args.config),
        station_ids=args.station_ids,
        minimum_training_samples=args.minimum_training_samples,
        control_context_days=args.control_context_days,
    )
    _atomic_catalog(catalog, args.catalog, overwrite=args.overwrite)
    stored = load_event_episode_catalog(
        args.catalog,
        expected_data_version=args.data_version,
        expected_evaluation_split=args.evaluation_split,
    )
    report = _audit_report(
        stored,
        source,
        input_path=args.input,
        catalog_path=args.catalog,
        config_path=args.config,
    )
    _atomic_json(report, args.audit_output, overwrite=args.overwrite)
    return report


def _audit(args: argparse.Namespace) -> dict[str, Any]:
    source = pd.read_parquet(args.input)
    catalog = load_event_episode_catalog(args.catalog)
    report = _audit_report(
        catalog,
        source,
        input_path=args.input,
        catalog_path=args.catalog,
        config_path=None,
    )
    _atomic_json(report, args.audit_output, overwrite=args.overwrite)
    return report


def main() -> None:
    args = build_parser().parse_args()
    report = _build(args) if args.command == "build" else _audit(args)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
