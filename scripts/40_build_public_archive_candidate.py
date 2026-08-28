#!/usr/bin/env python3
"""Build a rights-filtered local archive candidate without minting a DOI."""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.governance import public_export_exclude

DIST = ROOT / "dist"
RELEASE_VERSION = "1.1.0"
ARCHIVE = DIST / f"stream-recoverability-v{RELEASE_VERSION}-archive-candidate.tar.gz"
MANIFEST = DIST / f"stream-recoverability-v{RELEASE_VERSION}-archive-candidate.manifest.json"

TOP_LEVEL = {
    ".zenodo.json",
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
    "results/audits/blueprint_completion_audit.json",
    "results/audits/reproduction_report_acceptance_revision.json",
    "results/audits/restricted_hosting_audit.json",
    "results/audits/submission_gate.json",
    "results/audits/goal_completion_audit.json",
    "results/development_v11/final_summary.json",
    "results/development_v11/reviewer_completion/summary.json",
    "results/development_v11/reviewer_completion/empirical_transfer_metrics.csv",
    "results/development_v11/reviewer_completion/empirical_transfer_coverage_audit.csv",
    "results/development_v11/reviewer_completion/heterogeneity_metrics.csv",
    "results/development_v11/reviewer_completion/model_roster_metrics.csv",
    "results/development_v11/reviewer_completion/learned_error_model_metrics.csv",
    "results/development_v11/reviewer_completion/mechanism_decomposition.csv",
    "results/development_v11/reviewer_completion/rank_decomposition.csv",
    "results/development_v11/reviewer_completion/interval_metrics_by_horizon_season_domain.csv",
    "results/development_v11/reviewer_completion/recalibration_budget_curve.csv",
    "results/development_v11/reviewer_completion/risk_control_budget_curve.csv",
    "results/development_v11/reviewer_completion/placement_replay_curve.csv",
    "results/development_v11/reviewer_completion/placement_pairwise_losses.csv",
    "results/development_v11/reviewer_completion/recurrent_sensitivity_manifest.json",
    "results/development_v11/reviewer_completion/recurrent_sensitivity_predictions.csv",
    "results/development_v11/reviewer_completion/recurrent_sensitivity_provider_metrics.csv",
    "results/development_v11/reviewer_completion/recurrent_sensitivity_training.csv",
    "results/development_v11/reviewer_completion/process_hybrid_manifest.json",
    "results/development_v11/reviewer_completion/process_hybrid_readiness.csv",
    "results/development_v11/reviewer_completion/process_hybrid_station_gaps.csv",
    "results/development_v11/reviewer_completion/process_hybrid_failures.csv",
    "results/development_v11/reviewer_completion/lstm_sensitivity_manifest.json",
    "results/development_v11/reviewer_completion/lstm_sensitivity_predictions.csv",
    "results/development_v11/reviewer_completion/lstm_sensitivity_provider_metrics.csv",
    "results/development_v11/reviewer_completion/lstm_sensitivity_training.csv",
    "results/development_v11/reviewer_completion/lstm_sensitivity_failures.csv",
    "results/development_v11/reviewer_completion/us_heterogeneity_manifest.json",
    "results/development_v11/reviewer_completion/us_heterogeneity_panel.csv",
    "results/development_v11/reviewer_completion/us_heterogeneity_networks.csv",
    "results/development_v11/reviewer_completion/us_heterogeneity_coefficients.csv",
    "results/development_v11/reviewer_completion/us_heterogeneity_level_slopes.csv",
    "results/development_v11/reviewer_completion/figure_01_workflow.png",
    "results/development_v11/reviewer_completion/figure_02_confirmation_calibration.png",
    "results/development_v11/reviewer_completion/figure_03_mechanism.png",
    "results/development_v11/reviewer_completion/figure_04_placement_replay.png",
    "results/development_v11/reviewer_completion/figure_05_domain_adaptation.png",
    "results/development_v11/reviewer_completion/figure_06_us_heterogeneity.png",
    "results/development_v11/matched_outage_geometry/summary.json",
    "results/development_v11/matched_outage_geometry/matched_item_predictions.csv",
    "results/development_v11/matched_outage_geometry/matched_network_comparison.csv",
    "results/development_v11/matched_outage_geometry/empirical_source_audit.csv",
    "results/development_v11/matched_outage_geometry/simple_predictor_attrition.csv",
    "results/development_v11/independent_air2stream_equivalent/manifest.json",
    "results/development_v11/independent_air2stream_equivalent/input_coverage.csv",
    "results/development_v11/independent_air2stream_equivalent/input_requests.csv",
    "results/development_v11/independent_air2stream_equivalent/model_parameters.csv",
    "results/development_v11/independent_air2stream_equivalent/placement_losses.csv",
    "results/development_v11/independent_air2stream_equivalent/station_gap_losses.csv",
    "results/development_v11/independent_air2stream_equivalent/failures.csv",
    "results/framework/t4_t5_post_t2_v1/t4_result_manifest.json",
    "results/framework/t4_t5_post_t2_v1/t4_network_comparison.csv",
    "results/development_v11/second_confirmation/candidate_summary.json",
    "results/development_v11/second_confirmation/candidates.csv",
    "results/development_v11/second_confirmation/readiness.json",
    "results/development_v11/second_confirmation/readiness_roster.csv",
    "results/development_v11/second_confirmation/frozen_scoring_roster_v2.csv",
    "results/development_v11/second_confirmation/amendment_registration_record.json",
    "results/development_v11/second_confirmation/canada_source_audit.json",
    "results/development_v11/second_confirmation/canada_candidate.csv",
    "results/development_v11/second_confirmation/nve/candidates.csv",
    "results/development_v11/second_confirmation/nve/network_qc_summary.csv",
    "results/development_v11/second_confirmation/nve/source_audit.md",
    "results/development_v11/second_confirmation/scoring/withheld.json",
    "results/development_v11/second_confirmation/scoring/summary.json",
    "results/development_v11/second_confirmation/scoring/simple_predictions.csv",
    "results/development_v11/second_confirmation/scoring/empirical_predictions.csv",
    "results/development_v11/second_confirmation/scoring/empirical_intervals.csv",
    "results/development_v11/second_confirmation/scoring/scoring_attrition.csv",
    "results/development_v11/second_confirmation/scoring/triage_endpoint.json",
    "results/development_v11/second_confirmation/scoring/placement_summary.json",
    "results/development_v11/second_confirmation/scoring/placement_attrition.csv",
    "results/development_v11/second_confirmation/scoring/placement_policy_summary.csv",
    "results/development_v11/second_confirmation/scoring/placement_pairwise_losses.csv",
    "results/development_v11/second_confirmation/scoring/placement_replay_curve.csv",
    "results/development_v11/second_confirmation/scoring/heterogeneity_metrics.csv",
}
SAFE_CORPUS_FILES = {
    "data_versions/global_network_corpus_v1/qualified_corpus_v1/network_catalog_v3_qualified.parquet",
    "data_versions/global_network_corpus_v1/qualified_corpus_v1/network_catalog_v3_qualified_manifest.json",
    "data_versions/global_network_corpus_v1/qualified_corpus_v1/qualified_corpus_manifest.json",
    "data_versions/global_network_corpus_v1/qualified_corpus_v1/network_catalog_v3_exclusions.csv",
    "data_versions/global_network_corpus_v1/qualified_corpus_v1/network_catalog_v3_balance.csv",
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
        or relative in SAFE_CORPUS_FILES
        or relative in SAFE_METADATA_FILES
    ):
        return True
    return any(relative.startswith(prefix) for prefix in SAFE_PREFIXES)


def _candidate_files() -> list[Path]:
    candidates = {
        ROOT / relative
        for relative in TOP_LEVEL
        | SAFE_RESULT_FILES
        | SAFE_CORPUS_FILES
        | SAFE_METADATA_FILES
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
            archive.add(
                path,
                arcname=Path(f"stream-recoverability-v{RELEASE_VERSION}") / relative,
            )
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
            "confidential reviewer-data upload is incomplete",
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
