#!/usr/bin/env python3
"""Replay the post-review extension from an extracted candidate package.

The package carries compact reference, mask and D2 annual inputs so the
818-archive calendar extension can be recomputed without the restricted
leave-one-year-out case parquet. This checks denominators, numeric summaries and
the generated SI tables within a stated tolerance.
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
DEST = ROOT / "dist/wrr_final_candidate_20261031_r2.zip"
RELATIVE = Path("results/wrr_final_revision_20261031")
NUMERIC_FILES = [
    "retention_family_summary.csv",
    "retention_geometry_cases.csv",
    "reference_truths.csv",
    "annual_predictions_compact.csv",
]
EXACT_FILES = [
    "retention_choice_counts.csv",
    "reference_year_sets.csv",
    "estimator_availability.csv",
    "estimator_paired_comparisons.csv",
    "estimator_unavailable_subset.csv",
]
TABLE_FILES = [
    "paper/wrr_tr/stanford_revision_values.tex",
    "paper/wrr_tr/stanford_calendar_table.tex",
    "paper/wrr_tr/stanford_geometry_table.tex",
]
TOLERANCE = 1e-12


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEST)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results/final_release_20261031_r2/extension_replay.json",
    )
    args = parser.parse_args()
    archive = args.archive if args.archive.is_absolute() else ROOT / args.archive
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "stanford_extension_replay_v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "archive": str(archive),
        "archive_sha256": digest(archive),
        "tolerance": TOLERANCE,
        "scope": "Extracted-package replay of scripts/981_stanford_revision.py using compact inputs; no model refit and no raw-data reconstruction.",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="wrr_extension_replay_") as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(archive) as zipped:
                if zipped.testzip():
                    raise RuntimeError("ZIP CRC failure")
                zipped.extractall(root)
            reference = root / "extension_reference"
            shutil.copytree(root / RELATIVE, reference)
            for relative in TABLE_FILES:
                target = reference / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / relative, target)
            process = subprocess.run(
                [sys.executable, "scripts/981_stanford_revision.py"],
                cwd=root,
                text=True,
                capture_output=True,
            )
            if process.returncode:
                raise RuntimeError("Extension replay failed: " + (process.stdout + process.stderr)[-4000:])
            differences = {}
            for name in NUMERIC_FILES:
                before = pd.read_csv(reference / name)
                after = pd.read_csv(root / RELATIVE / name)
                if before.shape != after.shape:
                    raise RuntimeError("Extension replay changed table dimensions: " + name)
                numeric = [column for column in before.columns if pd.api.types.is_numeric_dtype(before[column])]
                if numeric:
                    differences[name] = float(
                        np.max(np.abs(before[numeric].to_numpy(float) - after[numeric].to_numpy(float)))
                    )
            exact = {}
            for name in EXACT_FILES:
                same = digest(reference / name) == digest(root / RELATIVE / name)
                exact[name] = same
                if not same:
                    raise RuntimeError("Exact replay table differs: " + name)
            tables = {}
            for relative in TABLE_FILES:
                same = digest(reference / relative) == digest(root / relative)
                tables[relative] = same
                if not same:
                    raise RuntimeError("Generated LaTeX differs: " + relative)
            scope = json.loads((root / RELATIVE / "scope.json").read_text())
            if scope["archives"] != 1623 or scope["geometry_rows"] != 8115:
                raise RuntimeError("Replayed extension denominator changed")
            if differences and max(differences.values()) > TOLERANCE:
                raise RuntimeError("Replayed numeric values exceed tolerance")
            report.update(
                status="passed",
                archives=int(scope["archives"]),
                geometry_rows=int(scope["geometry_rows"]),
                max_numeric_difference=max(differences.values(), default=0.0),
                numeric_differences=differences,
                exact_tables=exact,
                generated_tables=tables,
                replay_stdout_tail=process.stdout[-2000:],
            )
    except Exception as error:  # noqa: BLE001 - record any replay failure in the report
        report.update(status="failed", failure=str(error))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "report": str(output),
                      "max_numeric_difference": report.get("max_numeric_difference"),
                      "failure": report.get("failure")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
