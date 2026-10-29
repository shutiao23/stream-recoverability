#!/usr/bin/env python3
"""Freeze current observation inputs and replay their arithmetic checks offline.

The new manifests pin present file contents. They do not authenticate historical
provenance, repair a historical manifest, or certify sensors, rights or models.
Historical manifests and all snapshot data remain unchanged.
"""
from __future__ import annotations

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_revision_20261029/replay_integrity"
SCHEMA = "current_observation_snapshot_v1"
SEMANTICS = "current content freeze, not evidence of past provenance"
SPECS = {
    "open_observed": {
        "legacy": "results/wrr_review_response_20261027/open_observed_record_snapshot/manifest.json",
        "base": "results/wrr_review_response_20261027/open_observed_record_snapshot",
        "manifest": "open_observed_current_manifest.json",
        "script": "scripts/654_verify_open_observed_snapshot.py",
        "report": "open_observed_reproduction.json",
    },
    "usgs_observed": {
        "legacy": "results/wrr_review_response_20261027/audit/usgs_observed_snapshot_manifest.json",
        "base": ".",
        "manifest": "usgs_observed_current_manifest.json",
        "script": "scripts/652_verify_usgs_observed_reproduction.py",
        "report": "usgs_observed_reproduction.json",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timestamp() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    return {"utc": now.isoformat(), "Asia/Shanghai": now.astimezone(ZoneInfo("Asia/Shanghai")).isoformat()}


def safe_file(base: Path, relative: str) -> Path:
    """Require a regular file under its fixed base, without symlink traversal."""
    relative_path = Path(relative)
    if not relative or relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"Unsafe snapshot path: {relative}")
    base = base.resolve()
    path = base / relative_path
    partial = base
    for part in relative_path.parts:
        partial = partial / part
        if partial.is_symlink():
            raise ValueError(f"Symlink in snapshot path: {relative}")
    if not path.is_file() or not path.resolve().is_relative_to(base):
        raise ValueError(f"Missing or unsafe snapshot file: {relative}")
    return path


def read_legacy(spec: dict, root: Path) -> tuple[dict, str]:
    legacy_path = safe_file(root, spec["legacy"])
    doc = json.loads(legacy_path.read_text())
    files = doc.get("files", [])
    names = [entry["path"] for entry in files]
    if not files or len(names) != len(set(names)):
        raise ValueError("Historical file list is empty or contains duplicate paths")
    return doc, sha256(legacy_path)


def verify_current_manifest(path: Path, spec: dict, root: Path = ROOT) -> dict:
    doc = json.loads(path.read_text())
    legacy, legacy_hash = read_legacy(spec, root)
    if (doc.get("schema_version") != SCHEMA or doc.get("freeze_semantics") != SEMANTICS
            or doc.get("historical_provenance_authenticated") is not False
            or doc.get("legacy_manifest", {}).get("path") != spec["legacy"]
            or doc["legacy_manifest"].get("sha256") != legacy_hash
            or doc.get("snapshot_file_base") != spec["base"]):
        raise ValueError("Current manifest scope or legacy-manifest identity is invalid")
    # Preserve every historical scope field; only file hashes belong to this new freeze.
    for key, value in legacy.items():
        if key != "files" and doc.get(key) != value:
            raise ValueError(f"Current manifest changed the historical scope field: {key}")
    files = doc.get("files", [])
    if [entry["path"] for entry in files] != [entry["path"] for entry in legacy["files"]]:
        raise ValueError("Current manifest file list differs from the historical list")
    base = root / spec["base"]
    for entry in files:
        current = safe_file(base, entry["path"])
        if (not entry.get("sha256") or sha256(current) != entry["sha256"]
                or current.stat().st_size != entry.get("bytes")):
            raise ValueError("Current snapshot content changed: " + entry["path"])
    return doc


def prepare_manifest(spec: dict, destination: Path, root: Path = ROOT) -> dict:
    legacy, legacy_hash = read_legacy(spec, root)
    if destination.exists():
        doc = verify_current_manifest(destination, spec, root)
        return {"manifest": str(destination), "sha256": sha256(destination),
                "files": len(doc["files"]), "reused_existing_current_freeze": True}
    doc = copy.deepcopy(legacy)
    doc.update(
        schema_version=SCHEMA,
        frozen_at=timestamp(),
        freeze_semantics=SEMANTICS,
        historical_provenance_authenticated=False,
        snapshot_file_base=spec["base"],
        legacy_manifest={
            "path": spec["legacy"], "sha256": legacy_hash,
            "files_without_sha256": sum(not entry.get("sha256") for entry in legacy["files"]),
        },
    )
    base = root / spec["base"]
    for entry in doc["files"]:
        file = safe_file(base, entry["path"])
        before = file.stat()
        entry["sha256"] = sha256(file)
        after = file.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ValueError("Snapshot changed while freezing: " + entry["path"])
        entry["bytes"] = after.st_size
    if sha256(root / spec["legacy"]) != legacy_hash:
        raise ValueError("Historical manifest changed while freezing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x") as stream:
        stream.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    verify_current_manifest(destination, spec, root)
    return {"manifest": str(destination), "sha256": sha256(destination),
            "files": len(doc["files"]), "reused_existing_current_freeze": False}


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def validate_replay_report(name: str, report: dict, manifest: dict, root: Path = ROOT) -> dict:
    """Require a fresh successful report and derive expected counts from pinned inputs."""
    if report.get("status") != "passed":
        raise ValueError(f"{name} verifier did not report passed: {report.get('error', report.get('status'))}")
    if name == "open_observed":
        base = root / SPECS[name]["base"]
        expected = {
            "included_stations": manifest["included_eligible_stations"],
            "original_stations": manifest["total_original_eligible_stations"],
            "witness_station_years": manifest["original_witnesses_included"],
            "rule_decisions_checked": len(read_csv(base / "witness_rules.csv")),
        }
    else:
        base = root / "results/additional_usgs_observed"
        references = read_csv(base / "raw_reference_summary.csv")
        expected = {
            "snapshot_files_verified": len(manifest["files"]),
            "station_count": manifest["station_count"],
            "complete_reference_station_years": sum(int(row["n_raw_approved_complete_years"]) for row in references),
            "witness_station_years": len(read_csv(base / "robust_record_witnesses.csv")),
        }
        for flag in ["requests_http_disabled_for_analysis", "selection_replayed_with_original_implementation", "independent_arithmetic_audit_passed"]:
            if report.get(flag) is not True:
                raise ValueError(f"{name} verifier did not establish {flag}")
    for field, expected_value in expected.items():
        if report.get(field) != expected_value:
            raise ValueError(f"{name} report scope mismatch for {field}: {report.get(field)} != {expected_value}")
    # Return the actual newly produced fields, not numbers copied from an old passing report.
    return {field: report[field] for field in expected}


def replay_one(name: str, spec: dict, manifest_path: Path, output: Path, root: Path = ROOT) -> dict:
    manifest = verify_current_manifest(manifest_path, spec, root)
    report_path = output / spec["report"]
    stdout_path, stderr_path = output / f"{name}.stdout.log", output / f"{name}.stderr.log"
    command = [sys.executable, str(root / spec["script"]), "--manifest", str(manifest_path), "--output", str(report_path)]
    record = {"command": command, "shell_command": shlex.join(command), "cwd": str(root),
              "manifest": str(manifest_path), "manifest_sha256": sha256(manifest_path),
              "verifier_sha256": sha256(root / spec["script"]), "started_at": timestamp(),
              "stdout_log": str(stdout_path), "stderr_log": str(stderr_path), "report": str(report_path)}
    # A failing command cannot accidentally reuse a previous passing report.
    if report_path.exists():
        report_path.unlink()
    with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
        proc = subprocess.run(command, cwd=root, stdout=stdout, stderr=stderr, check=False)
    record.update(returncode=proc.returncode, completed_at=timestamp())
    if proc.returncode != 0:
        record.update(status="failed", error="Verifier exited unsuccessfully; see saved logs")
        return record
    try:
        report = json.loads(report_path.read_text())
        record.update(actual_report_counts=validate_replay_report(name, report, manifest, root),
                      report_sha256=sha256(report_path))
        # Verify that the same frozen files survived the subprocess execution.
        verify_current_manifest(manifest_path, spec, root)
        record["status"] = "passed"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ["prepare", "replay"]:
        child = subparsers.add_parser(action)
        child.add_argument("--output", type=Path, default=OUT, help="Directory for current manifests, fresh reports and logs")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    record = {"schema_version": "current_observation_replay_v1", "action": args.action,
              "freeze_semantics": SEMANTICS, "historical_provenance_authenticated": False,
              "command": [sys.executable, *sys.argv], "started_at": timestamp(),
              "scope": "Current offline observation arithmetic and rule replay only; not whole-paper model reproduction, sensor verification or historical-provenance authentication.",
              "checks": {}}
    for name, spec in SPECS.items():
        try:
            manifest_path = output / spec["manifest"]
            if args.action == "prepare":
                record["checks"][name] = {"status": "passed", **prepare_manifest(spec, manifest_path)}
            else:
                record["checks"][name] = replay_one(name, spec, manifest_path, output)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            record["checks"][name] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    record["status"] = "passed" if all(item["status"] == "passed" for item in record["checks"].values()) else "failed"
    record["completed_at"] = timestamp()
    (output / f"{args.action}_report.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if record["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
