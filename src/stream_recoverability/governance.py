"""Submission, hosting, and evidence-snapshot helpers.

These functions record what is actually on disk. They do not invent formal
results or mint DOIs.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from stream_recoverability.data.quality import load_quality_codebook
from stream_recoverability.experiments.contracts import (
    DEFAULT_DESIGN_PATH,
    EXECUTABLE_DESIGN_VERSION,
    file_sha256,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RESTRICTED_PATH_PREFIXES = (
    "data/raw/",
    "data/processed/",
    "data_versions/published_v1/",
    "data_versions/published_v2/",
    "data_versions/no_s2_suspect_",
    "data_versions/b1_no_level_",
    "data_versions/b1_shift_sensitivity_",
    "masks/test/",
    "masks/validation/",
    "metadata/validation_anchors.csv",
    "metadata/frontier_anchors.csv",
    "metadata/event_episode_catalog.csv",
)
PUBLIC_SAFE_PREFIXES = (
    "src/",
    "scripts/",
    "tests/",
    "configs/",
    "paper/",
    "docs/",
    "metadata/data_dictionary.csv",
    "metadata/quality_codebook.csv",
    "metadata/data_rights.csv",
    "metadata/station_metadata.csv",
)


def _git(*arguments: str, cwd: Path = REPOSITORY_ROOT) -> str:
    completed = subprocess.run(
        ("git", "-C", str(cwd), *arguments),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def current_commit(repository: Path = REPOSITORY_ROOT) -> str:
    return _git("rev-parse", "HEAD", cwd=repository)


def worktree_clean(repository: Path = REPOSITORY_ROOT) -> bool:
    return _git("status", "--porcelain", cwd=repository) == ""


def load_design(path: str | Path = REPOSITORY_ROOT / DEFAULT_DESIGN_PATH) -> dict[str, Any]:
    document = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("design freeze must be a mapping")
    return document


def restricted_tracked_paths(repository: Path = REPOSITORY_ROOT) -> list[str]:
    listing = _git("ls-files", cwd=repository)
    if not listing:
        return []
    paths = []
    for relative in listing.splitlines():
        if any(relative.startswith(prefix) or relative == prefix.rstrip("/") for prefix in RESTRICTED_PATH_PREFIXES):
            paths.append(relative)
    return paths


def audit_restricted_hosting(repository: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Record whether restricted bytes are still on the public development tip."""

    paths = restricted_tracked_paths(repository)
    return {
        "status": "public_hosting_defect" if paths else "restricted_bytes_absent_from_tip",
        "public_hosting_defect": bool(paths),
        "restricted_tracked_path_count": len(paths),
        "restricted_tracked_paths": paths,
        "history_rewrite": "not_performed_in_this_wave",
        "reviewer_access_route": "agu_gems_confidential_data_files_for_peer_review",
        "note": (
            "Presence of restricted columns on the public GitHub tip is a hosting "
            "defect, not an open-data grant. History rewrite requires an institutional "
            "mirror and a coordinated force-push; this helper does not rewrite git."
        ),
    }


def roster_path(repository: Path = REPOSITORY_ROOT) -> Path | None:
    candidates = sorted(repository.glob("results/validation_funnel/**/finalized_model_roster_v1.json"))
    return candidates[-1] if candidates else None


def formal_manifest_path(repository: Path = REPOSITORY_ROOT) -> Path:
    return repository / "results/final_results_manifest.json"


def evidence_snapshot(repository: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Machine-readable snapshot of what the current commit can honestly claim."""

    design_path = repository / DEFAULT_DESIGN_PATH
    design = load_design(design_path)
    codebook = load_quality_codebook(repository / "metadata/quality_codebook.csv")
    unflagged = codebook.loc[codebook["qc_status"].eq("observed_unflagged")].iloc[0]
    hosting = audit_restricted_hosting(repository)
    roster = roster_path(repository)
    formal = formal_manifest_path(repository)
    manuscript = (repository / "paper/manuscript.md").read_text(encoding="utf-8")
    pending = manuscript.count("RESULTS_PENDING")
    return {
        "snapshot_schema_version": "evidence_snapshot_v3",
        "git_commit": current_commit(repository),
        "worktree_clean": worktree_clean(repository),
        "executable_design": EXECUTABLE_DESIGN_VERSION,
        "design_path": str(DEFAULT_DESIGN_PATH),
        "design_sha256": file_sha256(design_path),
        "design_version": design.get("design_version"),
        "primary_data_version": design.get("data_versions", {}).get("primary"),
        "max_epochs": design.get("training", {})
        .get("fixed_model_protocols", {})
        .get("common", {})
        .get("max_epochs"),
        "hit_epoch_limit_rejected": bool(
            design.get("training", {}).get("budget_rule", {}).get("reject_if_hit_epoch_limit")
        ),
        "dual_frontier_required": (
            design.get("statistics", {})
            .get("frontier_denominators", {})
            .get("best_simple_baseline_relative", {})
            .get("status")
            == "primary_required"
        ),
        "application_thresholds": design.get("statistics", {})
        .get("application_thresholds", {})
        .get("status"),
        "observed_unflagged_provider_qc_status": str(unflagged["provider_qc_status"]),
        "hosting": hosting,
        "finalized_model_roster": "present" if roster is not None else "pending",
        "roster_path": str(roster.relative_to(repository)) if roster is not None else None,
        "formal_results_manifest": "present" if formal.is_file() else "pending",
        "manuscript_results_pending_markers": pending,
        "current_protocol_result_claims": "none" if pending else "see_manuscript",
        "confirmatory_data": "not_opened",
        "confirmatory_evaluation": "not_run",
    }


def submission_gate(repository: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Fail closed until the P0 evidence chain actually exists."""

    snapshot = evidence_snapshot(repository)
    blockers: list[str] = []
    if snapshot["design_version"] != EXECUTABLE_DESIGN_VERSION:
        blockers.append("executable design is not design_freeze_v3")
    if snapshot["observed_unflagged_provider_qc_status"] == "approved":
        blockers.append("observed_unflagged is still marked provider-approved")
    if snapshot["finalized_model_roster"] != "present":
        blockers.append("finalized_model_roster_v1 is absent")
    if snapshot["formal_results_manifest"] != "present":
        blockers.append("current-protocol formal results manifest is absent")
    if snapshot["manuscript_results_pending_markers"]:
        blockers.append("manuscript still contains RESULTS_PENDING markers")
    if snapshot["hosting"]["public_hosting_defect"]:
        blockers.append("restricted bytes remain on the public development tip")
    if snapshot["confirmatory_evaluation"] != "complete":
        blockers.append("external evaluate-once confirmation has not completed")
    if not snapshot["dual_frontier_required"]:
        blockers.append("best-simple frontier is not required")
    passed = not blockers
    return {
        "passed": passed,
        "decision": "go" if passed else "no_go",
        "blockers": blockers,
        "snapshot": snapshot,
        "note": "A failing gate is the correct state until formal evidence exists.",
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    payload = {**payload, "document_sha256": digest}
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return destination


def public_export_exclude(relative: str) -> bool:
    return any(
        relative.startswith(prefix) or relative == prefix.rstrip("/")
        for prefix in RESTRICTED_PATH_PREFIXES
    )


def public_safe_paths(paths: Sequence[str]) -> list[str]:
    return [path for path in paths if not public_export_exclude(path)]


__all__ = [
    "RESTRICTED_PATH_PREFIXES",
    "audit_restricted_hosting",
    "evidence_snapshot",
    "public_safe_paths",
    "submission_gate",
    "write_json",
]
