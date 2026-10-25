#!/usr/bin/env python3
"""TR evidence: every number quoted in the target-recovery manuscript, and its tables.

Writes paper/wrr_tr/tr_claims.tex (LaTeX macros), tr_tables_main.tex and
tr_si_tables.tex from the result files, plus a machine-readable claims.json.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import wrr_tr_common as T

PAPER = T.ROOT / "paper/wrr_tr"
OUT = T.OUT / "evidence"
RULE_NAMES = {
    "R1_complete_year (USGS/SWToolbox)": "Complete calendar year (USGS statistics service)",
    "R1_usgs_indicator_311d_24pm": "$\\geq$311 days and $\\geq$24 days per month (USGS indicators)",
    "R1_usgs_indicator_strict_7d": "As above, $\\geq$26 days per month and $\\leq$1 missing day per 7 days",
    "R1_wmo_11_5": "WMO-1203 11/5 rule for every month",
    "R1_etccdi_15_3": "ETCCDI: $\\leq$15 missing days, $\\leq$3 per month",
    "R1_gsim_350d": "GSIM: $\\geq$350 observed days",
    "R1_michel_no_gap_over_14d": "No gap longer than 14 days (Michel et al.)",
    "R1_johnson_gap_le_49d": "Longest gap $\\leq$49 days (Johnson et al.)",
    "R2_oregon_jas_80pct": "July--September $\\geq$80\\% observed (Oregon)",
    "R2_norwest_aug_90pct": "August $\\geq$90\\% observed (NorWeST)",
    "R2_beaufort_julaug_complete": "July--August complete (Beaufort et al.)",
    "R2_dunham_jul15_sep15_complete": "15 July--15 September complete (Dunham et al.)",
    "R2_warm_gap_le_7d": "Longest May--September gap $\\leq$7 days",
    "R2_warm_gap_le_14d": "Longest May--September gap $\\leq$14 days",
    "R2_warm_gap_le_30d": "Longest May--September gap $\\leq$30 days",
}
SCORE_NAMES = {
    "R1_annual_missing_fraction": "Annual missing fraction (threshold varied)",
    "R2_warm_missing_fraction": "Warm-season missing fraction (threshold varied)",
    "R3_observed_lower_bound (NRFA-type)": "Observed lower bound (NRFA type)",
    "R4_daily_disagreement": "Daily reconstruction disagreement",
    "R5_h30_target_disagreement": "H30 reconstruction disagreement",
    "R6_recovery_law_pfail": "Recovery law, parametric (v2)",
    "R6b_replay_law_pfail": "Recovery law, training-year replay (v3)",
    "R7a_target_aware_pfail (D2* distribution)": "Target-aware: D2* predictive distribution",
    "R7b_direct_failure_probability (P0)": "Direct failure probability (plug-in value)",
    "R7b_direct_failure_probability (D2*)": "Direct failure probability (D2* value)",
    "R8_oracle_error_order": "Oracle error order (bound)",
}
ESTIMATOR_NAMES = {"P0": "P0 plug-in", "Pobs": "Recorded days only", "P1": "Air2stream-3", "P2": "P2 functional debiasing", "P3": "P3 air-state simulation", "P3raw": "P3 raw residual blocks", "P5a": "P5a distribution regression", "P5b": "P5b = D2*"}
TARGET_NAMES = {"h30": "H30", "h7": "H7", "annual_mean": "Annual mean", "c30": "C30", "degree_days_jjas": "Jun--Sep degree-days", "days_above_20": "Days $>$20\\,$^{\\circ}$C"}


def number(value: float, digits: int = 2) -> str:
    if value is None or not np.isfinite(value):
        return "--"
    text = f"{value:,.{digits}f}"
    return text.replace(",", "{,}")


def pct(value: float, digits: int = 1) -> str:
    return number(100 * value, digits)


def read_json(path: str) -> dict:
    return json.loads((T.OUT / path).read_text())


def table(frame: pd.DataFrame, caption: str, label: str, columns: str, header: list[str], size: str = "\\scriptsize") -> str:
    lines = ["\\begin{table}", f"\\caption{{{caption}}}", f"\\label{{{label}}}", "\\centering", size, "\\fittable{%", f"\\begin{{tabular}}{{{columns}}}", "\\toprule", " & ".join(header) + " \\\\", "\\midrule"]
    for row in frame.itertuples(index=False):
        lines.append(" & ".join(str(v) for v in row) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "}", "\\end{table}", ""]
    return "\n".join(lines)


def main() -> int:
    PAPER.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    macros: dict[str, str] = {}
    claims: dict[str, float] = {}

    def put(name: str, value, text: str | None = None) -> None:
        claims[name] = value if not isinstance(value, (np.floating, np.integer)) else float(value)
        macros[name] = text if text is not None else str(value)

    # Archive and cases.
    archive = read_json("e1_archive/summary.json")
    put("TArchiveStations", archive["n_stations"], number(archive["n_stations"], 0))
    put("TArchiveYears", archive["n_station_years"], number(archive["n_station_years"], 0))
    cases = read_json("e2_cases/cases_summary.json")
    put("TSourceCases", cases["n_cases"], number(cases["n_cases"], 0))
    put("TSourceYears", cases["n_station_years"], number(cases["n_station_years"], 0))
    put("TSourceStations", cases["n_stations"], number(cases["n_stations"], 0))
    put("TSourceGroups", cases["n_groups"], number(cases["n_groups"], 0))
    put("TSourceRegions", cases["n_regions"], number(cases["n_regions"], 0))
    put("TCrossedCases", cases["families"]["crossed"], number(cases["families"]["crossed"], 0))
    put("TCalendarCases", cases["families"]["calendar"], number(cases["families"]["calendar"], 0))
    put("TAirLayerShare", cases["policy"]["air_ridge"] / cases["n_cases"], pct(cases["policy"]["air_ridge"] / cases["n_cases"], 0))
    tolerance = read_json("e2_prereg/target_tolerances.json")
    for key, name in (("h7", "TTolHSeven"), ("annual_mean", "TTolMean"), ("c30", "TTolCThirty"), ("degree_days_jjas", "TTolDD"), ("days_above_20", "TTolDays")):
        put(name, tolerance["tolerance"][key], number(tolerance["tolerance"][key], 2 if key not in ("degree_days_jjas", "days_above_20") else 1))

    # E1.
    e1 = read_json("e1_missingness/summary.json")
    models = pd.read_csv(T.OUT / "e1_missingness/missingness_models.csv")

    def odds(analysis: str, covariate: str, prefix: str) -> None:
        row = models.loc[(models.analysis == analysis) & (models.covariate == covariate)].iloc[0]
        put(prefix, row.odds_ratio, number(row.odds_ratio, 2))
        put(prefix + "Low", row.odds_ratio_lower95, number(row.odds_ratio_lower95, 2))
        put(prefix + "High", row.odds_ratio_upper95, number(row.odds_ratio_upper95, 2))

    odds("station_year_conditional_logit", "z_air", "TOrAir")
    odds("station_year_conditional_logit_julaug", "z_air", "TOrAirJulAug")
    odds("station_year_mixed_station_region_year", "z_air", "TOrAirMixed")
    odds("onset_case_crossover_air", "z_air_week", "TOrOnset")
    odds("onset_case_crossover_air_water", "z_water_lag", "TOrWater")
    odds("onset_case_crossover_usgs_flow", "low_flow", "TOrLowFlow")
    odds("station_year_conditional_logit", "trend", "TOrDecade")
    odds("gap_log_duration_station_fe", "z_air_week", "TDurationRatio")
    put("TEOneYears", e1["n_station_years"], number(e1["n_station_years"], 0))
    put("TEOneStations", e1["n_stations"], number(e1["n_stations"], 0))
    put("TWarmIncomplete", e1["warm_incomplete_share"], pct(e1["warm_incomplete_share"], 0))
    put("THotContrast", e1["hot_summer_contrast_warm_incomplete"], pct(e1["hot_summer_contrast_warm_incomplete"], 1))
    put("THotContrastLow", e1["hot_summer_contrast_lower95"], pct(e1["hot_summer_contrast_lower95"], 1))
    put("THotContrastHigh", e1["hot_summer_contrast_upper95"], pct(e1["hot_summer_contrast_upper95"], 1))
    put("TImpliedBias", e1["implied_complete_year_h30_bias_mean_C"], number(e1["implied_complete_year_h30_bias_mean_C"], 3))
    put("TImpliedBiasLow", e1["implied_bias_lower95"], number(e1["implied_bias_lower95"], 3))
    put("TImpliedBiasHigh", e1["implied_bias_upper95"], number(e1["implied_bias_upper95"], 3))

    # E3.
    law = pd.read_csv(T.OUT / "e3_recovery_law/summary.csv")

    def law_value(population: str, version: str, metric: str, truncated: bool = True) -> float:
        rows = law.loc[(law.population == population) & (law.version == version) & (law.metric == metric)]
        if "truncated" in rows and rows.truncated.notna().any():
            rows = rows.loc[rows.truncated.astype(str).str.lower().eq(str(truncated).lower())]
        return float(rows.value.iloc[0])

    put("TLawEceMech", law_value("mech", "v2", "ece"), number(law_value("mech", "v2", "ece"), 3))
    put("TLawEceDeploy", law_value("deploy", "v2", "ece"), number(law_value("deploy", "v2", "ece"), 3))
    put("TLawBrierSkillMech", law_value("mech", "v2", "brier_skill_vs_base_rate"), pct(law_value("mech", "v2", "brier_skill_vs_base_rate"), 0))
    put("TLawBrierSkillDeploy", law_value("deploy", "v2", "brier_skill_vs_base_rate"), pct(law_value("deploy", "v2", "brier_skill_vs_base_rate"), 0))
    cells = law.loc[law.population.eq("mech_cells")].set_index("metric").value
    put("TLawCellFailEV", cells["explained_variance_failure_rate_by_law_pfail"], pct(cells["explained_variance_failure_rate_by_law_pfail"], 0))
    put("TLawCellBiasEV", cells["explained_variance_mean_error_by_law_bias"], pct(cells["explained_variance_mean_error_by_law_bias"], 0))
    put("TLawCellBiasEVUntruncated", cells["explained_variance_mean_error_by_law_bias_untruncated"], pct(cells["explained_variance_mean_error_by_law_bias_untruncated"], 0))
    put("TLawVOneCellBiasEV", cells["explained_variance_mean_error_by_law_v1_bias"], pct(cells["explained_variance_mean_error_by_law_v1_bias"], 0))
    put("TReplayCellBiasEV", cells["explained_variance_mean_error_by_law_v3_bias"], pct(cells["explained_variance_mean_error_by_law_v3_bias"], 0))
    put("TReplayCellFailEV", cells["explained_variance_failure_rate_by_law_v3_pfail"], pct(cells["explained_variance_failure_rate_by_law_v3_pfail"], 0))
    put("TReplayBiasMech", law_value("mech", "v3", "mean_predicted_bias"), number(law_value("mech", "v3", "mean_predicted_bias"), 3))
    put("TObservedBiasMech", law_value("mech", "v3", "observed_mean_error"), number(law_value("mech", "v3", "observed_mean_error"), 3))
    put("TReplayEceMech", law_value("mech", "v3", "ece"), number(law_value("mech", "v3", "ece"), 3))
    by_layer = pd.read_csv(T.OUT / "e3_recovery_law/by_layer.csv").set_index(["population", "layer"])
    put("TLawRTwoAir", by_layer.loc[("mech", "air_ridge"), "law_r2"], number(by_layer.loc[("mech", "air_ridge"), "law_r2"], 2))
    put("TLawRTwoDonor", by_layer.loc[("mech", "donor_ridge"), "law_r2"], number(by_layer.loc[("mech", "donor_ridge"), "law_r2"], 2))

    # E4.
    p1 = read_json("e4_estimators/endpoint_P1.json")
    selection = read_json("e4_estimators/d2_selection.json")
    for key, name in (("P1_bias_P0", "TPOneBiasPZero"), ("P1_bias", "TPOneBias"), ("P1_mae_P0", "TPOneMaePZero"), ("P1_mae", "TPOneMae")):
        put(name, p1[key], number(p1[key], 2))
    put("TPOneReduction", p1["P1_reduction"], pct(p1["P1_reduction"], 0))
    put("TPOneReductionLow", p1["P1_reduction_lower95"], pct(p1["P1_reduction_lower95"], 0))
    put("TPOneReductionHigh", p1["P1_reduction_upper95"], pct(p1["P1_reduction_upper95"], 0))
    put("TPOneCoverage", p1["P1_coverage90"], pct(p1["P1_coverage90"], 1))
    put("TPOneCoverageLow", p1["P1_coverage90_lower95"], pct(p1["P1_coverage90_lower95"], 1))
    put("TPOneCoverageHigh", p1["P1_coverage90_upper95"], pct(p1["P1_coverage90_upper95"], 1))
    put("TPOneN", p1["P1_n"], number(p1["P1_n"], 0))
    put("TPOneGroups", p1["P1_n_groups"], number(p1["P1_n_groups"], 0))
    for name, value in selection["mean_quantile_crps"].items():
        put(f"TCrps{name.replace('raw', 'Raw').replace('P', 'P')}".replace("P3Raw", "PThreeRaw").replace("P3", "PThree").replace("P5a", "PFiveA").replace("P5b", "PFiveB"), value, number(value, 3))
    endpoint_p1 = pd.read_csv(T.OUT / "e4_estimators/endpoint_P1.csv").set_index("estimator")
    put("TPOneBiasPTwo", endpoint_p1.loc["P2", "bias"], number(endpoint_p1.loc["P2", "bias"], 2))
    put("TPOneBiasPThree", endpoint_p1.loc["P3", "bias"], number(endpoint_p1.loc["P3", "bias"], 2))
    put("TPOneBiasPThreeRaw", endpoint_p1.loc["P3raw", "bias"], number(endpoint_p1.loc["P3raw", "bias"], 2))
    metrics = pd.read_csv(T.OUT / "e4_estimators/estimator_metrics.csv")

    def metric(population: str, stratum: str, estimator: str, column: str, target: str = "h30") -> float:
        return float(metrics.loc[(metrics.population == population) & (metrics.stratum == stratum) & (metrics.estimator == estimator) & (metrics.target == target), column].iloc[0])

    put("TDeployFailPZero", metric("deploy", "all", "P0", "failure_rate"), pct(metric("deploy", "all", "P0", "failure_rate"), 1))
    put("TDeployFailDTwo", metric("deploy", "all", "P5b", "failure_rate"), pct(metric("deploy", "all", "P5b", "failure_rate"), 1))
    put("TDeployFailObs", metric("deploy", "all", "Pobs", "failure_rate"), pct(metric("deploy", "all", "Pobs", "failure_rate"), 1))
    put("TMechFailPZero", metric("mech", "all", "P0", "failure_rate"), pct(metric("mech", "all", "P0", "failure_rate"), 1))
    put("TMechFailDTwo", metric("mech", "all", "P5b", "failure_rate"), pct(metric("mech", "all", "P5b", "failure_rate"), 1))
    put("TWarmAnomBiasPZero", metric("mech", "warm_anomaly_half_hidden", "P0", "bias"), number(metric("mech", "warm_anomaly_half_hidden", "P0", "bias"), 2))
    put("TWarmAnomBiasDTwo", metric("mech", "warm_anomaly_half_hidden", "P5b", "bias"), number(metric("mech", "warm_anomaly_half_hidden", "P5b", "bias"), 2))
    put("TMechCoverageDTwo", metric("mech", "all", "P5b", "coverage90"), pct(metric("mech", "all", "P5b", "coverage90"), 1))
    put("TMechCoverageRaw", metric("mech", "all", "P3raw", "coverage90"), pct(metric("mech", "all", "P3raw", "coverage90"), 1))
    put("TAirTwoStreamBias", metric("mech", "air_layer_half_hidden", "P1", "bias"), number(metric("mech", "air_layer_half_hidden", "P1", "bias"), 2))
    put("TObsDaysBiasHidden", metric("mech", "peak_half_hidden", "Pobs", "bias"), number(metric("mech", "peak_half_hidden", "Pobs", "bias"), 2))

    # E5.
    rules = pd.read_csv(T.OUT / "e5_rules/risk_retention.csv")
    deploy = rules.loc[rules.population.eq("deploy")]
    waste = pd.read_csv(T.OUT / "e5_rules/rule_waste.csv")
    waste_deploy = waste.loc[waste.population.eq("deploy")].set_index("rule")
    for key, name in (("R1_usgs_indicator_311d_24pm", "USGS"), ("R1_wmo_11_5", "WMO"), ("R1_etccdi_15_3", "ETCCDI"), ("R1_gsim_350d", "GSIM"), ("R2_oregon_jas_80pct", "Oregon"), ("R2_beaufort_julaug_complete", "Beaufort"), ("R1_johnson_gap_le_49d", "Johnson")):
        put(f"TRetain{name}", waste_deploy.loc[key, "retention"], pct(waste_deploy.loc[key, "retention"], 0))
        put(f"TRejectedUsable{name}", waste_deploy.loc[key, "rejected_share_usable_D2"], pct(waste_deploy.loc[key, "rejected_share_usable_D2"], 0))
    put("TRejectedUsableMin", waste_deploy.rejected_share_usable_D2.drop("R1_complete_year (USGS/SWToolbox)").min(), pct(waste_deploy.rejected_share_usable_D2.drop("R1_complete_year (USGS/SWToolbox)").min(), 0))
    put("TRejectedUsableMax", waste_deploy.rejected_share_usable_D2.max(), pct(waste_deploy.rejected_share_usable_D2.max(), 0))
    scores = rules.loc[rules.kind.eq("score")]

    def retention(population: str, delivered: str, rule: str, level: str = "retention_at_050") -> float:
        return float(scores.loc[(scores.population == population) & (scores.delivered == delivered) & (scores.rule == rule), level].iloc[0])

    put("TDeployRetWarmTwoFive", retention("deploy", "P0", "R2_warm_missing_fraction", "retention_at_025"), pct(retention("deploy", "P0", "R2_warm_missing_fraction", "retention_at_025"), 1))
    put("TDeployRetTargetTwoFive", retention("deploy", "D2*", "R7a_target_aware_pfail (D2* distribution)", "retention_at_025"), pct(retention("deploy", "D2*", "R7a_target_aware_pfail (D2* distribution)", "retention_at_025"), 1))
    put("TDeployRetOracleTwoFive", retention("deploy", "D2*", "R8_oracle_error_order", "retention_at_025"), pct(retention("deploy", "D2*", "R8_oracle_error_order", "retention_at_025"), 1))
    put("TMechRetTarget", retention("mech", "D2*", "R7a_target_aware_pfail (D2* distribution)"), pct(retention("mech", "D2*", "R7a_target_aware_pfail (D2* distribution)"), 0))
    put("TMechRetWarm", retention("mech", "P0", "R2_warm_missing_fraction"), pct(retention("mech", "P0", "R2_warm_missing_fraction"), 0))
    put("TMechRetLaw", retention("mech", "P0", "R6_recovery_law_pfail"), pct(retention("mech", "P0", "R6_recovery_law_pfail"), 0))
    put("TMechRetDirect", retention("mech", "P0", "R7b_direct_failure_probability (P0)"), pct(retention("mech", "P0", "R7b_direct_failure_probability (P0)"), 0))
    put("TMechRetTargetDisagree", retention("mech", "P0", "R5_h30_target_disagreement"), pct(retention("mech", "P0", "R5_h30_target_disagreement"), 0))
    put("TMechRetOracle", retention("mech", "D2*", "R8_oracle_error_order"), pct(retention("mech", "D2*", "R8_oracle_error_order"), 0))
    e5 = read_json("e5_rules/summary.json")
    put("TPTwoGain", e5["endpoint_P2_retention_gain_at_5pct"], pct(e5["endpoint_P2_retention_gain_at_5pct"], 1))

    # E6.
    agreement = pd.read_csv(T.OUT / "e6_multitarget/target_agreement.csv")

    def kappa(population: str, a: str, b: str) -> float:
        return float(agreement.loc[(agreement.population == population) & (agreement.target_a == a) & (agreement.target_b == b), "kappa_usable"].iloc[0])

    put("TKappaHSeven", kappa("deploy", "h30", "h7"), number(kappa("deploy", "h30", "h7"), 2))
    put("TKappaMean", kappa("deploy", "h30", "annual_mean"), number(kappa("deploy", "h30", "annual_mean"), 2))
    put("TKappaCThirty", kappa("deploy", "h30", "c30"), number(kappa("deploy", "h30", "c30"), 2))
    put("TKappaCThirtyMech", kappa("mech", "h30", "c30"), number(kappa("mech", "h30", "c30"), 2))
    spearman = float(agreement.loc[(agreement.population == "mech") & (agreement.target_a == "h30") & (agreement.target_b == "c30"), "spearman_abs_error"].iloc[0])
    put("TSpearmanCThirtyMech", spearman, number(spearman, 2))
    misjudge = pd.read_csv(T.OUT / "e6_multitarget/rule_misjudgement_by_target.csv")
    for target, name in (("h30", "H"), ("c30", "C")):
        value = float(misjudge.loc[(misjudge.population == "deploy") & (misjudge.target == target) & (misjudge.rule == "R2_oregon_jas_80pct"), "false_acceptance"].iloc[0])
        put(f"TOregonFalseAccept{name}", value, pct(value, 1))
    frontier = pd.read_csv(T.OUT / "e6_multitarget/target_frontier.csv")
    own = frontier.loc[frontier.population.eq("mech")].set_index("target")
    by_h30 = frontier.loc[frontier.population.eq("mech|scored_by_h30")].set_index("target")
    put("TDaysOwnScore", own.loc["days_above_20", "target_aware_retention_at_5pct"], pct(own.loc["days_above_20", "target_aware_retention_at_5pct"], 0))
    put("TDaysHScore", by_h30.loc["days_above_20", "target_aware_retention_at_5pct"], pct(by_h30.loc["days_above_20", "target_aware_retention_at_5pct"], 0))

    # E7.
    p3 = read_json("e7_transfer/endpoint_P3_source.json")
    put("TLoroRegions", p3["mech_n_regions"], str(p3["mech_n_regions"]))
    put("TLoroShareMech", p3["mech_share_risk_le_7pct"], pct(p3["mech_share_risk_le_7pct"], 0))
    put("TLoroMedianMech", p3["mech_median_risk"], pct(p3["mech_median_risk"], 1))
    put("TLoroShareDeploy", p3["deploy_share_risk_le_7pct"], pct(p3["deploy_share_risk_le_7pct"], 0))
    put("TLoroMedianDeploy", p3["deploy_median_risk"], pct(p3["deploy_median_risk"], 1))
    put("TLoroPredMech", p3["mech_predictive_p_new_region_le_7pct"], pct(p3["mech_predictive_p_new_region_le_7pct"], 0))
    summary = pd.read_csv(T.OUT / "e7_transfer/transfer_summary.csv")
    marginal_mech = summary.loc[(summary.population == "mech") & (summary.score == "R7a_target_aware") & (summary.method == "marginal")].iloc[0]
    put("TLoroMarginalMedianMech", marginal_mech.median_risk, pct(marginal_mech.median_risk, 1))
    sealed = read_json("e7_sealed/sealed_results.json")
    put("TAuStations", sealed["n_stations"], number(sealed["n_stations"], 0))
    put("TAuYears", sealed["n_station_years"], number(sealed["n_station_years"], 0))
    put("TAuNetworks", sealed["n_networks"], number(sealed["n_networks"], 0))
    put("TAuCases", sealed["n_cases"], number(sealed["n_cases"], 0))
    put("TAuAirShare", sealed["layer_shares"]["air_ridge"], pct(sealed["layer_shares"]["air_ridge"], 0))
    put("TAuRiskDeploy", sealed["P3_frozen_mondrian_realised_risk_deploy"], pct(sealed["P3_frozen_mondrian_realised_risk_deploy"], 1))
    put("TAuRiskDeployHigh", sealed["P3_risk_upper95"], pct(sealed["P3_risk_upper95"], 1))
    put("TAuRiskMech", sealed["P3_mech_realised_risk"], pct(sealed["P3_mech_realised_risk"], 1))
    put("TAuGain", sealed["P2_retention_gain_at_5pct_deploy"], pct(sealed["P2_retention_gain_at_5pct_deploy"], 0))
    put("TAuPOneReduction", sealed["P1_air_half_hidden"]["reduction"], pct(sealed["P1_air_half_hidden"]["reduction"], 0))
    put("TAuPOneCoverage", sealed["P1_air_half_hidden"]["coverage90"], pct(sealed["P1_air_half_hidden"]["coverage90"], 0))
    put("TAuLawPredicted", sealed["law_predicted_failure_rate_deploy"], pct(sealed["law_predicted_failure_rate_deploy"], 1))
    put("TAuObservedFail", sealed["observed_P0_failure_rate_deploy"], pct(sealed["observed_P0_failure_rate_deploy"], 1))
    frozen = pd.read_csv(T.OUT / "e7_sealed/sealed_frozen_thresholds.csv")
    unscreened = frozen.loc[(frozen.population == "deploy") & (frozen.score == "R7a_target_aware")].unscreened_risk.iloc[0]
    put("TAuUnscreenedDTwo", unscreened, pct(unscreened, 1))
    diag = pd.read_csv(T.OUT / "e7_sealed/posthoc_domain_contrast.csv").set_index(["domain", "family"])
    put("TAuRTwo", diag.loc[("australia", "calendar"), "median_r2"], number(diag.loc[("australia", "calendar"), "median_r2"], 2))
    put("TSourceRTwo", diag.loc[("source", "calendar"), "median_r2"], number(diag.loc[("source", "calendar"), "median_r2"], 2))
    put("TAuMissing", diag.loc[("australia", "calendar"), "median_missing_fraction"], pct(diag.loc[("australia", "calendar"), "median_missing_fraction"], 1))
    put("TSourceMissing", diag.loc[("source", "calendar"), "median_missing_fraction"], pct(diag.loc[("source", "calendar"), "median_missing_fraction"], 1))
    expected = pd.read_csv(T.OUT / "e7_transfer/expected_risk_threshold.csv")
    au_post = expected.loc[expected.domain.eq("australia_post_hoc")].set_index(["population", "score"])
    put("TAuPostRiskDeploy", au_post.loc[("deploy", "R7a"), "risk"], pct(au_post.loc[("deploy", "R7a"), "risk"], 1))
    put("TAuPostRetDeploy", au_post.loc[("deploy", "R7a"), "retention"], pct(au_post.loc[("deploy", "R7a"), "retention"], 0))
    put("TAuPostRiskMechDirect", au_post.loc[("mech", "R7b"), "risk"], pct(au_post.loc[("mech", "R7b"), "risk"], 1))
    expected_summary = pd.read_csv(T.OUT / "e7_transfer/expected_risk_threshold_summary.csv").set_index(["population", "score"])
    put("TExpectedShareMechDirect", expected_summary.loc[("mech", "R7b"), "share_risk_le_7pct"], pct(expected_summary.loc[("mech", "R7b"), "share_risk_le_7pct"], 0))
    put("TExpectedMedianMechDirect", expected_summary.loc[("mech", "R7b"), "median_risk"], pct(expected_summary.loc[("mech", "R7b"), "median_risk"], 1))
    put("TExpectedShareMechTarget", expected_summary.loc[("mech", "R7a"), "share_risk_le_7pct"], pct(expected_summary.loc[("mech", "R7a"), "share_risk_le_7pct"], 0))

    # E8.
    p4 = read_json("e8_downstream/endpoint_P4.json")
    p4b = read_json("e8_downstream/min_years_15/endpoint_P4.json")
    put("TTrendStations", p4["n_stations"], str(p4["n_stations"]))
    put("TTrendGroups", p4["n_groups"], str(p4["n_groups"]))
    put("TTrendRmseAOne", p4["rmse_A1"], number(p4["rmse_A1"], 3))
    put("TTrendRmseC", p4["rmse_C"], number(p4["rmse_C"], 3))
    put("TTrendReduction", p4["rmse_reduction"], pct(p4["rmse_reduction"], 0))
    put("TTrendReductionLow", p4["rmse_reduction_lower95"], pct(p4["rmse_reduction_lower95"], 0))
    put("TTrendReductionHigh", p4["rmse_reduction_upper95"], pct(p4["rmse_reduction_upper95"], 0))
    put("TTrendCoverage", p4["coverage_C_missing_component"], pct(p4["coverage_C_missing_component"], 1))
    put("TTrendStationsFifteen", p4b["n_stations"], str(p4b["n_stations"]))
    put("TTrendReductionFifteen", p4b["rmse_reduction"], pct(p4b["rmse_reduction"], 0))
    e8 = pd.read_csv(T.OUT / "e8_downstream/summary.csv").set_index(["scenario", "pipeline"])
    put("TTrendRmseAZero", e8.loc[("mnar1", "A0"), "slope_rmse"], number(e8.loc[("mnar1", "A0"), "slope_rmse"], 2))
    put("TTrendRmseB", e8.loc[("mnar1", "B"), "slope_rmse"], number(e8.loc[("mnar1", "B"), "slope_rmse"], 3))
    put("TYearsAZero", e8.loc[("mnar1", "A0"), "mean_years"], number(e8.loc[("mnar1", "A0"), "mean_years"], 1))
    put("TYearsAll", e8.loc[("mnar1", "C"), "mean_years"], number(e8.loc[("mnar1", "C"), "mean_years"], 1))
    for pipeline, name in (("A1", "AOne"), ("B", "B"), ("C", "C")):
        value = e8.loc[("mnar1", pipeline), "hot_missed_incomplete"] / e8.loc[("mnar1", pipeline), "hot_true_incomplete"]
        put(f"THotMissed{name}", value, pct(value, 0))
    put("TMeanBiasB", e8.loc[("mnar1", "B"), "mean_h30_bias"], number(e8.loc[("mnar1", "B"), "mean_h30_bias"], 3))

    # E9.
    e9 = read_json("e9_application/summary.json")
    put("TRealYears", e9["n_real_incomplete_station_years"], number(e9["n_real_incomplete_station_years"], 0))
    put("TRealStations", e9["n_stations"], number(e9["n_stations"], 0))
    put("TRealAdmitted", e9["target_aware_admitted_share"], pct(e9["target_aware_admitted_share"], 1))
    put("TRealBestRule", e9["best_rule_share"], pct(e9["best_rule_share"], 1))
    usage = pd.read_csv(T.OUT / "e9_application/usable_station_years.csv").set_index("provider")
    put("TRealUSGSRule", usage.loc["all", "R1_usgs_indicator_311d_24pm"], pct(usage.loc["all", "R1_usgs_indicator_311d_24pm"], 0))
    regional = pd.read_csv(T.OUT / "e9_application/regional_trends.csv").set_index("region")
    put("TLubwSlopeAZero", regional.loc["lubw", "slope_A0"], number(regional.loc["lubw", "slope_A0"], 2))
    put("TLubwSlopeC", regional.loc["lubw", "slope_C"], number(regional.loc["lubw", "slope_C"], 2))
    put("TLubwStations", regional.loc["lubw", "n_stations"], number(regional.loc["lubw", "n_stations"], 0))

    # E11.
    ablation = pd.read_csv(T.OUT / "e11_ablation/score_ablation.csv").set_index(["population", "score"])
    for key, name in (("full (R7b)", "Full"), ("full_plus_old_window_summaries", "Window"), ("no_simulation", "NoSim"), ("law_only", "Law"), ("geometry_only", "Geometry"), ("target_disagreement_only", "TargetDis"), ("daily_disagreement_only", "DailyDis")):
        put(f"TAbl{name}", ablation.loc[("mech", key), "retention_at_050"], pct(ablation.loc[("mech", key), "retention_at_050"], 1))
    shrink = pd.read_csv(T.OUT / "e11_ablation/shrinkage_ablation.csv").set_index(["population", "estimator"])
    put("TShrinkRidge", shrink.loc[("mech", "air_ridge (P0)"), "bias"], number(shrink.loc[("mech", "air_ridge (P0)"), "bias"], 3))
    put("TShrinkOls", shrink.loc[("mech", "air_ols (no shrinkage)"), "bias"], number(shrink.loc[("mech", "air_ols (no shrinkage)"), "bias"], 3))

    lines = ["%% Generated by scripts/448_tr_evidence.py; do not edit by hand."] + [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
    (PAPER / "tr_claims.tex").write_text("\n".join(lines) + "\n")
    T.write_json(OUT / "claims.json", claims)

    # Main tables.
    main = []
    verdict = lambda met: "Met" if met else "Not met"  # noqa: E731
    endpoint_rows = [
        ["P1", "Signed H30 bias, air layer, true peak $\\geq$50\\% hidden", f"{macros['TPOneBiasPZero']} $\\rightarrow$ {macros['TPOneBias']}\\,$^{{\\circ}}$C; reduction {macros['TPOneReduction']}\\% [{macros['TPOneReductionLow']}, {macros['TPOneReductionHigh']}]; 90\\% coverage {macros['TPOneCoverage']}\\%", verdict(p1["P1_success"])],
        ["P2", "Retention gain at 5\\% realised risk over the best rule, real calendars", f"{macros['TPTwoGain']} points; unscreened risk of D2* is {macros['TDeployFailDTwo']}\\%", verdict(e5["endpoint_P2_success"])],
        ["P3", "Held-out regions with realised risk $\\leq$7\\% (layer calibration)", f"controlled gaps {macros['TLoroShareMech']}\\% (median {macros['TLoroMedianMech']}\\%); real calendars {macros['TLoroShareDeploy']}\\% (median {macros['TLoroMedianDeploy']}\\%); Australia {macros['TAuRiskDeploy']}\\% and {macros['TAuRiskMech']}\\%", verdict(p3["P3_source_success"] and sealed["P3_sealed_success"])],
        ["P4", "Station H30 trend RMSE, C versus A1", f"{macros['TTrendRmseAOne']} $\\rightarrow$ {macros['TTrendRmseC']}\\,$^{{\\circ}}$C/decade; reduction {macros['TTrendReduction']}\\% [{macros['TTrendReductionLow']}, {macros['TTrendReductionHigh']}]; coverage {macros['TTrendCoverage']}\\%", verdict(p4["P4_success"])],
    ]
    main.append(table(pd.DataFrame(endpoint_rows), "Preregistered primary endpoints. Success criteria were fixed before the endpoint was computed; the Australian test was evaluated after the pipeline was frozen. Intervals resample independence groups.", "tab:endpoints", "p{0.04\\textwidth}p{0.27\\textwidth}p{0.46\\textwidth}p{0.08\\textwidth}", ["", "Quantity", "Result", "Verdict"]))
    rule_rows = []
    fixed = deploy.loc[deploy.kind.eq("fixed") & deploy.delivered.eq("Pobs")].set_index("rule")
    for key, label in RULE_NAMES.items():
        if key not in fixed.index:
            continue
        rule_rows.append([label, pct(fixed.loc[key, "retention"], 0), pct(fixed.loc[key, "risk"], 2) if fixed.loc[key, "retention"] > 0 else "--", pct(waste_deploy.loc[key, "rejected_share_usable_D2"], 0)])
    rule_rows.append(["No screening, value from D2*", "100", macros["TDeployFailDTwo"], "--"])
    main.append(table(pd.DataFrame(rule_rows), "Published completeness rules applied to real incomplete calendars transplanted onto complete years (deployment population, provider-weighted). Retained values are computed from recorded days, as in practice. The last column gives the share of rejected station-years whose D2* estimate would have been within 0.5\\,$^{\\circ}$C.", "tab:rules", "p{0.42\\textwidth}p{0.1\\textwidth}p{0.13\\textwidth}p{0.14\\textwidth}", ["Rule", "Used (\\%)", "Failures among used (\\%)", "Rejected but recoverable (\\%)"]))
    (PAPER / "tr_tables_main.tex").write_text("\n".join(main))

    # Supporting tables.
    si = []
    m = models.copy()
    m["or"] = [f"{number(a, 2)} [{number(b, 2)}, {number(c, 2)}]" for a, b, c in zip(m.odds_ratio, m.odds_ratio_lower95, m.odds_ratio_upper95)]
    si.append(table(m[["analysis", "covariate", "n", "or"]].assign(analysis=lambda f: f.analysis.str.replace("_", " "), covariate=lambda f: f.covariate.str.replace("_", " "), n=lambda f: f.n.map(lambda v: number(v, 0))), "E1 missingness models. Station-year models use station fixed effects (conditional logit) or station and region-year random intercepts; onset models are time-stratified case-crossover designs (strata: station $\\times$ year $\\times$ month). Duration is a ratio of gap lengths. Intervals resample independence groups (model-based for the mixed model and duration).", "tab:si_e1", "llrl", ["Analysis", "Covariate", "n", "Odds ratio [95\\%]"]))
    tol = pd.DataFrame([[TARGET_NAMES.get(k, k), number(tolerance["median_interannual_sd"].get(k, np.nan), 2), number(v, 2)] for k, v in tolerance["tolerance"].items() if k in TARGET_NAMES])
    si.append(table(tol, "Target tolerances fixed in the preregistration: the share of the median within-station interannual standard deviation that 0.5\\,$^{\\circ}$C represents for H30, with floors of 0.2\\,$^{\\circ}$C and one day.", "tab:si_tolerance", "lrr", ["Target", "Median interannual SD", "Tolerance"]))
    lawtab = law.loc[law.population.isin(["mech", "deploy"]) & law.metric.isin(["ece", "brier_skill_vs_base_rate", "mean_predicted_pfail", "observed_failure_rate", "mean_predicted_bias", "observed_mean_error"])]
    lawtab = lawtab.loc[lawtab.truncated.astype(str).str.lower().eq("true")].pivot_table(index=["population", "version"], columns="metric", values="value").reset_index()
    lawtab = lawtab[["population", "version", "ece", "brier_skill_vs_base_rate", "mean_predicted_pfail", "observed_failure_rate", "mean_predicted_bias", "observed_mean_error"]]
    for column in lawtab.columns[2:]:
        lawtab[column] = lawtab[column].map(lambda v: number(v, 3))
    si.append(table(lawtab, "E3 recovery law. v1: daily-scale shrinkage; v2: window-scale shrinkage (main parametric law); v3: replay of the same gap on training years. No version is fitted to reconstruction errors.", "tab:si_law", "llrrrrrr", ["Population", "Law", "ECE", "Brier skill", "Predicted failure", "Observed failure", "Predicted bias", "Observed bias"]))
    cell = pd.read_csv(T.OUT / "e3_recovery_law/cells.csv")
    cell = cell[["gap_length", "overlap_class", "layer", "n", "mean_error", "law_bias", "law_v3_bias", "failure_rate", "law_pfail", "law_v3_pfail"]].copy()
    cell["layer"] = cell.layer.str.replace("_", " ")
    for column in ("mean_error", "law_bias", "law_v3_bias", "failure_rate", "law_pfail", "law_v3_pfail"):
        cell[column] = cell[column].map(lambda v: number(v, 3))
    cell["n"] = cell.n.map(lambda v: number(v, 0))
    si.append(table(cell, "E3 cells of the controlled population (gap length $\\times$ overlap with the climatological peak $\\times$ information layer).", "tab:si_cells", "rllrrrrrrr", ["Days", "Overlap", "Layer", "n", "Mean error", "v2 bias", "v3 bias", "Failure", "v2 P(fail)", "v3 P(fail)"], "\\tiny"))
    est = metrics.loc[metrics.target.eq("h30") & metrics.population.isin(["mech", "deploy"]) & metrics.stratum.isin(["all", "peak_half_hidden", "air_layer_half_hidden", "donor_layer_half_hidden", "warm_anomaly_half_hidden"])].copy()
    est["estimator"] = est.estimator.map(ESTIMATOR_NAMES)
    est["stratum"] = est.stratum.str.replace("_", " ")
    for column in ("bias", "mae", "crps_q"):
        est[column] = est[column].map(lambda v: number(v, 3))
    for column in ("failure_rate", "coverage90"):
        est[column] = est[column].map(lambda v: pct(v, 1))
    est["n"] = est.n.map(lambda v: number(v, 0))
    si.append(table(est[["population", "stratum", "estimator", "n", "bias", "mae", "failure_rate", "crps_q", "coverage90"]], "E4 H30 estimators, leave-one-region-out. Strata use the true peak window (evaluation only); warm anomaly: true H30 at least 1\\,$^{\\circ}$C above the training mean.", "tab:si_estimators", "lllrrrrrr", ["Population", "Stratum", "Estimator", "n", "Bias", "MAE", "Failure (\\%)", "CRPS", "Cover90 (\\%)"], "\\tiny"))
    other = metrics.loc[metrics.target.ne("h30") & metrics.population.isin(["mech", "deploy"]) & metrics.stratum.eq("all") & metrics.estimator.isin(["P0", "Pobs", "P2", "P3", "P5b"])].copy()
    other["target"] = other.target.map(TARGET_NAMES)
    other["estimator"] = other.estimator.map(ESTIMATOR_NAMES)
    for column in ("bias", "mae"):
        other[column] = other[column].map(lambda v: number(v, 3))
    other["failure_rate"] = other.failure_rate.map(lambda v: pct(v, 1))
    si.append(table(other[["population", "target", "estimator", "bias", "mae", "failure_rate"]], "E4 estimators for the other targets (all cases), with the preregistered target tolerances.", "tab:si_other_targets", "lllrrr", ["Population", "Target", "Estimator", "Bias", "MAE", "Failure (\\%)"], "\\tiny"))
    curve = scores.loc[scores.population.isin(["deploy", "mech"])].copy()
    curve["rule"] = curve.rule.map(SCORE_NAMES)
    for column in ("retention_at_025", "retention_at_050", "retention_at_100"):
        curve[column] = curve[column].map(lambda v: pct(v, 1))
    for column in ("aurc", "augrc"):
        curve[column] = curve[column].map(lambda v: number(v, 4))
    si.append(table(curve[["population", "delivered", "rule", "retention_at_025", "retention_at_050", "retention_at_100", "aurc", "augrc"]], "E5 scores: retention at equal realised risk, AURC and AUGRC for each delivered value.", "tab:si_scores", "lllrrrrr", ["Population", "Value", "Score", "2.5\\%", "5\\%", "10\\%", "AURC", "AUGRC"], "\\tiny"))
    agree = agreement.loc[agreement.population.isin(["deploy", "mech"])].copy()
    agree["target_a"] = agree.target_a.map(TARGET_NAMES)
    agree["target_b"] = agree.target_b.map(TARGET_NAMES)
    for column in ("kappa_usable", "spearman_abs_error"):
        agree[column] = agree[column].map(lambda v: number(v, 2))
    for column in ("share_unusable_a_usable_b", "share_usable_a_unusable_b"):
        agree[column] = agree[column].map(lambda v: pct(v, 1))
    si.append(table(agree[["population", "target_a", "target_b", "kappa_usable", "spearman_abs_error", "share_unusable_a_usable_b", "share_usable_a_unusable_b"]], "E6 agreement of usability between targets for the plug-in value.", "tab:si_agreement", "lllrrrr", ["Population", "Target A", "Target B", "$\\kappa$", "Spearman", "A no, B yes (\\%)", "A yes, B no (\\%)"], "\\tiny"))
    loro = pd.read_csv(T.OUT / "e7_transfer/loro_transfer.csv")
    loro = loro.loc[loro.score.eq("R7a_target_aware") & loro.method.isin(["marginal", "mondrian_layer", "weighted_mondrian"])].pivot_table(index=["population", "region", "n_groups"], columns="method", values="risk").reset_index()
    for column in ("marginal", "mondrian_layer", "weighted_mondrian"):
        loro[column] = loro[column].map(lambda v: pct(v, 1))
    loro["region"] = loro.region.str.replace("_", " ")
    si.append(table(loro, "E7 leave-one-region-out realised risk (\\%) of the target-aware score at nominal 5\\%: one threshold, one per information layer, and layer thresholds reweighted to the held-out region.", "tab:si_loro", "llrrrr", ["Population", "Region", "Groups", "Marginal", "Layer", "Weighted"], "\\tiny"))
    fz = frozen.copy()
    for column in ("retention", "risk", "risk_lower95", "risk_upper95", "unscreened_risk"):
        fz[column] = fz[column].map(lambda v: pct(v, 1))
    si.append(table(fz[["population", "score", "method", "n_cases", "n_groups", "retention", "risk", "risk_lower95", "risk_upper95", "unscreened_risk"]].assign(score=lambda f: f.score.str.replace("_", " "), method=lambda f: f.method.str.replace("_", " ")), "E7 sealed Australian test: frozen thresholds. Intervals resample the 55 hydrological networks.", "tab:si_sealed", "lllrrrrrrr", ["Population", "Score", "Threshold", "Cases", "Networks", "Used (\\%)", "Risk (\\%)", "Low", "High", "Unscreened (\\%)"], "\\tiny"))
    contrast = pd.read_csv(T.OUT / "e7_sealed/posthoc_domain_contrast.csv")
    for column in ("air_layer_share", "median_missing_fraction", "share_peak_overlap_half", "failure_P0", "failure_D2", "coverage90_D2"):
        contrast[column] = contrast[column].map(lambda v: pct(v, 1))
    for column in ("median_sigma_a", "median_sigma_r", "median_r2", "mean_error_P0"):
        contrast[column] = contrast[column].map(lambda v: number(v, 2))
    si.append(table(contrast[["domain", "family", "air_layer_share", "median_sigma_a", "median_sigma_r", "median_r2", "median_missing_fraction", "share_peak_overlap_half", "failure_P0", "failure_D2", "coverage90_D2"]], "Post hoc contrast between the source and Australia, written after the sealed evaluation.", "tab:si_posthoc", "llrrrrrrrrr", ["Domain", "Family", "Air (\\%)", "$\\sigma_a$", "$\\sigma_r$", "$R^2$", "Missing (\\%)", "Peak $\\geq$50\\% (\\%)", "Fail P0", "Fail D2*", "Cover90"], "\\tiny"))
    er = expected.copy()
    for column in ("retention", "risk"):
        er[column] = er[column].map(lambda v: pct(v, 1))
    er = er.loc[er.score.isin(["R7a", "R7b"])]
    si.append(table(er[["domain", "population", "region", "score", "retention", "risk"]].assign(domain=lambda f: f.domain.str.replace("_", " "), region=lambda f: f.region.str.replace("_", " ")), "E7d label-free expected-risk thresholds: the largest threshold whose mean predicted failure probability among admitted cases is at most 5\\%, computed in the held-out region without labels. Australia is post hoc.", "tab:si_expected", "llllrr", ["Domain", "Population", "Region", "Score", "Used (\\%)", "Risk (\\%)"], "\\tiny"))
    e8full = pd.read_csv(T.OUT / "e8_downstream/summary.csv")
    e8full["hot_missed"] = e8full.hot_missed_incomplete / e8full.hot_true_incomplete
    for column in ("slope_bias", "slope_rmse", "mean_h30_bias"):
        e8full[column] = e8full[column].map(lambda v: number(v, 4))
    for column in ("cover_missing_component", "detect_warming", "hot_missed"):
        e8full[column] = e8full[column].map(lambda v: pct(v, 1))
    e8full["mean_years"] = e8full.mean_years.map(lambda v: number(v, 1))
    si.append(table(e8full[["scenario", "pipeline", "mean_years", "slope_bias", "slope_rmse", "cover_missing_component", "detect_warming", "mean_h30_bias", "hot_missed"]].assign(scenario=lambda f: f.scenario.str.replace("_", " ")), f"E8 downstream pipelines on {p4['n_stations']} stations with at least 20 complete years (200 degradations each). Slopes in $^{{\\circ}}$C per decade relative to the complete record.", "tab:si_downstream", "llrrrrrrr", ["Scenario", "Pipeline", "Years", "Trend bias", "Trend RMSE", "Cover (\\%)", "Detect (\\%)", "Mean H30 bias", "Hot missed (\\%)"], "\\tiny"))
    use = pd.read_csv(T.OUT / "e9_application/usable_station_years.csv")
    keep = ["provider", "n_incomplete_station_years", "target_aware_admitted", "R1_usgs_indicator_311d_24pm", "R1_wmo_11_5", "R2_oregon_jas_80pct", "R2_beaufort_julaug_complete"]
    use = use[keep].copy()
    for column in keep[2:]:
        use[column] = use[column].map(lambda v: pct(v, 0))
    use["provider"] = use.provider.str.replace("_", " ")
    si.append(table(use, "E9 real incomplete station-years: share used by the frozen target-aware rule and by four published rules (no truth is available; this is an application).", "tab:si_application", "lrrrrrr", ["Provider", "Years", "Target-aware", "USGS 311 d", "WMO 11/5", "Oregon", "Jul--Aug"], "\\scriptsize"))
    abl = pd.read_csv(T.OUT / "e11_ablation/score_ablation.csv")
    for column in ("retention_at_025", "retention_at_050", "retention_at_100"):
        abl[column] = abl[column].map(lambda v: pct(v, 1))
    for column in ("aurc", "brier"):
        abl[column] = abl[column].map(lambda v: number(v, 4))
    si.append(table(abl[["population", "score", "retention_at_025", "retention_at_050", "retention_at_100", "aurc", "brier"]].assign(score=lambda f: f.score.str.replace("_", " ")), "E11 score ablations for the plug-in failure, leave-one-region-out.", "tab:si_ablation", "llrrrrr", ["Population", "Score", "2.5\\%", "5\\%", "10\\%", "AURC", "Brier"], "\\scriptsize"))
    sens = pd.read_csv(T.OUT / "e5_rules/tolerance_sensitivity.csv")
    sens = sens[["tolerance_c", "population", "unscreened_risk_P0", "unscreened_risk_Pobs", "unscreened_risk_D2*", "target_aware_retention_at_025", "best_fixed_rule_retention_at_025", "target_aware_retention_at_050", "best_fixed_rule_retention_at_050"]].copy()
    for column in sens.columns[2:]:
        sens[column] = sens[column].map(lambda v: pct(v, 1))
    sens["tolerance_c"] = sens.tolerance_c.map(lambda v: number(v, 2))
    si.append(table(sens, "Sensitivity to the tolerance (preregistered 0.25, 0.5 and 1.0\\,$^{\\circ}$C): unscreened failure rates and retention at 2.5\\% and 5\\% realised risk of the target-aware judgment (D2* value) and of the best fixed published rule (recorded-day or plug-in value).", "tab:si_tolerance_sensitivity", "llrrrrrrr", ["Tolerance", "Population", "Fail P0", "Fail recorded", "Fail D2*", "Target 2.5\\%", "Rule 2.5\\%", "Target 5\\%", "Rule 5\\%"], "\\scriptsize"))
    shift = pd.read_csv(T.OUT / "e7_sealed/posthoc_conditional_shift.csv")
    shift["failure"] = shift.failure.map(lambda v: pct(v, 1))
    shift["mean_score"] = shift.mean_score.map(lambda v: number(v, 3))
    shift["n"] = shift.n.map(lambda v: number(v, 0))
    si.append(table(shift[["domain", "score", "n", "mean_score", "failure"]], "Post hoc conditional calibration of the target-aware score (D2* failure probability) under real gap calendars: observed failure rate by score bin in the source (frozen models, in-sample) and in Australia.", "tab:si_conditional_shift", "llrrr", ["Domain", "Score bin", "n", "Mean score", "Observed failure (\\%)"], "\\scriptsize"))
    (PAPER / "tr_si_tables.tex").write_text("\n".join(si))
    print(f"[448] {len(macros)} macros, {len(main)} main tables, {len(si)} SI tables", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
