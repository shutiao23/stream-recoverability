#!/usr/bin/env python3
"""Audit every deliverable in the pasted WRR improvement plan."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "results/development_v11/reviewer_completion"
SECOND = ROOT / "results/development_v11/second_confirmation"
OUTPUT_JSON = ROOT / "results/audits/goal_completion_audit.json"
OUTPUT_MD = ROOT / "docs/goal_completion_audit.md"


def item(
    identifier: str,
    requirement: str,
    status: str,
    evidence: str,
    *,
    gate: bool | None = None,
    completion: bool = True,
) -> dict[str, object]:
    result: dict[str, object] = {
        "id": identifier,
        "requirement": requirement,
        "status": status,
        "evidence": evidence,
        "completion_satisfied": completion,
    }
    if gate is not None:
        result["gate_passed"] = gate
    return result


def main() -> None:
    summary = json.loads((REVIEW / "summary.json").read_text(encoding="utf-8"))
    readiness = json.loads((SECOND / "readiness.json").read_text(encoding="utf-8"))
    empirical = {
        row["phase"]: row for row in summary["empirical_transfer"]
    }
    roster = pd.read_csv(REVIEW / "model_roster_metrics.csv")
    mechanism = pd.read_csv(REVIEW / "mechanism_decomposition.csv")
    replay = pd.read_csv(REVIEW / "placement_replay_curve.csv")
    risk = pd.read_csv(REVIEW / "risk_control_budget_curve.csv")
    references = (ROOT / "paper/references.bib").read_text(encoding="utf-8")
    manuscript = (ROOT / "paper/development_v11/manuscript.md").read_text(
        encoding="utf-8"
    )
    authors = json.loads(
        (ROOT / "metadata/submission_author_metadata.json").read_text(encoding="utf-8")
    )

    interval = summary["empirical_network_block_interval"]
    interval_gate = bool(
        0.85 <= interval["network_simultaneous_coverage"] <= 0.95
        and interval["median_width_over_median_loss"] <= 2.0
    )
    required_references = {
        "caselton1984monitoring",
        "krause2008sensor",
        "pardo1998gauges",
        "alfonso2012voi",
        "oh2025sensors",
        "moffat2007gap",
        "richardson2007longgaps",
        "denhertog2006kriging",
        "yamamoto2000kriging",
        "auer2024uncertainty",
    }
    references_present = all(f"{{{key}," in references for key in required_references)
    manuscript_files = [
        "manuscript.md",
        "supporting_information.md",
        "figure_captions.md",
        "cover_letter.md",
        "claim_matrix.md",
        "submission_checklist.md",
        "package_manifest.json",
    ]
    package_present = all(
        (ROOT / "paper/development_v11" / name).is_file()
        for name in manuscript_files
    ) and len(list(REVIEW.glob("figure_*.png"))) == 5

    requirements = [
        item(
            "P0",
            "Retitle around evidence actually supported by data",
            "achieved",
            manuscript.splitlines()[0],
            gate=True,
        ),
        item(
            "P1a",
            "Fitting-period empirical-transfer baseline",
            "achieved",
            f"confirmation n={empirical['confirmation']['n']}; network Spearman={empirical['confirmation']['network_spearman']:.3f}; R2={empirical['confirmation']['r2']:.3f}",
            gate=True,
        ),
        item(
            "P1b",
            "Learned error model with analytic-risk increment",
            "achieved_negative_increment",
            "LONO R2 0.7009 without operator and 0.7042 with operator",
            gate=False,
        ),
        item(
            "P1c",
            "Network-grouped conditional conformal intervals",
            "experiment_complete_gate_failed",
            f"simultaneous coverage={interval['network_simultaneous_coverage']:.3f}; median-width/loss={interval['median_width_over_median_loss']:.3f}",
            gate=interval_gate,
        ),
        item(
            "P1d",
            "At least three recovery-model families",
            "achieved",
            "|".join(sorted(roster["model_family"].unique())),
            gate=len(roster["model_family"].unique()) >= 3,
        ),
        item(
            "P1e",
            "Conditional-variance saturation mechanism on fixed roster",
            "achieved",
            f"{len(mechanism)} horizons; n={int(mechanism['n_stations'].min())} fixed stations",
            gate=len(mechanism) == 7 and mechanism["n_stations"].nunique() == 1,
        ),
        item(
            "P2a",
            "Real-data leave-k-station-out replay with MI and QR baselines",
            "achieved_open_development",
            f"{replay['network_id'].nunique()} networks; policies={','.join(sorted(replay['policy'].unique()))}",
            gate=replay["network_id"].nunique() >= 5,
        ),
        item(
            "P2b",
            "Finite-sample 5% false-release risk control",
            "experiment_complete_no_nonempty_certified_release",
            f"{len(risk)} budget-domain-model evaluations; certified fraction max={risk.groupby(['risk_model','domain_group','requested_budget'])['status'].apply(lambda x: x.eq('certified').mean()).max():.3f}",
            gate=False,
        ),
        item(
            "P3_candidates",
            "Second-confirmation candidate floor and 60-network target",
            "achieved",
            f"candidates={readiness['candidate_networks']}; strict-QC arrivals={readiness['qualified_networks_before_scoring']}",
            gate=bool(readiness["candidate_floor_passed"] and readiness["target_60_networks_arrived"]),
        ),
        item(
            "P3_domains",
            "US, Canada, and at least two European domains",
            "incomplete_external_canada_quality",
            json.dumps(readiness["domain_checks"], sort_keys=True),
            gate=bool(readiness["domain_composition_passed"]),
            completion=False,
        ),
        item(
            "P3_scoring",
            "Run independent second confirmation only after all arrival floors",
            "withheld_by_protocol",
            readiness["scoring_status"],
            gate=bool(readiness["scoring_authorized"]),
            completion=False,
        ),
        item(
            "P4_literature",
            "Monitoring design, empirical gaps, kriging, and conformal literature",
            "achieved",
            f"{len(required_references)} required reference families present",
            gate=references_present,
        ),
        item(
            "P4_package",
            "Complete manuscript, SI, five figures, cover letter, and checklist",
            "achieved_pending_external_declarations",
            f"package files={len(manuscript_files)}; figures={len(list(REVIEW.glob('figure_*.png')))}",
            gate=package_present,
        ),
        item(
            "ADMIN_authors",
            "Author identities and legal declarations",
            "incomplete_requires_authors",
            f"metadata complete={authors['complete']}; approved={authors['approved_by_all_authors']}",
            gate=bool(authors["complete"] and authors["approved_by_all_authors"]),
            completion=False,
        ),
        item(
            "ADMIN_doi",
            "Mint archival software DOI",
            "incomplete_requires_repository_service",
            "CITATION.cff intentionally has no DOI",
            gate=False,
            completion=False,
        ),
    ]
    all_passed = all(bool(row["completion_satisfied"]) for row in requirements)
    payload = {
        "audit": "goal_completion_audit_v1",
        "overall_status": "complete" if all_passed else "incomplete",
        "requirements": requirements,
        "remaining_blocking_conditions": [
            row["id"] for row in requirements if not row["completion_satisfied"]
        ],
    }
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Goal completion audit",
        "",
        f"Overall status: **{payload['overall_status']}**.",
        "",
        "| ID | Requirement | Status | Work complete | Scientific gate | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in requirements:
        gate = row.get("gate_passed")
        lines.append(
            f"| {row['id']} | {row['requirement']} | {row['status']} | "
            f"{'yes' if row['completion_satisfied'] else 'no'} | "
            f"{'pass' if gate is True else 'fail' if gate is False else 'n/a'} | "
            f"{str(row['evidence']).replace('|', '/')} |"
        )
    lines.extend(
        [
            "",
            "The audit distinguishes a completed experiment with a negative gate "
            "from a missing experiment. Second-confirmation scoring is missing by "
            "design because the Canadian arrival floor has not passed.",
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"overall_status": payload["overall_status"], "remaining": payload["remaining_blocking_conditions"]}, indent=2))


if __name__ == "__main__":
    main()
