#!/usr/bin/env python3
"""Add NASA POWER Rs to the internal panel and rebuild data versions.

Does not edit T/F/L/Ta/P/W/RH/DH values. Existing version directories are
replaced only after hydro invariants pass. Hashes are computed from the new
files; they are not invented beforehand.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from stream_recoverability.data.internal_rs import rebuild_internal_rs_panel
from stream_recoverability.data.prepare import (
    fit_train_scaler,
    to_daily_wide,
    write_prepared_outputs,
)
from stream_recoverability.data.versions import DATA_VERSION_NAMES, build_data_versions
from stream_recoverability.experiments.contracts import file_sha256


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-long",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed" / "daily_long.parquet",
    )
    parser.add_argument(
        "--station-metadata",
        type=Path,
        default=PROJECT_ROOT / "metadata" / "station_metadata.csv",
    )
    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed",
    )
    parser.add_argument(
        "--data-versions-root",
        type=Path,
        default=PROJECT_ROOT / "data_versions",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "results" / "data_audit" / "internal_nasa_rs_rebuild.json",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = __import__("pandas").read_parquet(args.input_long)
    if "data_version" in source.columns:
        source = source.drop(columns=["data_version", "data_version_action"], errors="ignore")
    merged, report = rebuild_internal_rs_panel(
        source,
        args.station_metadata,
    )
    wide, measurement_columns = to_daily_wide(merged)
    scaler = fit_train_scaler(wide, measurement_columns)
    write_prepared_outputs(merged, wide, scaler, args.processed_dir)

    staging = args.data_versions_root.parent / f"{args.data_versions_root.name}_rs_staging"
    if staging.exists():
        shutil.rmtree(staging)
    manifests = build_data_versions(
        args.processed_dir / "daily_long.parquet",
        staging,
        DATA_VERSION_NAMES,
    )
    backup = args.data_versions_root.parent / f"{args.data_versions_root.name}_pre_rs"
    if backup.exists():
        shutil.rmtree(backup)
    args.data_versions_root.rename(backup)
    staging.rename(args.data_versions_root)

    report["processed_daily_long_sha256"] = file_sha256(
        args.processed_dir / "daily_long.parquet"
    )
    report["processed_daily_wide_sha256"] = file_sha256(
        args.processed_dir / "daily_wide.parquet"
    )
    report["data_version_artifacts"] = {
        name: {
            "daily_long_sha256": manifest["artifacts"]["daily_long.parquet"]["sha256"],
            "daily_wide_sha256": manifest["artifacts"]["daily_wide.parquet"]["sha256"],
            "version_manifest_sha256": file_sha256(
                args.data_versions_root / name / "version_manifest.json"
            ),
        }
        for name, manifest in manifests.items()
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["data_version_artifacts"], indent=2))


if __name__ == "__main__":
    main()
