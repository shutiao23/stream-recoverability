#!/usr/bin/env python3
"""Finish developed-reference, joint-planning and backup-readiness evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd
from scipy.stats import beta

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision.state_trajectory import sample_crps

RUN = C.READY / "followup_20261021"
PAPER = C.ROOT / "paper/wrr"


def run_record(inputs, **extra):
    """Creation time, script and input paths of an output, with its scope flags."""
    return {"created_at_utc": datetime.now(timezone.utc).isoformat(), "script": {"path": f"scripts/{Path(__file__).name}"},
            "inputs": {name: {"path": str(Path(path).resolve())} for name, path in inputs.items()}, **extra}


def probability_quality():
    """Describe finite-sample quality without selecting another configuration."""
    rows, reliability = [], []
    keys = ["network_id", "station_id", "year", "realization_id"]
    for role in ("development", "calibration", "test"):
        frame = pd.read_parquet(RUN / "probability_development" / role / "cases.parquet")
        flow = pd.read_parquet(RUN / "trajectory/leave_one_year_out" / role / "cases.parquet")
        flow = flow.loc[flow.variant.eq("raw_block14") & flow.n_draws.eq(128), keys + ["flow_coverage", "gap_lowflow_fraction"]]
        frame = frame.merge(flow, on=keys, how="left", validate="one_to_one")
        original_n = len(frame)
        frame = frame.loc[frame.available].copy()
        for draws in (8, 16, 32):
            values = np.stack(frame.h30_samples_C.to_numpy())[:, :draws]
            point = np.median(values, axis=1)
            truth = frame.truth_h30.to_numpy()
            lower, upper = np.quantile(values, [.05, .95], axis=1)
            p_hot = np.mean(values > frame.local_hot_threshold_C.to_numpy()[:, None], axis=1)
            quality = frame[keys + ["independence_group", "warm_anomaly", "flow_coverage", "gap_lowflow_fraction"]].copy()
            quality["bias_C"] = point - truth
            quality["MAE_C"] = abs(point - truth)
            quality["CRPS_C"] = [sample_crps(value, target) for value, target in zip(values, truth)]
            quality["coverage90"] = (lower <= truth) & (truth <= upper)
            quality["width_C"] = upper - lower
            quality["Brier_hot"] = (p_hot - (truth > frame.local_hot_threshold_C.to_numpy())) ** 2
            quality["point_shift_from32_C"] = abs(point - frame.h30_point.to_numpy())
            subsets = {"all": np.ones(len(frame), dtype=bool)}
            if role == "test" and draws == 32:
                subsets.update({"warm_anomaly": frame.warm_anomaly.to_numpy(dtype=bool), "other_years": ~frame.warm_anomaly.to_numpy(dtype=bool),
                                "majority_lowflow_gap": (frame.flow_coverage.eq(1) & frame.gap_lowflow_fraction.ge(.5)).to_numpy(),
                                "not_majority_lowflow_gap": (frame.flow_coverage.eq(1) & frame.gap_lowflow_fraction.lt(.5)).to_numpy(),
                                "flow_incomplete": frame.flow_coverage.ne(1).to_numpy()})
            metrics = ["bias_C", "MAE_C", "CRPS_C", "coverage90", "width_C", "Brier_hot", "point_shift_from32_C"]
            for subset, mask in subsets.items():
                selected = quality.loc[mask]
                rows.append({"role": role, "draws": draws, "subset": subset, "original_N": original_n, "n": len(selected), "groups": selected.independence_group.nunique(), **selected[metrics].mean().to_dict()})
            if draws == 32:
                bins = pd.DataFrame({"probability": p_hot, "truth_hot": truth > frame.local_hot_threshold_C.to_numpy(), "bin": np.minimum((p_hot * 10).astype(int), 9)})
                bins = bins.groupby("bin").agg(n=("truth_hot", "size"), mean_probability=("probability", "mean"), observed_fraction=("truth_hot", "mean")).reset_index()
                bins["role"] = role
                reliability.append(bins)
    result = pd.DataFrame(rows)
    result.to_csv(RUN / "probability_development/quality_and_sampling.csv", index=False)
    pd.concat(reliability, ignore_index=True).to_csv(RUN / "probability_development/raw_probability_reliability.csv", index=False)
    return result


def planning():
    path = RUN / "joint_power/joint_power_all.csv"
    power = pd.read_csv(path)
    successes = np.rint(power.true_joint_power * power.repetitions).astype(int)
    alpha = .05 / len(power)
    power["mc_family_lower"] = [float(beta.ppf(alpha / 2, k, n - k + 1)) if k else 0.0 for k, n in zip(successes, power.repetitions)]
    power["mc_family_upper"] = [float(beta.ppf(1 - alpha / 2, k + 1, n - k)) if k < n else 1.0 for k, n in zip(successes, power.repetitions)]
    power.to_csv(RUN / "joint_power/joint_power_familywise_MC.csv", index=False)
    feasible = power.loc[power.mc_family_lower >= .8]
    C.write_json(RUN / "joint_power/final_sampling_decision.json", {"source_like_complete_refits": 3000, "paired_model_fits": 6000, "budget_cells": len(power),
                 "actual_component_support_train_calibration_test": [59, 21, 24], "MC_intervals_simultaneous_over_budget_grid": True,
                 "maximum_primary_joint_success_probability": float(power.true_joint_power.max()), "maximum_normal_approximation_sensitivity": float(power.asymptotic_true_joint_power.max()),
                 "maximum_simultaneous_MC_upper_bound": float(power.mc_family_upper.max()),
                 "supported_80_percent_plans": feasible.to_dict("records"), "recommended_recruitment_sample_size": None if feasible.empty else "see supported plans",
                 "status": "planning under finite role-specific empirical source laws, not new observations or a guarantee under hydrological shift"})
    return power


def finalize():
    required = [RUN / "probability_development/selection.json", RUN / "system_factorial_developed/operating.csv", RUN / "natural_backup/short_history/csdi_developed_results.csv"]
    required += [RUN / "probability_development" / role / "ensemble_extension.json" for role in ("development", "calibration", "test")]
    required += [RUN / "developed_calibration_budget/budget_summary.csv", PAPER / "r6_calibration_budget.tex", PAPER / "si_r6_tables.tex"]
    missing = [str(path.relative_to(C.ROOT)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Required computations still pending: " + ", ".join(missing))
    helper = C.load_script("extended_SI_table_writer", C.ROOT / "scripts/383_wrr_followup_evidence.py")
    probability = RUN / "probability_development"
    C.write_json(probability / "software_environment.json", {"python": platform.python_version(), "platform": platform.platform(),
                 "packages": {name: version(name) for name in ("numpy", "pandas", "scipy", "scikit-learn", "torch", "pypots", "joblib")},
                 "training_threads_per_configuration": 4, "inference_workers_per_role": 12, "threads_per_worker": 1,
                 "additional_shared_tail_workers": json.loads((probability / "parallel_backfill_contract.json").read_text())["additional_workers_shared_across_roles"] if (probability / "parallel_backfill_contract.json").exists() else 0,
                 "inference_scope": "all original role cases, 32 scenarios, 50 diffusion steps; no case or draw subsampling for runtime"})
    selected = json.loads((probability / "selection.json").read_text())
    development = pd.read_csv(probability / "development_results.csv")
    for name in development.configuration:
        manifest = json.loads((probability / name / "training.json").read_text())
        development.loc[development.configuration.eq(name), "max_epochs"] = manifest["maximum_epochs"]
        development.loc[development.configuration.eq(name), "wall_minutes"] = manifest["wall_seconds"] / 60
    development["selected"] = development.configuration.eq(selected["selected"])
    tables = [helper.table(development[["configuration", "n_groups", "n_candidates", "n_available", "equal_group_h30_crps_C", "max_epochs", "wall_minutes", "selected"]].rename(columns={"configuration": "Config.", "equal_group_h30_crps_C": "CRPS C", "max_epochs": "Epoch cap", "wall_minutes": "Fit minutes"}),
         "Old-group-only probability development. Both air-conditioned CSDI configurations share data, structured masks, seed, optimizer, maximum thirty epochs and patience five. Selection uses equal-group H30 CRPS on thirty old held-out groups and five masks per group; no external recovery outcome chooses the configuration. These budgets are not a claim of optimized state of the art.", "extended_probability_budget")]
    operating = pd.read_csv(RUN / "system_factorial_developed/operating.csv")
    admission_cases = pd.read_parquet(RUN / "system_factorial_developed/admission_cases.parquet")
    matched = admission_cases.loc[admission_cases.method.eq("air2stream3") & admission_cases.score_kind.eq("native_CDF")]
    matched_n = int((matched.cdf_available & np.isfinite(matched.reconstruction_point)).sum())
    operating_display = operating[["method", "score_kind", "n_point_available", "matched_subset_MAE_C", "accepted", "failed", "retention", "risk", "equal_group_risk", "formal_accepted"]].copy()
    operating_display["method"] = operating_display.method.replace({"csdi_developed_air": "Neural point"})
    operating_display["score_kind"] = operating_display.score_kind.replace({"native_CDF": "Native CDF", "boost_direct": "Direct head", "boost_window": "Window head"})
    operating_display = operating_display.rename(columns={"score_kind": "Score", "n_point_available": "Point N", "matched_subset_MAE_C": "MAE C", "failed": "Failed", "risk": "Case risk", "equal_group_risk": "Group risk"})
    tables.append(helper.table(operating_display,
         f"Developed same-air system comparison on all 945 original controlled Swiss candidates. Point availability and admission retain that full pool; MAE compares the same {matched_n} candidates with available Air2stream-3 and conditional distributions. Every point method receives the same selected H30 distribution. Native CDF failure probability is evaluated against that method's point before any window ablation; boosted direct and window scores share capacity and roles. Case risk pools accepted candidates; group risk is the ratio of mean group failure-and-admission to mean group admission. Unavailable numerical points remain unknown. Direct cost classification uses the same H30 law regardless of delivered point. This opened-data comparison is not a new confirmation.", "extended_probability_system"))
    power = planning()
    summary = power.groupby(["training_groups", "policy"]).agg(max_primary_success=("true_joint_power", "max"), max_MC_family_upper=("mc_family_upper", "max"),
                 max_normal_sensitivity=("asymptotic_true_joint_power", "max"), max_actual_target_fraction=("population_target_fraction", "max")).reset_index()
    tables.append(helper.table(summary.rename(columns={"training_groups": "Train G", "policy": "Rule", "max_primary_success": "Joint", "max_MC_family_upper": "MC upper", "max_normal_sensitivity": "Normal", "max_actual_target_fraction": "Population met"}), "Full-procedure joint planning for the original priority-point direct/window heads under the empirical source laws, 1,000 complete paired refits per training budget. Simulated calibration budgets range from 60 to 3,840 and evaluation budgets from 60 to 7,680 groups. Actual source supports contain 59 fitting, 21 calibration and 24 evaluation components; larger budgets are simulated iid draws, not acquired independent histories. Formal and empirical calibration are both evaluated. Primary success requires risk evidence for both methods and a Hoeffding lower retention-gain bound above five points; the normal approximation is sensitivity only. Each column maximizes over calibration/test budgets. Monte Carlo upper bounds cover the entire planning grid. No evaluated cell supports eighty-percent success. This does not plan a new neural-point candidate.", "extended_joint_planning"))
    qualification = json.loads((RUN / "natural_backup/qualification_summary.json").read_text())
    reasons = pd.DataFrame([{"qualification": key, "pair_years": value} for key, value in qualification["reasons"].items()])
    reasons["qualification"] = reasons.qualification.replace({"annual_boundary_outside_verified_primary_support": "Annual boundary outside verified primary support", "backup_does_not_cover_every_actual_missing_day": "Backup does not cover all missing days", "fewer_than_three_complete_prior_primary_years": "Fewer than three complete prior primary years", "primary_year_already_complete": "Primary year already complete", "sensor_records_not_comparable_under_prespecified_QC": "Sensors fail prespecified comparability checks"})
    tables.append(helper.table(reasons, "Redundant-logger resource qualification before reconstruction errors. There are 180 candidate sensor-pair-years, not 180 independent rivers. No case meets the unchanged three-complete-prior-primary-year protocol. Three compatible-reference pair-years correspond to two primary logger-years; they fail only historical support and remain a separately labelled short-history sensitivity. Source quality is project aggregation, not certified daily means.", "extended_backup_qualification"))
    natural = []
    for method in ("linear_interp", "air2stream3", "csdi_old", "csdi_developed"):
        frame = pd.read_csv(RUN / "natural_backup/short_history" / f"{method}_results.csv")
        if "available" not in frame:
            frame["available"] = np.isfinite(frame.h30_point)
        natural.append({"method": method, "pair_year_references": len(frame), "primary_logger_years": frame.input_id.nunique(), "available_comparisons": int(frame.available.sum()),
                        "MAE_C": frame.absolute_error_C.mean(), "reference_failures": int(frame.reference_failure.fillna(False).astype(bool).sum()),
                        "n_available_primary_years": frame.loc[frame.available, "input_id"].nunique()})
    natural_display = pd.DataFrame(natural).rename(columns={"pair_year_references": "References", "primary_logger_years": "Primary years", "available_comparisons": "Available", "MAE_C": "MAE C", "reference_failures": "Failures", "n_available_primary_years": "Available years"})
    natural_display["method"] = natural_display.method.replace({"csdi_old": "Fixed CSDI (8)", "csdi_developed": "Developed CSDI"})
    tables.append(helper.table(natural_display, "Short-history backup-reference sensitivity, retaining all three pair references and two primary years. The four unavailable daily means arise from 8--19 hourly samples per day, occur in winter, and are not demonstrated full-day sensor failures. Their observed hot windows remain intact. Air2stream unavailability is charged as unknown in use, not counted as zero numerical risk. Free backup union completes the recorded reference by definition and establishes no costly-query advantage. All cases form one dependent provincial cohort; they do not validate risk under long warm-season outages.", "extended_natural_sensitivity"))
    quality = probability_quality()
    quality_display = quality[["role", "draws", "subset", "n", "groups", "bias_C", "MAE_C", "CRPS_C", "coverage90", "width_C", "Brier_hot"]].copy()
    quality_display["role"] = quality_display.role.map({"development": "Dev.", "calibration": "Cal.", "test": "Test"})
    quality_display["subset"] = quality_display.subset.map({"all": "All", "warm_anomaly": "Warm", "other_years": "Other years", "majority_lowflow_gap": "Low flow", "not_majority_lowflow_gap": "Other flow", "flow_incomplete": "Incomplete flow"})
    quality_display = quality_display.rename(columns={"role": "Role", "draws": "Draws", "subset": "Subset", "n": "N", "groups": "G", "bias_C": "Bias C", "MAE_C": "MAE C", "CRPS_C": "CRPS C", "coverage90": "Cov. 90", "width_C": "Width C", "Brier_hot": "Brier"})
    tables.append(helper.table(quality_display,
         "Developed distribution quality and prefix-sampling sensitivity on available opened cases; unavailable numerical outputs remain explicit in the original-pool system table. Warm-year and low-flow subsets are diagnostic conditions, not additional neural inputs. Low-flow rows require complete forcing coverage; incomplete flow is retained separately. The nominal band is 90 percent, probabilities are raw before Platt calibration, and point shifts compare nested 8/16/32-draw prefixes. Small Monte Carlo shifts cannot establish distributional reliability. Repeated masks are not independent observations.", "extended_probability_quality"))
    all_costs = pd.read_csv(RUN / "system_factorial_developed/decision_costs.csv")
    cost = all_costs.loc[all_costs.fn_cost.eq(5) & all_costs.abstention_cost.eq(.05)].copy()
    shared = cost.method.eq("priority") & cost.score_kind.eq("native_CDF") & cost.policy.isin(["direct_calibrated_NN_cost", "all_unknown", "all_hot", "all_cool"])
    retain = cost.policy.isin(["magnitude_screen", "random_matched_screen"]) | (cost.score_kind.eq("native_CDF") & cost.policy.eq("reconstruct_all")) | shared
    cost = cost.loc[retain].copy()
    cost.loc[shared.loc[cost.index], "method"] = "Shared"
    cost.loc[~cost.policy.isin(["magnitude_screen", "random_matched_screen"]), "score_kind"] = "--"
    cost["method"] = cost.method.replace({"csdi_developed_air": "Neural point"})
    cost["score_kind"] = cost.score_kind.replace({"native_CDF": "CDF", "boost_direct": "Direct", "boost_window": "Window"})
    cost["policy"] = cost.policy.replace({"direct_calibrated_NN_cost": "CDF cost decision", "magnitude_screen": "Magnitude screen", "random_matched_screen": "Matched random"})
    cost = cost[["method", "score_kind", "policy", "n_candidates", "loss", "false_negative", "false_positive", "unknown"]].rename(columns={"score_kind": "Head", "policy": "Action"})
    tables.append(helper.table(cost, "Developed-system absolute use loss on all 945 original controlled Swiss candidates, at missed-hot cost five and unknown cost 0.05. Native-CDF/direct/window admission heads screen each point separately. Reconstruction, screening and matched-random references are method specific; the calibrated H30-law decision and constant answers are shared across points. Random counts are exact expectations, and unavailable point answers remain unknown. These secondary cost parameters are experimental, and results are opened-data supplements, not new confirmation.", "extended_system_costs"))
    (PAPER / "si_r5_tables.tex").write_text("% Generated from extended evidence by script 391.\n" + "\n".join(tables))
    crps = development.set_index("configuration").equal_group_h30_crps_C
    max_success = power.true_joint_power.max()
    test_quality = quality.loc[quality.role.eq("test") & quality.draws.eq(32) & quality.subset.eq("all")].iloc[0]
    test_shift = quality.loc[quality.role.eq("test") & quality.draws.eq(8) & quality.subset.eq("all"), "point_shift_from32_C"].iloc[0]
    warm_quality = quality.loc[quality.role.eq("test") & quality.draws.eq(32) & quality.subset.eq("warm_anomaly")].iloc[0]
    lowflow_quality = quality.loc[quality.role.eq("test") & quality.draws.eq(32) & quality.subset.eq("majority_lowflow_gap")].iloc[0]
    neural_direct = operating.loc[operating.method.eq("csdi_developed_air") & operating.score_kind.eq("boost_direct")].iloc[0]
    neural_window = operating.loc[operating.method.eq("csdi_developed_air") & operating.score_kind.eq("boost_window")].iloc[0]
    neural_native = operating.loc[operating.method.eq("csdi_developed_air") & operating.score_kind.eq("native_CDF")].iloc[0]
    air_direct = operating.loc[operating.method.eq("air2stream3") & operating.score_kind.eq("boost_direct")].iloc[0]
    air_window = operating.loc[operating.method.eq("air2stream3") & operating.score_kind.eq("boost_window")].iloc[0]
    use_cell = all_costs.loc[all_costs.fn_cost.eq(5) & all_costs.abstention_cost.eq(.05)]
    neural_cost = use_cell.loc[use_cell.method.eq("csdi_developed_air") & use_cell.policy.eq("magnitude_screen")].set_index("score_kind").loss
    cdf_cost = use_cell.loc[use_cell.method.eq("priority") & use_cell.score_kind.eq("native_CDF") & use_cell.policy.eq("direct_calibrated_NN_cost"), "loss"].iloc[0]
    (PAPER / "r5_results.tex").write_text(
        "\\subsection{A developed probability reference does not remove the evidence requirements}\n\n"
        f"Two air-conditioned CSDI configurations use the same 3,469 old fitting station-years, thirty group-disjoint old validation components, five task masks per component, and equal thirty-epoch maximum budgets. Their H30 CRPS values are {crps.loc['air32']:.3f} and {crps.loc['air64']:.3f}\\,$^{{\\circ}}$C; the old-only rule selects {selected['selected']}. Thirty-two samples support a shared H30 distribution for priority, Air2stream-3 and neural points. The same distribution supplies the direct failure-probability reference before extra windows, and use-matched hot probabilities. Each point relearns its own error and recalibrates admission. Full denominators and the native-CDF rule are retained in SI; these opened-data additions establish no new independent advantage.\n\n"
        f"The selected model returns finite distributions for {int(test_quality.n)} of {int(test_quality.original_N)} controlled Swiss test candidates. Among these predictions, H30 CRPS is {test_quality.CRPS_C:.3f}\\,$^{{\\circ}}$C, nominal-90\\% coverage is {100*test_quality.coverage90:.1f}\\%, and mean band width is {test_quality.width_C:.3f}\\,$^{{\\circ}}$C. Warm-year signed bias is {warm_quality.bias_C:.3f}\\,$^{{\\circ}}$C; coverage on the {int(lowflow_quality.n)} majority-low-flow gaps with complete flow records is {100*lowflow_quality.coverage90:.1f}\\%. These are overlapping diagnostic conditions, not identified causal effects. The mean absolute functional-point change from eight to thirty-two draws is {test_shift:.3f}\\,$^{{\\circ}}$C. Sampling stability cannot repair distributional miscalibration.\n\n"
        "\\input{r6_calibration_budget.tex}\n\n"
        f"The window increment depends on the delivered point and direct comparator. For the neural point, the window head accepts {int(neural_window.accepted)} candidates with {int(neural_window.failed)} failures, versus {int(neural_direct.accepted)} with {int(neural_direct.failed)} for the boosted direct head: a conditional {100*(neural_window.retention-neural_direct.retention):.1f}-point retention increase. However, the native CDF rule already accepts {int(neural_native.accepted)} with {int(neural_native.failed)} failures, exceeding the window head's retention with lower sample risk. For Air2stream-3, boosted-head acceptance instead changes from {int(air_direct.accepted)} to {int(air_window.accepted)}, with failures changing from {int(air_direct.failed)} to {int(air_window.failed)}. No cell has positive formal admission. These opened-data operating points neither establish a new independent advantage over the strongest direct reference nor support a universal negative claim about window information.\n\n"
        f"At missed-hot cost five and unknown cost 0.05 on the same 945-candidate pool, the neural direct-head magnitude screen has loss {neural_cost.loc['boost_direct']:.4f}, versus {neural_cost.loc['boost_window']:.4f} for its window head. The calibrated CDF cost decision has loss {cdf_cost:.4f}; all-unknown loss is 0.0500. Numerical retention, numerical risk and label loss therefore rank these choices differently. These are secondary declared-cost comparisons, not ecological losses or new confirmatory wins.\n\n"
        f"Joint planning for the original priority-point comparison refits learning and calibration 3,000 times across training, calibration and evaluation budgets. Its largest primary source-like joint success estimate is {100*max_success:.1f}\\%, with no evaluated budget cell supporting the 80\\% target. Actual role supports are only 59/21/24 components; simulated budgets do not create observed histories or unseen climates. These calculations neither plan the neural-point candidate nor justify recruiting a nominal 59 or 118 groups for it.\n\n"
        "A newly inspected DFO redundant-logger resource yields no cases within the original three-complete-prior-year support. Three compatible backup-reference pair-years represent only two primary logger-years outside that support. Their four cold-season daily deficits contain 8--19 hourly measurements, rather than demonstrated whole-day failures. Interpolation and the old univariate reference preserve H30 because its hot window remains observed; this is not evidence of difficult peak recovery. These project aggregates and free backup union are separate sensitivities, not warm-season outage confirmation or a costly-acquisition benefit \\cite{dfo2024}.\n")
    (PAPER / "r5_methods.tex").write_text(
        "\\subsection{Developed probability and joint-design checks}\n\n"
        "A further probability-reference budget compares two air-conditioned CSDI widths using old group-disjoint data only. Fitting has 3,469 years, while thirty old validation groups each provide five predeclared peak, boundary and fragmented masks. Early stopping uses masked-water validation loss; configuration selection uses H30 CRPS in degrees Celsius. Source normalization excludes the target year, and observed water remains fixed. We report compute and 8/16/32-sample sensitivity. Distribution samples are shared across reconstruction points so direct failure probability is computed for each delivered point before testing added windows. Calibration and use decisions retain their independent roles and original pools.\n\n"
        "The joint sample-budget experiment refits both direct-probability heads, recalibrates thresholds and evaluates paired components in 1,000 repetitions per training size. Original role supports remain disjoint; simulated larger groups are iid draws from their finite empirical role laws, not new observations. Primary gain evidence uses the bounded paired difference in $[-1,1]$, with one-sided lower bound $\\bar D-\\sqrt{2\\log(1/\\alpha)/G}$ \\cite{hoeffding1963}. Risk tests allocate error separately to both models. With formal calibration, this original paired experiment splits its 5\\% familywise budget as 0.005 per calibration head (with candidate-family correction), 0.01 per test risk and 0.02 for gain. The empirical selector remains heuristic; independently evaluated test-risk and gain evidence are still required. A normal-bound sensitivity is explicitly non-primary. Monte Carlo intervals are adjusted over the planning grid. Source-like simulations cannot verify independence or represent new hydrological types. The separate future protocol now retains both native-CDF and matched-boosting direct references, requiring joint success against each. Its three risk tests, three formal calibrations and two gain tests share a new 5\\% error allocation; the original paired source plan does not establish power for that future procedure.\n")
    (PAPER / "r5_supporting.tex").write_text(
        "\\subsection{Expanded probability development and natural-record readiness}\n"
        "The developed neural reference conditions on water and available air, unlike the original fixed univariate reference. Both new widths share data and development limits. It is therefore an information and budget change relative to the original reference, not proof of an architectural improvement. The developed system supplies its entire empirical H30 law to every point arm, including native tolerance-exceedance probability; extra window features cannot be credited merely for supplying previously omitted direct uncertainty. Group-disjoint development/calibration/testing roles and unavailable original candidates remain explicit. Thirty-two scenarios per case are evaluated using twelve parallel case-chunk workers per role, one torch thread and batch thirty-two each. An optional shared tail scheduler adds thirty-two workers calling exactly the same sampler on the same reconstructed inputs. Each chunk has a distinct deterministic seed. Repeated-input batching changes random-number ordering but not the conditional sampling law; scheduling cannot change cached chunk outputs. This remains a finite development budget, not a probability-model ceiling.\n\n"
        "The Canadian archive is staged, and its metadata and source models are fixed, before thermal outcomes are opened. An amended reference definition is written after metadata inspection but before temperature inspection: observed primary days plus independent backup on missing days define a complete recorded year, and both serial orientations are candidates. Sensor agreement and minimum daily coverage are fixed before reconstruction errors. Implementation corrections distinguish moved loggers by reported coordinates and preserve a finite reading when its duplicate is missing; no threshold or historical-support requirement is relaxed. One dependent provincial cohort is retained rather than assigning independent certainty to sensors or repeated references. No originally supported case survives; a separately prespecified short-history sensitivity retains all three history-ineligible but reference-compatible pair-years. The later raw-sampling clarification does not exclude any of those references.\n\n"
        "Raw sampling audits distinguish absent hourly records from under-covered daily means. All four selected deficient days retain some observations and occur in winter. Illustrative missing-temperature ceilings of 40, 60 and 100 degrees leave the annual H30 upper and observed-window lower bounds equal in these two records. These are conditional support sensitivities, not validated physical or sensor-error bounds; they explain why this sample is weak evidence for peak recovery. True warmer and longer outages with suitable backups remain necessary. Public free backups and air forcing are incorporated or shown as references, never assigned invented query costs.\n")
    # Place numerical evidence beside its scientific question, rather than
    # appending the entire development history to the end of Results.
    paragraphs = (PAPER / "r5_results.tex").read_text().split("\n\n")
    if len(paragraphs) != 8:
        raise RuntimeError("Developed-result paragraph structure changed")
    (PAPER / "r5_results.tex").write_text(paragraphs[2] + "\n\n" + paragraphs[4] + "\n")
    (PAPER / "r5_use_results.tex").write_text(paragraphs[5] + "\n")
    (PAPER / "r5_planning_results.tex").write_text(paragraphs[6] + "\n")
    (PAPER / "r5_natural_results.tex").write_text(
        paragraphs[7].replace("\\cite{dfo2024}", "(Fisheries and Oceans Canada, 2024; see the article reference list)") + "\n")
    method_paragraphs = (PAPER / "r5_methods.tex").read_text().split("\n\n")
    (PAPER / "r5_methods.tex").write_text("\\subsection{Conditional H30 distributions}\n\n" + method_paragraphs[1] + "\n")
    (PAPER / "r5_planning_methods.tex").write_text(
        method_paragraphs[2].replace("\\cite{hoeffding1963}", "(Hoeffding, 1963; see the article reference list)") + "\n")
    with (PAPER / "r5_supporting.tex").open("a") as handle:
        handle.write("\n\\subsection{Joint budget design and backup-reference eligibility}\n"
                     "\\input{r5_planning_methods.tex}\n\\input{r5_planning_results.tex}\n\\input{r8_three_method_planning.tex}\n\\input{r5_natural_results.tex}\n")
    methods = PAPER / "r3_methods.tex"
    if "r5_methods.tex" not in methods.read_text():
        methods.write_text(methods.read_text() + "\n\\input{r5_methods.tex}\n")
    results = PAPER / "r3_results.tex"
    if "r5_results.tex" not in results.read_text():
        results.write_text(results.read_text() + "\n\\input{r5_results.tex}\n")
    supporting = PAPER / "wrr_supporting_information.tex"
    text = supporting.read_text()
    if "si_r5_tables.tex" not in text:
        text = text.replace("\\input{si_r4_tables.tex}", "\\input{si_r4_tables.tex}\n\\input{r5_supporting.tex}\n\\input{si_r5_tables.tex}")
    if "si_r6_tables.tex" not in text:
        text = text.replace("\\input{si_r5_tables.tex}", "\\input{si_r5_tables.tex}\n\\input{si_r6_tables.tex}")
    if "si_r8_tables.tex" not in text:
        text = text.replace("\\input{si_r6_tables.tex}", "\\input{si_r6_tables.tex}\n\\input{si_r8_tables.tex}")
    if (PAPER / "si_r10_tables.tex").exists() and "si_r10_tables.tex" not in text:
        text = text.replace("\\input{si_r8_tables.tex}", "\\input{si_r8_tables.tex}\n\\input{si_r10_tables.tex}")
    for old in (35, 40, 41, 42, 43):
        text = text.replace(f"Tables S1--S{old}", "Tables S1--S44").replace(f"Tables S25--S{old}", "Tables S25--S44")
    if (PAPER / "si_r10_tables.tex").exists():
        text = text.replace("Tables S1--S44", "Tables S1--S50").replace("Tables S25--S44", "Tables S25--S50")
        text = text.replace("Tables S25--S50 are supplementary analyses of previously opened outcomes.",
                            "Tables S25--S50 contain supplementary development, planning and source-qualification evidence; they do not constitute a new joint confirmation.")
    supporting.write_text(text)
    bibliography = PAPER / "references_r3.bib"
    entries = {
        "dfo2024": "\n@misc{dfo2024,\n  author = {{Fisheries and Oceans Canada}},\n  title = {Water Temperature and Level Monitoring in Newfoundland and Labrador Rivers},\n  year = {2024},\n  url = {https://open.canada.ca/data/en/dataset/bef00bd7-255e-461c-a08b-09f81977170c},\n  note = {Metadata updated 24 March 2026; accessed 20 October 2026}\n}\n",
        "hoeffding1963": "\n@article{hoeffding1963,\n  author = {Hoeffding, Wassily},\n  title = {Probability Inequalities for Sums of Bounded Random Variables},\n  journal = {Journal of the American Statistical Association},\n  volume = {58},\n  number = {301},\n  pages = {13--30},\n  year = {1963},\n  doi = {10.1080/01621459.1963.10500830}\n}\n"
    }
    bib_text = bibliography.read_text()
    for key, value in entries.items():
        if "{" + key + "," not in bib_text:
            bib_text += value
    bibliography.write_text(bib_text)
    inputs = {"probability_selection": probability / "selection.json", "probability_development": probability / "development_results.csv", "developed_system": RUN / "system_factorial_developed/operating.csv", "power_grid": RUN / "joint_power/joint_power_familywise_MC.csv", "natural_qualification": RUN / "natural_backup/qualification_summary.json", "raw_gap_audit": RUN / "natural_backup/short_history/gap_sampling_audit.csv"}
    inputs["distribution_quality"] = probability / "quality_and_sampling.csv"
    inputs["developed_system_costs"] = RUN / "system_factorial_developed/decision_costs.csv"
    if (probability / "parallel_backfill_contract.json").exists():
        inputs["tail_scheduling_contract"] = probability / "parallel_backfill_contract.json"
    C.write_json(RUN / "evidence/extended_bindings.json", run_record(inputs, new_primary_confirmation=False, long_warm_season_natural_outage_validation=False))
    print("[391] developed reference, joint planning and narrowly qualified backup evidence generated", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--planning-only", action="store_true")
    args = parser.parse_args()
    planning() if args.planning_only else finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
