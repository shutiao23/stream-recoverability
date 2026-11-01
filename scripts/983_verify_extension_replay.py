#!/usr/bin/env python3
"""Replay the post-review extension from an extracted candidate package.

The package carries compact reference, mask and D2 annual inputs so the
818-archive calendar extension can be recomputed without the restricted
leave-one-year-out case parquet. The comparison checks schema, keys, labels,
legal missing values, finite values and every declared science table; NaN is
never used as a passing shortcut.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import revision_table_spec

DEST = ROOT / "dist/wrr_final_candidate_20261101_r2.zip"
RELATIVE = Path("results/wrr_final_revision_20261031")
PAPER_RELATIVE = Path("paper/wrr_tr")
TABLE_NAMES = list(revision_table_spec.TABLES)
PAPER_FILES = [
    "stanford_revision_values.tex",
    "stanford_calendar_table.tex",
    "stanford_geometry_table.tex",
]
TOLERANCE = 1e-12


class ReplayComparisonError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail(message: str) -> None:
    raise ReplayComparisonError(message)


def _label_values(series: pd.Series) -> pd.Series:
    return series.astype(object).where(series.notna(), "\x00__NA__").astype(str)


def compare_table(before_path: Path, after_path: Path, spec: dict) -> dict:
    """Compare one declared table without letting NaN or labels escape checks."""
    before = pd.read_csv(before_path)
    after = pd.read_csv(after_path)
    name = Path(before_path).name
    if list(before.columns) != list(after.columns):
        _fail(f"{name} column sets differ")
    if list(before.columns) != list(spec["columns"]):
        _fail(f"{name} columns differ from table_spec.json")
    keys = spec["keys"]
    if not set(keys).issubset(before.columns):
        _fail(f"{name} is missing a declared primary key")
    for label, frame in [("before", before), ("after", after)]:
        if frame[keys].isna().any().any():
            _fail(f"{name} has a missing primary key in {label}")
        if frame.duplicated(keys).any():
            _fail(f"{name} has duplicate primary keys in {label}")
        allowed = revision_table_spec.allowed_nan_mask(frame, spec)
        unexpected = frame.isna() & ~allowed
        if unexpected.any().any():
            locations = unexpected.stack()
            _fail(f"{name} has an unexpected NaN in {label} at {locations[locations].index[:3].tolist()}")
    before = before.sort_values(keys).reset_index(drop=True)
    after = after.sort_values(keys).reset_index(drop=True)
    if not before[keys].equals(after[keys]):
        _fail(f"{name} key set or key order differs after alignment")
    for column in spec["labels"]:
        if not _label_values(before[column]).equals(_label_values(after[column])):
            _fail(f"{name}.{column} label differs")
    max_difference = 0.0
    finite_pairs = 0
    nan_pairs = 0
    for column in spec["numeric"]:
        left = pd.to_numeric(before[column], errors="coerce").astype(float)
        right = pd.to_numeric(after[column], errors="coerce").astype(float)
        if (before[column].notna() & left.isna()).any() or (after[column].notna() & right.isna()).any():
            _fail(f"{name}.{column} contains non-numeric text")
        if np.isinf(left).any() or np.isinf(right).any():
            _fail(f"{name}.{column} contains infinity")
        if not left.isna().equals(right.isna()):
            _fail(f"{name}.{column} NaN pattern differs")
        nan_pairs += int(left.isna().sum())
        finite = ~left.isna()
        finite_pairs += int(finite.sum())
        if finite.any():
            difference = (left[finite] - right[finite]).abs()
            if not np.isfinite(difference).all():
                _fail(f"{name}.{column} produced a non-finite difference")
            max_difference = max(max_difference, float(difference.max()))
    if not np.isfinite(max_difference) or max_difference > TOLERANCE:
        _fail(f"{name} exceeds tolerance: {max_difference}")
    return {
        "rows": int(len(before)),
        "keys": keys,
        "numeric_columns": len(spec["numeric"]),
        "label_columns": len(spec["labels"]),
        "finite_pairs": finite_pairs,
        "nan_pairs": nan_pairs,
        "max_finite_difference": max_difference,
    }


def verify_manifest(root: Path, relative: Path) -> dict:
    manifest_path = root / relative / "data_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    outputs = manifest.get("outputs", {})
    if "data_manifest.json" in outputs:
        _fail("data_manifest.json must not record its own hash")
    verified = 0
    for label, expected in outputs.items():
        path = root / relative / label
        if not path.is_file():
            path = root / label
        if not path.is_file():
            path = Path(label)
        if not path.is_file():
            _fail("manifest output is missing: " + label)
        if digest(path) != expected:
            _fail("manifest hash is stale: " + label)
        verified += 1
    return {"outputs": verified, "self_hash_excluded": True}


def compare_scope(before: dict, after: dict) -> dict:
    fields = [
        "exploratory", "new_models_fit", "existing_outputs_changed",
        "archives", "geometry_rows", "family_counts", "reference_year_sets",
        "table_spec", "compact_replay",
    ]
    for field in fields:
        if before.get(field) != after.get(field):
            _fail("scope field differs: " + field)
    left = before.get("sign_disagreement", {})
    right = after.get("sign_disagreement", {})
    if set(left) != set(right):
        _fail("scope sign-disagreement families differ")
    for family, schemes in left.items():
        if set(schemes) != set(right[family]):
            _fail("scope sign-disagreement schemes differ: " + family)
        for scheme, entry in schemes.items():
            other = right[family][scheme]
            if entry.get("quantity") != other.get("quantity"):
                _fail("scope sign-disagreement quantity differs")
            if entry.get("count") != other.get("count"):
                _fail("scope sign-disagreement count differs")
            left_expected = entry.get("expected_count")
            right_expected = other.get("expected_count")
            if (left_expected is None) != (right_expected is None):
                _fail("scope sign-disagreement expected-count presence differs")
            if left_expected is not None and not np.isclose(
                left_expected, right_expected, rtol=0, atol=TOLERANCE
            ):
                _fail("scope sign-disagreement expected count differs")
    return {"compared_fields": fields + ["sign_disagreement"], "input_hashes_excluded": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEST)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results/final_release_20261101_r2/extension_replay.json",
    )
    args = parser.parse_args()
    archive = args.archive if args.archive.is_absolute() else ROOT / args.archive
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "stanford_extension_replay_v2",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "archive": str(archive),
        "archive_sha256": digest(archive),
        "tolerance": TOLERANCE,
        "scope": "Extracted-package replay of scripts/981_stanford_revision.py using compact inputs; no model refit and no raw-data reconstruction.",
        "comparison": "Schema, primary keys, labels, legal NaN positions, finite values and every declared table; JSON has no NaN or Inf.",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="wrr_extension_replay_") as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(archive) as zipped:
                if zipped.testzip():
                    _fail("ZIP CRC failure")
                zipped.extractall(root)
            reference = root / "extension_reference"
            shutil.copytree(root / RELATIVE, reference)
            for name in PAPER_FILES:
                target = reference / PAPER_RELATIVE / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / PAPER_RELATIVE / name, target)
            process = subprocess.run(
                [sys.executable, "scripts/981_stanford_revision.py"],
                cwd=root,
                text=True,
                capture_output=True,
            )
            if process.returncode:
                _fail("Extension replay failed: " + (process.stdout + process.stderr)[-4000:])
            spec_document = json.loads((reference / "table_spec.json").read_text())
            replay_spec_document = json.loads((root / RELATIVE / "table_spec.json").read_text())
            if spec_document != replay_spec_document:
                _fail("table_spec.json differs after replay")
            tables = {}
            for name in TABLE_NAMES:
                spec = spec_document["tables"][name]
                tables[name] = compare_table(reference / name, root / RELATIVE / name, spec)
            scope_before = json.loads((reference / "scope.json").read_text())
            scope_after = json.loads((root / RELATIVE / "scope.json").read_text())
            scope_check = compare_scope(scope_before, scope_after)
            manifests = {
                "reference": verify_manifest(root, Path("extension_reference")),
                "replay": verify_manifest(root, RELATIVE),
            }
            paper = {}
            for name in PAPER_FILES:
                same = digest(reference / PAPER_RELATIVE / name) == digest(root / PAPER_RELATIVE / name)
                paper[name] = same
                if not same:
                    _fail("Generated LaTeX differs: " + name)
            overall = max(item["max_finite_difference"] for item in tables.values())
            if not np.isfinite(overall) or overall > TOLERANCE:
                _fail(f"Overall finite difference exceeds tolerance: {overall}")
            report.update(
                status="passed",
                archives=int(scope_after["archives"]),
                geometry_rows=int(scope_after["geometry_rows"]),
                max_numeric_difference=overall,
                tables=tables,
                scope=scope_check,
                manifests=manifests,
                paper_tables=paper,
                replay_stdout_tail=process.stdout[-2000:],
            )
    except Exception as error:  # noqa: BLE001 - record any replay failure in the report
        report.update(status="failed", failure=str(error))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "report": str(output),
                      "max_numeric_difference": report.get("max_numeric_difference"),
                      "failure": report.get("failure")}, ensure_ascii=False, allow_nan=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
