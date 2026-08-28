#!/usr/bin/env python3
"""Build an evidence-backed P0--P2 completion audit for the review blueprint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_JSON = ROOT / "results/audits/blueprint_completion_audit.json"
OUTPUT_MD = ROOT / "docs/blueprint_completion_audit.md"


def _json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _exists(*relative: str) -> bool:
    return all((ROOT / path).is_file() for path in relative)


def _item(
    requirement_id: str,
    title: str,
    status: str,
    evidence: list[str],
    finding: str,
    remaining: str,
) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "title": title,
        "status": status,
        "evidence": evidence,
        "finding": finding,
        "remaining": remaining,
    }


def build_audit() -> dict[str, Any]:
    study = _json("paper/study_manifest.json")
    corpus = _json(
        "data_versions/global_network_corpus_v1/qualified_corpus_v1/qualified_corpus_manifest.json"
    )
    catalog = _json(
        "data_versions/global_network_corpus_v1/qualified_corpus_v1/network_catalog_v3_qualified_manifest.json"
    )
    sealed = _json(
        "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1/sealed_qc_manifest.json"
    )
    registry = _json("paper/main_v9/results_registry.json")
    twin = _json(
        "results/framework/synthetic_v2/twin_e_holdout/twin_e_holdout_negative_result.json"
    )
    geometry = _json(
        "results/framework/t2_outage_geometry_v1/geometry_binding_manifest.json"
    )
    tier2 = _json(
        "results/framework/t2_recovery_benchmark_v1/tier2_development_subsample_manifest.json"
    )
    t4 = _json("results/framework/t4_t5_post_t2_v1/t4_result_manifest.json")
    t5 = _json("results/framework/t4_t5_post_t2_v1/t5_result_manifest.json")
    online = _json("results/framework/t2_online_causal_v1/preparation_run.json")
    operations = _json("results/framework/public_catalog/reservoir_operations_check.json")
    submission = _json("results/audits/submission_gate.json")
    power = pd.read_csv(ROOT / "results/framework/development_power_curve.csv")
    max_power = float(power["power"].max())

    requirements = [
        _item(
            "P0-0",
            "Split v4 and v9 paper lineages",
            "complete",
            ["paper/study_manifest.json", "paper/case_study_v1/", "paper/main_v9/"],
            "Two canonical lineages have separate designs, manuscripts, claim matrices, and registries.",
            "None.",
        ),
        _item(
            "P0-1",
            "Qualified independent-network inventory",
            "failed_gate",
            [
                "data_versions/global_network_corpus_v1/qualified_corpus_v1/network_catalog_v3_qualified.parquet",
                catalog["audit_outputs"]["exclusions_path"],
                catalog["audit_outputs"]["balance_path"],
            ],
            f"{corpus['qualified_total']}/100 unique networks qualified; exclusions and balance are explicit.",
            "The frozen 100-network floor was missed and may not be lowered post hoc.",
        ),
        _item(
            "P0-2",
            "Executable confirmatory protocol",
            "complete",
            ["configs/design_freeze_v10_executable.yaml", "paper/main_v9/results_registry.json"],
            "Primary horizon, loss, roster, split, thresholds, and once semantics were frozen before unseal.",
            "Execution failed later gates; the frozen YAML remains an immutable pre-unseal record.",
        ),
        _item(
            "P0-3",
            "Synthetic operator identification",
            "complete_negative",
            [
                "results/framework/synthetic_identifiability/identifiability.csv",
                "results/framework/synthetic_v2/twin_e_holdout/twin_e_holdout_negative_result.json",
            ],
            (
                f"Locked Twin E recovered rank (Spearman {twin['gate']['operator_spearman']:.3f}) "
                f"but missed calibration (slope {twin['gate']['operator_calibration_slope']:.3f}); "
                "the generator was not retuned."
            ),
            "Operator-specific calibration is not established; retain the negative result.",
        ),
        _item(
            "P0-4",
            "Same-model information-source ablation",
            "partial",
            ["results/framework/t2_recovery_benchmark_v1/w7_open_role_bd_combined/nested_ablation.csv"],
            "Boundary/donor coalitions use a shared frozen model rule; meteorology and hydraulics remain unbound.",
            "M/H source cells require timestamp-safe auxiliary inputs and cannot be inferred from temperature-only data.",
        ),
        _item(
            "P0-5",
            "Empirical and adversarial outage geometry",
            "complete_binding_negative_analysis",
            [
                "results/framework/t2_outage_geometry_v1/natural_outage_catalog.csv",
                "results/framework/t2_outage_geometry_v1/adversarial_stress_catalog.csv",
                "results/framework/t4_t5_post_t2_v1/t4_result_manifest.json",
            ],
            (
                f"Frozen {geometry['natural_outage']['n_geometry_rows']} empirical counterparts and "
                f"{geometry['adversarial']['n_rows']} adversarial cells across {geometry['n_networks']} open networks; "
                f"T4 interval withheld below 100 networks ({t4['status']})."
            ),
            "No actual missing day was scored and no operational claim is licensed.",
        ),
        _item(
            "P0-6",
            "Development power and attrition audit",
            "complete_failed_floor",
            [
                "results/framework/development_power_curve.csv",
                "results/framework/t2_recovery_benchmark_v1/tier2_development_subsample_manifest.json",
                "data_versions/global_network_corpus_v1/global_attrition_v1/global_attrition_summary.json",
            ],
            f"Development simulation reached maximum recorded power {max_power:.3f}; Tier-2 and network floors still failed.",
            "No confirmatory interval may be reported from the under-floor corpus.",
        ),
        _item(
            "P0-7",
            "Evaluate-once sealed confirmation",
            "failed_before_scoring",
            [
                "results/framework/t2_sealed_confirmatory_v1/evaluate_once_lock.json",
                "results/framework/t2_sealed_confirmatory_v1/evaluate_once_run_ledger.json",
                "results/framework/t2_sealed_confirmatory_v1/sealed_qc_v1/sealed_qc_manifest.json",
            ],
            (
                f"QC read {sealed['n_sealed_objects_read']} objects once and retained "
                f"{sealed['n_eligible_networks']}/40 networks; confirmatory scoring was withheld."
            ),
            "The authorization is consumed. Rerun, replacement, and floor reduction are forbidden.",
        ),
        _item(
            "P0-8",
            "Decision utility and uncertainty",
            "development_failed_sealed_untested",
            [
                "paper/main_v9/results.md",
                "results/framework/t4_t5_post_t2_v1/t5_result_manifest.json",
            ],
            "Development placement/triage gates failed; sealed utility could not be evaluated after P0-7 stopped.",
            "No monitoring-design or safe-fill headline is licensed.",
        ),
        _item(
            "P0-9",
            "Manuscript, figures, SI, and FAIR package",
            "partial_external_blocked",
            [
                "paper/case_study_v1/",
                "paper/main_v9/",
                "results/audits/submission_gate.json",
            ],
            "The case-study package and v9 failure closure are synchronized; the release gate remains NO-GO.",
            "; ".join(submission["blockers"]),
        ),
        _item(
            "P1-1",
            "Structural SOTA sensitivity",
            "partial_budget_failure",
            [
                "docs/locked_sota_baseline_protocol.md",
                "results/framework/t2_recovery_benchmark_v1/tier2_development_subsample_manifest.json",
            ],
            f"SAITS/CSDI ran on {tier2['n_networks_attempted']} development networks; Air2stream and GRIN obligations remain unrun.",
            "The locked sample attrited below its allowed range; reselection is forbidden.",
        ),
        _item(
            "P1-2",
            "Topology-matched falsification",
            "complete_negative",
            ["results/framework/t4_t5_post_t2_v1/t5_result_manifest.json"],
            (
                f"Only {t5['n_unique_network_pairs']} unique network pairs supported the frozen contrast; "
                "balance did not support formal confound control."
            ),
            "Reservoir causation remains forbidden.",
        ),
        _item(
            "P1-3",
            "Thermal-state and extreme-event audit",
            "specified_not_cross_network_executed",
            ["configs/design_freeze_v9.yaml", "docs/experiments/e1_through_e10.md"],
            "Season, heat-wave, low-flow, winter, and state-shift strata are specified.",
            "A complete cross-network outcome audit does not exist because sealed scoring was withheld.",
        ),
        _item(
            "P1-4",
            "Risk intervals and calibration",
            "blocked_no_sealed_score",
            ["configs/design_freeze_v10_executable.yaml", "paper/main_v9/results_registry.json"],
            "Calibration and interval gates are frozen but have no confirmatory outcome vector.",
            "Coverage, width, and OOD calibration cannot be computed without a valid scored panel.",
        ),
        _item(
            "P1-5",
            "Online-causal estimand",
            "implementation_smoke_complete",
            [
                "results/framework/t2_online_causal_v1/workload_manifest.json",
                "results/framework/t2_online_causal_v1/last_run.json",
            ],
            (
                f"A separate {online['n_work_items']}-item one-sided workload exists; "
                f"the bounded run executed {online['run']['executed']} items without future-boundary exposure."
            ),
            "Full execution is intentionally NO-GO below the network floor and without timestamp-safe M/H.",
        ),
        _item(
            "P2-1",
            "Reservoir operations and heat balance",
            "external_data_blocked",
            [
                "results/framework/public_catalog/reservoir_operations_check.json",
                "paper/main_v9/boundary_ledger.md",
            ],
            (
                f"The modern USGS API is reachable and exposes {operations['example_storage_sites_found']} "
                "sample storage time series, but no aligned release temperature, outlet-depth, "
                "operation, control-river, or heat-flux corpus is available."
            ),
            "Requires new provider/institutional data; no causal mechanism claim is permitted.",
        ),
        _item(
            "P2-2",
            "Cross-continental monitoring policy",
            "blocked_by_p0_7",
            ["docs/sealed_t7_qc_failure_closure.md"],
            "The sealed panel failed before risk calibration and decision scoring.",
            "A policy study requires a new prospective untouched panel.",
        ),
        _item(
            "P2-3",
            "Public companion benchmark",
            "partial",
            [
                "results/framework/t2_outage_geometry_v1/",
                "data_versions/global_network_corpus_v1/qualified_corpus_v1/",
            ],
            "Public geometry, split, QC inventory, and benchmark contracts exist; confirmatory labels do not.",
            "Do not publish nonexistent or under-floor recoverability labels.",
        ),
        _item(
            "P2-4",
            "Management dashboard",
            "not_started_not_licensed",
            ["paper/main_v9/claim_matrix.md"],
            "No calibrated decision output exists to power a responsible dashboard.",
            "Building recommendations now would exceed the evidence license.",
        ),
    ]
    complete_statuses = {
        "complete",
        "complete_negative",
        "complete_binding_negative_analysis",
        "complete_failed_floor",
        "implementation_smoke_complete",
    }
    incomplete = [row["id"] for row in requirements if row["status"] not in complete_statuses]
    return {
        "manifest_schema": "review_blueprint_completion_audit_v1",
        "objective_complete": False,
        "study_manifest_schema": study["manifest_schema"],
        "formal_evidence": registry["formal_evidence"],
        "counts": {
            "qualified_networks": corpus["qualified_total"],
            "qualified_floor": corpus["network_ci_floor"],
            "sealed_eligible": sealed["n_eligible_networks"],
            "sealed_floor": sealed["sealed_absolute_floor"],
        },
        "requirements": requirements,
        "incomplete_requirement_ids": incomplete,
        "external_submission_blockers": submission["blockers"],
        "irreversible_scientific_blocker": (
            "v10 evaluate-once authorization consumed after sealed QC retained fewer than 40 networks"
        ),
        "next_valid_scientific_route": (
            "new prospective protocol with genuinely untouched networks; no reuse, relabeling, or retuning of v10"
        ),
    }


def _write_markdown(audit: dict[str, Any]) -> None:
    lines = [
        "# Review blueprint completion audit",
        "",
        "This is a current-state audit, not a claim that every blueprint item passed.",
        "",
        f"**Objective complete:** `{str(audit['objective_complete']).lower()}`",
        "",
        "| ID | Status | Evidence-backed finding | Remaining condition |",
        "| --- | --- | --- | --- |",
    ]
    for row in audit["requirements"]:
        lines.append(
            f"| {row['id']} | `{row['status']}` | {row['finding']} | {row['remaining']} |"
        )
    lines.extend(
        [
            "",
            "## Current hard boundaries",
            "",
            f"- {audit['irreversible_scientific_blocker']}.",
            f"- Valid next route: {audit['next_valid_scientific_route']}.",
            "- External submission blockers:",
            "",
        ]
    )
    lines.extend(f"  - {item}" for item in audit["external_submission_blockers"])
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    audit = build_audit()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_markdown(audit)
    print(json.dumps({"output": str(OUTPUT_JSON), "objective_complete": False}, indent=2))


if __name__ == "__main__":
    main()
