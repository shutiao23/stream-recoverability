#!/usr/bin/env python3
"""Build a rights-filtered local archive candidate without minting a DOI."""

from __future__ import annotations

import hashlib
import json
import tarfile
from pathlib import Path

from stream_recoverability.governance import public_export_exclude

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
ARCHIVE = DIST / "stream-recoverability-v1.0.0-archive-candidate.tar.gz"
MANIFEST = DIST / "stream-recoverability-v1.0.0-archive-candidate.manifest.json"

TOP_LEVEL = {
    "CITATION.cff",
    "DATA_RIGHTS.md",
    "Dockerfile",
    "LICENSE",
    "Makefile",
    "README.md",
    "constraints.in",
    "constraints.txt",
    "environment.yml",
    "pyproject.toml",
    "study_manifest.yaml",
}
SAFE_PREFIXES = (
    "src/",
    "scripts/",
    "tests/",
    "configs/",
    "docs/",
    "paper/",
    "figures/main/",
    "results/revision/",
    "results/regulation_panel_v1_legacy_transport/",
    "results/predictions/",
)
SAFE_METADATA_FILES = {
    "metadata/candidate_stations.csv",
    "metadata/dam_metadata.csv",
    "metadata/data_dictionary.csv",
    "metadata/data_rights.csv",
    "metadata/editor_data_exception_approval.json",
    "metadata/gems_reviewer_data_upload.json",
    "metadata/quality_codebook.csv",
    "metadata/regulation_panel_freeze_v1.sha256",
    "metadata/source_documentation/README.md",
    "metadata/source_documentation/source_provenance_v3.md",
    "metadata/station_metadata.csv",
    "metadata/submission_author_metadata.json",
}
SAFE_RESULT_FILES = {
    "results/final_results_manifest.json",
    "results/audits/reproduction_report_acceptance_revision.json",
    "results/audits/restricted_hosting_audit.json",
    "results/audits/submission_gate.json",
}
IGNORED_SUFFIXES = {".pyc", ".pt", ".npz"}
IGNORED_NAMES = {"__pycache__", ".DS_Store"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _selected(relative: str) -> bool:
    if (
        relative in TOP_LEVEL
        or relative in SAFE_RESULT_FILES
        or relative in SAFE_METADATA_FILES
    ):
        return True
    return any(relative.startswith(prefix) for prefix in SAFE_PREFIXES)


def _candidate_files() -> list[Path]:
    candidates = {
        ROOT / relative
        for relative in TOP_LEVEL | SAFE_RESULT_FILES | SAFE_METADATA_FILES
    }
    for prefix in SAFE_PREFIXES:
        source = ROOT / prefix.rstrip("/")
        if source.is_file():
            candidates.add(source)
        elif source.is_dir():
            candidates.update(path for path in source.rglob("*") if path.is_file())
    files: list[Path] = []
    for path in candidates:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith((".git/", "dist/")):
            continue
        if any(part in IGNORED_NAMES for part in path.parts):
            continue
        if path.suffix in IGNORED_SUFFIXES or not _selected(relative):
            continue
        if public_export_exclude(relative):
            raise ValueError(f"selected archive path is restricted: {relative}")
        files.append(path)
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def main() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    files = _candidate_files()
    records = []
    with tarfile.open(ARCHIVE, "w:gz", compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(ROOT)
            archive.add(path, arcname=Path("stream-recoverability-v1.0.0") / relative)
            records.append(
                {
                    "path": relative.as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    payload = {
        "schema_version": "public_archive_candidate_v1",
        "status": "candidate_not_archival_record",
        "doi": None,
        "archive": ARCHIVE.name,
        "archive_bytes": ARCHIVE.stat().st_size,
        "archive_sha256": _sha256(ARCHIVE),
        "file_count": len(records),
        "files": records,
        "blockers": [
            "candidate is built from an uncommitted worktree",
            "author metadata and editor data exception remain open",
            "a repository service must mint the real DOI",
        ],
    }
    MANIFEST.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": payload["status"],
                "files": len(records),
                "archive_bytes": payload["archive_bytes"],
                "archive_sha256": payload["archive_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
