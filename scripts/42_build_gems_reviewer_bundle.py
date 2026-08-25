#!/usr/bin/env python3
"""Build a local confidential GEMS reviewer bundle. Does not upload."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "private" / "gems_reviewer_bundle"
INVENTORY = ROOT / "metadata" / "gems_reviewer_bundle_inventory.json"
UPLOAD_RECORD = ROOT / "metadata" / "gems_reviewer_data_upload.json"
DATA_RIGHTS = ROOT / "metadata" / "data_rights.csv"
TIME_RANGE = "2006-01-01/2020-12-31"
CONFIDENTIAL_TYPE = "Data File(s) for Peer Review (will not publish)"
IGNORED_SUFFIXES = {".pyc", ".pt", ".pth"}
IGNORED_NAMES = {"__pycache__", ".DS_Store"}

DOCUMENTATION = (
    "DATA_RIGHTS.md",
    "metadata/data_rights.csv",
    "metadata/data_dictionary.csv",
    "metadata/station_metadata.csv",
    "paper/editor_data_exception_request.md",
)
RAW_CSVS = ("data/raw/b1.csv", "data/raw/s2.csv", "data/raw/p3.csv")
PROCESSED_FILES = (
    "data/processed/daily_long.parquet",
    "data/processed/daily_wide.parquet",
    "data/processed/event_labels.parquet",
    "data/processed/scaler.json",
    "data/processed/splits/train.parquet",
    "data/processed/splits/validation.parquet",
    "data/processed/splits/test.parquet",
)
VERSION_TREES = (
    "data_versions/published_v1",
    "data_versions/published_v2",
    "data_versions/no_s2_suspect_v1",
    "data_versions/no_s2_suspect_v2",
    "data_versions/b1_no_level_v1",
    "data_versions/b1_no_level_v2",
    "data_versions/b1_shift_sensitivity_v1",
    "data_versions/b1_shift_sensitivity_v2",
)
VERSION_RELATIVE_FILES = (
    "version_manifest.json",
    "daily_long.parquet",
    "daily_wide.parquet",
    "scaler.json",
    "splits/train.parquet",
    "splits/validation.parquet",
    "splits/test.parquet",
)
MASK_FILES = (
    "masks/test/masks.npz",
    "masks/test/manifest.json",
    "masks/test/manifest.csv",
    "masks/validation/masks.npz",
    "masks/validation/manifest.json",
    "masks/validation/manifest.csv",
)
ANCHOR_FILES = (
    "metadata/validation_anchors.csv",
    "metadata/validation_anchors_v2.csv",
    "metadata/frontier_anchors.csv",
    "metadata/frontier_anchors_v2.csv",
    "metadata/event_episode_catalog.csv",
    "metadata/event_episode_catalog_v2.csv",
    "metadata/event_episode_catalog.audit.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_rights() -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not DATA_RIGHTS.is_file():
        return mapping
    with DATA_RIGHTS.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            artifact = (row.get("artifact") or "").strip()
            if not artifact:
                continue
            allowed = (row.get("redistribution_allowed") or "").strip().lower()
            license_name = (row.get("license") or "").strip()
            if allowed == "true":
                mapping[artifact] = f"public:{license_name or 'unspecified'}"
            elif allowed == "restricted":
                mapping[artifact] = f"restricted:{license_name or 'bitmask_or_dates'}"
            else:
                mapping[artifact] = f"restricted:{license_name or 'no_redistribution'}"
    return mapping


def _rights_class(relative: str, rights: dict[str, str]) -> str:
    if relative in rights:
        return rights[relative]
    for artifact, label in sorted(rights.items(), key=lambda item: -len(item[0])):
        if relative == artifact or relative.startswith(artifact.rstrip("/") + "/"):
            return label
    if relative in {"README.md", "MANIFEST.json"}:
        return "bundle_index"
    if relative.startswith("data/raw/"):
        return "restricted:mixed_most_restrictive"
    if relative.startswith("data/processed/") or relative.startswith("data_versions/"):
        return "restricted:mixed_inherited"
    if relative.startswith("masks/"):
        return "restricted:compact_bitmask_or_hidden_dates"
    if relative.startswith("metadata/") and any(
        token in relative
        for token in ("anchors", "event_episode_catalog")
    ):
        return "restricted:anchor_or_event_catalog"
    if relative.startswith(("DATA_RIGHTS.md", "metadata/", "paper/")):
        return "public_project_metadata"
    return "unclassified"


def _skip(path: Path) -> bool:
    return any(part in IGNORED_NAMES for part in path.parts) or path.suffix in IGNORED_SUFFIXES


def _expected_entries() -> list[dict[str, str]]:
    entries = [
        {"path": "README.md", "category": "bundle_index"},
        {"path": "MANIFEST.json", "category": "bundle_index"},
    ]
    entries.extend({"path": path, "category": "documentation"} for path in DOCUMENTATION)
    entries.extend({"path": path, "category": "raw_observations"} for path in RAW_CSVS)
    entries.extend({"path": path, "category": "processed_tables"} for path in PROCESSED_FILES)
    for tree in VERSION_TREES:
        for relative in VERSION_RELATIVE_FILES:
            entries.append(
                {
                    "path": f"{tree}/{relative}",
                    "category": "data_version_tree",
                }
            )
    entries.extend({"path": path, "category": "jinsha_masks"} for path in MASK_FILES)
    entries.extend(
        {"path": path, "category": "restricted_metadata_anchors"} for path in ANCHOR_FILES
    )
    return entries


def _copy_file(source: Path, relative: str) -> dict[str, object]:
    destination = BUNDLE / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "path": relative,
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def _walk_optional_tree(prefix: str) -> list[Path]:
    source = ROOT / prefix
    if not source.is_dir():
        return []
    files: list[Path] = []
    for path in source.rglob("*"):
        if path.is_file() and not _skip(path):
            files.append(path)
    return files


def _readme_text() -> str:
    return f"""# Confidential GEMS reviewer bundle

**File type in AGU GEMS:** {CONFIDENTIAL_TYPE}

This directory is a confidential peer-review packet. It is not a public
archive, not a Zenodo deposit, and not the rights-filtered candidate from
`scripts/40_build_public_archive_candidate.py`. Do not publish these files.
Do not treat this upload as a sublicense of yearbook, CMA, or WMO/CMA data.

## Time range

Daily series used in the Jinsha working tree cover **{TIME_RANGE}**.

## Stations and files

Internal hydrological stations in `data/raw/`:

| File | Station | River |
| --- | --- | --- |
| `data/raw/b1.csv` | B1 Batang | Jinsha |
| `data/raw/s2.csv` | S2 Shigu | Jinsha |
| `data/raw/p3.csv` | P3 Panzhihua | Jinsha |

Raw header:

`DATE,WTEMP,WLEVEL,FLOW,TEMP,WDSP,PRCP,RHMEAN,DH`

The CSVs do not embed station names, time zone, hydrological-day cutoff, or
per-value quality flags. Use `metadata/station_metadata.csv` and
`metadata/data_dictionary.csv` for those definitions.

## Fields and units

| Raw name | Standard | Meaning | Raw unit | Notes |
| --- | --- | --- | --- | --- |
| DATE | date | observation date | local calendar day | time zone not in the file |
| WTEMP | T | mean stream temperature | degC | Yearbook Vol. VI; restricted |
| WLEVEL | L | mean water-surface level | m | Yearbook Vol. VI; restricted |
| FLOW | F | mean discharge | m3/s | Yearbook Vol. VI; restricted |
| TEMP | Ta | mean air temperature | degC | WMO/CMA matching GSOD; restricted |
| WDSP | W | mean wind speed | knot | convert by 0.514444 to m/s; restricted |
| PRCP | P | total precipitation | inch | convert by 25.4 to mm/day; restricted |
| RHMEAN | RH | mean relative humidity | percent | CMA V3.0; restricted |
| DH | DH | bright sunshine duration | hour | CMA V3.0; Jinsha sensitivity only |
| Rs | Rs | all-sky shortwave | MJ/m^2/day | NASA POWER; public source, does not license the mixed CSV |

A file that mixes Yearbook, CMA, and WMO/CMA columns takes the most
restrictive reading: the whole CSV is not redistributable.

## What else is in this bundle

- `data/processed/` derived tables and the train-only scaler
- `data_versions/published_*` and the three sensitivity families (v1 and v2)
- `masks/test` and `masks/validation` boolean mask libraries (no hydrology
  values in `masks.npz`, but manifests list the restricted calendar)
- Restricted validation/frontier anchors and event-episode catalogs
- `DATA_RIGHTS.md` and `metadata/data_rights.csv`

## Reviewer access rule

Editors mediate access under GEMS confidentiality. This upload is not
permission to redistribute daily values, not a CMA transfer, and not a public
data release. After review, do not publish these files.
"""


def _assert_upload_record_untouched() -> None:
    if not UPLOAD_RECORD.is_file():
        return
    payload = json.loads(UPLOAD_RECORD.read_text(encoding="utf-8"))
    if payload.get("uploaded") is True:
        raise SystemExit(
            "refusing to rewrite a bundle after gems_reviewer_data_upload.json "
            "already records uploaded=true; move that record aside first"
        )


def main() -> None:
    _assert_upload_record_untouched()
    rights = _load_rights()
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    BUNDLE.mkdir(parents=True, exist_ok=True)

    copied: dict[str, dict[str, object]] = {}
    skipped_missing_trees: list[str] = []

    for relative in DOCUMENTATION:
        source = ROOT / relative
        if source.is_file():
            copied[relative] = _copy_file(source, relative)

    for relative in (*RAW_CSVS, *PROCESSED_FILES, *MASK_FILES, *ANCHOR_FILES):
        source = ROOT / relative
        if source.is_file() and not _skip(source):
            copied[relative] = _copy_file(source, relative)

    for tree in VERSION_TREES:
        files = _walk_optional_tree(tree)
        if not files:
            skipped_missing_trees.append(tree)
            continue
        for source in files:
            relative = source.relative_to(ROOT).as_posix()
            copied[relative] = _copy_file(source, relative)

    readme_relative = "README.md"
    (BUNDLE / readme_relative).write_text(_readme_text(), encoding="utf-8")
    copied[readme_relative] = {
        "path": readme_relative,
        "bytes": (BUNDLE / readme_relative).stat().st_size,
        "sha256": _sha256(BUNDLE / readme_relative),
    }

    manifest_records = []
    for relative in sorted(copied):
        record = dict(copied[relative])
        record["rights_class"] = _rights_class(relative, rights)
        manifest_records.append(record)

    manifest_payload = {
        "schema_version": "gems_reviewer_bundle_manifest_v1",
        "confidential_file_type": CONFIDENTIAL_TYPE,
        "not_a_public_archive": True,
        "time_range": TIME_RANGE,
        "file_count": len(manifest_records),
        "bundle_bytes": sum(int(item["bytes"]) for item in manifest_records),
        "skipped_missing_trees": skipped_missing_trees,
        "files": manifest_records,
        "note": (
            "Confidential local bundle only. MANIFEST.json indexes the copied "
            "files and is omitted from this file list so its own hash stays "
            "stable. Do not set metadata/gems_reviewer_data_upload.json "
            "uploaded=true until the GEMS upload is finished."
        ),
    }
    manifest_path = BUNDLE / "MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    expected = []
    missing = []
    for item in _expected_entries():
        found = item["path"] in copied or item["path"] == "MANIFEST.json"
        row = {
            "path": item["path"],
            "found": found,
            "category": item["category"],
            "rights_class": _rights_class(item["path"], rights),
        }
        expected.append(row)
        if not found:
            missing.append(item["path"])

    additional = sorted(
        path
        for path in copied
        if path not in {item["path"] for item in expected}
    )
    inventory = {
        "schema_version": "gems_reviewer_bundle_inventory_v1",
        "status": "local_bundle_only_not_uploaded",
        "confidential_file_type": CONFIDENTIAL_TYPE,
        "not_a_public_archive": True,
        "gems_upload_complete": False,
        "bundle_directory": "private/gems_reviewer_bundle/",
        "bundle_gitignored": True,
        "time_range": TIME_RANGE,
        "expected_file_count": len(expected),
        "found_expected_count": sum(1 for item in expected if item["found"]),
        "missing_expected_files": missing,
        "additional_files_copied": additional,
        "skipped_missing_trees": skipped_missing_trees,
        "copied_file_count": len(manifest_records) + 1,
        "expected_files": expected,
        "note": (
            "Values-free inventory: logical paths and found flags only. "
            "Observation values stay in the gitignored private bundle. "
            "Do not set metadata/gems_reviewer_data_upload.json uploaded=true "
            "until the confidential GEMS upload is done."
        ),
    }
    INVENTORY.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    if UPLOAD_RECORD.is_file():
        upload = json.loads(UPLOAD_RECORD.read_text(encoding="utf-8"))
        if upload.get("uploaded") is True:
            raise SystemExit("upload record was changed to uploaded=true; aborting")

    print(
        json.dumps(
            {
                "status": "local_bundle_only_not_uploaded",
                "files": len(manifest_records) + 1,
                "indexed_files": len(manifest_records),
                "bundle_bytes": manifest_payload["bundle_bytes"]
                + manifest_path.stat().st_size,
                "missing_expected": missing,
                "skipped_missing_trees": skipped_missing_trees,
                "uploaded_flag_unchanged": True,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
