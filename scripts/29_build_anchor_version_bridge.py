#!/usr/bin/env python3
"""Relabel frozen v1 anchors for published_v2 after semantic equivalence checks.

The bridge deliberately records structural evidence rather than content hashes.
It never chooses or moves an anchor and never inspects model performance.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_long(path: Path, expected_version: str) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    required = {
        "date",
        "station_id",
        "variable",
        "value",
        "natural_observed",
        "quality_approved",
        "data_version",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{path} is missing columns: {missing}")
    versions = tuple(frame["data_version"].dropna().astype(str).unique())
    if versions != (expected_version,):
        raise ValueError(f"{path} carries {versions}, expected {expected_version!r}")
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"]).dt.normalize()
    result = result.set_index(["date", "station_id", "variable"], verify_integrity=True)
    return result.sort_index()


def _anchor_keys(catalog: pd.DataFrame) -> pd.MultiIndex:
    dates = pd.to_datetime(catalog["center_date"]).dt.normalize()
    rows: list[tuple[pd.Timestamp, str, str]] = []
    for date, station, targets in zip(
        dates,
        catalog["station_id"].astype(str),
        catalog["target"].astype(str),
        strict=True,
    ):
        for target in targets.split("_"):
            rows.append((date, station, target))
    return pd.MultiIndex.from_tuples(rows, names=["date", "station_id", "variable"])


def _bridge_catalog(
    source_path: Path,
    output_path: Path,
    *,
    v1: pd.DataFrame,
    v2: pd.DataFrame,
) -> dict[str, object]:
    catalog = pd.read_csv(source_path)
    required = {
        "anchor_id",
        "center_date",
        "center_index",
        "station_id",
        "target",
        "data_version",
    }
    missing = sorted(required.difference(catalog.columns))
    if missing:
        raise ValueError(f"{source_path} is missing columns: {missing}")
    if set(catalog["data_version"].astype(str)) != {"published_v1"}:
        raise ValueError(f"{source_path} is not a published_v1 catalog")
    keys = _anchor_keys(catalog)
    left = v1.reindex(keys)
    right = v2.reindex(keys)
    if left["value"].isna().any() or right["value"].isna().any():
        raise ValueError(f"{source_path} points to missing anchor truth")
    if not left["value"].equals(right["value"]):
        raise ValueError(f"{source_path} anchor truth differs between v1 and v2")
    legacy = left["quality_approved"].fillna(False).astype(bool)
    analysis = right["analysis_eligible"].fillna(False).astype(bool)
    if not legacy.equals(analysis):
        raise ValueError(f"{source_path} eligibility differs between v1 and v2")
    if (
        not left["natural_observed"]
        .fillna(False)
        .astype(bool)
        .equals(right["natural_observed"].fillna(False).astype(bool))
    ):
        raise ValueError(f"{source_path} natural-observation status differs")

    bridged = catalog.copy()
    bridged["anchor_id"] = bridged["anchor_id"].str.replace(
        "publishedv1", "publishedv2", regex=False
    )
    bridged["data_version"] = "published_v2"
    if bridged["anchor_id"].duplicated().any():
        raise ValueError("bridged anchor IDs are not unique")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bridged.to_csv(output_path, index=False)
    return {
        "source_catalog": str(source_path.relative_to(PROJECT_ROOT)),
        "output_catalog": str(output_path.relative_to(PROJECT_ROOT)),
        "anchor_count": int(len(bridged)),
        "truth_cells_checked": int(len(keys)),
        "known_issue_anchor_cells": int(
            right["known_issue_flag"].fillna(False).astype(bool).sum()
        ),
        "status": "equivalent",
    }


def build_bridge() -> dict[str, object]:
    v1 = _load_long(
        PROJECT_ROOT / "data_versions/published_v1/daily_long.parquet", "published_v1"
    )
    v2 = _load_long(
        PROJECT_ROOT / "data_versions/published_v2/daily_long.parquet", "published_v2"
    )
    if not v1.index.equals(v2.index):
        raise ValueError(
            "published_v1 and published_v2 do not share an identical row index"
        )
    reports = [
        _bridge_catalog(
            PROJECT_ROOT / "metadata/validation_anchors.csv",
            PROJECT_ROOT / "metadata/validation_anchors_v2.csv",
            v1=v1,
            v2=v2,
        ),
        _bridge_catalog(
            PROJECT_ROOT / "metadata/frontier_anchors.csv",
            PROJECT_ROOT / "metadata/frontier_anchors_v2.csv",
            v1=v1,
            v2=v2,
        ),
    ]
    report: dict[str, object] = {
        "schema_version": "anchor_version_bridge_v1",
        "source_data_version": "published_v1",
        "evaluation_data_version": "published_v2",
        "date_axis_equal": True,
        "row_index_equal": True,
        "catalogs": reports,
        "status": "complete",
    }
    output = PROJECT_ROOT / "metadata/anchor_bridge_published_v1_to_v2.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(build_bridge(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
