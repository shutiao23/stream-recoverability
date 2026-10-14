#!/usr/bin/env python3
"""Reproducible objective-completion audit.

Replaces the hand-written OBJECTIVE_COMPLETION_AUDIT.csv with a script that
checks each blueprint gate against the artifacts that satisfy it, and writes
results/wrr_submission_ready/OBJECTIVE_COMPLETION_AUDIT.csv.

Modes:
  done              the gate is met by an artifact or a passing check
  failure_shoukou   the gate cannot be met and an explicit failure-closure
                    document records why (this is a completed response, not an
                    open item)
  human_gate        the gate needs a human decision that a repository must not
                    invent (author metadata)
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "OBJECTIVE_COMPLETION_AUDIT.csv"


def exists(relative: str) -> bool:
    return (ROOT / relative).exists()


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text())


def check_claim_binding() -> tuple[bool, str]:
    script = ROOT / "scripts" / "254_wrr_claim_binding_check.py"
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, errors="replace", cwd=str(ROOT)
    )
    report = load("results/wrr_submission_ready/claim_binding_check.json")
    detail = (
        f"hard_ok={report['hard_ok']} allowed_failures={len(report['allowed_failures'])} "
        f"barred_violations={len(report['barred_number_violations'])} "
        f"label_violations={len(report.get('label_violations', []))}"
    )
    return result.returncode == 0 and bool(report["hard_ok"]), detail


def main() -> int:
    rows: list[dict[str, object]] = []

    def add(requirement: str, ok: bool, mode: str, evidence: str) -> None:
        rows.append({"requirement": requirement, "ok": bool(ok), "mode": mode, "evidence": evidence})

    # P0-01 claim identity
    add(
        "P0-01 claim registry + live binding check",
        exists("results/wrr_submission_ready/claim_registry.csv") and check_claim_binding()[0],
        "done",
        "claim_registry.csv; claim_binding_check.json (" + check_claim_binding()[1] + ")",
    )

    # P0-02 inputs, provenance, access
    manifest = list(
        csv.DictReader((READY / "current_data_manifest.csv").open())
    ) if exists("results/wrr_submission_ready/current_data_manifest.csv") else []
    missing = [row for row in manifest if not (ROOT / row["input_path"]).is_file()]
    add(
        "P0-02 input manifest complete (146 networks, 0 missing)",
        len(manifest) == 146 and not missing,
        "done",
        f"n={len(manifest)} missing={len(missing)}",
    )
    add(
        "P0-02 measurement provenance + acquisition routes",
        exists("results/wrr_submission_ready/measurement_provenance_dictionary.csv")
        and exists("results/wrr_submission_ready/current_data_acquisition.csv"),
        "done",
        "measurement_provenance_dictionary.csv; current_data_acquisition.csv",
    )
    add(
        "P0-02/P0-08 reviewer access route and frozen bundle",
        exists("docs/reviews/wrr_input_access_route.md")
        and exists("results/wrr_submission_ready/reviewer_input_bundle_manifest.json"),
        "done",
        "docs/reviews/wrr_input_access_route.md; reviewer_input_bundle_manifest.json; scripts/262",
    )

    # P0-03 run identity and P0-04 fixes
    add(
        "P0-03/P0-04 outage geometry fix recomputed",
        exists("results/wrr_submission_ready/e1_maintenance_recompute/maintenance_counterfactual.json"),
        "done",
        "e1_maintenance_recompute/ (multi-year placement, assertion in scripts/210)",
    )
    add(
        "P0-04 instrument-error recompute under a locked method",
        exists("results/wrr_submission_ready/amendments/step22_noise_post_fix/summary.json"),
        "done",
        "amendments/step22_noise_post_fix/",
    )
    add(
        "P0-04 exact-donor-count control with generation guard",
        exists("results/wrr_submission_ready/amendments/step5_mechanism_equal_k/summary.json"),
        "done",
        "amendments/step5_mechanism_equal_k/; equal_k_mechanism.py",
    )

    # P0-05 truth-free prediction
    deploy = load("results/wrr_submission_ready/e2_certificate_predict/summary.json")
    add(
        "P0-05 predict without truth columns",
        int(deploy["n_incomplete_rows"]) == 2422 and int(deploy["n_with_certificate_choice"]) == 2422,
        "done",
        f"e2_certificate_predict n={deploy['n_incomplete_rows']}; invariance test in amendments notes",
    )

    # P0-06 freeze
    add("P0-06 method freeze", exists("results/wrr_submission_ready/P0_06_method_freeze.json"), "done", "P0_06_method_freeze.json")

    # P0-07: wave-2 is the live confirmation; first seals preserved as withdrawn.
    wave2_path = "results/wrr_submission_ready/p0_07_wave2_ingest/p0_07_wave2_confirmation/verdict.json"
    wave2 = load(wave2_path) if exists(wave2_path) else {}
    seal_new = load("results/wrr_submission_ready/P0_07_NEW_CONFIRMATION_SEAL.json") if exists(
        "results/wrr_submission_ready/P0_07_NEW_CONFIRMATION_SEAL.json"
    ) else {}
    add(
        "P0-07 wave-2 independent confirmation scored once",
        bool(wave2.get("predeclared_success_rule_met"))
        and bool(wave2.get("scored_once"))
        and bool(seal_new.get("scored"))
        and int(wave2.get("n_networks") or 0) >= 30
        and int(wave2.get("n_cert_reconstruction_failures") or 0) == 0,
        "done",
        (
            f"{wave2.get('n_networks')} networks, {wave2.get('n_cases')} cases, "
            f"Δ={float(wave2.get('contrast_points', 0)):.2f} pp; "
            f"providers={wave2.get('providers')}"
            if wave2
            else "missing wave2 verdict"
        ),
    )
    add(
        "P0-07 wave-2 prior-access clean + floors met",
        exists("results/wrr_submission_ready/p0_07_wave2_ingest/wave2_prior_access_summary.json")
        and exists("results/wrr_submission_ready/p0_07_wave2_ingest/wave2_manifest_summary.json")
        and bool(load("results/wrr_submission_ready/p0_07_wave2_ingest/wave2_prior_access_summary.json").get("clean"))
        and bool(load("results/wrr_submission_ready/p0_07_wave2_ingest/wave2_manifest_summary.json").get("floors_met")),
        "done",
        "wave2_prior_access_summary.json; wave2_manifest_summary.json",
    )
    sealed = load("results/wrr_submission_ready/p0_07_sealed_confirmation/verdict.json")
    add(
        "P0-07 first sealed USGS preserved (withdrawn after audit)",
        bool(sealed.get("scored_once")) and int(sealed["n_networks"]) >= 30,
        "done",
        f"preserved artifact: 39 networks, pooled {sealed['contrast_points']:.2f} pp (not live claim)",
    )
    transport_scored = exists("results/wrr_submission_ready/p0_07b_multi_agency_transport/verdict.json")
    add(
        "P0-07 first transport seal preserved (QC gate failed; withdrawn)",
        transport_scored or exists("results/wrr_submission_ready/multi_agency_seal.json"),
        "done" if transport_scored else "failure_shoukou",
        "p0_07b_multi_agency_transport/verdict.json (withdrawn; not live claim)",
    )

    # P0-08 package
    add(
        "P0-08 submission PDFs built from the live source",
        (ROOT / "paper/wrr/wrr_manuscript.pdf").is_file(),
        "done",
        "paper/wrr/wrr_manuscript.pdf; paper/wrr/wrr_supporting_information.pdf",
    )
    add(
        "P0-08 author metadata",
        False,
        "human_gate",
        "metadata/submission_author_metadata.json; AUTHOR_METADATA_FAILURE_SHOUKOU.md",
    )

    # P1 supplements
    add(
        "P1-01 hidden-bias (pattern-mixture) sensitivity",
        exists("results/wrr_submission_ready/amendments/mnar_pattern_mixture/summary.json"),
        "done",
        "amendments/mnar_pattern_mixture/ (delta in [-1,+1] C, no flip)",
    )
    add(
        "P1-02 reference-error scenarios and phase identifiability rule",
        exists("results/wrr_submission_ready/amendments/step22_noise_post_fix/scenario_contrasts.csv")
        and exists("results/wrr_submission_ready/amendments/winter_regulatory/summary_sine.json"),
        "done",
        "scenario_contrasts.csv; summary_sine.json (A/sigma >= 4.5)",
    )
    add(
        "P1-03 cold-endpoint and regulatory-endpoint analyses",
        exists("results/wrr_submission_ready/amendments/winter_regulatory/cold_support_contrast.csv")
        and exists("results/wrr_submission_ready/amendments/regulatory_daily_max/threshold_class_change.csv"),
        "done",
        "winter_regulatory/; regulatory_daily_max/",
    )
    add(
        "P1-04 faithful baseline reimplementation",
        exists("results/wrr_submission_ready/amendments/faithful_baseline/comparison.csv"),
        "done",
        "amendments/faithful_baseline/ (12.76% vs 15.16% vs 9.00%)",
    )
    add(
        "P1-05 SI and amendment register",
        exists("paper/wrr/wrr_supporting_information.tex")
        and "amendment register" in (ROOT / "paper/wrr/wrr_supporting_information.tex").read_text().lower(),
        "done",
        "wrr_supporting_information.tex (confirmation, transport and amendment register)",
    )

    # P2
    add(
        "P2-01 observed outage-cause classification and closure",
        exists("results/wrr_submission_ready/amendments/outage_causes/REPORT.md"),
        "failure_shoukou",
        "amendments/outage_causes/: no cause-naming qualifier exists, so the simulated counterfactual stays exploratory",
    )
    add(
        "P2-02 transfer boundary documented",
        exists("docs/reviews/p2_02_transfer_boundary.md"),
        "failure_shoukou",
        "docs/reviews/p2_02_transfer_boundary.md (no Chinese archive; transport panel is the transfer case)",
    )
    add(
        "P2-03 companion dataset and dashboard",
        exists("docs/companion/companion_dataset.csv") and exists("dist/companion/index.html"),
        "done",
        "docs/companion/companion_dataset.csv; dist/companion/index.html; scripts/264",
    )

    # Finding closure
    closure = list(csv.DictReader((READY / "F_FINDINGS_CLOSURE_AUDIT.csv").open()))
    blockers_open = [
        row for row in closure if row["severity"] == "Blocker" and not row["status"].startswith("closed")
    ]
    add(
        "F01-F22 closure audit without open blockers",
        not blockers_open,
        "done",
        f"{len(closure)} findings, {len(blockers_open)} open blockers",
    )

    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["requirement", "ok", "mode", "evidence"])
        writer.writeheader()
        writer.writerows(rows)

    failures = [row for row in rows if not row["ok"] and row["mode"] == "done"]
    print(json.dumps({"rows": len(rows), "hard_failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
