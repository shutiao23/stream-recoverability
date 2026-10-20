#!/usr/bin/env python3
"""Generate scientific evidence tables, including failed hypotheses and exclusions."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_r3_common as C

OUT = C.RUN / "r3_20_si_tables"
RET = "leave_one_year_out"
PRIOR = "strictly_prior_years"
LABELS = {"uncertain_support": "Window", "generic_target_disagreement": "Generic H30", "generic_daily_disagreement": "Generic daily", "generic_both_diagnostics": "Generic + OOF", "complete_diagnostic_model": "Complete diag.", "generic_direct_h30_uncertainty": "Direct H30", "generic_plus_climatological_support": "Generic + overlap", "uncertain_support_no_competition": "No competition", "uncertain_support_no_window_uncertainty": "No window spread", "uncertain_support_no_donor_features": "No donor features", "certificate": "Certificate proxy", "policy_certificate": "Policy certificate", "certificate_joint": "Joint certificate", "small_logit": "Small logit", "small_logit_plus_support": "Logit + overlap", "season_spline": "Season spline", "season_spline_plus_support": "Spline + overlap", "length_rule": "Length", "peak_overlap_rule": "Climate overlap", "warm_coverage_rule": "Warm coverage", "probabilistic_support_rule": "Mean support", "upper_support_rule": "Upper support", "direct_h30_uncertainty": "Raw H30 uncertainty", "daily_disagreement_rule": "Daily disagreement", "target_disagreement_rule": "H30 disagreement", "historical_h30_error_rule": "Historical H30", "scaled_support_rule": "Overlap x residual", "oof_daily_sd_rule": "OOF daily scale", "doy_climatology": "Daily climate", "smooth_climatology": "Smooth climate", "linear_interp": "Interpolation", "donor_ridge": "Neighbour ridge", "air_ridge": "Air ridge"}
MODES = {"frozen_source": "F0", "frozen_model_local_calibration": "F1", "local_fit_and_calibration": "F2", "frozen_unseen_provider": "F0-P", "frozen_intercontinental": "F0-US"}


def escape(value) -> str:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return "--"
    if isinstance(value, (int, np.integer)):
        return str(value)
    if isinstance(value, (float, np.floating)):
        return f"{value:.3f}" if np.isfinite(value) else "--"
    text = str(value)
    for before, after in [("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"), ("_", r"\_\allowbreak "), ("#", r"\#")]:
        text = text.replace(before, after)
    return text


def main() -> int:
    C.protocol()
    OUT.mkdir(parents=True, exist_ok=True)
    parts, manifest = [], []

    def table(name: str, caption: str, data: pd.DataFrame, columns: list[tuple[str, str]]) -> None:
        data.to_csv(OUT / f"{name}.csv", index=False)
        headers = " & ".join(escape(label) for column, label in columns)
        count = len(columns)
        widths = [0.24] + [(0.88 - 0.24) / (count - 1)] * (count - 1)
        specification = "".join(f"p{{{width:.3f}\\textwidth}}" for width in widths)
        start = "{\\tabletext\n\\setlength{\\tabcolsep}{3pt}\n\\begin{longtable}{" + specification + "}\n"
        start += "\\caption{" + caption + "}\\label{tab:r3si-" + name + "}\\\\\n\\toprule\n" + headers + " \\\\\n\\midrule\n\\endfirsthead\n\\toprule\n" + headers + " \\\\\n\\midrule\n\\endhead\n"
        body = "\n".join(" & ".join(escape(row[column]) for column, label in columns) + " \\\\" for row in data.to_dict("records"))
        parts.append(start + body + "\n\\bottomrule\n\\end{longtable}\n}\n")
        manifest.append({"table": name, "rows": len(data), "source": str((OUT / f"{name}.csv").relative_to(C.ROOT)), "sha256": C.digest(OUT / f"{name}.csv")})

    source = pd.read_parquet(C.source_cases(RET))
    providers = source.groupby(["provider", "statistic_class"]).agg(networks=("network_id", "nunique"), stations=("station_id", "nunique"), cases=("year", "size")).reset_index()
    table("providers", "Opened-source admission cohort. Network labels are not independent when target or donor records overlap. Documented daily means define the primary measurement scope; unclear daily statistics and project-aggregated records are sensitivity analyses.", providers, [("provider", "Provider"), ("statistic_class", "Daily statistic"), ("networks", "Labels"), ("stations", "Stations"), ("cases", "Cases")])
    cohort = pd.read_csv(C.RUN / "r3_17_evidence/new_cohort.csv")
    cohort = cohort.groupby(["provider", "external_role"]).agg(stations=("station_ID", "nunique"), groups=("independence_group", "nunique")).reset_index()
    table("new_cohort", "New-to-project continuous reference records after all-old-target/donor and metadata-only catchment exclusions. Roles were salted before daily values were acquired and never reshuffled. French daily means are project aggregates and include explicitly unqualified source observations. Institutional novelty and station novelty are not the same.", cohort, [("provider", "Provider"), ("external_role", "Role"), ("stations", "Stations"), ("groups", "Components")])
    controlled_path = C.RUN / "r3_03_representative_recovery" / RET / "cases.parquet"
    controlled = pd.read_parquet(controlled_path, columns=["provider", "station_id", "year", "statistic_class", "design_family", "longest_run", "overlap_class"])
    controlled = controlled.loc[controlled.design_family.eq("crossed_contiguous") & controlled.statistic_class.isin(["daily_mean", "documented_daily_mean"])]
    cells = controlled.groupby(["longest_run", "overlap_class"]).agg(cases=("year", "size")).reset_index()
    cells["station_years"] = [len(block[["provider", "station_id", "year"]].drop_duplicates()) for key, block in controlled.groupby(["longest_run", "overlap_class"])]
    table("controlled_cells", "Primary documented-mean controlled cells. Four start realizations are attempted per feasible station-year cell; an impossible cell is not fabricated. Case counts do not measure independent replication.", cells, [("overlap_class", "Climate overlap"), ("longest_run", "Days"), ("cases", "Masks"), ("station_years", "Station-years")])
    base = C.RUN / "r3_05_mechanism" / RET / "documented_daily_mean"
    position = pd.read_csv(base / "paired_position_contrasts.csv")
    position["method"] = position.reconstructor.map(LABELS)
    position["family"] = position.family.map({"crossed_contiguous": "All seasons", "within_warm_season": "Warm season"})
    table("position", "Paired full-minus-zero climatological overlap changes in absolute H30 error, averaging start realizations within a station-year before component bootstrap. Warm-season controls hold total missing warm-season days fixed. Intervals are 95 percent component-bootstrap intervals, not causal effects of an unobserved missingness mechanism.", position, [("method", "Method"), ("family", "Control"), ("gap_length", "Days"), ("mean", "Change C"), ("ci_low", "Lower"), ("ci_high", "Upper"), ("n_groups", "Groups")])
    length = pd.read_csv(base / "paired_length_contrasts.csv")
    length["method"] = length.reconstructor.map(LABELS)
    table("length", "Paired 90-minus-30-day H30 error at high and fully hidden true support. The 0.999 cutoff denotes the exact all-hidden discrete case; the comparison remains conditional on feasible masks and eligible station-years. Length is not negligible for every reconstruction.", length, [("method", "Method"), ("true_hidden_share_cutoff", "Hidden cutoff"), ("mean", "Change C"), ("ci_low", "Lower"), ("ci_high", "Upper"), ("n_station_years", "Station-years"), ("n_groups", "Groups")])
    fragment = pd.read_csv(base / "equal_budget_fragmentation.csv")
    fragment["method"] = fragment.reconstructor.map(LABELS)
    table("fragmentation", "Fragmented-minus-contiguous contrasts with equal total missing warm-season days. True hidden support is not held fixed; its change is shown rather than silently attributing the entire effect to fragmentation. Policy eligibility uses longest run, not total missing days.", fragment, [("method", "Method"), ("total_missing", "Days"), ("mean", "Error change C"), ("mean_true_hidden_share_difference", "Support change"), ("ci_low", "Lower"), ("ci_high", "Upper")])
    identity = pd.read_csv(base / "identity_and_switch_signs.csv")
    identity["method"] = identity.reconstructor.map(LABELS)
    table("identity", "Exact decomposition and sign audit. A positive switch increment is often compensation for underestimation, not a fabricated hot peak. Numerical identity residuals below the displayed precision are not evidence of physical truth accuracy.", identity, [("method", "Method"), ("n_valid", "Cases"), ("n_positive_increment", "Switches"), ("share_positive_increment_still_underestimates", "Still low share"), ("maximum_identity_residual_C", "Max residual C")])
    oracle = pd.read_csv(base / "oracle_factorial_interventions.csv")
    oracle["method"] = oracle.reconstructor.map(LABELS)
    table("oracle", "Two-by-two residual intervention: original, permuted, mean removed, and both. The interaction is original minus permuted minus centered plus both. Truth is required for all these interventions. Their percentage improvements cannot be added as identified physical contributions. Deployable visible-anchor adjustment is evaluated separately in the text.", oracle, [("method", "Method"), ("variant", "Intervention"), ("mean", "MAE / interaction C"), ("ci_low", "Lower"), ("ci_high", "Upper"), ("n_groups", "Groups")])
    operating, contrasts, whole, power, curves = [], [], [], [], []
    for protocol_name, label in [(RET, "Retro"), (PRIOR, "Past-local")]:
        directory = C.RUN / "r3_07_decision_report/admission" / protocol_name / "documented_daily_mean"
        data = pd.read_csv(directory / "operating_points.csv")
        data = data.loc[data.selection.eq("empirical")].copy()
        for arm, block in data.groupby("arm"):
            operating.append({"method": LABELS.get(arm, arm), "protocol": label, "retention": f"{100*block.retention.median():.1f} [{100*block.retention.min():.1f}, {100*block.retention.max():.1f}]", "risk": f"{100*block.risk_among_admitted.median():.1f} [{100*block.risk_among_admitted.min():.1f}, {100*block.risk_among_admitted.max():.1f}]"})
        data = pd.read_csv(directory / "paired_contrasts.csv")
        selected = data.loc[(data.left.eq("uncertain_support") & data.right.isin(["generic_target_disagreement", "generic_direct_h30_uncertainty", "complete_diagnostic_model", "generic_both_diagnostics"])) | data.left.isin(["generic_target_disagreement", "generic_plus_climatological_support", "small_logit_plus_support", "season_spline_plus_support"])].copy()
        selected["comparison"] = selected.left.map(LABELS) + " - " + selected.right.map(LABELS)
        selected["protocol"] = label
        for column in ("difference", "ci_low", "ci_high"):
            selected[column] *= 100
        contrasts.append(selected)
        directory = C.RUN / "r3_13_learning_power/admission" / protocol_name
        data = pd.read_csv(directory / "whole_procedure_intervals.csv")
        data["protocol"] = "Retro" if protocol_name == RET else "Prospective"
        data["comparison"] = data.left.map(LABELS) + " - " + data.right.map(LABELS)
        for column in ("mean_refitted_procedure_difference", "whole_procedure_ci_low", "whole_procedure_ci_high"):
            data[column] *= 100
        whole.append(data)
        data = pd.read_csv(directory / "power_projections.csv")
        data = data.loc[data.left.eq("uncertain_support") & data.right.eq("generic_target_disagreement") & data.planned_test_groups.isin([7, 19, 53, 100, 400]) & data.null_margin.eq(0.05) & data.assumed_true_gain.isin([0.08, 0.10])].copy()
        data["protocol"] = "Retro" if protocol_name == RET else "Prospective"
        power.append(data)
        data = pd.read_csv(directory / "learning_curves.csv")
        for (size, method), block in data.groupby(["training_groups", "name"]):
            curves.append({"method": LABELS[method], "protocol": "Retro" if protocol_name == RET else "Prospective", "training_groups": size, "distinct_subsets": block.unique_training_subset.nunique(), "fits": len(block), "retention_mean": 100*block.retention.mean(), "retention_sd": 100*block.retention.std()})
    table("ablation", "Same-point source admission with disjoint 60/20/20 fitting, calibration and evaluation components. Entries are median [minimum, maximum] over three split seeds, not confidence intervals or independent experiments. Past-local recomputes local inputs from earlier years but does not freeze the global head in calendar time. All scores share the same empirical 5 percent calibration target, not identical realized test risk.", pd.DataFrame(operating), [("method", "Score"), ("protocol", "Protocol"), ("retention", "Retention percent"), ("risk", "Selected failures percent")])
    table("conditional_contrasts", "Conditional-on-fitted-procedure paired retention differences in percentage points. The primary superiority margin is 5 points and equivalence margin is 2 points. Crossing zero is not equivalence; a small conditional interval does not establish whole-procedure equivalence.", pd.concat(contrasts), [("comparison", "Comparison"), ("protocol", "Protocol"), ("fold_seed", "Seed"), ("difference", "Difference"), ("ci_low", "Lower"), ("ci_high", "Upper")])
    table("whole_procedure", "Whole-procedure uncertainty from 1,000 network resamples, refitting four risk learners and recalibrating thresholds. The prospective global head and calibration use years through 2018 and evaluation uses 2019--2022. Cached local fits are unchanged under resampling their whole component.", pd.concat(whole), [("comparison", "Comparison"), ("protocol", "Protocol"), ("mean_refitted_procedure_difference", "Difference pp"), ("whole_procedure_ci_low", "Lower"), ("whole_procedure_ci_high", "Upper"), ("n_evaluation_groups", "Test groups")])
    table("power", "Projected power to exceed the five-point practical margin under predeclared 8- and 10-point location-shift alternatives. Projections assume source-like independent groups and do not establish common-risk feasibility under transfer. Neither 80 nor 90 percent power is reached in this tested range; increasing only test groups leaves training/calibration variability. An effect exactly at the null margin cannot have high superiority power.", pd.concat(power), [("protocol", "Protocol"), ("planned_test_groups", "Test groups"), ("assumed_true_gain", "Assumed gain"), ("projected_power", "Power")])
    table("learning", "Repeated source learning curves. Every non-full size uses twenty independently sampled subsets of the opened-source training pool; full-pool repeats vary learner seed but have one unique subset. Evaluation and calibration groups are fixed and independent of fitting. Standard deviations are across fits, not evidence from additional rivers.", pd.DataFrame(curves), [("method", "Score"), ("protocol", "Protocol"), ("training_groups", "Train groups"), ("distinct_subsets", "Subsets"), ("fits", "Fits"), ("retention_mean", "Retention percent"), ("retention_sd", "SD pp")])
    independent = pd.read_csv(C.RUN / "r3_17_evidence/independent_admission.csv")
    independent = independent.loc[independent.selection.eq("empirical") & independent.arm.isin(["generic_target_disagreement", "generic_direct_h30_uncertainty", "uncertain_support", "complete_diagnostic_model", "certificate_joint"]) & ((independent.provider.eq("foen") & independent.scope.eq("documented_daily_mean")) | independent.provider.eq("hubeau"))].copy()
    independent["method"] = independent.arm.map(LABELS)
    independent["deployment"] = independent["mode"].map(MODES)
    independent["protocol"] = independent.training_protocol.map({RET: "Retro", PRIOR: "Prospective"})
    for column in ("retention", "risk_among_admitted"):
        independent[column] *= 100
    table("transfer", "Independent new-station transfer, with Swiss documented means primary and French project aggregates separate. F0: source model and source threshold unchanged; F1: same model, new local calibration; F2: new development fitting and local calibration; F0-P: target provider excluded; F0-US: USGS-only intercontinental source. A local reconstruction fit to permitted station history is allowed in every regime. The joint certificate delivers its own selected point; the other feature comparisons deliver the fixed information-priority point. None of these point risks is a per-network guarantee.", independent, [("method", "Score"), ("protocol", "Time"), ("provider", "Provider"), ("deployment", "Mode"), ("retention", "Keep percent"), ("risk_among_admitted", "Fail percent"), ("n_independent_groups", "Groups")])
    hydrology = []
    for protocol_name in (RET, PRIOR):
        data = pd.read_csv(C.RUN / "r3_19_hydrological_correction" / protocol_name / "admission/corrected_hydrological_strata.csv")
        data = data.loc[data.arm.eq("uncertain_support") & data["mode"].isin(["frozen_source", "frozen_model_local_calibration"]) & ((data.provider.eq("foen") & data.scope.eq("documented_daily_mean")) | data.provider.eq("hubeau"))].copy()
        data["deployment"] = data["mode"].map(MODES)
        data["time"] = "Retro" if protocol_name == RET else "Prospective"
        hydrology.append(data)
    table("hydrology", "Corrected hydrological strata for the uncertain-window score. Snow precipitation is a percent: majority snow means at least 50 percent, not 0.5. Glacier influence has priority. This descriptive unit correction changed no predictor, threshold, case, eligibility or frozen role. Single-component strata cannot certify their risk; raw script-360 hydrological labels are superseded by this table.", pd.concat(hydrology), [("stratum", "Hydrology"), ("time", "Time"), ("provider", "Provider"), ("deployment", "Mode"), ("n_admitted", "Admit"), ("n_failed_among_admitted", "Fail"), ("n_independent_groups", "Groups"), ("risk_ci_high", "Risk upper")])
    anomaly, networks = [], []
    for protocol_name in (RET, PRIOR):
        directory = C.RUN / "r3_10_external_decisions/test" / protocol_name / "admission/cofailure_0"
        data = pd.read_csv(directory / "stratum_results.csv")
        select = data.arm.eq("uncertain_support") & data["mode"].isin(["frozen_source", "frozen_model_local_calibration"]) & ((data.provider.eq("foen") & data.scope.eq("documented_daily_mean")) | data.provider.eq("hubeau"))
        data = data.loc[select & data.stratum_type.isin(["warm_anomaly", "compound_heat_lowflow", "published_event_overlap"])].copy()
        data["time"] = "Retro" if protocol_name == RET else "Prospective"
        data["deployment"] = data["mode"].map(MODES)
        anomaly.append(data)
        data = pd.read_csv(directory / "group_results.csv")
        select = data.arm.eq("uncertain_support") & data["mode"].isin(["frozen_source", "frozen_model_local_calibration"]) & ((data.provider.eq("foen") & data.scope.eq("documented_daily_mean")) | data.provider.eq("hubeau"))
        data = data.loc[select].copy()
        info = pd.read_parquet(directory / "case_information.parquet")
        station = info.groupby("independence_group").station_id.first()
        data["station"] = data.group.map(station)
        data["time"] = "Retro" if protocol_name == RET else "Prospective"
        data["deployment"] = data["mode"].map(MODES)
        networks.append(data)
    table("anomalies", "Independent admission under warm anomalies, compound low-flow/heat overlap and the independently published event catalog. Flow missing on required gap-event days is explicitly unknown, not absence of compound stress. The project event threshold requires three days; published episodes require two. These are outcome strata, never deployment features.", pd.concat(anomaly), [("stratum", "Condition"), ("time", "Time"), ("provider", "Provider"), ("deployment", "Mode"), ("n_admitted", "Admit"), ("n_failed_among_admitted", "Fail"), ("n_independent_groups", "Groups"), ("risk_ci_high", "Risk upper")])
    table("networks", "Every independent new-station component for the uncertain-window policy. Counts expose concentrated failures that pooled risk can hide. Repeated masks and years within one river are not independent Bernoulli trials: a zero numerator is not a safety certificate and no case-binomial confidence interval is claimed.", pd.concat(networks), [("station", "Station"), ("time", "Time"), ("deployment", "Mode"), ("n_candidates", "Pool"), ("n_admitted", "Admit"), ("n_failed_among_admitted", "Fail"), ("risk_among_admitted", "Risk")])
    stress = pd.read_csv(C.RUN / "r3_06_independence_risk/cluster_risk_stress_summary.csv")
    table("risk_stress", "Constructed population stress test, not observed river failure rates. Groups are independent with perfectly dependent failures within groups, true failure probability 0.06 and uninformative scores. Empty admissions are not zero risk. The rigorous bounded-group test addresses a group-expectation ratio under its assumptions, not every catchment or arbitrary domain shift.", stress, [(column, column.replace("_", " ")) for column in stress.columns[:6]])
    replay = []
    for protocol_name in (RET, PRIOR):
        for fraction in (0, 0.5, 1):
            data = pd.read_csv(C.RUN / "r3_15_held_group_replay" / protocol_name / "events" / f"cofailure_{fraction:g}/stratum_results.csv")
            data = data.loc[data.arm.eq("uncertain_support") & data.scope.eq("documented_daily_mean") & data.dimension.eq("event_phase")]
            for phase, block in data.groupby("stratum"):
                replay.append({"phase": phase, "time": "Retro" if protocol_name == RET else "Past-local", "removed_fraction": fraction, "retention": block.retention.mean(), "risk": block.risk_among_admitted.mean(), "n_cases": block.n_candidates.iloc[0]})
    table("event_cofailure", "Opened-source component-held-out event/cofailure assay. Exactly the admission-trained heads and thresholds are applied without adaptation. Values average the three dependent split sensitivities. Before/during/after masks are relative to the same longest training-threshold episode. The new European component bundles are single-station and cannot by themselves identify donor-cofailure sensitivity; this nondegenerate multi-station test supplies that diagnostic, not independent confirmation.", pd.DataFrame(replay), [("phase", "Gap phase"), ("time", "Inputs"), ("removed_fraction", "Removed share"), ("retention", "Retention"), ("risk", "Selected risk"), ("n_cases", "Candidates")])
    composition = []
    for protocol_name in (RET, PRIOR):
        data = pd.read_csv(C.RUN / "r3_16_composition_transfer/test" / protocol_name / "group_predictions.csv")
        data["time"] = "Retro" if protocol_name == RET else "Prospective"
        composition.append(data)
    table("composition", "No-screen composition rule on independent natural-calendar replay. Only French records contribute qualifying calendars here; there is no independent Swiss documented-mean calendar estimate. Bin boundaries were inherited from opened analyses; cell risks were fitted on opened-source empirical geometries and fixed before new-test replay. Advice based on a point forecast is not certification; source-only prediction intervals omit unmodelled domain shift and one target component cannot establish safety.", pd.concat(composition), [("group", "Component"), ("time", "Time"), ("n_cases", "Masks"), ("n_station_years", "Station-years"), ("predicted_risk", "Predicted risk"), ("observed_risk", "Observed risk"), ("rule_says_no_screen", "No-screen advice")])
    reference = pd.read_parquet(C.RUN / "r3_11_probabilistic_reference/external_test_cases.parquet")
    rows = []
    cross = pd.read_parquet(C.RUN / "r3_08_external_recovery/test" / RET / "crossed/cofailure_0/cases.parquet")
    cross = cross.loc[cross.replicate.eq(0) & cross.design_family.eq("crossed_contiguous")]
    keys = ["network_id", "station_id", "year", "realization_id"]
    for point, label in [("absolute_error_series_point", "CSDI: median series"), ("absolute_error_functional_point", "CSDI: median H30")]:
        matched = reference.merge(cross[keys + ["abserr_policy"]], on=keys, validate="one_to_one")
        valid = np.isfinite(matched[point])
        rows.append({"method": label, "time": "Retro", "inputs": "Target only", "all_cases": len(matched), "available": int(valid.sum()), "mae": matched.loc[valid, point].mean(), "matched_policy_mae": matched.loc[valid, "abserr_policy"].mean(), "failure": (matched.loc[valid, point] > 0.5).mean()})
    for method in ["doy_climatology", "smooth_climatology", "linear_interp", "donor_ridge", "air_ridge"]:
        valid = np.isfinite(cross[f"abserr_{method}"])
        rows.append({"method": LABELS[method], "time": "Retro", "inputs": "Target + neighbours" if method == "donor_ridge" else "Target + air" if method == "air_ridge" else "Target only", "all_cases": len(cross), "available": int(valid.sum()), "mae": cross.loc[valid, f"abserr_{method}"].mean(), "matched_policy_mae": cross.loc[valid, "abserr_policy"].mean(), "failure": (cross.loc[valid, f"abserr_{method}"] > 0.5).mean()})
    process = pd.read_parquet(C.RUN / "r3_12_process_reference/test" / RET / "cases.parquet")
    for method, block in process.groupby("method"):
        matched = block.merge(cross[keys + ["abserr_policy"]], on=keys, validate="one_to_one")
        valid = matched.status.eq("available") & np.isfinite(matched.absolute_error_C)
        rows.append({"method": method, "time": "Retro", "inputs": "Target + air + flow" if method == "air2stream8" else "Target + air", "all_cases": len(matched), "available": int(valid.sum()), "mae": matched.loc[valid, "absolute_error_C"].mean(), "matched_policy_mae": matched.loc[valid, "abserr_policy"].mean(), "failure": (matched.loc[valid, "absolute_error_C"] > 0.5).mean()})
    prior_cross = pd.read_parquet(C.RUN / "r3_08_external_recovery/test" / PRIOR / "crossed/cofailure_0/cases.parquet")
    prior_cross = prior_cross.loc[prior_cross.replicate.eq(0) & prior_cross.design_family.eq("crossed_contiguous") & prior_cross.year.between(2019, 2022)]
    prior_process = pd.read_parquet(C.RUN / "r3_12_process_reference/test" / PRIOR / "cases.parquet")
    for method, block in prior_process.groupby("method"):
        matched = block.merge(prior_cross[keys + ["abserr_policy"]], on=keys, validate="one_to_one")
        valid = matched.status.eq("available") & np.isfinite(matched.absolute_error_C)
        rows.append({"method": method, "time": "Prospective", "inputs": "Target + air + flow" if method == "air2stream8" else "Target + air", "all_cases": len(matched), "available": int(valid.sum()), "mae": matched.loc[valid, "absolute_error_C"].mean(), "matched_policy_mae": matched.loc[valid, "abserr_policy"].mean(), "failure": (matched.loc[valid, "absolute_error_C"] > 0.5).mean()})
    table("reconstruction_references", "Reconstruction references on identical replicate-zero crossed cases. Availability is explicit, and the fixed policy MAE is recomputed on each method's identical supported subset. Inputs differ, so differences are not attributed solely to architecture. CSDI is an old-source-trained, fixed eight-draw retrospective univariate reference, not a claim to optimized state of the art. Air2stream parameters and discharge normalization exclude the target year and are strictly prior prospectively; every gap starts from an observed left anchor. No unsupported prediction is counted as a success.", pd.DataFrame(rows), [("method", "Reconstructor"), ("time", "Time"), ("inputs", "Information"), ("available", "Available"), ("mae", "H30 MAE C"), ("matched_policy_mae", "Matched policy C"), ("failure", "Failure share")])
    intervals = []
    for protocol_name in (RET, PRIOR):
        for family in ("admission", "crossed", "events", "real_calendars"):
            data = pd.read_csv(C.RUN / "r3_10_external_decisions/test" / protocol_name / family / "cofailure_0/scenario_interval_diagnostics.csv")
            data["time"] = "Retro" if protocol_name == RET else "Prospective"
            data["family"] = family
            intervals.append(data)
    table("scenario_bands", "Raw 90 percent conditional-trajectory band diagnostics. These are uncalibrated scenario bands for the fixed priority point, not valid confidence intervals or selected-risk certificates. Missing bands remain missing. The conditional residual bootstrap does not capture all bias or transfer uncertainty.", pd.concat(intervals), [("family", "Assay"), ("time", "Time"), ("provider", "Provider"), ("n_original_candidates", "Candidates"), ("n_finite_bands", "Bands"), ("finite_band_coverage", "Coverage"), ("mean_width_C", "Width C")])
    costs = pd.read_csv(C.RUN / "r3_17_evidence/independent_decisions.csv")
    costs = costs.loc[costs.arm.eq("uncertain_support") & costs["mode"].eq("frozen_source") & costs.threshold_definition.eq("local_training_q90") & costs.measurement_margin_C.eq(0) & costs.judgement_policy.eq("magnitude_screen") & ((costs.provider.eq("foen") & costs.scope.eq("documented_daily_mean")) | costs.provider.eq("hubeau"))].copy()
    costs["time"] = costs.training_protocol.map({RET: "Retro", PRIOR: "Prospective"})
    costs["absolute_loss"] = (costs.false_negative_cost * costs.false_negative + costs.false_positive + costs.abstention_cost * costs.abstained) / costs.n
    costs["always_unknown_loss"] = costs.abstention_cost
    costs["always_hot_loss"] = costs.true_cool / costs.n
    costs["always_cool_loss"] = costs.false_negative_cost * costs.true_hot / costs.n
    costs["loss_difference_vs_always_unknown"] = costs.absolute_loss - costs.always_unknown_loss
    costs["loss_difference_vs_always_hot"] = costs.absolute_loss - costs.always_hot_loss
    costs["loss_difference_vs_always_cool"] = costs.absolute_loss - costs.always_cool_loss
    table("decision_costs", "Full original-candidate locally anomalous-hot decisions, fixed source uncertain-window policy. False-hot cost is one; costs were declared before new test. Negative differences favor screening. Always-unknown cost equals the declared abstention cost, with no magnitude estimate or finite selected risk. This stronger deterministic comparator was added in the post-test scientific audit without changing any decision. Always-hot/cool costs and the original descriptive component-bootstrap intervals remain in the source CSV; no simultaneous guarantee or measured agency preference is claimed.", costs, [("time", "Time"), ("provider", "Provider"), ("false_negative_cost", "Miss cost"), ("abstention_cost", "Unknown cost"), ("absolute_loss", "Screen loss"), ("loss_difference_vs_reconstruct_all", "vs all recon."), ("loss_difference_vs_always_unknown", "vs all unknown")])
    representation = pd.read_csv(C.RUN / "r3_17_evidence/independent_decisions.csv")
    representation = representation.loc[representation.arm.eq("uncertain_support") & representation["mode"].eq("frozen_source") & representation.threshold_definition.eq("local_training_q90") & representation.measurement_margin_C.eq(0) & representation.false_negative_cost.eq(5) & representation.abstention_cost.eq(0.05) & ((representation.provider.eq("foen") & representation.scope.eq("documented_daily_mean")) | representation.provider.eq("hubeau"))].copy()
    representation["time"] = representation.training_protocol.map({RET: "Retro", PRIOR: "Prospective"})
    representation["decision"] = representation.judgement_policy.map({"magnitude_screen": "Magnitude", "screen_plus_observed_hot": "Hot-label rescue"})
    table("representation", "Locally hot and cool refusals, selected-sample frequency error and original-pool unknown-label bounds. Bounds allow every unknown label to be cool or hot and are not statistical confidence intervals; classification mistakes among judged cases can still affect them. Magnitude and hot-label admission are distinct outputs. Declaring an observed hot lower bound never certifies a cool record.", representation, [("time", "Time"), ("provider", "Provider"), ("decision", "Decision"), ("hot_refusal_rate", "Hot refusal"), ("cool_refusal_rate", "Cool refusal"), ("selected_frequency_error", "Freq. error"), ("original_pool_hot_frequency_lower", "Pool lower"), ("original_pool_hot_frequency_upper", "Pool upper")])
    destination = C.ROOT / "paper/wrr/si_r3_tables.tex"
    destination.write_text("%% Generated by scripts/369_wrr_revision_si.py\n" + "\n".join(parts))
    C.write_json(OUT / "table_manifest.json", {"tables": manifest, "all_generated_from_actual_results": True})
    print(f"[369] {len(manifest)} scientific evidence tables generated", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
