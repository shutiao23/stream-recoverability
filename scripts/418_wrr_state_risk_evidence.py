#!/usr/bin/env python3
"""Report the completed opened-data conditional-law and system comparisons."""
from __future__ import annotations

import argparse
import importlib
import json

import numpy as np
import pandas as pd

import wrr_r3_common as C
from stream_recoverability.experiments.v19_revision.state_trajectory import sample_crps

F = importlib.import_module("416_wrr_state_risk_factorial")
G = F.G
S = importlib.import_module("417_wrr_state_risk_system")
OUT = G.OUT / "evidence"
PAPER = C.ROOT / "paper/wrr"
LABELS = {"raw_block14": "Raw blocks", "visible_adjustment": "Visible shift", "seasonal_slow": "Seasonal slow",
          "seasonal_air_slow": "Seasonal + air", "seasonal_air_flow_slow": "Seasonal + air + flow",
          "neural_air32": "Neural air32", "neural_air32_visible_adjustment": "Neural + visible shift",
          "priority": "Priority", "air2stream3": "Air2stream-3", "air2stream8": "Air2stream-8",
          "neural_median32": "Neural median", "state_median32": "State median", "flow_state_median32": "Flow-state median"}


def condition_masks(frame):
    """Reuse the existing warm and complete-flow definitions, with unknowns kept."""
    if frame.warm_anomaly.isna().any():
        raise ValueError("Warm-year evaluation state is unknown")
    complete = frame.flow_coverage.eq(1).to_numpy()
    fraction = pd.to_numeric(frame.gap_lowflow_fraction, errors="coerce")
    if fraction.loc[complete].isna().any():
        raise ValueError("Complete flow has no verified gap-state fraction")
    return {"all": np.ones(len(frame), dtype=bool), "warm": frame.warm_anomaly.to_numpy(dtype=bool),
            "other_years": ~frame.warm_anomaly.to_numpy(dtype=bool),
            "low_flow": complete & fraction.ge(.5).to_numpy(),
            "other_flow": complete & fraction.lt(.5).to_numpy(), "unknown_flow": ~complete}


def conditional_quality(data, *, draws_count=32, requested_laws=None):
    common = F.common_support(data, list(G.LAWS))
    source = C.READY / "followup_20261021/trajectory/leave_one_year_out/test/cases.parquet"
    flow = pd.read_parquet(source)
    flow = flow.loc[flow.variant.eq("raw_block14") & flow.n_draws.eq(128), G.KEYS + ["flow_coverage", "gap_lowflow_fraction"]]
    rows = []
    for law in requested_laws or G.LAWS:
        frame = data[law].merge(flow, on=G.KEYS, how="left", validate="one_to_one")
        masks = condition_masks(frame)
        for name, mask in masks.items():
            block = frame.loc[common & mask]
            if block.empty:
                rows.append({"law": law, "condition": name, "original_condition_candidates": int(mask.sum()), "n": 0})
                continue
            values = np.stack(block.h30_samples_C.to_numpy())
            if values.shape[1] < draws_count:
                raise ValueError("The requested sampling budget was not generated")
            draws = values[:, :draws_count]
            truth, point = block.truth_hottest30.to_numpy(), block.reconstruction_point.to_numpy()
            median = np.median(draws, axis=1)
            lower, upper = np.quantile(draws, [.05, .95], axis=1)
            raw_failure = np.mean(np.abs(draws - point[:, None]) > .5, axis=1)
            raw_hot = np.mean(draws > block.local_hot_threshold_C.to_numpy()[:, None], axis=1)
            rows.append({"law": law, "condition": name, "original_condition_candidates": int(mask.sum()), "n": len(block),
                         "groups": block.independence_group.nunique(), "CDF_median_bias_C": float((median - truth).mean()),
                         "CRPS_C": float(np.mean([sample_crps(s, t) for s, t in zip(draws, truth)])),
                         "coverage90": float(((lower <= truth) & (truth <= upper)).mean()), "width90_C": float((upper - lower).mean()),
                         "failure_Brier": float(np.mean((raw_failure - block.own_failure.to_numpy()) ** 2)),
                         "hot_Brier": float(np.mean((raw_hot - (truth > block.local_hot_threshold_C.to_numpy())) ** 2))})
    return pd.DataFrame(rows), source


def factorial_table(operating, costs, tier):
    selected = operating.loc[operating.tier.eq(tier)]
    output = []
    for (point, law), rows in selected.groupby(["point", "law"], sort=False):
        arms = rows.set_index("score_kind")
        use = costs.loc[costs.tier.eq(tier) & costs.point.eq(point) & costs.law.eq(law) & costs.fn_cost.eq(5) & costs.abstention_cost.eq(.05)]
        window = use.loc[use.score_kind.eq("boost_window")].set_index("policy")
        output.append({"Point": LABELS[point], "CDF law": LABELS[law], "Matched MAE": rows.matched_point_MAE_C.iloc[0],
                       **{label: f"{int(arms.loc[kind, 'accepted'])}/{int(arms.loc[kind, 'failed'])}"
                          for kind, label in [("native_CDF", "Native A/F"), ("boost_direct", "Direct A/F"), ("boost_window", "Window A/F")]},
                       "Window loss": window.loc["magnitude_screen", "loss"],
                       "Cost-rule loss": window.loc["direct_calibrated_CDF_cost", "loss"]})
    return pd.DataFrame(output)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    selected = json.loads((F.OUT / "development_selection.json").read_text())["selected_law"]
    neural = json.loads((S.OUT / "development_reference_choice.json").read_text())["selected_neural_law"]
    laws = F.role_data("test")
    conditional, _ = conditional_quality(laws)
    conditional.to_csv(OUT / "conditional_quality.csv", index=False)
    sensitivity = [conditional.assign(draws=32)]
    for count in (128, 512):
        diagnostic, _ = conditional_quality(laws, draws_count=count, requested_laws=G.LAWS[:5])
        sensitivity.append(diagnostic.assign(draws=count))
    sensitivity = pd.concat(sensitivity, ignore_index=True)
    sensitivity.to_csv(OUT / "conditional_sampling_quality.csv", index=False)
    quality = pd.read_csv(F.OUT / "distribution_quality.csv")
    operating = pd.read_csv(F.OUT / "operating.csv")
    system = pd.read_csv(S.OUT / "operating.csv")
    costs = pd.read_csv(S.OUT / "decision_costs.csv")
    primary = quality.loc[quality.role.eq("test") & quality.support.eq("common_all_laws") & quality.draws.eq(32)].copy()
    if len(primary) != 7 or primary.n.nunique() != 1:
        raise RuntimeError("Primary law comparison lost common support")
    checks = []
    def check(name, passed):
        checks.append({"check": name, "passed": bool(passed)})
    check("fixed_point_21_complete_cells", len(operating) == 21 and operating.n_candidates.eq(945).all())
    check("system_42_complete_cells", len(system) == 42 and system.n_candidates.eq(945).all())
    check("all_formal_admissions_remain_empty", operating.formal_accepted.eq(0).all() and system.formal_accepted.eq(0).all())
    totals = costs[["true_positive", "true_negative", "false_negative", "false_positive", "unknown"]].sum(axis=1)
    check("all_system_policies_keep_original_candidates", np.allclose(totals, costs.n_candidates))
    baseline = costs.loc[costs.policy.eq("all_unknown")]
    check("all_unknown_loss_is_the_declared_cost", np.allclose(baseline.loss, baseline.abstention_cost))
    check("same_fixed_point_error_across_laws", all(laws[law].own_failure.equals(laws[G.LAWS[0]].own_failure) for law in G.LAWS))
    check("conditional_quality_same_common_sample", conditional.groupby("condition").n.nunique().eq(1).all())
    base = primary.set_index("law")
    condition_all = conditional.loc[conditional.condition.eq("all")].set_index("law")
    check("conditional_all_reproduces_existing_quality", all(np.allclose(base[name].sort_index(), condition_all[name].sort_index(), rtol=0, atol=1e-12)
          for name in ["CRPS_C", "coverage90", "width90_C", "failure_Brier", "hot_Brier"]))
    failure = [row["check"] for row in checks if not row["passed"]]
    if failure:
        raise RuntimeError(f"State-risk evidence failed: {failure}")
    pd.DataFrame(checks).to_csv(OUT / "checks.csv", index=False)
    helper = C.load_script("state_risk_table_writer", C.ROOT / "scripts/383_wrr_followup_evidence.py")
    tables = []
    def table(frame, caption, label):
        frame.to_csv(OUT / f"{label}.csv", index=False)
        tables.append(helper.table(frame, caption, label))
    labels = lambda values: values.map(LABELS)
    display = primary[["law", "n", "CDF_median_MAE_C", "CDF_median_bias_C", "CRPS_C", "coverage90", "width90_C", "failure_Brier", "hot_Brier"]].copy()
    display.law = labels(display.law)
    display = display.rename(columns={"law": "Law", "n": "N", "CDF_median_MAE_C": "Median MAE", "CDF_median_bias_C": "Bias", "CRPS_C": "CRPS", "coverage90": "Cover.", "width90_C": "Width", "failure_Brier": "Failure BS", "hot_Brier": "Hot BS"})
    table(display, "Conditional H30-law quality on identical controlled Swiss cases at 32 draws. All laws evaluate the same original priority point's tolerance event; median error describes a possible alternative numerical point, not a change to that fixed-point comparison. The common subset excludes unsupported laws only by declared availability; full-pool admission and costs retain all 945 candidates. Temperature errors and widths are in degrees Celsius; coverages are fractions. The flow law adds information and is supplementary. Laws and neural configuration were developed on already opened data; these controlled gaps do not estimate natural outage prevalence or provide new independent confirmation.", "state_risk_law_quality")
    display = conditional.loc[conditional.law.isin([neural, selected, "seasonal_air_flow_slow"]) & conditional.condition.isin(["warm", "low_flow", "unknown_flow"]), ["law", "condition", "n", "CDF_median_bias_C", "CRPS_C", "coverage90", "failure_Brier"]].copy()
    display.law = labels(display.law)
    display.condition = display.condition.replace({"warm": "Warm year", "low_flow": "Low-flow gap", "unknown_flow": "Incomplete flow"})
    display = display.rename(columns={"law": "Law", "condition": "Condition", "n": "N", "CDF_median_bias_C": "Bias", "CRPS_C": "CRPS", "coverage90": "Cover.", "failure_Brier": "Failure BS"})
    table(display, "Conditional diagnostics on the common law-support subset at 32 draws. The existing warm-anomaly flag requires recorded H30 at least one degree Celsius above the permitted training climatology's H30; it differs from the local-q90 label used for costs. Low flow requires complete gap-flow observations and at least half of missing-water days at or below the permitted training month's discharge twentieth percentile. Incomplete flow remains unknown. Conditions overlap and masks do not create independent events or physical attribution. The neural reference and residual candidate were selected using old development CRPS only.", "state_risk_conditions")
    display = quality.loc[quality.role.eq("test") & quality.support.eq("common_all_laws") & quality.law.isin(G.LAWS[:5]), ["law", "draws", "n", "CRPS_C", "coverage90", "width90_C", "failure_Brier"]].copy()
    warm_sampling = sensitivity.loc[sensitivity.condition.eq("warm"), ["law", "draws", "coverage90", "CDF_median_bias_C"]]
    display = display.merge(warm_sampling.rename(columns={"coverage90": "warm_coverage90", "CDF_median_bias_C": "warm_bias_C"}), on=["law", "draws"], validate="one_to_one")
    display.law = labels(display.law)
    display = display.rename(columns={"law": "Law", "draws": "Draws", "n": "N", "CRPS_C": "CRPS", "coverage90": "Cover.", "width90_C": "Width", "failure_Brier": "Failure BS", "warm_coverage90": "Warm cover.", "warm_bias_C": "Warm bias"})
    table(display, "Nested 32/128/512-draw sensitivity for residual laws on common opened Swiss support. Admission comparisons use only the first 32 draws for every law. The same fixed laws and cases isolate the finite sampling budget: aggregate empirical-band coverage can approach its nominal level as draws increase, while the warm-year columns retain conditional errors. Warm cover and bias use the same 357 common warm-year cases. Larger scenario sets do not supply new river events or verify transfer. Neural laws have only their preserved 32 draws and are not represented as 128- or 512-draw experiments.", "state_risk_sampling")
    display = []
    for law, rows in operating.groupby("law", sort=False):
        arms = rows.set_index("score_kind")
        display.append({"Law": LABELS[law], "CDF available": int(rows.cdf_available.iloc[0]),
                        **{label: f"{int(arms.loc[kind,'accepted'])}/{int(arms.loc[kind,'failed'])}"
                           for kind, label in [("native_CDF", "Native A/F"), ("boost_direct", "Direct A/F"), ("boost_window", "Window A/F")]}})
    table(pd.DataFrame(display), "Fixed-priority-point admission for seven H30 laws and three matched score types. A/F is accepted/failed, with failure defined by absolute priority-point error above 0.5 degrees Celsius. All 945 original candidates remain, including unsupported laws as unknown. Boosted heads share the declared common fitting/calibration support and generic feature budget; the window head adds only the corresponding law's window summaries. Values use the empirical calibration rule; all 21 multiplicity-adjusted formal rules give no admission, whose risk is undefined. Sample operating risk is not a population guarantee.", "state_risk_fixed_point")
    table(factorial_table(system, costs, "available_air"), "Complete same-air point/law/score system comparison. Each row contains three own-error heads, hence 24 cells across four points and two development-selected laws. Matched MAE uses the identical 828 supported test cases. Every admission and loss uses all 945 original candidates, charging unavailable outputs as unknown. Losses use missed-hot cost five and unknown cost 0.05; always unknown therefore has loss 0.05. Window loss uses numerical screening followed by classification; cost-rule loss directly compares cool, hot and unknown expected costs. All references, random-rejection expectations and cost grids are retained in the source CSV. Empirical operating points do not certify risk, and all formal admissions remain empty.", "state_risk_air_system")
    table(factorial_table(system, costs, "air_and_flow"), "Flow-tier system comparison, separately from the same-air tier. Each row contains native-CDF, direct and window heads, giving 18 cells across three numerical points and two laws. Matched MAE uses 821 common supported cases; admission and utility retain all 945 candidates. The flow-conditioned law and Air2stream-8 add observed discharge information and do not identify an architectural effect. A/F denotes accepted/failed, with the same 0.5-degree event. The illustrated loss uses missed-hot cost five and unknown cost 0.05. All formal rules have empty admission.", "state_risk_flow_system")
    (PAPER / "si_r10_tables.tex").write_text("% Generated by script 418 from the completed old-data experiments.\n" + "\n".join(tables))
    candidate = base.loc[selected]
    raw = base.loc["raw_block14"]
    n = int(candidate.n)
    state_native = operating.loc[operating.law.eq(selected) & operating.score_kind.eq("native_CDF")].iloc[0]
    state_window = operating.loc[operating.law.eq(selected) & operating.score_kind.eq("boost_window")].iloc[0]
    warm = conditional.set_index(["law", "condition"])
    warm_state, warm_neural = warm.loc[(selected, "warm")], warm.loc[(neural, "warm")]
    warm512 = sensitivity.loc[sensitivity.law.eq(selected) & sensitivity.condition.eq("warm") & sensitivity.draws.eq(512)].iloc[0]
    all512 = quality.loc[quality.role.eq("test") & quality.support.eq("common_all_laws") & quality.law.eq(selected) & quality.draws.eq(512)].iloc[0]
    note = ("A further experiment on previously opened data separates the conditional H30 law from its delivered numerical point. It retains the same controlled crossed-contiguous Swiss cases as the earlier reconstruction factorial; these masks do not estimate natural outage prevalence. Seven laws retain one priority point, including raw blocks, visible shifts, seasonal slow-plus-short residuals with and without available air, a separate flow tier, and the preserved air32 neural law with and without the same visible shift. Residual laws supply 512 nested draws for sampling diagnostics; all primary law, score and use comparisons use 32 draws. Observations remain fixed and residual histories exclude each target year. This is retrospective supplementation, not a change to the frozen prospective predictor.\n\n"
            f"CRPS on the common development cases selects the residual model conditioned on season and air temperature. On {n} common old Swiss test cases, its CRPS is {candidate.CRPS_C:.3f} versus {raw.CRPS_C:.3f} degrees Celsius for raw blocks, and nominal-90\\% coverage is {100*candidate.coverage90:.1f}\\% versus {100*raw.coverage90:.1f}\\% (Tables~\\ref{{tab:state_risk_law_quality}}--\\ref{{tab:state_risk_sampling}}). At the unchanged priority point, its native CDF rule accepts {int(state_native.accepted)} cases with {int(state_native.failed)} failures, while the corresponding window head accepts {int(state_window.accepted)} with {int(state_window.failed)} failures. These empirical operating points neither establish the joint five-point advantage against both direct references nor certify risk.\n\n"
            f"The aggregate improvement does not resolve warm-year errors. Across {int(warm_state.n)} common warm-year cases at 32 draws, the selected residual law's H30 median bias is {warm_state.CDF_median_bias_C:.3f} degrees Celsius and coverage is {100*warm_state.coverage90:.1f}\\%; the neural reference has bias {warm_neural.CDF_median_bias_C:.3f} and coverage {100*warm_neural.coverage90:.1f}\\%. With 512 draws the selected residual law reaches {100*all512.coverage90:.1f}\\% aggregate coverage, showing an effect of the finite empirical-band budget. Its warm-year coverage remains {100*warm512.coverage90:.1f}\\% and bias {warm512.CDF_median_bias_C:.3f} degrees Celsius. These overlapping diagnostic conditions do not identify a physical cause or demonstrate transfer to an unseen climate or event.\n\n"
            "The system experiment also changes numerical point while refitting each point's own error and calibrated admission. Four points, two same-air laws and three score types give 24 cells; a separate flow tier adds 18. The 945-candidate denominator is retained for every decision, while common-subset MAE has 828 same-air or 821 flow-supported cases. Improved point error does not by itself validate a CDF tolerance event or admission threshold. All 63 formal rules across the law and system experiments have empty admission. Conditional warm/flow checks and full expected-cost references remain supplementary, with unchanged original H1--H3 and no new independent confirmation.\n")
    (PAPER / "r10_state_risk.tex").write_text(note)
    C.write_json(OUT / "summary.json", {"fixed_point_cells": 21, "system_cells": 42, "same_air_system_cells": 24, "additional_flow_system_cells": 18,
                 "selected_residual_law": selected, "selected_neural_reference_law": neural, "original_test_candidates": 945,
                 "common_distribution_test_candidates": n, "formal_positive_cells": 0, "checks_passed": len(checks),
                 "new_independent_confirmation_completed": False, "prospective_predictive_bank_changed": False,
                 "new_USGS_or_Australian_prediction_errors_opened": False})
    print(f"[418] {len(checks)} checks; six evidence tables for 21 law and 42 system cells; no new confirmation", flush=True)
    return 0


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    raise SystemExit(main())
