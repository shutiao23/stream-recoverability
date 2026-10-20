"""Shared paths, locked protocol and evidence for the scientific revision."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
READY = ROOT / "results" / "wrr_submission_ready"
RUN = READY / "major_revision_20261020c"
DOCS = ROOT / "docs" / "reviews" / "wrr_major_revision_20261020c"
CONFIG = ROOT / "configs" / "wrr_revision_20261020c.json"
LOCK = RUN / "protocol_lock.json"


def source_cases(protocol_name: str, cohort: str = "admission") -> Path:
    if cohort == "admission":
        return RUN / "r3_14_monitoring_replay" / protocol_name / "admission/cofailure_0/cases.parquet"
    if cohort == "controlled":
        return RUN / "r3_03_representative_recovery" / protocol_name / "cases.parquet"
    raise ValueError(f"Unknown analysis cohort: {cohort}")


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def protocol() -> dict:
    if not LOCK.exists():
        raise RuntimeError("Run scripts/348_wrr_revision_protocol.py before experiments")
    lock = json.loads(LOCK.read_text())
    for item in lock["inputs"].values():
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"Protocol changed after lock: {item['path']}")
    return json.loads(CONFIG.read_text())


def fingerprint(script: Path, inputs: dict[str, Path], **extra) -> dict:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": commit,
        "script": {"path": str(script.relative_to(ROOT)), "sha256": digest(script)},
        "protocol_lock_sha256": digest(LOCK) if LOCK.exists() else None,
        "inputs": {
            name: {"path": str(path.resolve()), "sha256": digest(path)}
            for name, path in inputs.items()
        },
        **extra,
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
