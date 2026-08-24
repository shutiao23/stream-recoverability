"""Submission, hosting, and evidence-snapshot helpers.

These functions record what is actually on disk. They do not invent formal
results or mint DOIs.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from stream_recoverability.data.quality import load_quality_codebook
from stream_recoverability.experiments.contracts import (
    DEFAULT_DESIGN_PATH,
    EXECUTABLE_DESIGN_VERSION,
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


def load_design(
    path: str | Path = REPOSITORY_ROOT / DEFAULT_DESIGN_PATH,
) -> dict[str, Any]:
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
        if any(
            relative.startswith(prefix) or relative == prefix.rstrip("/")
            for prefix in RESTRICTED_PATH_PREFIXES
        ):
            paths.append(relative)
    return paths


def audit_restricted_hosting(repository: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Record whether restricted bytes are still on the public development tip."""

    paths = restricted_tracked_paths(repository)
    return {
        "status": "complete",
        "finding": "public_hosting_defect"
        if paths
        else "restricted_bytes_absent_from_tip",
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
    candidates = sorted(
        repository.glob("results/validation_funnel/**/finalized_model_roster.json")
    )
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
    citation = yaml.safe_load((repository / "CITATION.cff").read_text(encoding="utf-8"))
    citation_doi = citation.get("doi") if isinstance(citation, Mapping) else None
    external_manifest_path = (
        repository
        / "results/confirmatory/external_upper_middle_chattahoochee_v1"
        / "external_confirmation/completion_manifest.json"
    )
    external_lock_path = (
        repository
        / "data_versions"
        / ".external_upper_middle_chattahoochee_v1.confirmatory-evaluation-once.lock.json"
    )
    external_manifest = (
        json.loads(external_manifest_path.read_text(encoding="utf-8"))
        if external_manifest_path.is_file()
        else {}
    )
    external_lock = (
        json.loads(external_lock_path.read_text(encoding="utf-8"))
        if external_lock_path.is_file()
        else {}
    )
    external_complete = bool(
        external_manifest.get("complete") is True
        and external_manifest.get("formal_evidence") is True
        and external_lock.get("status") == "complete"
    )
    return {
        "snapshot_schema_version": "evidence_snapshot_v3",
        "git_commit": current_commit(repository),
        "worktree_clean": worktree_clean(repository),
        "executable_design": EXECUTABLE_DESIGN_VERSION,
        "design_path": str(DEFAULT_DESIGN_PATH),
        "design_version": design.get("design_version"),
        "primary_data_version": design.get("data_versions", {}).get("primary"),
        "max_epochs": design.get("training", {})
        .get("fixed_model_protocols", {})
        .get("common", {})
        .get("max_epochs"),
        "hit_epoch_limit_rejected": bool(
            design.get("training", {})
            .get("budget_rule", {})
            .get("reject_if_hit_epoch_limit")
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
        "roster_path": str(roster.relative_to(repository))
        if roster is not None
        else None,
        "formal_results_manifest": "present" if formal.is_file() else "pending",
        "archival_software_doi": str(citation_doi) if citation_doi else None,
        "manuscript_results_pending_markers": pending,
        "current_protocol_result_claims": "none" if pending else "see_manuscript",
        "confirmatory_data": "opened_after_roster_freeze"
        if external_complete
        else "not_opened",
        "confirmatory_evaluation": "complete_evaluate_once"
        if external_complete
        else "not_run",
        "confirmatory_completed_run_units": int(
            external_manifest.get("completed_run_unit_count", 0)
        ),
    }


def _load_release_record(
    path: str | Path | None, label: str
) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, f"{label} was not supplied"
    source = Path(path)
    if not source.is_file():
        return None, f"{label} is missing: {source}"
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"{label} is unreadable: {error}"
    if not isinstance(value, dict):
        return None, f"{label} must be a JSON mapping"
    return value, None


def _record_complete(value: Mapping[str, Any]) -> bool:
    if (
        value.get("complete") is True
        or value.get("finalized") is True
        or value.get("immutable") is True
    ):
        return True
    return str(value.get("status", "")).lower() in {
        "complete",
        "completed",
        "ok",
        "passed",
    }


def submission_gate(
    repository: Path = REPOSITORY_ROOT,
    *,
    roster: str | Path | None = None,
    primary_registry: str | Path | None = None,
    primary_aggregate_manifest: str | Path | None = None,
    analysis_manifest: str | Path | None = None,
    confirmatory_data_manifest: str | Path | None = None,
    confirmatory_run_manifest: str | Path | None = None,
    once_lock: str | Path | None = None,
    rights_audit: str | Path | None = None,
    reproduction_report: str | Path | None = None,
) -> dict[str, Any]:
    """Validate explicit release evidence; never discover a convenient file by glob."""

    snapshot = evidence_snapshot(repository)
    blockers: list[str] = []
    if snapshot["design_version"] != EXECUTABLE_DESIGN_VERSION:
        blockers.append(f"executable design is not {EXECUTABLE_DESIGN_VERSION}")
    if snapshot["observed_unflagged_provider_qc_status"] == "approved":
        blockers.append("observed_unflagged is still marked provider-approved")
    supplied = {
        "finalized roster": roster,
        "primary formal registry": primary_registry,
        "primary aggregate manifest": primary_aggregate_manifest,
        "analysis manifest": analysis_manifest,
        "confirmatory data manifest": confirmatory_data_manifest,
        "confirmatory run manifest": confirmatory_run_manifest,
        "confirmatory once-lock": once_lock,
        "rights audit": rights_audit,
        "reproduction report": reproduction_report,
    }
    records: dict[str, dict[str, Any]] = {}
    for label, path in supplied.items():
        value, error = _load_release_record(path, label)
        if error is not None:
            blockers.append(error)
        else:
            assert value is not None
            records[label] = value
    roster_record = records.get("finalized roster")
    if roster_record is not None and (
        roster_record.get("finalized") is not True
        or roster_record.get("design_version") != EXECUTABLE_DESIGN_VERSION
        or roster_record.get("data_version") != snapshot["primary_data_version"]
        or "best_simple_baseline_lookup" not in roster_record.get("artifacts", {})
    ):
        blockers.append("finalized roster does not satisfy the current v4 contract")
    for label in (
        "primary formal registry",
        "primary aggregate manifest",
        "analysis manifest",
        "confirmatory data manifest",
        "confirmatory run manifest",
        "rights audit",
        "reproduction report",
    ):
        record = records.get(label)
        if record is not None and not _record_complete(record):
            blockers.append(f"{label} is not complete")
    aggregate = records.get("primary aggregate manifest")
    if aggregate is not None and aggregate.get("retryable_run_unit_count", 0) != 0:
        blockers.append("primary aggregate contains retryable failures")
    analysis = records.get("analysis manifest")
    required_analysis = {
        "dual_frontier_comparison.csv",
        "donor_c_falsification_effects.csv",
        "donor_c_falsification_decision.csv",
    }
    if analysis is not None:
        artifacts = analysis.get("artifacts", {})
        if not isinstance(artifacts, Mapping) or not required_analysis.issubset(
            artifacts
        ):
            blockers.append(
                "analysis manifest lacks dual-frontier/falsification artifacts"
            )
    confirmatory = records.get("confirmatory run manifest")
    if confirmatory is not None and (
        confirmatory.get("formal_evidence") is not True
        or confirmatory.get("completed_run_unit_count")
        != confirmatory.get("expected_run_unit_count")
    ):
        blockers.append(
            "confirmatory run is not complete formal evaluate-once evidence"
        )
    lock = records.get("confirmatory once-lock")
    if lock is not None and lock.get("status") != "complete":
        blockers.append("confirmatory once-lock is not complete")
    if snapshot["manuscript_results_pending_markers"]:
        blockers.append("manuscript still contains RESULTS_PENDING markers")
    if snapshot["hosting"]["public_hosting_defect"]:
        blockers.append("restricted bytes remain on the public development tip")
    if not snapshot.get("archival_software_doi"):
        blockers.append("archival software DOI has not been minted")
    if not snapshot["dual_frontier_required"]:
        blockers.append("best-simple frontier is not required")
    passed = not blockers
    return {
        "passed": passed,
        "decision": "go" if passed else "no_go",
        "blockers": blockers,
        "snapshot": snapshot,
        "explicit_inputs": {
            label: str(path) if path is not None else None
            for label, path in supplied.items()
        },
        "note": "A failing gate is the correct state until formal evidence exists.",
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
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
