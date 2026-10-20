#!/usr/bin/env python3
"""Bind final scientific claims to named source and frozen-test result rows."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as C

OUT = C.RUN / "r3_17_evidence"
PAPER = C.ROOT / "paper/wrr"
RET = "leave_one_year_out"
PRIOR = "strictly_prior_years"


def main() -> int:
    C.protocol()
    gate = C.load_script("r3_evidence_test_gate", C.ROOT / "scripts/358_wrr_external_recovery.py")
    gate.verify_role_access("test")
    OUT.mkdir(parents=True, exist_ok=True)
    claims = []

    def bind(name: str, value, source: Path, selector: str, *, decimals: int | None = None) -> None:
        if pd.isna(value):
            numeric, rendered = None, "not estimable"
        elif decimals is None:
            numeric = int(value)
            rendered = f"{numeric:,}".replace(",", "{,}")
        else:
            numeric = float(value)
            rendered = f"{numeric:.{decimals}f}"
        claims.append({"macro": name, "value": numeric, "rendered": rendered, "source": str(source.relative_to(C.ROOT)), "selector": selector, "source_sha256": C.digest(source)})

    source = C.source_cases(RET)
    admission = pd.read_parquet(source)
    for name, value, selector in [
        ("RAdmissionCases", len(admission), "all rows"),
        ("RSourceNetworks", admission.network_id.nunique(), "nunique(network_id)"),
        ("RSourceGroups", admission.independence_group.nunique(), "nunique(independence_group)"),
        ("RSourceStations", len(admission[["provider", "station_id"]].drop_duplicates()), "unique provider/station_id"),
        ("RSourceYears", len(admission[["provider", "station_id", "year"]].drop_duplicates()), "unique provider/station_id/year"),
        ("RSourceProviders", admission.provider.nunique(), "nunique(provider)"),
        ("RStratifiedCases", int(admission.design_family.eq("stratified").sum()), "design_family=stratified"),
        ("REmpiricalCases", int(admission.design_family.eq("empirical").sum()), "design_family=empirical"),
    ]:
        bind(name, value, source, selector)
    for protocol_name, macro in [(RET, "RControlledCases"), (PRIOR, "RPriorControlledCases")]:
        path = C.RUN / "r3_03_representative_recovery" / protocol_name / "summary.json"
        bind(macro, json.loads(path.read_text())["n_cases"], path, "n_cases")
    path = C.source_cases(PRIOR)
    bind("RPriorAdmissionCases", len(pd.read_parquet(path, columns=["year"])), path, "all rows")
    path = C.RUN / "r3_05_mechanism" / RET / "documented_daily_mean/summary.json"
    mechanism = json.loads(path.read_text())
    bind("RDocumentedControlledCases", mechanism["n_cases"], path, "n_cases")
    bind("RDocumentedGroups", mechanism["n_groups"], path, "n_groups")
    bind("RDocumentedYears", mechanism["deployable_adjustment_minus_original_mae_C"]["n_station_years"], path, "deployable_adjustment_minus_original_mae_C.n_station_years")
    for field, name in [("mean", "RDeployableImprovement"), ("ci_high", "RDeployableLow"), ("ci_low", "RDeployableHigh")]:
        bind(name, -mechanism["deployable_adjustment_minus_original_mae_C"][field], path, f"negative deployable_adjustment_minus_original_mae_C.{field}", decimals=3)
    base = path.parent
    path = base / "paired_position_contrasts.csv"
    positions = pd.read_csv(path)
    selected = positions.loc[positions.family.eq("crossed_contiguous") & positions.reconstructor.eq("doy_climatology") & positions.gap_length.eq(30)].iloc[0]
    for field, name in [("mean", "RPosition"), ("ci_low", "RPositionLow"), ("ci_high", "RPositionHigh")]:
        bind(name, selected[field], path, f"crossed_contiguous/doy_climatology/30/{field}", decimals=2)
    path = base / "paired_length_contrasts.csv"
    lengths = pd.read_csv(path)
    for method, prefix in [("doy_climatology", "RLength"), ("linear_interp", "RInterpLength")]:
        row = lengths.loc[lengths.reconstructor.eq(method) & lengths.true_hidden_share_cutoff.eq(0.999)].iloc[0]
        for field, suffix in [("mean", ""), ("ci_low", "Low"), ("ci_high", "High")]:
            bind(prefix + suffix, row[field], path, f"{method}/true_hidden_share>=0.999/{field}", decimals=2)
    path = base / "identity_and_switch_signs.csv"
    row = pd.read_csv(path).set_index("reconstructor").loc["doy_climatology"]
    bind("RCompensatingSwitchShare", 100 * row.share_positive_increment_still_underestimates, path, "doy_climatology/share_positive_increment_still_underestimates*100", decimals=1)
    path = base / "oracle_factorial_interventions.csv"
    factorial = pd.read_csv(path)
    for variant, name in [("raw", "ROracleRaw"), ("permuted", "ROraclePermuted"), ("demeaned", "ROracleDemeaned"), ("demeaned_permuted", "ROracleBoth"), ("interaction", "ROracleInteraction")]:
        value = factorial.loc[factorial.reconstructor.eq("doy_climatology") & factorial.variant.eq(variant), "mean"].iloc[0]
        bind(name, value, path, f"doy_climatology/{variant}/mean", decimals=3)
    for protocol_name, prefix in [(RET, "RRet"), (PRIOR, "RPriorLocal")]:
        path = C.RUN / "r3_07_decision_report/admission" / protocol_name / "documented_daily_mean/paired_contrasts.csv"
        contrasts = pd.read_csv(path)
        rows = contrasts.loc[contrasts.left.eq("uncertain_support") & contrasts.right.eq("generic_target_disagreement")]
        bind(prefix + "GainMin", 100 * rows.difference.min(), path, "uncertain_support minus generic_target_disagreement; minimum over three fold seeds", decimals=1)
        bind(prefix + "GainMax", 100 * rows.difference.max(), path, "uncertain_support minus generic_target_disagreement; maximum over three fold seeds", decimals=1)
        if protocol_name == RET:
            for left, right, label in [("generic_target_disagreement", "generic_daily_disagreement", "RTargetDaily"), ("small_logit_plus_support", "small_logit", "RSmallSupport"), ("season_spline_plus_support", "season_spline", "RSplineSupport")]:
                selected = contrasts.loc[contrasts.left.eq(left) & contrasts.right.eq(right)]
                bind(label + "Min", 100 * selected.difference.min(), path, f"{left} minus {right}; minimum over three split seeds*100", decimals=1)
                bind(label + "Max", 100 * selected.difference.max(), path, f"{left} minus {right}; maximum over three split seeds*100", decimals=1)
    for protocol_name, prefix in [(RET, "RWholeRet"), (PRIOR, "RWholePrior")]:
        path = C.RUN / "r3_13_learning_power/admission" / protocol_name / "whole_procedure_intervals.csv"
        rows = pd.read_csv(path)
        row = rows.loc[rows.left.eq("uncertain_support") & rows.right.eq("generic_target_disagreement")].iloc[0]
        for field, suffix in [("mean_refitted_procedure_difference", "Gain"), ("whole_procedure_ci_low", "Low"), ("whole_procedure_ci_high", "High")]:
            bind(prefix + suffix, 100 * row[field], path, f"uncertain_support minus generic_target_disagreement/{field}*100", decimals=1)
        bind(prefix + "Refits", row.n_fully_refitted_procedures, path, "n_fully_refitted_procedures")
    acquisition = []
    for provider in ("foen", "hubeau"):
        path = C.RUN / "r3_02_external_resource" / f"daily_acquisition_{provider}.csv"
        block = pd.read_csv(path)
        block["provider"] = provider
        acquisition.append(block)
    acquisition = pd.concat(acquisition, ignore_index=True)
    eligibility_path = C.RUN / "r3_06_independence_risk/external_eligibility_addendum.csv"
    eligibility = pd.read_csv(eligibility_path)
    acquisition = acquisition.merge(eligibility[["station_ID", "eligible_after_full_input_audit"]], on="station_ID", validate="one_to_one")
    acquisition = acquisition.loc[acquisition.eligible_after_full_input_audit & acquisition.eligible_four_complete_years.fillna(False)]
    acquisition.to_csv(OUT / "new_cohort.csv", index=False)
    for role, name in [("development", "RNewDevelopment"), ("calibration", "RNewCalibration"), ("test", "RNewTest")]:
        bind(name, int(acquisition.external_role.eq(role).sum()), OUT / "new_cohort.csv", f"external_role={role}")
    bind("RNewStations", len(acquisition), OUT / "new_cohort.csv", "all eligible rows")
    for provider, name in [("foen", "RNewSwissTest"), ("hubeau", "RNewFrenchTest")]:
        bind(name, int((acquisition.external_role.eq("test") & acquisition.provider.eq(provider)).sum()), OUT / "new_cohort.csv", f"external_role=test/provider={provider}")
    operating = []
    costs = []
    bank = json.loads((C.RUN / "r3_09_frozen_transfer/head_bank.json").read_text())["heads"]
    report = C.load_script("r3_unsupported_metrics", C.ROOT / "scripts/357_wrr_decision_report.py")
    for protocol_name, prefix in [(RET, "RTestRet"), (PRIOR, "RTestPrior")]:
        directory = C.RUN / "r3_10_external_decisions/test" / protocol_name / "admission/cofailure_0"
        path = directory / "operating_points.csv"
        data = pd.read_csv(path)
        unavailable = []
        for record in bank:
            if record["protocol"] != protocol_name or record["status"] == "fitted":
                continue
            frame = pd.read_parquet(directory / "case_information.parquet")
            frame = frame.loc[frame.provider.eq(record["target_provider"])]
            if record["scope"] == "documented_daily_mean":
                frame = frame.loc[frame.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
            if frame.empty:
                continue
            if record["name"] == "certificate_joint":
                frame = frame.assign(policy_metric=np.nan)
            for selection in ("empirical", "certified"):
                unavailable.append({"arm": record["name"], "mode": "local_fit_and_calibration", "scope": record["scope"], "provider": record["target_provider"], "protocol": protocol_name, "family": "admission", "cofailure": 0, "selection": selection, "score_status": record["status"], "n_independent_groups": frame.independence_group.nunique(), "retention_ci_low": 0, "retention_ci_high": 0, "risk_ci_low": np.nan, "risk_ci_high": np.nan, **report.pooled_metrics(frame, np.zeros(len(frame), dtype=bool))})
        if unavailable:
            data = pd.concat([data, pd.DataFrame(unavailable)], ignore_index=True)
        data["training_protocol"] = protocol_name
        operating.append(data)
        primary = data.loc[data.provider.eq("foen") & data.scope.eq("documented_daily_mean") & data.selection.eq("empirical") & data.arm.eq("uncertain_support")]
        for mode, suffix in [("frozen_source", "Frozen"), ("frozen_model_local_calibration", "Recalibrated"), ("local_fit_and_calibration", "Local")]:
            row = primary.loc[primary["mode"].eq(mode)].iloc[0]
            for field, label in [("retention", "Retention"), ("risk_among_admitted", "Risk")]:
                bind(prefix + suffix + label, 100 * row[field], path, f"foen/documented_daily_mean/uncertain_support/empirical/{mode}/{field}*100", decimals=1)
        bind(prefix + "Cases", primary.n_candidates.iloc[0], path, "foen/documented_daily_mean/uncertain_support/empirical/n_candidates")
        path = directory / "decision_costs.csv"
        data = pd.read_csv(path)
        data["training_protocol"] = protocol_name
        costs.append(data)
        primary = data.loc[data.provider.eq("foen") & data.scope.eq("documented_daily_mean") & data.arm.eq("uncertain_support") & data["mode"].eq("frozen_source") & data.threshold_definition.eq("local_training_q90") & data.false_negative_cost.eq(5) & data.abstention_cost.eq(0.05) & data.measurement_margin_C.eq(0)]
        for policy, suffix in [("magnitude_screen", "Magnitude"), ("screen_plus_observed_hot", "Judgement")]:
            row = primary.loc[primary.judgement_policy.eq(policy)].iloc[0]
            absolute_loss = (5 * row.false_negative + row.false_positive + 0.05 * row.abstained) / row.n
            bind(prefix + suffix + "AbsoluteLoss", absolute_loss, path, f"foen/documented/F0/localq90/FN5/A0.05/{policy}; (5*FN+FP+0.05*unknown)/n", decimals=4)
            bind(prefix + suffix + "VsAllUnknown", absolute_loss - 0.05, path, f"foen/documented/F0/localq90/FN5/A0.05/{policy}; absolute loss minus always-unknown cost 0.05", decimals=4)
            for field, label, decimals in [("loss_difference_vs_reconstruct_all", "LossDifference", 4), ("loss_difference_ci_low", "LossLow", 4), ("loss_difference_ci_high", "LossHigh", 4), ("abstained", "Abstentions", None), ("observationally_rescued_labels", "Rescued", None)]:
                bind(prefix + suffix + label, row[field], path, f"foen/documented/frozen_source/uncertain_support/localq90/FN5/A0.05/margin0/{policy}/{field}", decimals=decimals)
            if policy == "magnitude_screen":
                for field, label in [("hot_refusal_rate", "HotRefusal"), ("cool_refusal_rate", "CoolRefusal"), ("overall_refusal_rate", "OverallRefusal")]:
                    bind(prefix + label, 100 * row[field], path, f"foen/documented/frozen_source/uncertain_support/localq90/{field}*100", decimals=1)
        path = directory / "paired_contrasts.csv"
        comparison = pd.read_csv(path)
        row = comparison.loc[comparison.provider.eq("foen") & comparison.scope.eq("documented_daily_mean") & comparison["mode"].eq("frozen_model_local_calibration") & comparison.left.eq("generic_target_disagreement") & comparison.right.eq("generic_daily_disagreement")].iloc[0]
        for field, suffix in [("difference", "Gain"), ("ci_low", "Low"), ("ci_high", "High")]:
            bind(prefix + "TargetDaily" + suffix, 100 * row[field], path, f"foen/documented/F1/generic_H30 minus generic_daily/{field}*100", decimals=1)
    pd.concat(operating, ignore_index=True).to_csv(OUT / "independent_admission.csv", index=False)
    decision_table = pd.concat(costs, ignore_index=True)
    decision_table["absolute_loss"] = (decision_table.false_negative_cost * decision_table.false_negative + decision_table.false_positive + decision_table.abstention_cost * decision_table.abstained) / decision_table.n
    decision_table["always_unknown_loss"] = decision_table.abstention_cost
    decision_table["always_hot_loss"] = decision_table.true_cool / decision_table.n
    decision_table["always_cool_loss"] = decision_table.false_negative_cost * decision_table.true_hot / decision_table.n
    for name in ("unknown", "hot", "cool"):
        decision_table[f"loss_difference_vs_always_{name}"] = decision_table.absolute_loss - decision_table[f"always_{name}_loss"]
    decision_table.to_csv(OUT / "independent_decisions.csv", index=False)
    path = C.RUN / "r3_16_composition_transfer/test" / RET / "pooled.csv"
    row = pd.read_csv(path).query("scope == 'all'").iloc[0]
    for field, name, decimals, multiplier in [("n_cases", "RNaturalCases", None, 1), ("n_groups", "RNaturalGroups", None, 1), ("predicted_case_weighted_risk", "RNaturalPredictedRisk", 1, 100), ("observed_case_weighted_risk", "RNaturalObservedRisk", 1, 100)]:
        bind(name, row[field] * multiplier, path, f"all/{field}*{multiplier}", decimals=decimals)
    settings = C.protocol()
    bind("RSingleThresholdGroups", int(np.ceil(np.log(settings["alpha"]) / np.log1p(-settings["risk_cap"]))), C.CONFIG, "ceil(log(alpha)/log(1-risk_cap)); zero failures, one all-admit threshold")
    bind("RGridThresholdGroups", int(np.ceil(np.log(settings["alpha"] / 21) / np.log1p(-settings["risk_cap"]))), C.CONFIG, "ceil(log(alpha/21)/log(1-risk_cap)); zero failures, 21 fixed thresholds")
    for protocol_name, macro in [(RET, "RBandSwissRet"), (PRIOR, "RBandSwissPrior")]:
        path = C.RUN / "r3_10_external_decisions/test" / protocol_name / "admission/cofailure_0/scenario_interval_diagnostics.csv"
        row = pd.read_csv(path).set_index("provider").loc["foen"]
        bind(macro, 100 * row.finite_band_coverage, path, "foen/finite_band_coverage*100", decimals=1)
    path = C.RUN / "r3_12_process_reference/test" / RET / "cases.parquet"
    process = pd.read_parquet(path)
    cross_path = C.RUN / "r3_08_external_recovery/test" / RET / "crossed/cofailure_0/cases.parquet"
    cross = pd.read_parquet(cross_path)
    cross = cross.loc[cross.replicate.eq(0) & cross.design_family.eq("crossed_contiguous")]
    for method, prefix in [("air2stream3", "RPhysicalThree"), ("air2stream8", "RPhysicalEight")]:
        selected = process.loc[process.method.eq(method) & process.status.eq("available") & np.isfinite(process.absolute_error_C)]
        matched = selected.merge(cross[["network_id", "station_id", "year", "realization_id", "abserr_policy"]], on=["network_id", "station_id", "year", "realization_id"], validate="one_to_one")
        bind(prefix + "MAE", selected.absolute_error_C.mean(), path, f"{method}/available/mean absolute_error_C", decimals=3)
        bind(prefix + "Cases", len(selected), path, f"{method}/available/count")
        bind(prefix + "PolicyMAE", matched.abserr_policy.mean(), cross_path, f"replicate0/crossed_contiguous; inner join available {method} keys from r3_12_process_reference/test; mean abserr_policy", decimals=3)
    C.write_json(OUT / "claim_registry.json", {"claims": claims, "test_protocol": "frozen before new calibration and test; no outcome-driven retuning", "units": "degrees C, percent or percentage points as specified in selector"})
    PAPER.joinpath("r3_claims.tex").write_text("%% Generated by scripts/367_wrr_revision_evidence.py\n" + "\n".join(f"\\newcommand{{\\{item['macro']}}}{{{item['rendered']}}}" for item in claims) + "\n")
    C.write_json(OUT / "summary.json", {"n_bound_claims": len(claims), "primary_margin_points": 5, "new_test_retuning": False, "negative_results_are_not_completion_failures": True})
    C.write_json(OUT / "protocol_fingerprint.json", C.fingerprint(Path(__file__), {f"claim_source_{index}": C.ROOT / item["source"] for index, item in enumerate(claims)}))
    print(f"[367] {len(claims)} scientific numbers bound to actual result rows", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
