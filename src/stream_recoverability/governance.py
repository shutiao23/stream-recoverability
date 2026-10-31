"""Submission, hosting, and evidence-snapshot helpers.

These functions record what is actually on disk. They do not invent formal
results or mint DOIs.
"""

from __future__ import annotations
import json
import subprocess
from collections.abc import Mapping, Sequence
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any
import yaml
from stream_recoverability.analysis.study_freeze import (
    DEFAULT_STUDY_FREEZE,
    load_study_freeze,
    study_is_confirmatory,
)
from stream_recoverability.data.quality import load_quality_codebook
from stream_recoverability.experiments.contracts import (
    DEFAULT_DESIGN_PATH,
    EXECUTABLE_DESIGN_VERSION,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RESTRICTED_PATH_PREFIXES = (
    "data/raw/",
    "data/processed/",
    "data/sealed_public_rivers_v3/",
    "data/sealed_public_rivers_foen_v1/",
    "data/sealed_public_rivers_foen_v2/",
    "data_versions/published_v1/",
    "data_versions/published_v2/",
    "data_versions/no_s2_suspect_",
    "data_versions/b1_no_level_",
    "data_versions/b1_shift_sensitivity_",
    "masks/test/",
    "masks/validation/",
    "masks/validation_funnel/",
    "masks/validation_branch_ablation/",
    "results/validation_funnel/published_v1/",
    "metadata/validation_anchors.csv",
    "metadata/frontier_anchors.csv",
    "metadata/event_episode_catalog.csv",
)
RESTRICTED_PATH_GLOBS = (
    "results/validation_funnel/**/scenarios/**",
    "results/validation_funnel/**/checkpoints/**",
    "results/validation_funnel/**/shards/**",
    "results/validation_funnel/**/shard_logs/**",
    "results/validation_funnel/**/daily_predictions.parquet",
    "results/validation_funnel/**/event_metrics.parquet",
    "results/validation_funnel/**/anchor_availability.csv",
    "results/validation_funnel/**/run_manifest.json",
    "results/validation_funnel/**/validation_stage_manifest.json",
    "results/validation_funnel/**/validation_mask_units.csv",
    "results/validation_funnel/**/branch_ablation_metrics.parquet",
    "results/validation_funnel/**/traditional",
    "results/validation_funnel/**/deep_single_seed",
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
        ("git", "-C", str(cwd), *arguments), check=False, capture_output=True, text=True
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


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
        if public_export_exclude(relative):
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
        "note": "Presence of restricted columns on the public GitHub tip is a hosting defect, not an open-data grant. History rewrite requires an institutional mirror and a coordinated force-push; this helper does not rewrite git.",
    }


def roster_path(repository: Path = REPOSITORY_ROOT) -> Path | None:
    candidates = sorted(
        repository.glob("results/validation_funnel/**/finalized_model_roster.json")
    )
    return candidates[-1] if candidates else None


def formal_manifest_path(repository: Path = REPOSITORY_ROOT) -> Path:
    return repository / "results/final_results_manifest.json"


def evidence_snapshot(repository: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Machine-readable snapshot of what the current checkout can honestly claim."""
    design_path = repository / DEFAULT_DESIGN_PATH
    design = load_design(design_path)
    codebook = load_quality_codebook(repository / "metadata/quality_codebook.csv")
    unflagged = codebook.loc[codebook["qc_status"].eq("observed_unflagged")].iloc[0]
    hosting = audit_restricted_hosting(repository)
    roster = roster_path(repository)
    formal = formal_manifest_path(repository)
    manuscript = (repository / "paper_archived/manuscript.md").read_text(
        encoding="utf-8"
    )
    pending = manuscript.count("RESULTS_PENDING")
    citation = yaml.safe_load((repository / "CITATION.cff").read_text(encoding="utf-8"))
    citation_doi = citation.get("doi") if isinstance(citation, Mapping) else None
    external_manifest_path = (
        repository
        / "results/confirmatory/external_upper_middle_chattahoochee_v1"
        / "external_confirmation/completion_manifest.json"
    )
    external_manifest = (
        json.loads(external_manifest_path.read_text(encoding="utf-8"))
        if external_manifest_path.is_file()
        else {}
    )
    external_complete = bool(
        external_manifest.get("complete") is True
        and external_manifest.get("formal_evidence") is True
    )
    return {
        "snapshot_schema_version": "evidence_snapshot_v3",
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
        "dual_frontier_required": design.get("statistics", {})
        .get("frontier_denominators", {})
        .get("best_simple_baseline_relative", {})
        .get("status")
        == "primary_required",
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
        "confirmatory_evaluation": "complete" if external_complete else "not_run",
        "confirmatory_completed_run_units": int(
            external_manifest.get("completed_run_unit_count", 0)
        ),
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
    rights_audit: str | Path | None = None,
    reproduction_report: str | Path | None = None,
    editor_exception_approval: str | Path | None = None,
    author_metadata: str | Path | None = None,
    reviewer_data_upload: str | Path | None = None,
) -> dict[str, Any]:
    """List supplied submission files; author paperwork does not gate research."""
    supplied = {
        "roster": roster,
        "primary_registry": primary_registry,
        "primary_aggregate_manifest": primary_aggregate_manifest,
        "analysis_manifest": analysis_manifest,
        "confirmatory_data_manifest": confirmatory_data_manifest,
        "confirmatory_run_manifest": confirmatory_run_manifest,
        "rights_audit": rights_audit,
        "reproduction_report": reproduction_report,
        "editor_exception_approval": editor_exception_approval,
        "author_metadata": author_metadata,
        "reviewer_data_upload": reviewer_data_upload,
    }
    files = {
        name: {
            "path": str(path) if path is not None else None,
            "exists": Path(path).is_file() if path is not None else False,
        }
        for name, path in supplied.items()
    }
    return {
        "decision": "inventory_only",
        "passed": None,
        "blockers": [],
        "explicit_inputs": files,
        "note": "File inventory only; no scientific, administrative or submission approval is inferred.",
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return destination


def public_export_exclude(relative: str) -> bool:
    prefix_match = any(
        (
            relative.startswith(prefix) or relative == prefix.rstrip("/")
            for prefix in RESTRICTED_PATH_PREFIXES
        )
    )
    return prefix_match or any(
        (fnmatchcase(relative, pattern) for pattern in RESTRICTED_PATH_GLOBS)
    )


def public_safe_paths(paths: Sequence[str]) -> list[str]:
    return [path for path in paths if not public_export_exclude(path)]


def next_study_status(repository: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    """Record the next-paper freeze without touching v4 formal evidence."""
    candidate = Path(repository) / "configs/design_freeze_v9.yaml"
    legacy = Path(repository) / "configs/recoverability_study_freeze_v1.yaml"
    if Path(repository) == REPOSITORY_ROOT:
        freeze_path = DEFAULT_STUDY_FREEZE
    elif candidate.is_file():
        freeze_path = candidate
    else:
        freeze_path = legacy
    freeze = load_study_freeze(freeze_path)
    return {
        "design_id": freeze["design_id"],
        "status": freeze["status"],
        "formal_evidence": bool(freeze.get("formal_evidence")),
        "sealed_outcomes_opened": bool(freeze.get("sealed_outcomes_opened")),
        "headline_claim_licensed": bool(freeze.get("headline_claim_licensed")),
        "confirmatory": study_is_confirmatory(freeze),
        "charter": str(freeze.get("charter")),
    }


__all__ = [
    "RESTRICTED_PATH_GLOBS",
    "RESTRICTED_PATH_PREFIXES",
    "audit_restricted_hosting",
    "evidence_snapshot",
    "next_study_status",
    "public_safe_paths",
    "submission_gate",
    "write_json",
]
