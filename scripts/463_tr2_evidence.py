#!/usr/bin/env python3
"""TR2 evidence: every number quoted in the revised manuscript, and its tables.

Round-2 counterpart of script 448. The missingness audit, the first
preregistration's verdicts and the first (Australian) test are read from
the round-1 results, which they belong to; everything recomputed under the
corrected hemisphere and season definitions, the second preregistration, the
USGS test and the post hoc analyses are read from the round-2 results.
Writes paper/wrr_tr/tr_claims.tex, tr_table_endpoints.tex, tr_table_rules.tex and tr_si_tables.tex
and a machine-readable claims.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import wrr_tr_common as T

E448 = T.load_script("tr_evidence_helpers", T.ROOT / "scripts/448_tr_evidence.py")
PAPER = T.ROOT / "paper/wrr_tr"
OUT = T.OUT / "evidence"
R1, R2 = T.ROUND1, T.OUT
number, pct = E448.number, E448.pct
MINUS = re.compile(r"(?<![\w$\-])-(?=\d)")


def minus(text: str) -> str:
    """Typeset a leading or free-standing minus sign as a mathematical minus."""

    return MINUS.sub(r"\\ensuremath{-}", text)


def table(frame: pd.DataFrame, *args, **kwargs) -> str:
    return E448.table(frame.apply(lambda column: column.map(lambda v: minus(v) if isinstance(v, str) else v)), *args, **kwargs)
RULE_NAMES = dict(E448.RULE_NAMES)
RULE_NAMES.update({
    "R2_oregon_jas_80pct": "Peak-season months $\\geq$80\\% observed (Oregon, July--September)",
    "R2_norwest_aug_90pct": "Peak month $\\geq$90\\% observed (NorWeST, August)",
    "R2_beaufort_julaug_complete": "Two peak months complete (Beaufort et al., July--August)",
    "R2_dunham_jul15_sep15_complete": "Peak window complete (Dunham et al., 15 July--15 September)",
    "R2_warm_gap_le_7d": "Longest warm-season gap $\\leq$7 days",
    "R2_warm_gap_le_14d": "Longest warm-season gap $\\leq$14 days",
    "R2_warm_gap_le_30d": "Longest warm-season gap $\\leq$30 days",
    "R2_oregon_jas_80pct_as_written": "As written: July--September $\\geq$80\\% observed",
    "R2_norwest_aug_90pct_as_written": "As written: August $\\geq$90\\% observed",
    "R2_beaufort_julaug_complete_as_written": "As written: July--August complete",
    "R2_dunham_jul15_sep15_complete_as_written": "As written: 15 July--15 September complete",
})
SCORE_NAMES = dict(E448.SCORE_NAMES)
ESTIMATOR_NAMES = dict(E448.ESTIMATOR_NAMES)
TARGET_NAMES = {"h30": "H30", "h7": "H7", "annual_mean": "Annual mean", "c30": "C30", "degree_days_peak4": "Degree-days, 4 hottest months", "days_above_20": "Days $>$20\\,$^{\\circ}$C"}


def load(root: Path, path: str):
    full = root / path
    return json.loads(full.read_text()) if full.suffix == ".json" else (pd.read_parquet(full) if full.suffix == ".parquet" else pd.read_csv(full))


def main() -> int:
    PAPER.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    macros: dict[str, str] = {}
    claims: dict[str, float] = {}

    def put(name: str, value, text: str | None = None) -> None:
        claims[name] = value if not isinstance(value, (np.floating, np.integer)) else float(value)
        macros[name] = minus(text if text is not None else str(value))

    def signed(value: float, digits: int = 2) -> str:
        return ("+" if value > 0 else "") + number(value, digits)

    # Archive, cases and definitions (M1).
    archive = load(T.E1, "summary.json")
    put("TArchiveStations", archive["n_stations"], number(archive["n_stations"], 0))
    put("TArchiveYears", archive["n_station_years"], number(archive["n_station_years"], 0))
    cases = load(R2, "e2_cases/cases_summary.json")
    put("TSourceCases", cases["n_cases"], number(cases["n_cases"], 0))
    put("TSourceYears", cases["n_station_years"], number(cases["n_station_years"], 0))
    put("TSourceStations", cases["n_stations"], number(cases["n_stations"], 0))
    put("TSourceGroups", cases["n_groups"], number(cases["n_groups"], 0))
    put("TSourceRegions", cases["n_regions"], number(cases["n_regions"], 0))
    put("TCrossedCases", cases["families"]["crossed"], number(cases["families"]["crossed"], 0))
    put("TCalendarCases", cases["families"]["calendar"], number(cases["families"]["calendar"], 0))
    put("TAirLayerShare", cases["policy"]["air_ridge"] / cases["n_cases"], pct(cases["policy"]["air_ridge"] / cases["n_cases"], 0))
    tolerance = load(R2, "e2_prereg/target_tolerances.json")
    for key, name in (("h7", "TTolHSeven"), ("annual_mean", "TTolMean"), ("c30", "TTolCThirty"), (T.DEGREE_DAYS, "TTolDD"), ("days_above_20", "TTolDays")):
        put(name, tolerance["tolerance"][key], number(tolerance["tolerance"][key], 2 if key not in (T.DEGREE_DAYS, "days_above_20") else 1))
    definition = load(R2, "e2_definition_check/source_differences.csv").set_index("quantity")
    put("TDefWarmNotMaySep", definition.loc["stations whose warm season is not May-September", "value"], number(definition.loc["stations whose warm season is not May-September", "value"], 0))
    put("TDefDDNotJunSep", definition.loc["stations whose degree-day months are not June-September", "value"], number(definition.loc["stations whose degree-day months are not June-September", "value"], 0))
    put("TDefStations", definition.loc["stations whose warm season is not May-September", "of"], number(definition.loc["stations whose warm season is not May-September", "of"], 0))
    put("TDefWarmChanged", definition.loc["cases with a changed warm-season observed fraction", "value"], pct(definition.loc["cases with a changed warm-season observed fraction", "value"], 1))
    australia = load(R2, "e2_definition_check/australia_before_after.csv")
    put("TAuEdgeBefore", australia.share_h30_window_at_year_edge.iloc[0], pct(australia.share_h30_window_at_year_edge.iloc[0], 0))
    put("TAuEdgeAfter", australia.share_h30_window_at_year_edge.iloc[-1], pct(australia.share_h30_window_at_year_edge.iloc[-1], 1))

    # E1 (round 1; unchanged by the season definitions).
    e1 = load(T.E1_MISSINGNESS, "summary.json")
    models = load(T.E1_MISSINGNESS, "missingness_models.csv")

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

    # E3 recovery law (round 2) and the hard-cell diagnosis (S2).
    law = load(R2, "e3_recovery_law/summary.csv")

    def law_value(population: str, version: str, metric: str, truncated: bool = True) -> float:
        rows = law.loc[(law.population == population) & (law.version == version) & (law.metric == metric)]
        if "truncated" in rows and rows.truncated.notna().any():
            rows = rows.loc[rows.truncated.astype(str).str.lower().eq(str(truncated).lower())]
        return float(rows.value.iloc[0])

    put("TLawEceMech", law_value("mech", "v2", "ece"), number(law_value("mech", "v2", "ece"), 3))
    put("TLawEceDeploy", law_value("deploy", "v2", "ece"), number(law_value("deploy", "v2", "ece"), 3))
    put("TLawBrierSkillMech", law_value("mech", "v2", "brier_skill_vs_base_rate"), number(law_value("mech", "v2", "brier_skill_vs_base_rate"), 2))
    put("TLawBrierSkillDeploy", law_value("deploy", "v2", "brier_skill_vs_base_rate"), number(law_value("deploy", "v2", "brier_skill_vs_base_rate"), 2))
    put("TLawAucMech", law_value("mech", "v2", "auc"), number(law_value("mech", "v2", "auc"), 2))
    put("TLawAucDeploy", law_value("deploy", "v2", "auc"), number(law_value("deploy", "v2", "auc"), 2))
    cells = law.loc[law.population.eq("mech_cells")].set_index("metric").value
    put("TLawCellFailEV", cells["explained_variance_failure_rate_by_law_pfail"], pct(cells["explained_variance_failure_rate_by_law_pfail"], 0))
    put("TLawCellBiasEV", cells["explained_variance_mean_error_by_law_bias"], pct(cells["explained_variance_mean_error_by_law_bias"], 0))
    put("TLawCellBiasEVUntruncated", cells["explained_variance_mean_error_by_law_bias_untruncated"], pct(cells["explained_variance_mean_error_by_law_bias_untruncated"], 0))
    put("TLawVOneCellBiasEV", cells["explained_variance_mean_error_by_law_v1_bias"], pct(cells["explained_variance_mean_error_by_law_v1_bias"], 0))
    put("TReplayCellBiasEV", cells["explained_variance_mean_error_by_law_v3_bias"], pct(cells["explained_variance_mean_error_by_law_v3_bias"], 0))
    put("TReplayCellFailEV", cells["explained_variance_failure_rate_by_law_v3_pfail"], pct(cells["explained_variance_failure_rate_by_law_v3_pfail"], 0))
    put("TReplayBiasMech", law_value("mech", "v3", "mean_predicted_bias"), number(law_value("mech", "v3", "mean_predicted_bias"), 3))
    put("TObservedBiasMech", law_value("mech", "v3", "observed_mean_error"), number(law_value("mech", "v3", "observed_mean_error"), 3))
    put("TVTwoPCellBiasEV", cells["explained_variance_mean_error_by_law_v2p_bias"], number(cells["explained_variance_mean_error_by_law_v2p_bias"], 2))
    by_layer = load(R2, "e3_recovery_law/by_layer.csv").set_index(["population", "layer"])
    put("TLawRTwoAir", by_layer.loc[("mech", "air_ridge"), "law_r2"], number(by_layer.loc[("mech", "air_ridge"), "law_r2"], 2))
    put("TLawRTwoDonor", by_layer.loc[("mech", "donor_ridge"), "law_r2"], number(by_layer.loc[("mech", "donor_ridge"), "law_r2"], 2))
    hard = load(R2, "e3_recovery_law/hard_cell_diagnosis.json")
    put("THardObserved", hard["hardest5_observed_failure"], pct(hard["hardest5_observed_failure"], 0))
    put("THardVTwo", hard["hardest5_v2"], pct(hard["hardest5_v2"], 0))
    put("THardVTwoP", hard["hardest5_v2p"], pct(hard["hardest5_v2p"], 0))
    put("THardBeyond", hard["hardest5_share_beyond_2sd"], pct(hard["hardest5_share_beyond_2sd"], 1))
    put("THardKurtosis", hard["hardest5_excess_kurtosis"], number(hard["hardest5_excess_kurtosis"], 0))
    put("THardVariance", hard["hardest5_variance_ratio"] - 1, pct(hard["hardest5_variance_ratio"] - 1, 0))
    put("THardHetero", hard["median_peak_to_warm_residual_sd_hardest5"], number(hard["median_peak_to_warm_residual_sd_hardest5"], 2))

    # E4 estimators: preregistered P1 (round 1), the same under corrected definitions, and the calibrated intervals (M2).
    p1_r1 = load(R1, "e4_estimators/endpoint_P1.json")
    put("TPOneReductionRone", p1_r1["P1_reduction"], pct(p1_r1["P1_reduction"], 0))
    put("TPOneCoverageRone", p1_r1["P1_coverage90"], pct(p1_r1["P1_coverage90"], 1))
    p1 = load(R2, "e4_estimators/endpoint_P1.json")
    for key, name in (("P1_bias_P0", "TPOneBiasPZero"), ("P1_bias", "TPOneBias"), ("P1_mae_P0", "TPOneMaePZero"), ("P1_mae", "TPOneMae")):
        put(name, p1[key], number(p1[key], 2))
    put("TPOneBiasPZeroAbs", abs(p1["P1_bias_P0"]), number(abs(p1["P1_bias_P0"]), 2))
    put("TPOneReduction", p1["P1_reduction"], pct(p1["P1_reduction"], 0))
    put("TPOneCoverage", p1["P1_coverage90"], pct(p1["P1_coverage90"], 1))
    put("TPOneN", p1["P1_n"], number(p1["P1_n"], 0))
    put("TPOneGroups", p1["P1_n_groups"], number(p1["P1_n_groups"], 0))
    cqr = load(R2, "e4_estimators/conformal_summary.json")
    put("TPOneBiasCal", cqr["P1_bias_D2c"], number(cqr["P1_bias_D2c"], 2))
    put("TPOneReductionCal", cqr["P1_reduction"], pct(cqr["P1_reduction"], 0))
    put("TPOneReductionCalLow", cqr["P1_reduction_lower95"], pct(cqr["P1_reduction_lower95"], 0))
    put("TPOneReductionCalHigh", cqr["P1_reduction_upper95"], pct(cqr["P1_reduction_upper95"], 0))
    put("TPOneCoverageCal", cqr["P1_coverage90"], pct(cqr["P1_coverage90"], 1))
    put("TPOneCoverageCalLow", cqr["P1_coverage90_lower95"], pct(cqr["P1_coverage90_lower95"], 1))
    put("TPOneCoverageCalHigh", cqr["P1_coverage90_upper95"], pct(cqr["P1_coverage90_upper95"], 1))
    groups = load(R2, "e4_estimators/conformal_group_coverage.csv")
    calibrated = groups.loc[groups.version.eq("calibrated") & groups.population.eq("all")]
    hidden = calibrated.loc[~calibrated.group.str.startswith("bin0")]
    visible = calibrated.loc[calibrated.group.str.startswith("bin0")]
    put("TCqrRawMin", cqr["raw_min_group_coverage"], pct(cqr["raw_min_group_coverage"], 1))
    put("TCqrHardMin", hidden.coverage90.min(), pct(hidden.coverage90.min(), 1))
    put("TCqrHardMax", hidden.coverage90.max(), pct(hidden.coverage90.max(), 1))
    put("TCqrEasyMin", visible.coverage90.min(), pct(visible.coverage90.min(), 1))
    put("TCqrEasyMax", visible.coverage90.max(), pct(visible.coverage90.max(), 1))
    put("TCqrGroups", cqr["n_groups_evaluated"], str(cqr["n_groups_evaluated"]))
    selection = load(R2, "e4_estimators/d2_selection.json")
    for name, value in selection["mean_quantile_crps"].items():
        put({"P3": "TCrpsPThree", "P3raw": "TCrpsPThreeRaw", "P5a": "TCrpsPFiveA", "P5b": "TCrpsPFiveB"}[name], value, number(value, 3))
    endpoint_p1 = load(R2, "e4_estimators/endpoint_P1.csv").set_index("estimator")
    put("TPOneBiasPTwo", endpoint_p1.loc["P2", "bias"], number(endpoint_p1.loc["P2", "bias"], 2))
    put("TPOneBiasPThree", endpoint_p1.loc["P3", "bias"], number(endpoint_p1.loc["P3", "bias"], 2))
    put("TPOneBiasPThreeRaw", endpoint_p1.loc["P3raw", "bias"], number(endpoint_p1.loc["P3raw", "bias"], 2))
    metrics = load(R2, "e4_estimators/estimator_metrics.csv")

    def metric(population: str, stratum: str, estimator: str, column: str, target: str = "h30") -> float:
        return float(metrics.loc[(metrics.population == population) & (metrics.stratum == stratum) & (metrics.estimator == estimator) & (metrics.target == target), column].iloc[0])

    put("TDeployFailPZero", metric("deploy", "all", "P0", "failure_rate"), pct(metric("deploy", "all", "P0", "failure_rate"), 1))
    put("TDeployFailObs", metric("deploy", "all", "Pobs", "failure_rate"), pct(metric("deploy", "all", "Pobs", "failure_rate"), 1))
    put("TMechFailPZero", metric("mech", "all", "P0", "failure_rate"), pct(metric("mech", "all", "P0", "failure_rate"), 1))
    put("TWarmAnomBiasPZero", metric("mech", "warm_anomaly_half_hidden", "P0", "bias"), number(metric("mech", "warm_anomaly_half_hidden", "P0", "bias"), 2))
    put("TWarmAnomBiasDTwo", metric("mech", "warm_anomaly_half_hidden", "P5b", "bias"), number(metric("mech", "warm_anomaly_half_hidden", "P5b", "bias"), 2))
    put("TWarmAnomBiasDTwoAbs", abs(metric("mech", "warm_anomaly_half_hidden", "P5b", "bias")), number(abs(metric("mech", "warm_anomaly_half_hidden", "P5b", "bias")), 2))
    put("TWarmAnomBiasPZeroAbs", abs(metric("mech", "warm_anomaly_half_hidden", "P0", "bias")), number(abs(metric("mech", "warm_anomaly_half_hidden", "P0", "bias")), 2))
    put("TObsDaysBiasHiddenAbs", abs(metric("mech", "peak_half_hidden", "Pobs", "bias")), number(abs(metric("mech", "peak_half_hidden", "Pobs", "bias")), 2))
    put("TAirTwoStreamBias", metric("mech", "air_layer_half_hidden", "P1", "bias"), number(metric("mech", "air_layer_half_hidden", "P1", "bias"), 2))
    put("TObsDaysBiasHidden", metric("mech", "peak_half_hidden", "Pobs", "bias"), number(metric("mech", "peak_half_hidden", "Pobs", "bias"), 2))

    # E5 rules (round 2, calibrated D2*).
    rules = load(R2, "e5_rules/risk_retention.csv")
    deploy = rules.loc[rules.population.eq("deploy")]
    put("TDeployFailDTwo", float(deploy.loc[deploy.delivered.eq("D2*"), "unscreened_risk"].iloc[0]), pct(float(deploy.loc[deploy.delivered.eq("D2*"), "unscreened_risk"].iloc[0]), 1))
    waste = load(R2, "e5_rules/rule_waste.csv")
    waste_deploy = waste.loc[waste.population.eq("deploy")].set_index("rule")
    for key, name in (("R1_usgs_indicator_311d_24pm", "USGS"), ("R1_wmo_11_5", "WMO"), ("R1_etccdi_15_3", "ETCCDI"), ("R1_gsim_350d", "GSIM"), ("R2_oregon_jas_80pct", "Oregon"), ("R2_beaufort_julaug_complete", "Beaufort"), ("R1_johnson_gap_le_49d", "Johnson")):
        put(f"TRetain{name}", waste_deploy.loc[key, "retention"], pct(waste_deploy.loc[key, "retention"], 0))
        put(f"TRejectedUsable{name}", waste_deploy.loc[key, "rejected_share_usable_D2"], pct(waste_deploy.loc[key, "rejected_share_usable_D2"], 0))
        put(f"TRejectedFailPZero{name}", 1 - waste_deploy.loc[key, "rejected_share_usable_P0"], pct(1 - waste_deploy.loc[key, "rejected_share_usable_P0"], 1))
    published = waste_deploy.loc[[k for k in RULE_NAMES if k in waste_deploy.index and not k.endswith("_as_written")]]
    put("TRejectedUsableMin", published.rejected_share_usable_D2.drop("R1_complete_year (USGS/SWToolbox)").min(), pct(published.rejected_share_usable_D2.drop("R1_complete_year (USGS/SWToolbox)").min(), 0))
    put("TRejectedUsableMax", published.rejected_share_usable_D2.max(), pct(published.rejected_share_usable_D2.max(), 0))
    retained = published.retention.drop("R1_complete_year (USGS/SWToolbox)")
    put("TRetainMin", retained.min(), pct(retained.min(), 0))
    put("TRetainMax", retained.max(), pct(retained.max(), 0))
    scores = rules.loc[rules.kind.eq("score")]

    def retention(population: str, delivered: str, rule: str, level: str = "retention_at_050") -> float:
        return float(scores.loc[(scores.population == population) & (scores.delivered == delivered) & (scores.rule == rule), level].iloc[0])

    put("TDeployRetWarmTwoFive", retention("deploy", "P0", "R2_warm_missing_fraction", "retention_at_025"), pct(retention("deploy", "P0", "R2_warm_missing_fraction", "retention_at_025"), 1))
    put("TDeployRetTargetTwoFive", retention("deploy", "D2*", "R7b_direct_failure_probability (D2*)", "retention_at_025"), pct(retention("deploy", "D2*", "R7b_direct_failure_probability (D2*)", "retention_at_025"), 1))
    put("TDeployRetOracleTwoFive", retention("deploy", "D2*", "R8_oracle_error_order", "retention_at_025"), pct(retention("deploy", "D2*", "R8_oracle_error_order", "retention_at_025"), 1))
    put("TMechRetTarget", retention("mech", "D2*", "R7b_direct_failure_probability (D2*)"), pct(retention("mech", "D2*", "R7b_direct_failure_probability (D2*)"), 0))
    put("TMechRetTargetA", retention("mech", "D2*", "R7a_target_aware_pfail (D2* distribution)"), pct(retention("mech", "D2*", "R7a_target_aware_pfail (D2* distribution)"), 0))
    put("TMechRetWarm", retention("mech", "P0", "R2_warm_missing_fraction"), pct(retention("mech", "P0", "R2_warm_missing_fraction"), 0))
    put("TMechRetLaw", retention("mech", "P0", "R6_recovery_law_pfail"), pct(retention("mech", "P0", "R6_recovery_law_pfail"), 0))
    put("TMechRetTargetDisagree", retention("mech", "P0", "R5_h30_target_disagreement"), pct(retention("mech", "P0", "R5_h30_target_disagreement"), 0))
    put("TMechRetOracle", retention("mech", "D2*", "R8_oracle_error_order"), pct(retention("mech", "D2*", "R8_oracle_error_order"), 0))
    e5 = load(R2, "e5_rules/summary.json")
    put("TPTwoGain", e5["endpoint_P2_retention_gain_at_5pct"], pct(e5["endpoint_P2_retention_gain_at_5pct"], 1))
    loro_thresholds = load(R2, "e5_rules/loro_thresholds.csv")
    lt = loro_thresholds.loc[loro_thresholds.alpha.eq(0.05)].set_index(["population", "score", "delivered"])
    put("TLoroFreeWarmRet", lt.loc[("deploy", "R2_warm_missing_fraction", "Pobs"), "retention"], pct(lt.loc[("deploy", "R2_warm_missing_fraction", "Pobs"), "retention"], 0))
    put("TLoroFreeWarmWorst", lt.loc[("deploy", "R2_warm_missing_fraction", "Pobs"), "worst_region_risk"], pct(lt.loc[("deploy", "R2_warm_missing_fraction", "Pobs"), "worst_region_risk"], 0))

    # E6 targets (round 2).
    agreement = load(R2, "e6_multitarget/target_agreement.csv")

    def kappa(population: str, a: str, b: str) -> float:
        return float(agreement.loc[(agreement.population == population) & (agreement.target_a == a) & (agreement.target_b == b), "kappa_usable"].iloc[0])

    put("TKappaHSeven", kappa("deploy", "h30", "h7"), number(kappa("deploy", "h30", "h7"), 2))
    put("TKappaMean", kappa("deploy", "h30", "annual_mean"), number(kappa("deploy", "h30", "annual_mean"), 2))
    put("TKappaCThirty", kappa("deploy", "h30", "c30"), number(kappa("deploy", "h30", "c30"), 2))
    put("TKappaCThirtyMech", kappa("mech", "h30", "c30"), number(kappa("mech", "h30", "c30"), 2))
    misjudge = load(R2, "e6_multitarget/rule_misjudgement_by_target.csv")
    for target, name in (("h30", "H"), ("c30", "C")):
        value = float(misjudge.loc[(misjudge.population == "deploy") & (misjudge.target == target) & (misjudge.rule == "R2_oregon_jas_80pct"), "false_acceptance"].iloc[0])
        put(f"TOregonFalseAccept{name}", value, pct(value, 1))
    frontier = load(R2, "e6_multitarget/target_frontier.csv")
    own = frontier.loc[frontier.population.eq("mech")].set_index("target")
    by_h30 = frontier.loc[frontier.population.eq("mech|scored_by_h30")].set_index("target")
    put("TDaysOwnScore", own.loc["days_above_20", "target_aware_retention_at_5pct"], pct(own.loc["days_above_20", "target_aware_retention_at_5pct"], 0))
    put("TDaysHScore", by_h30.loc["days_above_20", "target_aware_retention_at_5pct"], pct(by_h30.loc["days_above_20", "target_aware_retention_at_5pct"], 0))

    # E7: the preregistered P3 and the first test (round 1, as registered).
    p3 = load(R1, "e7_transfer/endpoint_P3_source.json")
    put("TLoroRegions", p3["mech_n_regions"], str(p3["mech_n_regions"]))
    put("TLoroShareMech", p3["mech_share_risk_le_7pct"], pct(p3["mech_share_risk_le_7pct"], 0))
    put("TLoroMedianMech", p3["mech_median_risk"], pct(p3["mech_median_risk"], 1))
    put("TLoroShareDeploy", p3["deploy_share_risk_le_7pct"], pct(p3["deploy_share_risk_le_7pct"], 0))
    put("TLoroMedianDeploy", p3["deploy_median_risk"], pct(p3["deploy_median_risk"], 1))
    p3_r2 = load(R2, "e7_transfer/endpoint_P3_source.json")
    put("TLoroShareMechRtwo", p3_r2["mech_share_risk_le_7pct"], pct(p3_r2["mech_share_risk_le_7pct"], 0))
    put("TLoroMedianMechRtwo", p3_r2["mech_median_risk"], pct(p3_r2["mech_median_risk"], 1))
    sealed = load(T.AU_ROUND1, "sealed_results.json")
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
    frozen = load(T.AU_ROUND1, "sealed_frozen_thresholds.csv")
    unscreened = frozen.loc[(frozen.population == "deploy") & (frozen.score == "R7a_target_aware")].unscreened_risk.iloc[0]
    put("TAuUnscreenedDTwo", unscreened, pct(unscreened, 1))
    diag = load(T.AU_ROUND1, "posthoc_domain_contrast.csv").set_index(["domain", "family"])
    put("TAuRTwo", diag.loc[("australia", "calendar"), "median_r2"], number(diag.loc[("australia", "calendar"), "median_r2"], 2))
    put("TSourceRTwo", diag.loc[("source", "calendar"), "median_r2"], number(diag.loc[("source", "calendar"), "median_r2"], 2))
    put("TAuMissing", diag.loc[("australia", "calendar"), "median_missing_fraction"], pct(diag.loc[("australia", "calendar"), "median_missing_fraction"], 1))
    put("TSourceMissing", diag.loc[("source", "calendar"), "median_missing_fraction"], pct(diag.loc[("source", "calendar"), "median_missing_fraction"], 1))

    # M3: the label-free expected-risk rule, developed leave-one-region-out (round 2).
    rule = load(R2, "e7_transfer/expected_risk_rule.json")
    put("TErFactor", rule["final_factor_k"]["R7b"], number(rule["final_factor_k"]["R7b"], 2))
    put("TErFactorA", rule["final_factor_k"]["R7a"], number(rule["final_factor_k"]["R7a"], 2))
    development = load(R2, "e7_transfer/expected_risk_development_summary.csv").set_index(["population", "score"])
    put("TErRegions", development.loc[("mech", "R7b"), "n_regions"], number(development.loc[("mech", "R7b"), "n_regions"], 0))
    for population, label in (("mech", "Mech"), ("deploy", "Deploy")):
        for score, suffix in (("R7b", ""), ("R7a", "A")):
            row = development.loc[(population, score)]
            put(f"TErShare{label}{suffix}", row.share_risk_le_7pct, pct(row.share_risk_le_7pct, 0))
            put(f"TErWorst{label}{suffix}", row.worst_region_risk, pct(row.worst_region_risk, 1))
            put(f"TErMedianRet{label}{suffix}", row.median_retention, pct(row.median_retention, 0))
            put(f"TErShareKOne{label}{suffix}", row.k1_share_risk_le_7pct, pct(row.k1_share_risk_le_7pct, 0))
            put(f"TErWorstKOne{label}{suffix}", row.k1_worst_region_risk, pct(row.k1_worst_region_risk, 1))
    au_dev = load(R2, "e7_au_development/development_check.json")
    dev = pd.DataFrame(au_dev["rule"]).set_index(["population", "score", "factor"])
    for population, label in (("deploy", "Deploy"), ("mech", "Mech")):
        row = dev.loc[(population, "R7b", "k")]
        put(f"TAuDevRisk{label}", row.risk, pct(row.risk, 1))
        put(f"TAuDevRisk{label}High", row.risk_upper95, pct(row.risk_upper95, 1))
        put(f"TAuDevRet{label}", row.retention, pct(row.retention, 0))
        put(f"TAuDevUnscreened{label}", row.unscreened_risk_D2, pct(row.unscreened_risk_D2, 1))
    put("TAuDevPOneReduction", au_dev["P1_reduction"], pct(au_dev["P1_reduction"], 0))
    put("TAuDevPOneCoverage", au_dev["P1_coverage90"], pct(au_dev["P1_coverage90"], 1))
    put("TAuDevHardCoverage", au_dev["hardest_bin_coverage90_mech"], pct(au_dev["hardest_bin_coverage90_mech"], 1))
    au_law = australia.iloc[-2:].set_index("family")
    put("TAuDevLawDeploy", au_law.loc["calendar", "predicted_law_pfail_050"], pct(au_law.loc["calendar", "predicted_law_pfail_050"], 1))
    put("TAuDevLawPDeploy", au_law.loc["calendar", "predicted_law_v2p_pfail_050"], pct(au_law.loc["calendar", "predicted_law_v2p_pfail_050"], 1))
    put("TAuDevObsDeploy", au_law.loc["calendar", "observed_failure_check"], pct(au_law.loc["calendar", "observed_failure_check"], 1))

    # M4: the test on new USGS stations (second preregistration).
    design = load(R2, "e10_sealed_usgs/sealed_design.json")
    new = load(R2, "e10_sealed_usgs/sealed_results.json")
    expected = load(R2, "e10_sealed_usgs/sealed_expected_risk.csv").set_index(["population", "score", "factor"])
    put("TNewCandidates", 155, "155")
    put("TNewStations", new["n_stations"], number(new["n_stations"], 0))
    put("TNewStationsDesign", design["n_targets"], number(design["n_targets"], 0))
    put("TNewGroups", new["n_groups"], number(new["n_groups"], 0))
    put("TNewHucs", new["n_regions"], number(new["n_regions"], 0))
    put("TNewYears", new["n_station_years"], number(new["n_station_years"], 0))
    put("TNewCases", new["n_cases"], number(new["n_cases"], 0))
    put("TNewFactor", rule["final_factor_k"]["R7b"], number(rule["final_factor_k"]["R7b"], 2))
    put("TNewAirShare", new["layer_shares"].get("air_ridge", 0.0), pct(new["layer_shares"].get("air_ridge", 0.0), 0))
    for population, label in (("deploy", "Deploy"), ("mech", "Mech")):
        row = expected.loc[(population, "R7b", "k")]
        put(f"TNewRisk{label}", row.risk, pct(row.risk, 1))
        put(f"TNewRisk{label}High", row.risk_upper95, pct(row.risk_upper95, 1))
        put(f"TNewRet{label}", row.retention, pct(row.retention, 0))
        put(f"TNewUnscreened{label}", row.unscreened_risk_D2, pct(row.unscreened_risk_D2, 1))
        put(f"TNewUnscreenedPZero{label}", row.unscreened_risk_P0, pct(row.unscreened_risk_P0, 1))
        row_a = expected.loc[(population, "R7a", "k")]
        put(f"TNewRiskA{label}", row_a.risk, pct(row_a.risk, 1))
        put(f"TNewRetA{label}", row_a.retention, pct(row_a.retention, 0))
        row_1 = expected.loc[(population, "R7b", "k1")]
        put(f"TNewRiskKOne{label}", row_1.risk, pct(row_1.risk, 1))
    primary_deploy = expected.loc[("deploy", "R7b", "k")]
    put("TNewRiskDeployHighMissing", primary_deploy.risk_high_missingness, pct(primary_deploy.risk_high_missingness, 1))
    put("TNewRiskDeployLowMissing", primary_deploy.risk_low_missingness, pct(primary_deploy.risk_low_missingness, 1))
    worst = max(expected.loc[("deploy", "R7b", "k")].worst_region_risk_ge200, expected.loc[("mech", "R7b", "k")].worst_region_risk_ge200)
    put("TNewWorstRegionRisk", worst, pct(worst, 1))
    for population, label in (("deploy", "Deploy"), ("mech", "Mech")):
        row = expected.loc[(population, "R7b", "k")]
        put(f"TNewWorstRegion{label}", row.worst_region_risk_ge200, pct(row.worst_region_risk_ge200, 1))
        put(f"TNewWorstGroup{label}", row.worst_group_risk_ge20, pct(row.worst_group_risk_ge20, 0))
        put(f"TNewRiskAKOne{label}", expected.loc[(population, "R7a", "k1")].risk, pct(expected.loc[(population, "R7a", "k1")].risk, 1))
    put("TNewRiskNoPrior", expected.loc[("mech", "R7b", "k")].risk_without_prior_huc8, pct(expected.loc[("mech", "R7b", "k")].risk_without_prior_huc8, 1))
    put("TNewRiskPerRegion", expected.loc[("mech", "R7b", "k")].risk_per_region_admission, pct(expected.loc[("mech", "R7b", "k")].risk_per_region_admission, 1))
    put("TNewHardCoverage", new["N2_hardest_bin_coverage90"], pct(new["N2_hardest_bin_coverage90"], 1))
    put("TNewHardCoverageVerdict", new["N2_success"], "met" if new["N2_success"] else "not met")
    n3 = new["N3_P1_stratum"]
    put("TNewPOneBiasPZero", n3["bias_P0"], number(n3["bias_P0"], 2))
    put("TNewPOneBiasDTwo", n3["bias_D2"], number(n3["bias_D2"], 2))
    put("TNewPOneReduction", n3["reduction"], pct(n3["reduction"], 0))
    put("TNewPOneReductionLow", n3["reduction_lower95"], pct(n3["reduction_lower95"], 0))
    put("TNewPOneReductionHigh", n3["reduction_upper95"], pct(n3["reduction_upper95"], 0))
    put("TNewPOneN", n3["n"], number(n3["n"], 0))
    put("TNewPOneCoverage", n3["coverage90"], pct(n3["coverage90"], 1))
    put("TNewPOneVerdict", new["N3_success"], "met" if new["N3_success"] else "not met")
    put("TNewGainMech", new["N4_ranking_gain_R7b"]["mech"], pct(new["N4_ranking_gain_R7b"]["mech"], 0))
    put("TNewGainDeploy", new["N4_ranking_gain_R7b"]["deploy"], pct(new["N4_ranking_gain_R7b"]["deploy"], 0))
    put("TNewLawPredicted", new["law"]["deploy"]["predicted_P0_failure_v2"], pct(new["law"]["deploy"]["predicted_P0_failure_v2"], 1))
    put("TNewObservedFail", new["law"]["deploy"]["observed_P0_failure"], pct(new["law"]["deploy"]["observed_P0_failure"], 1))
    put("TNewLawMech", new["law"]["mech"]["predicted_P0_failure_v2"], pct(new["law"]["mech"]["predicted_P0_failure_v2"], 1))
    put("TNewLawPMech", new["law"]["mech"]["predicted_P0_failure_v2p"], pct(new["law"]["mech"]["predicted_P0_failure_v2p"], 1))
    put("TNewObservedMech", new["law"]["mech"]["observed_P0_failure"], pct(new["law"]["mech"]["observed_P0_failure"], 1))
    put("TNewOwnCalendars", new["calendar_source"]["own"], pct(new["calendar_source"]["own"], 0))
    needed = new["local_groups_needed_for_80pct"]
    put("TNewLocalGroups", needed.get("mech"), str(needed.get("mech")) if needed.get("mech") else "more than 16")
    put("TNewNOneVerdict", new["N1_success"], "met" if new["N1_success"] else "not met")

    # E8 downstream (round 2) and its decomposition (M5).
    p4_r1 = load(R1, "e8_downstream/endpoint_P4.json")
    put("TTrendReductionRone", p4_r1["rmse_reduction"], pct(p4_r1["rmse_reduction"], 0))
    p4 = load(R2, "e8_downstream/endpoint_P4.json")
    p4b = load(R2, "e8_downstream/min_years_15/endpoint_P4.json")
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
    e8 = load(R2, "e8_downstream/summary.csv").set_index(["scenario", "pipeline"])
    put("TTrendRmseAZero", e8.loc[("mnar1", "A0"), "slope_rmse"], number(e8.loc[("mnar1", "A0"), "slope_rmse"], 2))
    put("TTrendRmseB", e8.loc[("mnar1", "B"), "slope_rmse"], number(e8.loc[("mnar1", "B"), "slope_rmse"], 3))
    put("TYearsAZero", e8.loc[("mnar1", "A0"), "mean_years"], number(e8.loc[("mnar1", "A0"), "mean_years"], 1))
    put("TYearsAll", e8.loc[("mnar1", "C"), "mean_years"], number(e8.loc[("mnar1", "C"), "mean_years"], 1))
    for pipeline, name in (("A1", "AOne"), ("B", "B"), ("C", "C")):
        value = e8.loc[("mnar1", pipeline), "hot_missed_incomplete"] / e8.loc[("mnar1", pipeline), "hot_true_incomplete"]
        put(f"THotMissed{name}", value, pct(value, 0))
    put("TMeanBiasB", e8.loc[("mnar1", "B"), "mean_h30_bias"], number(e8.loc[("mnar1", "B"), "mean_h30_bias"], 3))
    split = load(R2, "e8_downstream/decomposition.json")["mnar1"]
    put("TShareKeep", split["share_of_gain_from_keeping_years"], pct(split["share_of_gain_from_keeping_years"], 0))
    put("TShareKeepLow", split["share_lower95"], pct(split["share_lower95"], 0))
    put("TShareKeepHigh", split["share_upper95"], pct(split["share_upper95"], 0))
    for key, name in (("ratio_B_A1", "RatioBAOne"), ("ratio_C_B", "RatioCB")):
        put(f"T{name}", split[f"{key}_median"], number(split[f"{key}_median"], 2))
        put(f"T{name}Low", split[f"{key}_q25"], number(split[f"{key}_q25"], 2))
        put(f"T{name}High", split[f"{key}_q75"], number(split[f"{key}_q75"], 2))
        put(f"T{name}Below", split[f"{key}_share_below_1"], pct(split[f"{key}_share_below_1"], 0))
    put("TNStationsBExact", split["n_stations_B_exact"], number(split["n_stations_B_exact"], 0))
    put("TNStationsRatio", split["ratio_C_B_n"], number(split["ratio_C_B_n"], 0))
    put("TMedianTrend", split["median_station_trend"], number(split["median_station_trend"], 2))
    put("TRmseAOneShare", split["rmse_A1_over_median_trend"], pct(split["rmse_A1_over_median_trend"], 1))
    put("TRmseCShare", split["rmse_C_over_median_trend"], pct(split["rmse_C_over_median_trend"], 1))
    for pipeline, name in (("A0", "AZero"), ("A1", "AOne"), ("C", "C")):
        put(f"TDetect{name}", split[f"detect_given_full_detects_{pipeline}"], pct(split[f"detect_given_full_detects_{pipeline}"], 1))
        put(f"TCiWidth{name}", split[f"ci_width_{pipeline}"], number(split[f"ci_width_{pipeline}"], 2))
    put("TFalseDetectAZero", split["detect_given_full_not_A0"], pct(split["detect_given_full_not_A0"], 1))

    # E9 application (round 2) and the Baden-Wuerttemberg example (M5).
    e9 = load(R2, "e9_application/summary.json")
    put("TRealYears", e9["n_real_incomplete_station_years"], number(e9["n_real_incomplete_station_years"], 0))
    put("TRealStations", e9["n_stations"], number(e9["n_stations"], 0))
    put("TRealAdmitted", e9["target_aware_admitted_share"], pct(e9["target_aware_admitted_share"], 1))
    put("TRealBestRule", e9["best_rule_share"], pct(e9["best_rule_share"], 1))
    usage = load(R2, "e9_application/usable_station_years.csv").set_index("provider")
    put("TRealUSGSRule", usage.loc["all", "R1_usgs_indicator_311d_24pm"], pct(usage.loc["all", "R1_usgs_indicator_311d_24pm"], 0))
    bw = load(R2, "e9_application/bw_summary.json")
    put("TBwStations", bw["n_stations"], str(bw["n_stations"]))
    put("TBwGroups", bw["n_groups"], str(bw["n_groups"]))
    put("TBwCompleteShare", bw["complete_share_station_years"], pct(bw["complete_share_station_years"], 0))
    put("TBwIncompleteTwoThousandThree", bw["stations_incomplete_2003"], str(bw["stations_incomplete_2003"]))
    regional = pd.DataFrame(bw["regional"]).set_index(["years", "pipeline"])
    for years, suffix in (("all years", ""), ("without 2003", "NoTwoThousandThree")):
        for pipeline, name in (("A0", "AZero"), ("A1", "AOne"), ("B", "B"), ("C", "C")):
            row = regional.loc[(years, pipeline)]
            put(f"TBw{name}{suffix}", row.regional_trend, number(row.regional_trend, 2))
            put(f"TBw{name}{suffix}Low", row.lower95, number(row.lower95, 2))
            put(f"TBw{name}{suffix}High", row.upper95, number(row.upper95, 2))
    anomaly = load(R2, "e9_application/bw_anomaly_series.csv").set_index("year")
    complete_counts = anomaly.complete.fillna(0)
    put("TBwYears", len(anomaly), str(len(anomaly)))
    put("TBwYearsFewComplete", int((complete_counts < 5).sum()), str(int((complete_counts < 5).sum())))

    # E11 ablation (round 2).
    ablation = load(R2, "e11_ablation/score_ablation.csv").set_index(["population", "score"])
    for key, name in (("full (R7b)", "Full"), ("no_simulation", "NoSim"), ("law_only", "Law"), ("geometry_only", "Geometry")):
        put(f"TAbl{name}", ablation.loc[("mech", key), "retention_at_050"], pct(ablation.loc[("mech", key), "retention_at_050"], 1))
    shrink = load(R2, "e11_ablation/shrinkage_ablation.csv").set_index(["population", "estimator"])
    put("TShrinkRidge", shrink.loc[("mech", "air_ridge (P0)"), "bias"], number(shrink.loc[("mech", "air_ridge (P0)"), "bias"], 3))
    put("TShrinkOls", shrink.loc[("mech", "air_ols (no shrinkage)"), "bias"], number(shrink.loc[("mech", "air_ols (no shrinkage)"), "bias"], 3))

    # S1: the 7-day minimum flow.
    flow = load(R2, "s1_flow/summary.json")
    flow_metrics = load(R2, "s1_flow/estimator_metrics.csv").set_index(["population", "stratum", "estimator"])
    flow_rules = load(R2, "s1_flow/rules.csv")
    flow_trend = load(R2, "s1_flow/trend_summary.csv").set_index("pipeline")
    put("TFlowSites", flow["n_sites"], number(flow["n_sites"], 0))
    put("TFlowYears", flow["n_complete_years"], number(flow["n_complete_years"], 0))
    put("TFlowCases", flow["n_cases"], number(flow["n_cases"], 0))
    put("TFlowTol", flow["tolerance_percent"] / 100, pct(flow["tolerance_percent"] / 100, 0))
    for stratum, name in (("low-flow window at least half hidden", "Half"), ("half hidden, interpolation layer", "Interp"), ("half hidden, neighbour layer", "Neighbour")):
        for estimator, suffix in (("P0 plug-in", "PZero"), ("recorded days", "Recorded"), ("D2 target-aware", "DTwo")):
            value = float(np.exp(flow_metrics.loc[("deploy", stratum, estimator), "bias_log"]) - 1)
            put(f"TFlowBias{name}{suffix}", value, pct(value, 0))
    for estimator, suffix in (("P0 plug-in", "PZero"), ("D2 target-aware", "DTwo"), ("recorded days", "Recorded")):
        put(f"TFlowFail{suffix}", flow_metrics.loc[("deploy", "all", estimator), "failure_rate"], pct(flow_metrics.loc[("deploy", "all", estimator), "failure_rate"], 1))
    put("TFlowCoverage", flow_metrics.loc[("deploy", "all", "D2 target-aware"), "coverage90"], pct(flow_metrics.loc[("deploy", "all", "D2 target-aware"), "coverage90"], 0))
    fr = flow_rules.loc[flow_rules.population.eq("deploy")]

    def flow_rule(delivered: str, rule: str, column: str) -> float:
        return float(fr.loc[(fr.delivered == delivered) & (fr.rule == rule), column].iloc[0])

    put("TFlowRetTarget", flow_rule("D2", "target-aware failure probability", "retention_at_050"), pct(flow_rule("D2", "target-aware failure probability", "retention_at_050"), 0))
    put("TFlowRetMissing", flow_rule("recorded", "missing fraction", "retention_at_050"), pct(flow_rule("recorded", "missing fraction", "retention_at_050"), 0))
    put("TFlowRetNinety", flow_rule("recorded", "at least 90% of days", "retention"), pct(flow_rule("recorded", "at least 90% of days", "retention"), 0))
    put("TFlowRetOracle", flow_rule("D2", "R8_oracle_error_order", "retention_at_050"), pct(flow_rule("D2", "R8_oracle_error_order", "retention_at_050"), 0))
    put("TFlowUsable", float(fr.usable_share_of_rejected_by_SWToolbox_D2.iloc[0]), pct(float(fr.usable_share_of_rejected_by_SWToolbox_D2.iloc[0]), 0))
    for pipeline, name in (("A0", "AZero"), ("A1", "AOne"), ("B", "B"), ("C", "C")):
        put(f"TFlowTrend{name}", flow_trend.loc[pipeline, "rmse_per_decade_log"], number(flow_trend.loc[pipeline, "rmse_per_decade_log"], 4))
    reduction = 1 - flow_trend.loc["C", "rmse_per_decade_log"] / flow_trend.loc["A0", "rmse_per_decade_log"]
    put("TFlowTrendReduction", reduction, pct(reduction, 0))
    keep_share = (flow_trend.loc["A0", "rmse_per_decade_log"] - flow_trend.loc["B", "rmse_per_decade_log"]) / (flow_trend.loc["A0", "rmse_per_decade_log"] - flow_trend.loc["C", "rmse_per_decade_log"])
    put("TFlowShareKeep", keep_share, pct(keep_share, 0))
    put("TFlowTrendStations", flow["trend_stations"], number(flow["trend_stations"], 0))
    put("TFlowTrendCoverage", flow["trend_coverage_C"], pct(flow["trend_coverage_C"], 0))

    lines = ["%% Generated by scripts/463_tr2_evidence.py; do not edit by hand."] + [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
    (PAPER / "tr_claims.tex").write_text("\n".join(lines) + "\n")
    T.write_json(OUT / "claims.json", claims)

    # Main tables, one file each so that the manuscript places each where it is first cited.
    main = {}
    # P1-P4 are judged as registered, on the first-round files; the verdict follows the computed success flags.
    p2_r1 = load(R1, "e5_rules/summary.json")
    verdict = lambda met: "Met" if met else "Not met"  # noqa: E731
    endpoint_rows = [
        ["P1", "Signed H30 bias of D2*, air layer, true peak $\\geq$50\\% hidden (controlled gaps)", f"As registered: reduction {macros['TPOneReductionRone']}\\%, 90\\% coverage {macros['TPOneCoverageRone']}\\%. Corrected definitions: {macros['TPOneBiasPZero']} $\\rightarrow$ {macros['TPOneBias']}\\,$^{{\\circ}}$C, {macros['TPOneReduction']}\\%, coverage {macros['TPOneCoverage']}\\%; calibrated intervals {macros['TPOneCoverageCal']}\\%", verdict(p1_r1["P1_success"])],
        ["P2", "Retention gain at 5\\% realised risk over the best rule (real calendars)", f"{macros['TPTwoGain']} points; D2* without screening fails in {macros['TDeployFailDTwo']}\\% of cases", verdict(p2_r1["endpoint_P2_success"])],
        ["P3", "Regions with realised risk $\\leq$7\\% at nominal 5\\% (fixed thresholds)", f"Controlled gaps {macros['TLoroShareMech']}\\% (median {macros['TLoroMedianMech']}\\%), real calendars {macros['TLoroShareDeploy']}\\%; Australia {macros['TAuRiskDeploy']}\\% and {macros['TAuRiskMech']}\\%", verdict(p3["P3_source_success"] and sealed["P3_sealed_success"])],
        ["P4", "Station H30 trend RMSE, multiple imputation (C) versus the 90\\% rule (A1)", f"{macros['TTrendRmseAOne']} $\\rightarrow$ {macros['TTrendRmseC']}\\,$^{{\\circ}}$C/decade, reduction {macros['TTrendReduction']}\\% [{macros['TTrendReductionLow']}, {macros['TTrendReductionHigh']}] (as registered {macros['TTrendReductionRone']}\\%); coverage {macros['TTrendCoverage']}\\%", verdict(p4_r1["P4_success"])],
        ["N1", "Realised risk under the label-free rule (R7b, $k$={0}), new USGS stations".format(macros["TNewFactor"]), f"Real calendars {macros['TNewRiskDeploy']}\\% [up to {macros['TNewRiskDeployHigh']}], using {macros['TNewRetDeploy']}\\%; controlled gaps {macros['TNewRiskMech']}\\% [up to {macros['TNewRiskMechHigh']}], using {macros['TNewRetMech']}\\%", macros["TNewNOneVerdict"].capitalize()],
        ["N2", "90\\% coverage, climatological peak $>$75\\% hidden", f"{macros['TNewHardCoverage']}\\%", macros["TNewHardCoverageVerdict"].capitalize()],
        ["N3", "Bias reduction in the P1 stratum", f"{macros['TNewPOneBiasPZero']} $\\rightarrow$ {macros['TNewPOneBiasDTwo']}\\,$^{{\\circ}}$C, {macros['TNewPOneReduction']}\\%", macros["TNewPOneVerdict"].capitalize()],
        ["N4", "Ranking gain over the best rule at 5\\% realised risk", f"Controlled gaps {macros['TNewGainMech']} points, real calendars {macros['TNewGainDeploy']} points", "Descriptive"],
    ]
    main["tr_table_endpoints.tex"] = (table(pd.DataFrame(endpoint_rows),"Preregistered endpoints (P1--P4 first, N1--N4 second preregistration), recomputed after the change of seeds (Text~S6). Brackets: upper 95\\% bounds.", "tab:endpoints", "p{0.04\\textwidth}p{0.27\\textwidth}p{0.49\\textwidth}p{0.08\\textwidth}", ["", "Quantity", "Result", "Verdict"]))
    rule_rows = []
    fixed = deploy.loc[deploy.kind.eq("fixed") & deploy.delivered.eq("Pobs")].set_index("rule")
    for key, label in RULE_NAMES.items():
        if key not in fixed.index:
            continue
        rule_rows.append([label, pct(fixed.loc[key, "retention"], 0), pct(fixed.loc[key, "risk"], 2) if fixed.loc[key, "retention"] > 0 else "--",
                          pct(1 - waste_deploy.loc[key, "rejected_share_usable_P0"], 1), pct(waste_deploy.loc[key, "rejected_share_usable_D2"], 0)])
    for score, value, label in (("R1_annual_missing_fraction", "Pobs", "Annual missing fraction, threshold from other regions"), ("R2_warm_missing_fraction", "Pobs", "Warm-season missing fraction, threshold from other regions"), ("R3_observed_lower_bound (NRFA-type)", "Pobs", "Observed lower bound, threshold from other regions"), ("R7b_direct_failure_probability (D2*)", "D2*", "Target-aware (R7b, D2* value), threshold from other regions")):
        row = lt.loc[("deploy", score, value)]
        rule_rows.append([label, pct(row.retention, 0), pct(row.risk, 2), "--", f"worst region {pct(row.worst_region_risk, 0)}"])
    rule_rows.append(["No screening, value from D2*", "100", macros["TDeployFailDTwo"], "--", "--"])
    main["tr_table_rules.tex"] = (table(pd.DataFrame(rule_rows),"Published completeness rules under real gap calendars. Use is judged from recorded days; a rejected year is recoverable if its D2* estimate is within 0.5\\,$^{\\circ}$C.", "tab:rules", "p{0.40\\textwidth}p{0.08\\textwidth}p{0.11\\textwidth}p{0.12\\textwidth}p{0.14\\textwidth}", ["Rule", "Used (\\%)", "Failures among used (\\%)", "Failures among rejected, plug-in (\\%)", "Rejected but recoverable (\\%)"]))
    for name, tex in main.items():
        (PAPER / name).write_text(tex)

    # Supporting tables: the 17 tables of the first submission, recomputed, and five new ones.
    si = []
    m = models.copy()
    m["or"] = [f"{number(a, 2)} [{number(b, 2)}, {number(c, 2)}]" for a, b, c in zip(m.odds_ratio, m.odds_ratio_lower95, m.odds_ratio_upper95)]
    si.append(table(m[["analysis", "covariate", "n", "or"]].assign(analysis=lambda f: f.analysis.str.replace("_", " "), covariate=lambda f: f.covariate.str.replace("_", " "), n=lambda f: f.n.map(lambda v: number(v, 0))), "E1 missingness models. Station-year models use station fixed effects (conditional logit) or station and region-year random intercepts; onset models are time-stratified case-crossover designs (strata: station $\\times$ year $\\times$ month). Duration is a ratio of gap lengths. Intervals resample independence groups (model-based for the mixed model and duration).", "tab:si_e1", "llrl", ["Analysis", "Covariate", "n", "Odds ratio [95\\%]"]))
    tol = pd.DataFrame([[TARGET_NAMES.get(k, k), number(tolerance["median_interannual_sd"].get(k, np.nan), 2), number(v, 2)] for k, v in tolerance["tolerance"].items() if k in TARGET_NAMES])
    si.append(table(tol, "Target tolerances: the share of the median within-station interannual standard deviation that 0.5\\,$^{\\circ}$C represents for H30, with floors of 0.2\\,$^{\\circ}$C and one day, recomputed for the degree-days of each station's four climatologically hottest months.", "tab:si_tolerance", "lrr", ["Target", "Median interannual SD", "Tolerance"]))
    lawtab = law.loc[law.population.isin(["mech", "deploy"]) & law.metric.isin(["ece", "brier_skill_vs_base_rate", "auc", "mean_predicted_pfail", "observed_failure_rate", "mean_predicted_bias", "observed_mean_error"])]
    lawtab = lawtab.loc[lawtab.truncated.astype(str).str.lower().eq("true")].pivot_table(index=["population", "version"], columns="metric", values="value").reset_index()
    lawtab = lawtab[["population", "version", "ece", "brier_skill_vs_base_rate", "auc", "mean_predicted_pfail", "observed_failure_rate", "mean_predicted_bias", "observed_mean_error"]]
    for column in lawtab.columns[2:]:
        lawtab[column] = lawtab[column].map(lambda v: number(v, 3))
    si.append(table(lawtab, "E3 recovery law, case level. v1: daily-scale shrinkage; v2: window-scale shrinkage (main parametric law); v2p: residual moments inside the training peak windows; v3: replay of the same gap on training years (empirical comparator). No version is fitted to reconstruction errors.", "tab:si_law", "llrrrrrrr", ["Population", "Law", "ECE", "Brier skill", "AUC", "Predicted failure", "Observed failure", "Predicted bias", "Observed bias"]))
    cell = load(R2, "e3_recovery_law/cells.csv")
    cell = cell[["gap_length", "overlap_class", "layer", "n", "mean_error", "law_bias", "law_v3_bias", "failure_rate", "law_pfail", "law_v2p_pfail", "law_v3_pfail"]].copy()
    cell["layer"] = cell.layer.str.replace("_", " ")
    for column in ("mean_error", "law_bias", "law_v3_bias", "failure_rate", "law_pfail", "law_v2p_pfail", "law_v3_pfail"):
        cell[column] = cell[column].map(lambda v: number(v, 3))
    cell["n"] = cell.n.map(lambda v: number(v, 0))
    si.append(table(cell, "E3 cells of the controlled population (gap length $\\times$ overlap with the climatological peak $\\times$ information layer).", "tab:si_cells", "rllrrrrrrrr", ["Days", "Overlap", "Layer", "n", "Mean error", "v2 bias", "v3 bias", "Failure", "v2 P(fail)", "v2p P(fail)", "v3 P(fail)"], "\\tiny"))
    est = metrics.loc[metrics.target.eq("h30") & metrics.population.isin(["mech", "deploy"]) & metrics.stratum.isin(["all", "peak_half_hidden", "air_layer_half_hidden", "donor_layer_half_hidden", "warm_anomaly_half_hidden"])].copy()
    est["estimator"] = est.estimator.map(ESTIMATOR_NAMES)
    est["stratum"] = est.stratum.str.replace("_", " ")
    for column in ("bias", "mae", "crps_q"):
        est[column] = est[column].map(lambda v: number(v, 3))
    for column in ("failure_rate", "coverage90"):
        est[column] = est[column].map(lambda v: pct(v, 1))
    est["n"] = est.n.map(lambda v: number(v, 0))
    si.append(table(est[["population", "stratum", "estimator", "n", "bias", "mae", "failure_rate", "crps_q", "coverage90"]], "E4 H30 estimators, leave-one-region-out, before interval calibration. Strata use the true peak window (evaluation only); warm anomaly: true H30 at least 1\\,$^{\\circ}$C above the training mean. Calibrated coverage by difficulty group is in Table~\\ref{tab:si_conformal}.", "tab:si_estimators", "lllrrrrrr", ["Population", "Stratum", "Estimator", "n", "Bias", "MAE", "Failure (\\%)", "CRPS", "Cover90 (\\%)"], "\\tiny"))
    other = metrics.loc[metrics.target.ne("h30") & metrics.population.isin(["mech", "deploy"]) & metrics.stratum.eq("all") & metrics.estimator.isin(["P0", "Pobs", "P2", "P3", "P5b"])].copy()
    other["target"] = other.target.map(TARGET_NAMES)
    other["estimator"] = other.estimator.map(ESTIMATOR_NAMES)
    for column in ("bias", "mae"):
        other[column] = other[column].map(lambda v: number(v, 3))
    other["failure_rate"] = other.failure_rate.map(lambda v: pct(v, 1))
    si.append(table(other[["population", "target", "estimator", "bias", "mae", "failure_rate"]], "E4 estimators for the other targets (all cases), with the target tolerances.", "tab:si_other_targets", "lllrrr", ["Population", "Target", "Estimator", "Bias", "MAE", "Failure (\\%)"], "\\tiny"))
    curve = scores.loc[scores.population.isin(["deploy", "mech"])].copy()
    curve["rule"] = curve.rule.map(SCORE_NAMES)
    for column in ("retention_at_025", "retention_at_050", "retention_at_100"):
        curve[column] = curve[column].map(lambda v: pct(v, 1))
    for column in ("aurc", "augrc"):
        curve[column] = curve[column].map(lambda v: number(v, 4))
    si.append(table(curve[["population", "delivered", "rule", "retention_at_025", "retention_at_050", "retention_at_100", "aurc", "augrc"]], "E5 scores: retention at equal realised risk, AURC and AUGRC for each delivered value (D2* with calibrated intervals).", "tab:si_scores", "lllrrrrr", ["Population", "Value", "Score", "2.5\\%", "5\\%", "10\\%", "AURC", "AUGRC"], "\\tiny"))
    agree = agreement.loc[agreement.population.isin(["deploy", "mech"])].copy()
    agree["target_a"] = agree.target_a.map(TARGET_NAMES)
    agree["target_b"] = agree.target_b.map(TARGET_NAMES)
    for column in ("kappa_usable", "spearman_abs_error"):
        agree[column] = agree[column].map(lambda v: number(v, 2))
    for column in ("share_unusable_a_usable_b", "share_usable_a_unusable_b"):
        agree[column] = agree[column].map(lambda v: pct(v, 1))
    si.append(table(agree[["population", "target_a", "target_b", "kappa_usable", "spearman_abs_error", "share_unusable_a_usable_b", "share_usable_a_unusable_b"]], "E6 agreement of usability between targets for the plug-in value.", "tab:si_agreement", "lllrrrr", ["Population", "Target A", "Target B", "$\\kappa$", "Spearman", "A no, B yes (\\%)", "A yes, B no (\\%)"], "\\tiny"))
    loro = load(R1, "e7_transfer/loro_transfer.csv")
    loro = loro.loc[loro.score.eq("R7a_target_aware") & loro.method.isin(["marginal", "mondrian_layer", "weighted_mondrian"])].pivot_table(index=["population", "region", "n_groups"], columns="method", values="risk").reset_index()
    for column in ("marginal", "mondrian_layer", "weighted_mondrian"):
        loro[column] = loro[column].map(lambda v: pct(v, 1))
    loro["region"] = loro.region.str.replace("_", " ")
    si.append(table(loro, "E7 (first preregistration, P3) leave-one-region-out realised risk (\\%) of the fixed thresholds at nominal 5\\%: one threshold, one per information layer, and layer thresholds reweighted to the held-out region.", "tab:si_loro", "llrrrr", ["Population", "Region", "Groups", "Marginal", "Layer", "Weighted"], "\\tiny"))
    fz = frozen.copy()
    for column in ("retention", "risk", "risk_lower95", "risk_upper95", "unscreened_risk"):
        fz[column] = fz[column].map(lambda v: pct(v, 1))
    si.append(table(fz[["population", "score", "method", "n_cases", "n_groups", "retention", "risk", "risk_lower95", "risk_upper95", "unscreened_risk"]].assign(score=lambda f: f.score.str.replace("_", " "), method=lambda f: f.method.str.replace("_", " ")), "E7 first test (Australia): frozen thresholds, recomputed after the change of random seeds (Text~S6). Intervals resample the 55 hydrological networks.", "tab:si_sealed", "lllrrrrrrr", ["Population", "Score", "Threshold", "Cases", "Networks", "Used (\\%)", "Risk (\\%)", "Low", "High", "Unscreened (\\%)"], "\\tiny"))
    contrast = load(T.AU_ROUND1, "posthoc_domain_contrast.csv")
    for column in ("air_layer_share", "median_missing_fraction", "share_peak_overlap_half", "failure_P0", "failure_D2", "coverage90_D2"):
        contrast[column] = contrast[column].map(lambda v: pct(v, 1))
    for column in ("median_sigma_a", "median_sigma_r", "median_r2", "mean_error_P0"):
        contrast[column] = contrast[column].map(lambda v: number(v, 2))
    si.append(table(contrast[["domain", "family", "air_layer_share", "median_sigma_a", "median_sigma_r", "median_r2", "median_missing_fraction", "share_peak_overlap_half", "failure_P0", "failure_D2", "coverage90_D2"]], "Post hoc contrast between the source and Australia, written after the first evaluation in Australia (calendar years, May--September seasons).", "tab:si_posthoc", "llrrrrrrrrr", ["Domain", "Family", "Air (\\%)", "$\\sigma_a$", "$\\sigma_r$", "$R^2$", "Missing (\\%)", "Peak $\\geq$50\\% (\\%)", "Fail P0", "Fail D2*", "Cover90"], "\\tiny"))
    er = load(R2, "e7_transfer/expected_risk_development.csv")
    er = er[["population", "score", "region", "n_groups", "factor_k", "k1_risk", "risk", "retention", "unscreened_risk"]].copy()
    for column in ("k1_risk", "risk", "retention", "unscreened_risk"):
        er[column] = er[column].map(lambda v: pct(v, 1))
    er["factor_k"] = er.factor_k.map(lambda v: number(v, 2))
    er["region"] = er.region.str.replace("_", " ")
    au_rows = pd.DataFrame(au_dev["rule"])
    au_rows = au_rows.loc[au_rows.factor.eq("k")].assign(region="Australia (opened, post hoc)", n_groups=au_dev["n_networks"], k1_risk="--")
    au_rows = au_rows.rename(columns={"factor_value": "factor_k", "unscreened_risk_D2": "unscreened_risk"})[["population", "score", "region", "n_groups", "factor_k", "k1_risk", "risk", "retention", "unscreened_risk"]]
    for column in ("risk", "retention", "unscreened_risk"):
        au_rows[column] = au_rows[column].map(lambda v: pct(v, 1))
    au_rows["factor_k"] = au_rows.factor_k.map(lambda v: number(v, 2))
    si.append(table(pd.concat([er, au_rows], ignore_index=True), "Label-free expected-risk rule (M3), developed leave-one-region-out: admit cases by increasing score while $k$ times the mean predicted failure probability among admitted cases stays at or below 5\\%. The factor $k$ for each region is the 80th percentile of the realised-to-predicted ratio in the other regions. Risks refer to the D2* value. Australia, opened by the first test, is a development region scored with the frozen candidate models.", "tab:si_expected", "lllrrrrrr", ["Population", "Score", "Region", "Groups", "$k$", "Risk, $k$=1 (\\%)", "Risk (\\%)", "Used (\\%)", "Unscreened (\\%)"], "\\tiny"))
    e8full = load(R2, "e8_downstream/summary.csv")
    e8full["hot_missed"] = e8full.hot_missed_incomplete / e8full.hot_true_incomplete
    for column in ("slope_bias", "slope_rmse", "mean_h30_bias"):
        e8full[column] = e8full[column].map(lambda v: number(v, 4))
    for column in ("cover_missing_component", "detect_warming", "hot_missed"):
        e8full[column] = e8full[column].map(lambda v: pct(v, 1))
    e8full["mean_years"] = e8full.mean_years.map(lambda v: number(v, 1))
    si.append(table(e8full[["scenario", "pipeline", "mean_years", "slope_bias", "slope_rmse", "cover_missing_component", "detect_warming", "mean_h30_bias", "hot_missed"]].assign(scenario=lambda f: f.scenario.str.replace("_", " ")), f"E8 downstream pipelines on {p4['n_stations']} stations with at least 20 complete years (200 degradations each). Slopes in $^{{\\circ}}$C per decade relative to the complete record.", "tab:si_downstream", "llrrrrrrr", ["Scenario", "Pipeline", "Years", "Trend bias", "Trend RMSE", "Cover (\\%)", "Detect (\\%)", "Mean H30 bias", "Hot missed (\\%)"], "\\tiny"))
    use = load(R2, "e9_application/usable_station_years.csv")
    keep = ["provider", "n_incomplete_station_years", "target_aware_admitted", "R1_usgs_indicator_311d_24pm", "R1_wmo_11_5", "R2_oregon_jas_80pct", "R2_beaufort_julaug_complete"]
    use = use[keep].copy()
    for column in keep[2:]:
        use[column] = use[column].map(lambda v: pct(v, 0))
    use["provider"] = use.provider.str.replace("_", " ")
    si.append(table(use, "E9 real incomplete station-years: share admitted by the label-free rule (R7b, applied within each region) and by four published rules (no truth is available; this is an application).", "tab:si_application", "lrrrrrr", ["Provider", "Years", "Target-aware", "USGS 311 d", "WMO 11/5", "Peak months", "Two peak months"], "\\scriptsize"))
    abl = load(R2, "e11_ablation/score_ablation.csv")
    for column in ("retention_at_025", "retention_at_050", "retention_at_100"):
        abl[column] = abl[column].map(lambda v: pct(v, 1))
    for column in ("aurc", "brier"):
        abl[column] = abl[column].map(lambda v: number(v, 4))
    si.append(table(abl[["population", "score", "retention_at_025", "retention_at_050", "retention_at_100", "aurc", "brier"]].assign(score=lambda f: f.score.str.replace("_", " ")), "E11 score ablations for the plug-in failure, leave-one-region-out.", "tab:si_ablation", "llrrrrr", ["Population", "Score", "2.5\\%", "5\\%", "10\\%", "AURC", "Brier"], "\\scriptsize"))
    sens = load(R2, "e5_rules/tolerance_sensitivity.csv")
    sens = sens[["tolerance_c", "population", "unscreened_risk_P0", "unscreened_risk_Pobs", "unscreened_risk_D2*", "target_aware_retention_at_025", "best_fixed_rule_retention_at_025", "target_aware_retention_at_050", "best_fixed_rule_retention_at_050"]].copy()
    for column in sens.columns[2:]:
        sens[column] = sens[column].map(lambda v: pct(v, 1))
    sens["tolerance_c"] = sens.tolerance_c.map(lambda v: number(v, 2))
    si.append(table(sens, "Sensitivity to the tolerance (0.25, 0.5 and 1.0\\,$^{\\circ}$C): unscreened failure rates and retention at 2.5\\% and 5\\% realised risk of the target-aware judgment (D2* value) and of the best fixed published rule (recorded-day or plug-in value).", "tab:si_tolerance_sensitivity", "llrrrrrrr", ["Tolerance", "Population", "Fail P0", "Fail recorded", "Fail D2*", "Target 2.5\\%", "Rule 2.5\\%", "Target 5\\%", "Rule 5\\%"], "\\scriptsize"))
    shift = load(T.AU_ROUND1, "posthoc_conditional_shift.csv")
    shift["failure"] = shift.failure.map(lambda v: pct(v, 1))
    shift["mean_score"] = shift.mean_score.map(lambda v: number(v, 3))
    shift["n"] = shift.n.map(lambda v: number(v, 0))
    si.append(table(shift[["domain", "score", "n", "mean_score", "failure"]], "Post hoc conditional calibration of the target-aware score (D2* failure probability) under real gap calendars after the first test: observed failure rate by score bin in the source (frozen models, in-sample) and in Australia.", "tab:si_conditional_shift", "llrrr", ["Domain", "Score bin", "n", "Mean score", "Observed failure (\\%)"], "\\scriptsize"))

    # New table 1: what the corrected hemisphere and season definitions change.
    source_rows = definition.reset_index()
    source_rows["value"] = [number(v, 3) if v < 1 else number(v, 0) for v in source_rows.value]
    source_rows["of"] = source_rows["of"].map(lambda v: number(v, 0) if np.isfinite(v) else "")
    au_table = australia[["definition", "family", "n_cases", "share_h30_window_at_year_edge", "plug_in_failure", "plug_in_mean_error", "predicted_law_pfail_050", "predicted_law_v2p_pfail_050"]].copy()
    rows = [[q, v, o] for q, v, o in zip(source_rows.quantity, source_rows.value, source_rows["of"])]
    for r in au_table.itertuples(index=False):
        rows.append([f"Australia, {r.definition}, {r.family}: window at year edge / plug-in failure / mean error / law v2, v2p", f"{pct(r.share_h30_window_at_year_edge, 1)} / {pct(r.plug_in_failure, 1)} / {number(r.plug_in_mean_error, 3)}", f"{pct(r.predicted_law_pfail_050, 1)} / {pct(r.predicted_law_v2p_pfail_050, 1)}" if np.isfinite(r.predicted_law_pfail_050) else ""])
    si.append(table(pd.DataFrame(rows), "Corrected hemisphere and season definitions (M1). Source: round-1 and round-2 cases joined case by case. Australia: the round-1 test cases against the round-2 development cases (post hoc).", "tab:si_definitions", "p{0.62\\textwidth}p{0.18\\textwidth}p{0.12\\textwidth}", ["Quantity", "Value", "Of / law"], "\\scriptsize"))
    # New table 2: interval calibration by difficulty group.
    g = groups.loc[groups.population.eq("all")].pivot_table(index="group", columns="version", values=["coverage90", "width90"]).reset_index()
    g.columns = ["group", "coverage_calibrated", "coverage_raw", "width_calibrated", "width_raw"]
    counts = groups.loc[groups.population.eq("all") & groups.version.eq("calibrated")].set_index("group")[["n", "n_groups"]]
    g = g.join(counts, on="group")
    for column in ("coverage_raw", "coverage_calibrated"):
        g[column] = g[column].map(lambda v: pct(v, 1))
    for column in ("width_raw", "width_calibrated"):
        g[column] = g[column].map(lambda v: number(v, 2))
    g["n"] = g.n.map(lambda v: number(v, 0))
    g["group"] = g.group.str.replace("|", ", ", regex=False).str.replace("_", " ")
    si.append(table(g[["group", "n", "n_groups", "coverage_raw", "coverage_calibrated", "width_raw", "width_calibrated"]], "Split-conformal calibration of the D2* quantiles by decision-time difficulty group (share of the climatological peak window hidden: bin 0 = none, bins 1--4 = quarters; information layer), leave-one-region-out. Coverage and width of the 90\\% interval, all source cases.", "tab:si_conformal", "lrrrrrr", ["Group", "Cases", "Groups", "Cover raw (\\%)", "Cover calibrated (\\%)", "Width raw", "Width calibrated"], "\\scriptsize"))
    # New table 3: the USGS test.
    sealed_rows = load(R2, "e10_sealed_usgs/sealed_expected_risk.csv")
    st = sealed_rows[["population", "score", "factor", "n_cases", "n_groups", "retention", "risk", "risk_upper95", "unscreened_risk_D2", "risk_high_missingness", "risk_low_missingness"]].copy()
    for column in ("retention", "risk", "risk_upper95", "unscreened_risk_D2", "risk_high_missingness", "risk_low_missingness"):
        st[column] = st[column].map(lambda v: pct(v, 1))
    si.append(table(st, "Second test on new USGS stations (second preregistration, N1), recomputed after the change of random seeds (Text~S6). Admission by the label-free rule over all test cases of each population; R7b is primary, R7a and $k$=1 are secondary. Upper bounds resample independence groups; strata are fixed from availability metadata.", "tab:si_sealed_usgs", "lllrrrrrrrr", ["Population", "Score", "Factor", "Cases", "Groups", "Used (\\%)", "Risk (\\%)", "Upper (\\%)", "Unscreened (\\%)", "High missing (\\%)", "Low missing (\\%)"], "\\tiny"))
    # New table 4: decomposition of the downstream gain and the Baden-Wuerttemberg example.
    dec = load(R2, "e8_downstream/decomposition_summary.csv")
    rows = [[s.replace("_", " "), number(r.rmse_A1, 4), number(r.rmse_B, 4), number(r.rmse_C, 4), pct(r.share_of_gain_from_keeping_years, 0), f"{number(r.ratio_B_A1_median, 2)} [{number(r.ratio_B_A1_q25, 2)}, {number(r.ratio_B_A1_q75, 2)}]", f"{number(r.ratio_C_B_median, 2)} [{number(r.ratio_C_B_q25, 2)}, {number(r.ratio_C_B_q75, 2)}]"] for s, r in zip(dec.scenario, dec.itertuples(index=False))]
    for r in regional.reset_index().itertuples(index=False):
        rows.append([f"Baden-W\\\"urttemberg, {r.years}, {r.pipeline}", number(r.regional_trend, 2), f"[{number(r.lower95, 2)}, {number(r.upper95, 2)}]", "", "", "", ""])
    si.append(table(pd.DataFrame(rows), "Where the downstream gain comes from (M5). Upper rows: station H30 trend RMSE ($^{\\circ}$C per decade) for the 90\\% rule (A1), the plug-in with all years (B) and multiple imputation (C), the share of the A1-to-C gain obtained by keeping years (A1 to B), and station-level RMSE ratios (median and quartiles). Lower rows: regional mean H30 trend of the same 19 Baden-W\\\"urttemberg stations with a 95\\% interval over independence groups (real incomplete years, no truth).", "tab:si_decomposition", "lrrrrrr", ["Scenario or region", "A1", "B", "C", "From keeping years", "B/A1", "C/B"], "\\scriptsize"))
    # New table 5: the 7-day minimum flow.
    fm = flow_metrics.reset_index()
    fm = fm.loc[fm.stratum.isin(["all", "low-flow window at least half hidden", "half hidden, neighbour layer", "half hidden, interpolation layer"])].copy()
    fm["bias"] = fm.bias_log.map(lambda v: pct(np.exp(v) - 1, 1))
    fm["mae_log"] = fm.mae_log.map(lambda v: number(v, 3))
    fm["failure_rate"] = fm.failure_rate.map(lambda v: pct(v, 1))
    fm["coverage90"] = fm.coverage90.map(lambda v: pct(v, 1) if np.isfinite(v) else "--")
    fm["n"] = fm.n.map(lambda v: number(v, 0))
    si.append(table(fm[["population", "stratum", "estimator", "n", "bias", "mae_log", "failure_rate", "coverage90"]], f"S1: annual 7-day minimum flow on {macros['TFlowSites']} perennial USGS streams (climatic years April--March). Bias is the geometric-mean relative error, $\\exp(\\overline{{\\log \\hat Q - \\log Q}}) - 1$; failure means a log error beyond {macros['TFlowTol']}\\%. Trend RMSE of log 7Q per decade: skip incomplete years {macros['TFlowTrendAZero']}, plug-in {macros['TFlowTrendB']}, multiple imputation {macros['TFlowTrendC']}.", "tab:si_flow", "lllrrrrr", ["Population", "Stratum", "Estimator", "n", "Bias (\\%)", "MAE (log)", "Failure (\\%)", "Cover90 (\\%)"], "\\tiny"))
    (PAPER / "tr_si_tables.tex").write_text("\n".join(si))
    print(f"[463] {len(macros)} macros, {len(main)} main tables, {len(si)} SI tables", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
