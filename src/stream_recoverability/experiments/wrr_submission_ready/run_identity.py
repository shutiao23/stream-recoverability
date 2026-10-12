"""Run identity: independent output directories, input hashes, fail-closed workers."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUT_ROOT = REPO_ROOT / "results" / "wrr_submission_ready" / "runs"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(repo: Path = REPO_ROOT) -> str | None:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


@dataclass
class RunManifest:
    run_id: str
    created_utc: str
    objective: str
    git_head: str | None
    python: str
    command: list[str]
    input_files: list[dict[str, Any]] = field(default_factory=list)
    output_files: list[dict[str, Any]] = field(default_factory=list)
    status: str = "running"
    error: str | None = None

    def add_input(self, path: Path) -> None:
        resolved = path.resolve()
        self.input_files.append(
            {
                "path": str(resolved.relative_to(REPO_ROOT)) if resolved.is_relative_to(REPO_ROOT) else str(resolved),
                "sha256": sha256_file(resolved) if resolved.is_file() else None,
                "bytes": resolved.stat().st_size if resolved.is_file() else None,
                "exists": resolved.exists(),
            }
        )

    def add_output(self, path: Path) -> None:
        resolved = path.resolve()
        self.output_files.append(
            {
                "path": str(resolved.relative_to(REPO_ROOT)) if resolved.is_relative_to(REPO_ROOT) else str(resolved),
                "sha256": sha256_file(resolved) if resolved.is_file() else None,
                "bytes": resolved.stat().st_size if resolved.is_file() else None,
            }
        )

    def write(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "run_manifest.json"
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True) + "\n")
        return path


def new_run(objective: str, *, out_root: Path = DEFAULT_OUT_ROOT) -> tuple[Path, RunManifest]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}_{os.getpid()}"
    directory = out_root / run_id
    directory.mkdir(parents=True, exist_ok=False)
    manifest = RunManifest(
        run_id=run_id,
        created_utc=datetime.now(timezone.utc).isoformat(),
        objective=objective,
        git_head=git_head(),
        python=sys.version.replace("\n", " "),
        command=list(sys.argv),
    )
    manifest.write(directory)
    return directory, manifest


def run_fail_closed(
    objective: str,
    work: Callable[[Path, RunManifest], Iterable[Path] | None],
    *,
    inputs: Iterable[Path] = (),
    out_root: Path = DEFAULT_OUT_ROOT,
) -> Path:
    """Execute ``work`` in a fresh directory; on any exception mark failed and re-raise."""

    directory, manifest = new_run(objective, out_root=out_root)
    for path in inputs:
        manifest.add_input(Path(path))
    manifest.write(directory)
    try:
        outputs = work(directory, manifest) or []
        for path in outputs:
            manifest.add_output(Path(path))
        manifest.status = "success"
        manifest.write(directory)
        return directory
    except Exception as exc:  # noqa: BLE001 — fail closed by design
        manifest.status = "failed"
        manifest.error = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        manifest.write(directory)
        # Do not leave a SUCCESS marker beside partial tables.
        (directory / "FAILED").write_text(manifest.error)
        raise


def preflight_current_study() -> dict[str, Any]:
    """Cheap checks before a rebuild: manifest presence, claim registry, code entrypoints."""

    root = REPO_ROOT / "results" / "wrr_submission_ready"
    required = [
        root / "claim_registry.csv",
        root / "current_data_manifest.csv",
        root / "measurement_provenance.csv",
        root / "prior_access_ledger_reserved_networks.csv",
        root / "P0_06_method_freeze.json",
        root / "CONFIRMATION_PROTOCOL_SEALED.md",
    ]
    report = {"ok": True, "checks": []}
    for path in required:
        exists = path.is_file()
        report["checks"].append({"path": str(path.relative_to(REPO_ROOT)), "exists": exists})
        report["ok"] = report["ok"] and exists
    manifest = pd_safe_read(root / "current_data_manifest.csv")
    if manifest is not None:
        missing = int((manifest["status"] != "present").sum()) if "status" in manifest.columns else -1
        report["checks"].append({"path": "current_data_manifest.csv", "n_missing_inputs": missing})
        report["ok"] = report["ok"] and missing == 0
    return report


def pd_safe_read(path: Path):
    if not path.is_file():
        return None
    import pandas as pd

    return pd.read_csv(path)
