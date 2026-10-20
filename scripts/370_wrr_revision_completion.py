#!/usr/bin/env python3
"""Audit scientific requirements without confusing execution with hypothesis success."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as C

OUT = C.RUN / "r3_22_completion"
PROTOCOLS = ("leave_one_year_out", "strictly_prior_years")
SCOPES = ("documented_daily_mean", "all")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-pending-validation", action="store_true")
    args = parser.parse_args()
    settings = C.protocol()
    gate = C.load_script("r3_completion_frozen_gate", C.ROOT / "scripts/358_wrr_external_recovery.py")
    gate.verify_role_access("test")
    OUT.mkdir(parents=True, exist_ok=True)
    files = []
    checks = []

    def require(path: Path, meaning: str) -> None:
        if not path.exists() or not path.stat().st_size:
            raise RuntimeError(f"Missing actual scientific output: {meaning}: {path}")
        files.append({"path": str(path.relative_to(C.ROOT)), "sha256": C.digest(path), "meaning": meaning})

    for protocol_name in PROTOCOLS:
        require(C.source_cases(protocol_name), "separate short/long/empirical admission cohort")
        require(C.RUN / "r3_03_representative_recovery" / protocol_name / "cases.parquet", "broadened paired mechanism cohort")
        for scope in SCOPES:
            directory = C.RUN / "r3_04_uncertainty_ablation/admission" / protocol_name / scope
            completed = directory / "completed_scores.json"
            require(completed, "all final-cohort source score specifications")
            records = json.loads(completed.read_text())["scores"]
            if len(records) != 81 or len({(item["name"], item["fold_seed"]) for item in records}) != 81:
                raise RuntimeError("A final source ablation task is absent or duplicated")
            source_hash = C.digest(C.source_cases(protocol_name))
            if any(item["input_sha256"] != source_hash for item in records):
                raise RuntimeError("Admission scores were fitted on a different cohort")
            for record in records:
                require(directory / f"{record['name']}_{record['fold_seed']}.npz", "source out-of-group predictions and admission decisions")
            for name in ("operating_points", "paired_contrasts", "decision_costs", "stratum_results", "group_results"):
                require(C.RUN / "r3_07_decision_report/admission" / protocol_name / scope / f"{name}.csv", "source admission, contribution and original-pool utility")
        for name in ("paired_position_contrasts", "paired_length_contrasts", "equal_budget_fragmentation", "identity_and_switch_signs", "oracle_factorial_interventions", "deployable_bias_correction"):
            require(C.RUN / "r3_05_mechanism" / protocol_name / "documented_daily_mean" / f"{name}.csv", "primary measurement-scope mechanism inference")
        for family in ("events", "real_calendars"):
            for fraction in (0, 0.5, 1):
                directory = C.RUN / "r3_15_held_group_replay" / protocol_name / family / f"cofailure_{fraction:g}"
                require(directory / "operating_points.csv", "nondegenerate held-source cofailure/calendar/event assay")
                require(directory / "stratum_results.csv", "event phase and donor-availability strata")
        for family in ("admission", "crossed", "events", "real_calendars"):
            directory = C.RUN / "r3_10_external_decisions/test" / protocol_name / family / "cofailure_0"
            for name in ("operating_points", "paired_contrasts", "decision_costs", "stratum_results", "group_results", "scenario_interval_diagnostics"):
                require(directory / f"{name}.csv", "frozen independent outcome evaluation")
            require(directory / "case_information.parquet", "full candidate pool and observed-window/flow/event information")
            pool = pd.read_parquet(directory / "case_information.parquet", columns=["provider", "statistic_class", "maximum_training_calendar_year", "year"])
            if protocol_name == "strictly_prior_years" and ((pool.maximum_training_calendar_year >= pool.year).any() or not pool.year.between(2019, 2022).all()):
                raise RuntimeError("Prospective final outcomes contain forbidden future information or years")
            operating = pd.read_csv(directory / "operating_points.csv")
            for (provider, scope), block in operating.groupby(["provider", "scope"]):
                eligible = pool.loc[pool.provider.eq(provider)]
                if scope == "documented_daily_mean":
                    eligible = eligible.loc[eligible.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
                if not block.n_candidates.eq(len(eligible)).all() or not (block.n_admitted + block.n_abstained).eq(len(eligible)).all():
                    raise RuntimeError("A frozen magnitude arm dropped original candidate records")
                if (block.n_failed_among_admitted > block.n_admitted).any():
                    raise RuntimeError("Failure counts exceed magnitude admissions")
                if not block.loc[block.n_admitted.eq(0), "risk_among_admitted"].isna().all():
                    raise RuntimeError("Empty admission was reported as a finite selected risk")
            decision = pd.read_csv(directory / "decision_costs.csv")
            classified = decision[["true_positive", "true_negative", "false_negative", "false_positive", "abstained"]].sum(axis=1)
            if not classified.eq(decision.n).all():
                raise RuntimeError("A downstream arm dropped unknown or mistaken records")
            require(C.RUN / "r3_19_hydrological_correction" / protocol_name / family / "corrected_hydrological_strata.csv", "percent-unit-corrected hydrological evaluation without predictive changes")
        require(C.RUN / "r3_16_composition_transfer/test" / protocol_name / "group_predictions.csv", "independent no-screen composition audit")
        power = C.RUN / "r3_13_learning_power/admission" / protocol_name
        records = sorted((power / "bootstrap").glob("rep_*.json"))
        if len(records) != settings["power_draws"]:
            raise RuntimeError("Full-procedure resampling has not actually completed 1000 repetitions")
        summary = json.loads((power / "summary.json").read_text())
        if summary["n_completed_refitted_procedures"] != 1000 or summary["n_fitted_risk_models"] != 4000:
            raise RuntimeError("Whole-procedure summary does not describe actual refits")
        for name in ("whole_procedure_intervals", "power_projections", "learning_curves"):
            require(power / f"{name}.csv", "independent-unit training/calibration/evaluation uncertainty")
        learning = pd.read_csv(power / "learning_curves.csv")
        for size, block in learning.groupby("training_groups"):
            if size < learning.training_groups.max() and block.groupby("name").size().min() != 20:
                raise RuntimeError("A repeated learning-curve size has fewer than twenty fits")
        for role in ("development", "test"):
            require(C.RUN / "r3_12_process_reference" / role / protocol_name / "cases.parquet", "training-only Air2stream forcing reference and availability")
    for role in ("development", "test"):
        require(C.RUN / "r3_11_probabilistic_reference" / f"external_{role}_cases.parquet", "frozen CSDI reconstruction reference")
    require(C.RUN / "r3_06_independence_risk/cluster_risk_stress_summary.csv", "rare-group/zero-failure/dependence risk stress")
    require(C.RUN / "r3_06_independence_risk/all_target_and_donor_membership.csv", "all-old-input identity audit, not target-only audit")
    require(C.RUN / "pretest_power_decision_fingerprint.json", "documented source-only stopping decision")
    method = json.loads((C.RUN / "method_lock.json").read_text())
    deployment = json.loads((C.RUN / "deployment_lock.json").read_text())
    before = lambda value: datetime.fromisoformat(value["created_at_utc"])
    if before(method) >= before(deployment):
        raise RuntimeError("Method and deployment lock chronology is reversed")
    for protocol_name in PROTOCOLS:
        calibration = json.loads((C.RUN / "r3_08_external_recovery/calibration" / protocol_name / "admission/cofailure_0/protocol_fingerprint.json").read_text())
        if not before(method) < before(calibration) < before(deployment):
            raise RuntimeError("Target calibration did not occur strictly between the two freezes")
    bank = json.loads((C.RUN / "r3_09_frozen_transfer/head_bank.json").read_text())["heads"]
    if any({"hydrological_stratum", "Pt as snow", "Glaciers %"}.intersection(record.get("features", [])) for record in bank):
        raise RuntimeError("Descriptive hydrological correction affects a predictor")
    for protocol_name in PROTOCOLS:
        for family in ("admission", "crossed", "events", "real_calendars"):
            path = C.RUN / "r3_08_external_recovery/test" / protocol_name / family / "cofailure_0/protocol_fingerprint.json"
            if before(json.loads(path.read_text())) <= before(deployment):
                raise RuntimeError("A final test outcome panel predates its deployment lock")
    registry = C.RUN / "r3_17_evidence/claim_registry.json"
    require(registry, "numbers bound to their producing row and file hash")
    claims = json.loads(registry.read_text())["claims"]
    for item in claims:
        if C.digest(C.ROOT / item["source"]) != item["source_sha256"]:
            raise RuntimeError("A manuscript claim source changed after binding")
    decision_table = pd.read_csv(C.RUN / "r3_17_evidence/independent_decisions.csv")
    expected_loss = (decision_table.false_negative_cost * decision_table.false_negative + decision_table.false_positive + decision_table.abstention_cost * decision_table.abstained) / decision_table.n
    if not np.allclose(decision_table.absolute_loss, expected_loss) or not np.allclose(decision_table.always_unknown_loss, decision_table.abstention_cost):
        raise RuntimeError("The stronger deterministic utility baselines do not match the declared loss")
    require(C.DOCS / "DECISION_BASELINE_AUDIT.md", "post-test dummy baseline audit without changing any policy")
    require(C.DOCS / "CALENDAR_TIME_QUALIFICATION.md", "calendar-time hindcast is not an operational-vintage trial")
    build = C.load_script("r3_completion_document_reader", C.ROOT / "scripts/223_wrr_build.py")
    text = build.manuscript_text(C.ROOT / "paper/wrr/wrr_manuscript.tex")
    if build.missing_numbers(text):
        raise RuntimeError("Claim bindings do not match the current paper")
    if "H2 is not supported" not in text or "Unchanged transfer therefore misses" not in text:
        raise RuntimeError("The manuscript does not faithfully state the failed primary claims")
    if "fifty" not in (C.DOCS / "NONPREDICTIVE_ERRATUM.md").read_text() and "50" not in (C.DOCS / "NONPREDICTIVE_ERRATUM.md").read_text():
        raise RuntimeError("Hydrological unit correction is not disclosed")
    for name in ("wrr_manuscript.pdf", "wrr_manuscript_published.pdf", "wrr_supporting_information.pdf", "RESPONSE_TO_REVIEW.md", "RESPONSE_TO_REVIEW.pdf", "si_r3_tables.tex"):
        require(C.ROOT / "paper/wrr" / name, "final scientific article, SI or point-by-point response")
    for name in ("r3_f1_recovery", "r3_f2_channels", "r3_f3_information", "r3_f4_transfer", "r3_f5_utility", "r3_s1_learning", "r3_s2_cofailure"):
        require(C.ROOT / "paper/wrr/figures" / f"{name}.pdf", "figure generated from final-protocol evidence")
    require(C.RUN / "r3_20_si_tables/table_manifest.json", "generated source-backed SI tables")
    build_report = json.loads((C.ROOT / "paper/wrr/build_report.json").read_text())
    if build_report["checks_failed"]:
        raise RuntimeError("Current manuscript fails document checks")
    qa = json.loads((C.READY / "figure_qa.json").read_text())
    qa_summary = qa.get("summary", qa)
    figure_failures = qa_summary.get("hard_failures")
    if figure_failures is None:
        figure_failures = sum(len(record.get("hard_failures", [])) for record in qa.get("files", []))
    if figure_failures:
        raise RuntimeError("Figure QA has hard failures")
    exit_path = C.ROOT / "scratch/wrr_revision_20261020c/full_tests.exitcode"
    validation_complete = exit_path.exists() and exit_path.read_text().strip() == "0"
    if not validation_complete and not args.allow_pending_validation:
        raise RuntimeError("Full test suite has not completed successfully")
    requirements = pd.read_csv(C.DOCS / "REQUIREMENTS.csv")
    if validation_complete and requirements.status.str.contains("pending|in_progress", regex=True).any():
        raise RuntimeError("A tracked scientific requirement is still marked pending")
    require(C.DOCS / "EXECUTION_REPORT_ZH.md", "detailed scientific assessment and next-study guidance")
    status = "scientific_revision_complete" if validation_complete else "scientific_evidence_complete_validation_pending"
    checks.extend([{"check": "predictive locks unchanged", "passed": True}, {"check": "method < deployment < test outcomes", "passed": True}, {"check": "324 final-admission score tasks", "passed": True}, {"check": "2000 complete four-model procedure refits", "passed": True}, {"check": "new snow labels do not change decisions", "passed": True}, {"check": "negative results retained in current paper", "passed": True}, {"check": "all original-candidate denominators retained", "passed": True}, {"check": "full test suite exit zero", "passed": validation_complete}])
    versions = {}
    for package in ("numpy", "pandas", "scipy", "scikit-learn", "pyarrow", "torch", "pypots", "numba", "shapely", "pyproj"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"
    C.write_json(OUT / "environment.json", versions)
    C.write_json(OUT / "scientific_completion.json", {"status": status, "checks": checks, "n_claim_bindings": len(claims), "files": files, "original_uncertain_window_practical_superiority_established": False, "unchanged_transfer_risk_target_met": False, "distribution_free_target_risk_certified": False, "h3_scope": "declared comparisons only; always-unknown may dominate; no universal management or best-physical-workflow benefit", "time_scope": "calendar-time forward hindcast using current-vintage data; not operational-vintage or prospective field trial", "submission_ready": False, "remaining_submission_metadata": ["verified authors/affiliations/funding", "permanent analysis archive and redistribution rights"], "test_validation_complete": validation_complete})
    C.write_json(OUT / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {"method_lock": C.RUN / "method_lock.json", "deployment_lock": C.RUN / "deployment_lock.json", "claim_registry": registry, "manuscript": C.ROOT / "paper/wrr/wrr_manuscript.tex", "methods": C.ROOT / "paper/wrr/r3_methods.tex", "results": C.ROOT / "paper/wrr/r3_results.tex", "discussion": C.ROOT / "paper/wrr/r3_discussion.tex"}))
    print(f"[370] {status}; hypotheses and guarantees are not relabelled as successes", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
