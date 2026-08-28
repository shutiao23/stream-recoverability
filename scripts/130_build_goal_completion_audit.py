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
        (row["phase"], row.get("scope", "supported_only")): row
        for row in summary["empirical_transfer"]
    }
    empirical_supported = empirical[("confirmation", "supported_only")]
    empirical_all = empirical[
        ("confirmation", "all_cells_with_network_mean_fallback")
    ]
    roster = pd.read_csv(REVIEW / "model_roster_metrics.csv")
    mechanism = pd.read_csv(REVIEW / "mechanism_decomposition.csv")
    replay = pd.read_csv(REVIEW / "placement_replay_curve.csv")
    risk = pd.read_csv(REVIEW / "risk_control_budget_curve.csv")
    coverage = pd.read_csv(REVIEW / "empirical_transfer_coverage_audit.csv")
    heterogeneity = pd.read_csv(REVIEW / "heterogeneity_metrics.csv")
    recurrent = json.loads(
        (REVIEW / "recurrent_sensitivity_manifest.json").read_text(encoding="utf-8")
    )
    process_hybrid = json.loads(
        (REVIEW / "process_hybrid_manifest.json").read_text(encoding="utf-8")
    )
    second_result_path = SECOND / "scoring/summary.json"
    second_result = (
        json.loads(second_result_path.read_text(encoding="utf-8"))
        if second_result_path.is_file()
        else None
    )
    if second_result is None:
        second_evidence = readiness["scoring_status"]
    else:
        simple_second = second_result.get("simple_metrics", {})
        empirical_second = second_result.get(
            "empirical_point_metrics", second_result.get("empirical_metrics", {})
        )
        second_evidence = (
            f"attempted={second_result.get('attempted_networks')}; "
            f"scored={second_result.get('scored_networks')}; "
            f"attrited={second_result.get('attrited_networks')}; "
            f"simple network Spearman={simple_second.get('network_spearman')}; "
            f"simple slope={simple_second.get('calibration_slope')}; "
            f"empirical network Spearman={empirical_second.get('network_spearman')}; "
            f"empirical slope={empirical_second.get('calibration_slope')}"
        )
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
            f"supported confirmation n={empirical_supported['n']}; network Spearman={empirical_supported['network_spearman']:.3f}; R2={empirical_supported['r2']:.3f}",
            gate=True,
        ),
        item(
            "P1a_all",
            "Report empirical-transfer performance on all 1,440 cells with fallback",
            "achieved_weaker_complete_panel_result",
            f"n={empirical_all['n']}; network Spearman={empirical_all['network_spearman']:.3f}; pooled Spearman={empirical_all['spearman']:.3f}; R2={empirical_all['r2']:.3f}; sources={dict(zip(coverage['empirical_transfer_source'], coverage['n_station_gaps']))}",
            gate=bool(empirical_all["n"] == 1440),
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
            "P1f",
            "Bounded recurrent recovery sensitivity",
            "complete_exploratory_negative",
            f"{recurrent['n_selected_networks']} networks; empirical-vs-BRITS station-gap Spearman={recurrent['results']['empirical_vs_brits_station_gap_spearman']:.3f}; explicitly not full roster or SOTA LSTM",
            gate=False,
        ),
        item(
            "P1g",
            "Air-temperature/flow process sensitivity",
            "complete_development_proxy_negative_confirmation_unavailable",
            f"{process_hybrid['results']['n_development_networks_scored']} development networks; XGBoost-vs-proxy network Spearman={process_hybrid['results']['xgboost_vs_process_hybrid_network_spearman']:.3f}; published air2stream={process_hybrid['published_air2stream_implementation']}",
            gate=False,
        ),
        item(
            "P1h",
            "Published air2stream or equivalent process model on independent networks",
            "not_completed_missing_confirmation_ta_f",
            "; ".join(process_hybrid["reasons_requirement_not_satisfied"]),
            gate=False,
            completion=False,
        ),
        item(
            "P1i",
            "Real-outage geometry or T4-style planted-geometry experiment",
            "partial_related_geometry_negative_gate_failed",
            "T4 froze 2,355 observed-counterpart natural geometries across 67 networks; natural network Spearman=-0.394 versus artificial=-0.011 and the interval was withheld below 100 networks. It did not score actual missing days and is not the v11 empirical predictor/model.",
            gate=False,
            completion=False,
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
            "Amended second-confirmation domain composition",
            "achieved_internal_amendment_not_external_preregistration",
            f"{readiness['amendment_id']}; {json.dumps(readiness['domain_checks'], sort_keys=True)}",
            gate=bool(readiness["domain_composition_passed"]),
        ),
        item(
            "P3_canada",
            "Original validated Canadian source stratum",
            "complete_negative_external_quality_condition",
            "Official four-station source was assessed but states observations are not validated or checked; zero qualified Canadian networks.",
            gate=False,
        ),
        item(
            "P3_scoring",
            "Run independent second confirmation under the canonical hash-bound gate",
            (
                str(second_result.get("status", "scoring_summary_present"))
                if second_result is not None
                else "authorized_not_run"
            ),
            (
                second_evidence
            ),
            gate=bool(
                second_result is not None
                and second_result.get("performance_reporting_authorized", False)
            ),
            completion=bool(
                second_result is not None
                and second_result.get("performance_reporting_authorized", False)
            ),
        ),
        item(
            "P3_intervals",
            "Independent second-confirmation interval endpoint",
            "complete_negative_width_gate_failed",
            (
                f"simultaneous coverage={second_result['empirical_interval_metrics']['network_simultaneous_coverage']:.3f}; "
                f"median width/loss={second_result['empirical_interval_metrics']['median_width_over_median_loss']:.3f}"
                if second_result is not None
                else "second-confirmation interval result absent"
            ),
            gate=False,
            completion=second_result is not None,
        ),
        item(
            "P3_triage",
            "Independent 5% false-release triage endpoint",
            "complete_negative_no_certified_release",
            (
                f"57-network evaluation; endpoint passed={second_result['triage']['endpoint_passed']}; simple released={second_result['triage']['simple_descriptors']['n_released']}; empirical released={second_result['triage']['fitting_period_empirical_all_cells']['n_released']}"
                if second_result is not None and "triage" in second_result
                else "second-confirmation triage result absent"
            ),
            gate=False,
            completion=bool(second_result is not None and "triage" in second_result),
        ),
        item(
            "P3_placement",
            "Independent placement confirmation",
            "complete_directional_no_preregistered_utility_gate",
            (
                f"13/13 complete replay matrices; simple minimax mean regret={second_result['placement']['simple_minimax_mean_regret']:.6f} versus random={second_result['placement']['random_mean_regret']:.6f}; relative reduction={second_result['placement']['simple_minimax_relative_regret_reduction_vs_random']:.3%}; utility claim licensed={second_result['placement']['confirmatory_utility_claim_licensed']}"
                if second_result is not None and "placement" in second_result
                else "second-confirmation placement result absent"
            ),
            gate=False,
            completion=bool(second_result is not None and "placement" in second_result),
        ),
        item(
            "P3_heterogeneity",
            "Provider, domain, thermal-state, and network-size heterogeneity",
            "complete_descriptive_first_panel",
            f"moderators={','.join(sorted(heterogeneity['moderator'].unique()))}; all rows descriptive_only={bool(heterogeneity['descriptive_only'].all())}",
            gate=bool(heterogeneity["descriptive_only"].all()),
        ),
        item(
            "P3_climate_regulation",
            "Climate-zone and regulation-state heterogeneity on 100+ scored networks",
            "not_completed_requires_larger_scored_panel_and_metadata",
            "The first and second panels provide 42 + 57 = 99 scored networks, below the requested 100+ analysis floor, and lack complete harmonized climate/regulation modifiers.",
            gate=False,
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
            (
                "The audit distinguishes completed experiments with negative gates, "
                "protocol-protected pending work, missing experiments, and external "
                "administrative blockers. A scientific gate failure is not relabelled "
                "as unfinished work or success."
            ),
        ]
    )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"overall_status": payload["overall_status"], "remaining": payload["remaining_blocking_conditions"]}, indent=2))


if __name__ == "__main__":
    main()
