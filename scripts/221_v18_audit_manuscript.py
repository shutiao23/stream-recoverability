#!/usr/bin/env python3
"""Audit every v18 number in the manuscript against the artifact behind it.

Proofreading is not a control. The v17 programme found four wrong numbers in
its own prose after three careful readings, which is why the check is a script
that the test suite runs rather than a habit. Every value this file asserts is
recomputed from a file under `results/`, never from another sentence.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    E1_SEASONALITY,
    E2_DEPLOYMENT,
    E3_SINE,
    E4_REPRESENTATIVENESS,
    E5_AIR,
    E6_SUPPORT,
    E7_MISSINGNESS,
    RESULTS_ROOT,
    TOLERANCE_FRACTION,
)

MANUSCRIPT = ROOT / "paper_archived" / "v18" / "manuscript.md"
V17_NUMBERS = ROOT / "results" / "v17_fitness" / "paper_numbers.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def headline_block() -> dict:
    text = MANUSCRIPT.read_text(encoding="utf-8")
    match = re.search(r"<!-- numbers:start -->\s*```json\s*(\{.*?\})\s*```", text, re.S)
    if match is None:
        raise SystemExit("manuscript has no machine-readable numbers block")
    return json.loads(match.group(1))


def expected_values() -> dict[str, float]:
    """Every headline number, recomputed from its artifact."""

    v17 = load_json(V17_NUMBERS)
    e1 = load_json(E1_SEASONALITY / "summary.json")
    e2 = load_json(E2_DEPLOYMENT / "summary.json")
    e5 = load_json(E5_AIR / "summary.json")
    e6 = load_json(E6_SUPPORT / "summary.json")

    thresholds = pd.read_csv(E2_DEPLOYMENT / "threshold_disagreement.csv")
    unfilled = thresholds.iloc[0]
    consequence = pd.read_csv(E2_DEPLOYMENT / "archive_consequence.csv").set_index("rule")
    calendars = pd.read_csv(E1_SEASONALITY / "maintenance_calendars.csv").set_index("calendar")
    support = pd.read_csv(E5_AIR / "estimator_support.csv")
    frontier = pd.read_csv(E4_REPRESENTATIVENESS / "representativeness_frontier.csv")

    development = frontier.loc[
        (frontier["split"] == "development") & (frontier["retention_target"] == 0.70)
    ].set_index("rule")
    balancing = float(
        development.loc["calibrated screen, balanced within donor_and_elevation", "error_rate_pct"]
        - development.loc["calibrated screen, global threshold", "error_rate_pct"]
    )

    return {
        "networks": v17["panel"]["networks"],
        "stations": v17["panel"]["stations"],
        "complete_station_years": v17["panel"]["station_years"],
        "incomplete_station_years": e2["n_incomplete"],
        "cases": v17["cases"]["total"],
        "development_cases": v17["cases"]["development"],
        "reserved_cases": v17["cases"]["reserved"],
        "reserved_networks": v17["panel"]["reserved_networks"],
        "crossover_support_width_days": e6["P2_crossover"]["crossover_width_days"],
        "certificate_at_70_reserved": v17["frontier_at_70"]["reserved"]["certificate"],
        "length_rule_at_70_reserved": v17["frontier_at_70"]["reserved"]["length_rule"],
        "confirmation_contrast_points": v17["confirmation"]["primary"]["contrast_points"],
        "marginal_coverage": v17["confirmation"]["coverage"]["marginal"],
        "archive_disagreement_pct": float(unfilled["disagreement_pct"]),
        "archive_admitted_by_length_rejected_by_timing": int(
            unfilled["admitted_by_length_rejected_by_timing"]
        ),
        "archive_wholly_hidden_peak_admitted_at_140d": int(
            consequence.loc[
                "Johnson with imputation (<= 140 d)", "admitted_with_peak_window_wholly_hidden"
            ]
        ),
        "spring_calendar_penalty_points": float(calendars.loc["spring_mar_to_jul", "points_vs_observed"]),
        "autumn_calendar_saving_points": -float(calendars.loc["autumn_sep_to_jan", "points_vs_observed"]),
        "air_support_development_pct": float(
            support.loc[
                (support["split"] == "development") & (support["forcing"] == "v18 forcing"),
                "air_available_pct",
            ].iloc[0]
        ),
        "balancing_price_points": balancing,
    }


PROSE_CHECKS: list[tuple[str, str, float, float]] = []


def prose_expectations() -> list[dict]:
    """Inline claims in the prose, each with the artifact that settles it."""

    e1 = load_json(E1_SEASONALITY / "summary.json")
    e2 = load_json(E2_DEPLOYMENT / "summary.json")
    e6 = load_json(E6_SUPPORT / "summary.json")

    by_class = pd.read_csv(E1_SEASONALITY / "start_month_by_length_class.csv").set_index("length_class")
    thresholds = pd.read_csv(E2_DEPLOYMENT / "threshold_disagreement.csv")
    transported = pd.read_csv(E2_DEPLOYMENT / "transported_risk.csv").set_index("rule")
    consequence = pd.read_csv(E2_DEPLOYMENT / "archive_consequence.csv").set_index("rule")
    sine = pd.read_csv(E3_SINE / "sine_axis_comparison.csv")
    sine_all = sine
    sine = sine_all.loc[
        (sine_all["protocol"] == "repaired")
        & (sine_all["tolerance_fraction"].sub(TOLERANCE_FRACTION).abs() < 1e-6)
    ].set_index("endpoint")
    sine_observed = sine_all.loc[
        (sine_all["protocol"] == "observed_days_only")
        & (sine_all["tolerance_fraction"].sub(TOLERANCE_FRACTION).abs() < 1e-6)
    ].set_index("endpoint")
    sweep = pd.read_csv(E6_SUPPORT / "support_width_sweep.csv")
    sweep = sweep.loc[
        (sweep["split"] == "development")
        & (sweep["tolerance_fraction"].sub(TOLERANCE_FRACTION).abs() < 1e-6)
    ].set_index("support_width_days")
    matrix = pd.read_csv(E6_SUPPORT / "conditioning_width_matrix.csv").set_index("endpoint_width_days")
    elevation = pd.read_csv(E4_REPRESENTATIVENESS / "elevation_retention.csv")
    reserved_elevation = elevation.loc[elevation["split"] == "reserved"].set_index("rule")
    frontier = pd.read_csv(E4_REPRESENTATIVENESS / "representativeness_frontier.csv")
    reserved70 = frontier.loc[
        (frontier["split"] == "reserved") & (frontier["retention_target"] == 0.70)
    ].set_index("rule")
    fairness = pd.read_csv(E5_AIR / "fairness_with_air.csv")
    sizes = pd.read_csv(E5_AIR / "problem_size.csv")
    stability = pd.read_csv(E5_AIR / "axis_stability.csv").set_index("forcing")
    v17 = load_json(V17_NUMBERS)
    v17_incumbent = pd.DataFrame(v17["incumbent"]["reserved"]).set_index("rule")
    generality = pd.DataFrame(v17["metric_generality"]).set_index("metric")
    ablations = pd.DataFrame(v17["ablations"])
    arms = pd.DataFrame(v17["arm_robustness"])
    weighting = pd.DataFrame(v17["weighting"])
    near_threshold = pd.read_csv(
        ROOT / "results" / "v17_fitness" / "step20_round4" / "near_threshold.csv"
    )
    abstain = pd.read_csv(
        ROOT / "results" / "v17_fitness" / "step20_round4" / "abstain_versus_screen.csv"
    ).set_index("policy")
    tolerance_table = pd.read_csv(
        ROOT / "results" / "v17_fitness" / "step10_confirmation" / "frontiers.csv"
    )
    tolerance_table = tolerance_table.loc[tolerance_table["retention"].sub(0.70).abs() < 1e-9].set_index("screen")

    return [
        # -- §5.2 Table 1, carried from v17 and re-checked here rather than trusted
        {"claim": "Table 1, hottest7 peak overlap", "value": 0.823,
         "actual": float(generality.loc["hottest7", "auc_peak_overlap"]), "tol": 0.001},
        {"claim": "Table 1, hottest30 peak overlap", "value": 0.819,
         "actual": float(generality.loc["hottest30", "auc_peak_overlap"]), "tol": 0.001},
        {"claim": "Table 1, hottest30 longest run", "value": 0.750,
         "actual": float(generality.loc["hottest30", "auc_longest_run"]), "tol": 0.001},
        {"claim": "Table 1, annual mean longest run", "value": 0.845,
         "actual": float(generality.loc["annual_mean", "auc_longest_run"]), "tol": 0.001},
        {"claim": "Table 1, coldest30 peak overlap", "value": 0.447,
         "actual": float(generality.loc["coldest30", "auc_peak_overlap"]), "tol": 0.001},
        {"claim": "Table 1, amplitude warm coverage", "value": 0.792,
         "actual": float(generality.loc["amplitude30", "auc_warm_coverage"]), "tol": 0.001},
        # -- §5.6 Table 5, reserved panel across tolerances
        {"claim": "Table 5, length rule above 0.5", "value": 0.097,
         "actual": float(tolerance_table.loc["length_rule", "rate_above_0.5"]), "tol": 0.001},
        {"claim": "Table 5, screen above 0.5", "value": 0.025,
         "actual": float(tolerance_table.loc["certificate", "rate_above_0.5"]), "tol": 0.001},
        {"claim": "Table 5, screen above 1.0", "value": 0.004,
         "actual": float(tolerance_table.loc["certificate", "rate_above_1.0"]), "tol": 0.001},
        {"claim": "Table 5, length rule severe underestimate", "value": 0.020,
         "actual": float(tolerance_table.loc["length_rule", "severe_underestimate_rate"]), "tol": 0.001},
        # -- §5.8 Table 7, the ablation
        {"claim": "Table 7, three-variable logistic", "value": 0.0553,
         "actual": float(
             ablations.loc[ablations["variant"] == "three-variable logistic screen", "rate_above_0.5_at_70"].iloc[0]
         ), "tol": 0.0005},
        {"claim": "Table 7, full screen", "value": 0.0293,
         "actual": float(
             ablations.loc[
                 (ablations["variant"] == "full") & (ablations["kind"] == "certificate"),
                 "rate_above_0.5_at_70",
             ].iloc[0]
         ), "tol": 0.0005},
        # -- §5.9 Table 8, the arms
        {"claim": "Table 8, reserved empirical contrast", "value": -0.71,
         "actual": float(
             arms.loc[(arms["panel"] == "reserved") & (arms["arm"] == "empirical"), "contrast_points"].iloc[0]
         ), "tol": 0.01},
        {"claim": "Table 8, reserved stratified contrast", "value": -8.68,
         "actual": float(
             arms.loc[(arms["panel"] == "reserved") & (arms["arm"] == "stratified"), "contrast_points"].iloc[0]
         ), "tol": 0.01},
        # -- §5.6 weighting
        {"claim": "reserved network-equal weighting", "value": -5.82,
         "actual": float(
             weighting.loc[
                 (weighting["panel"] == "reserved") & (weighting["weighting"] == "network-equal"), "point"
             ].iloc[0]
         ), "tol": 0.02},
        {"claim": "reserved provider-equal weighting", "value": -6.29,
         "actual": float(
             weighting.loc[
                 (weighting["panel"] == "reserved") & (weighting["weighting"] == "provider-equal"), "point"
             ].iloc[0]
         ), "tol": 0.02},
        # -- §5.11 Tables 10 and 11
        {"claim": "Table 10, screened within 0.5 C of the threshold", "value": 0.0338,
         "actual": float(
             near_threshold.loc[
                 (near_threshold["subset"] == "truth within 0.5 °C of 20")
                 & (near_threshold["treatment"] == "certificate_screened"),
                 "misclassification_rate",
             ].iloc[0]
         ), "tol": 0.0005},
        {"claim": "Table 10, length-screened within 0.5 C", "value": 0.1024,
         "actual": float(
             near_threshold.loc[
                 (near_threshold["subset"] == "truth within 0.5 °C of 20")
                 & (near_threshold["treatment"] == "length_screened"),
                 "misclassification_rate",
             ].iloc[0]
         ), "tol": 0.0005},
        {"claim": "Table 11, abstention judges", "value": 0.927,
         "actual": float(
             abstain.loc["abstain only where the interval straddles 20 °C", "share_of_years_judged"]
         ), "tol": 0.001},
        {"claim": "Table 11, both", "value": 0.00084,
         "actual": float(abstain.loc["both", "misclassification_rate"]), "tol": 0.0002},
        # -- §5.2 the continuum
        {"claim": "fixed peak window advantage at k=1", "value": 0.074,
         "actual": float(sweep.loc[1, "fixed_peak_window_minus_missing_fraction"]), "tol": 0.001},
        {"claim": "fixed peak window advantage at k=365", "value": -0.173,
         "actual": float(sweep.loc[365, "fixed_peak_window_minus_missing_fraction"]), "tol": 0.001},
        {"claim": "crossover width days", "value": 91.0,
         "actual": float(e6["P2_crossover"]["crossover_width_days"]), "tol": 0.5},
        # -- §5.3 the dilation
        {"claim": "gain from widening at k=1", "value": 0.102,
         "actual": float(matrix.loc[1, "gain_from_widening"]), "tol": 0.001},
        {"claim": "support location wander at k=1 (days)", "value": 16.7,
         "actual": float(matrix.loc[1, "median_support_location_sd_days"]), "tol": 0.1},
        {"claim": "support location wander at k=90 (days)", "value": 7.4,
         "actual": float(matrix.loc[90, "median_support_location_sd_days"]), "tol": 0.1},
        {"claim": "AUC on own support at k=30", "value": 0.827,
         "actual": float(matrix.loc[30, "auc_at_own_support"]), "tol": 0.001},
        {"claim": "AUC at best conditioning window, k=30", "value": 0.852,
         "actual": float(matrix.loc[30, "auc_at_best"]), "tol": 0.001},
        # -- §5.4 the sine endpoints
        {"claim": "sine mean, peak overlap AUC", "value": 0.672,
         "actual": float(sine.loc["sine_mean", "auc_peak_overlap"]), "tol": 0.001},
        {"claim": "sine mean, missing fraction AUC", "value": 0.845,
         "actual": float(sine.loc["sine_mean", "auc_missing_fraction"]), "tol": 0.001},
        {"claim": "sine phase, peak overlap AUC", "value": 0.583,
         "actual": float(sine.loc["sine_phase", "auc_peak_overlap"]), "tol": 0.001},
        {"claim": "sine phase, influence-weighted AUC", "value": 0.847,
         "actual": float(sine.loc["sine_phase", "auc_influence_hidden"]), "tol": 0.001},
        {"claim": "sine amplitude, influence-weighted AUC", "value": 0.831,
         "actual": float(sine.loc["sine_amplitude", "auc_influence_hidden"]), "tol": 0.001},
        # -- §5.6 the corrected operating point
        {"claim": "reserved retention at the 140 d limit", "value": 0.851,
         "actual": float(v17_incumbent.loc["length <= 140 d (Johnson, with imputation)", "retention"]),
         "tol": 0.002},
        {"claim": "length rule rate at the 140 d limit", "value": 0.113,
         "actual": float(v17_incumbent.loc["length <= 140 d (Johnson, with imputation)", "rate_above_0.5"]),
         "tol": 0.001},
        {"claim": "screen rate at equal retention, 140 d limit", "value": 0.069,
         "actual": float(
             v17_incumbent.loc[
                 "length <= 140 d (Johnson, with imputation)",
                 "certificate_rate_above_0.5_at_equal_retention",
             ]
         ), "tol": 0.001},
        # -- §5.7 air forcing
        {"claim": "length rule with an always-air reconstruction", "value": 15.16,
         "actual": float(
             fairness.loc[
                 fairness["reconstruction"].str.startswith("always air"), "rate_above_0.5_pct"
             ].iloc[0]
         ), "tol": 0.02},
        {"claim": "length rule with the information-conditioned policy", "value": 9.00,
         "actual": float(
             fairness.loc[
                 fairness["reconstruction"].eq("information-conditioned policy"), "rate_above_0.5_pct"
             ].iloc[0]
         ), "tol": 0.02},
        {"claim": "screen with air available", "value": 2.87,
         "actual": float(
             fairness.loc[fairness["screen"].eq("calibrated screen"), "rate_above_0.5_pct"].iloc[0]
         ), "tol": 0.02},
        {"claim": "policy MAE with air forcing", "value": 0.225,
         "actual": float(
             sizes.loc[(sizes["forcing"] == "v18 forcing") & (sizes["donor_regime"] == "all"), "policy_mae_c"].iloc[0]
         ), "tol": 0.001},
        {"claim": "oracle MAE with air forcing", "value": 0.130,
         "actual": float(
             sizes.loc[(sizes["forcing"] == "v18 forcing") & (sizes["donor_regime"] == "all"), "oracle_mae_c"].iloc[0]
         ), "tol": 0.001},
        {"claim": "donorless policy MAE, old forcing", "value": 0.340,
         "actual": float(
             sizes.loc[(sizes["forcing"] == "v17 forcing") & (sizes["donor_regime"] == "none"), "policy_mae_c"].iloc[0]
         ), "tol": 0.001},
        {"claim": "donorless policy MAE, new forcing", "value": 0.364,
         "actual": float(
             sizes.loc[(sizes["forcing"] == "v18 forcing") & (sizes["donor_regime"] == "none"), "policy_mae_c"].iloc[0]
         ), "tol": 0.001},
        {"claim": "timing minus length AUC, old forcing", "value": 0.070,
         "actual": float(stability.loc["v17 forcing", "timing_minus_length"]), "tol": 0.001},
        {"claim": "timing minus length AUC, new forcing", "value": 0.081,
         "actual": float(stability.loc["v18 forcing", "timing_minus_length"]), "tol": 0.001},
        # -- §5.9 seasonality
        {"claim": "share of 90 d+ gaps starting Sep-Jan", "value": 0.723,
         "actual": float(by_class.loc["90 d and longer", "share_protected_sep_to_jan"]), "tol": 0.001},
        {"claim": "share of 90 d+ gaps starting Mar-Jul", "value": 0.179,
         "actual": float(by_class.loc["90 d and longer", "share_exposed_mar_to_jul"]), "tol": 0.001},
        {"claim": "chi2 uniformity, 90 d+ gaps", "value": 86.1,
         "actual": float(by_class.loc["90 d and longer", "chi2_uniformity"]), "tol": 0.1},
        {"claim": "chi2 uniformity, 30-89 d gaps", "value": 4.0,
         "actual": float(by_class.loc["30-89 d", "chi2_uniformity"]), "tol": 0.1},
        {"claim": "number of real interior gaps", "value": 6472,
         "actual": float(e1["n_gaps"]), "tol": 0.5},
        # -- §5.10 deployment
        {"claim": "incomplete station-years", "value": 2422,
         "actual": float(e2["n_incomplete"]), "tol": 0.5},
        {"claim": "disagreement at the unfilled limit", "value": 15.1,
         "actual": float(thresholds.iloc[0]["disagreement_pct"]), "tol": 0.05},
        {"claim": "disagreement at the imputed limit", "value": 11.6,
         "actual": float(thresholds.iloc[1]["disagreement_pct"]), "tol": 0.05},
        {"claim": "share of incomplete years with a peak day hidden", "value": 28.7,
         "actual": float(e2["disagreement"]["any_peak_day_hidden_pct"]), "tol": 0.05},
        {"claim": "wholly hidden peaks admitted at 140 d", "value": 17,
         "actual": float(consequence.loc["Johnson with imputation (<= 140 d)", "admitted_with_peak_window_wholly_hidden"]),
         "tol": 0.5},
        {"claim": "wholly hidden peaks admitted at 49 d", "value": 2,
         "actual": float(consequence.loc["Johnson unfilled (<= 49 d)", "admitted_with_peak_window_wholly_hidden"]),
         "tol": 0.5},
        {"claim": "transported risk, peak-window rule", "value": 0.26,
         "actual": float(transported.loc["peak window <= 10% hidden", "predicted_consequential_rate_pct"]),
         "tol": 0.01},
        {"claim": "transported risk, unfilled limit", "value": 0.98,
         "actual": float(transported.loc["Johnson unfilled (<= 49 d)", "predicted_consequential_rate_pct"]),
         "tol": 0.01},
        # -- §5.12 representativeness
        {"claim": "reserved high-tertile retention, global screen", "value": 0.669,
         "actual": float(reserved_elevation.loc["calibrated screen, global threshold", "retention_high"]),
         "tol": 0.001},
        {"claim": "reserved low-tertile retention, global screen", "value": 0.777,
         "actual": float(reserved_elevation.loc["calibrated screen, global threshold", "retention_low"]),
         "tol": 0.001},
        {"claim": "reserved screen error rate, global", "value": 2.53,
         "actual": float(reserved70.loc["calibrated screen, global threshold", "error_rate_pct"]), "tol": 0.02},
        {"claim": "reserved screen error rate, balanced within both", "value": 2.84,
         "actual": float(
             reserved70.loc["calibrated screen, balanced within donor_and_elevation", "error_rate_pct"]
         ), "tol": 0.02},
        # -- §5.13 informative missingness
        {"claim": "pre-gap anomaly, 90 d and longer", "value": -0.215,
         "actual": float(
             pd.read_csv(E7_MISSINGNESS / "flank_anomalies.csv")
             .set_index("length_class")
             .loc["90 d and longer", "pre_anomaly_c"]
         ), "tol": 0.002},
        {"claim": "pre-gap anomaly, gaps of a week or less", "value": 0.018,
         "actual": float(
             pd.read_csv(E7_MISSINGNESS / "flank_anomalies.csv")
             .set_index("length_class")
             .loc["1-7 d", "pre_anomaly_c"]
         ), "tol": 0.002},
        {"claim": "90th percentile of missing days, incomplete years", "value": 127.9,
         "actual": float(e2["disagreement"]["p90_missing_days"]), "tol": 0.1},
        {"claim": "smallest provider disagreement", "value": 11.1,
         "actual": float(
             pd.read_csv(E2_DEPLOYMENT / "disagreement_by_provider.csv")["disagreement_pct"].min()
         ), "tol": 0.05},
        {"claim": "largest provider disagreement", "value": 25.7,
         "actual": float(
             pd.read_csv(E2_DEPLOYMENT / "disagreement_by_provider.csv")["disagreement_pct"].max()
         ), "tol": 0.05},
        {"claim": "error gradient along missing days, annual mean", "value": 10.2,
         "actual": float(
             pd.read_csv(ROOT / "results" / "v17_fitness" / "step20_round4" / "mechanism_gradients.csv")
             .query("metric == 'annual_mean' and missing_quartile == 'RATIO Q4/Q1'")["mean_abs_error_c"]
             .iloc[0]
         ), "tol": 0.05},
        {"claim": "error gradient along peak overlap, hottest30", "value": 9.6,
         "actual": float(
             pd.read_csv(ROOT / "results" / "v17_fitness" / "step20_round4" / "mechanism_gradients.csv")
             .query("metric == 'hottest30' and missing_quartile == 'averaged'")["mean_abs_error_c"]
             .iloc[0]
         ), "tol": 0.05},
        {"claim": "sine mean AUC, observed-days protocol, peak overlap", "value": 0.667,
         "actual": float(sine_observed.loc["sine_mean", "auc_peak_overlap"]), "tol": 0.001},
        {"claim": "sine phase AUC, observed-days protocol, missing fraction", "value": 0.898,
         "actual": float(sine_observed.loc["sine_phase", "auc_missing_fraction"]), "tol": 0.001},
        {"claim": "donor anomaly through short gaps", "value": 0.063,
         "actual": float(
             pd.read_csv(E7_MISSINGNESS / "donor_anomaly_test.csv")
             .set_index("length_class")
             .loc["1-7 d", "donor_anomaly_difference_c"]
         ), "tol": 0.002},
    ]


def main() -> int:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    failures: list[dict] = []
    checks = 0

    stated = headline_block()
    expected = expected_values()
    for key, value in expected.items():
        checks += 1
        if key not in stated:
            failures.append({"check": f"headline:{key}", "reason": "missing from the manuscript block"})
            continue
        tolerance = 0.5 if float(value) > 100 else max(abs(float(value)) * 5e-3, 5e-3)
        if abs(float(stated[key]) - float(value)) > tolerance:
            failures.append(
                {"check": f"headline:{key}", "stated": stated[key], "artifact": value}
            )

    for item in prose_expectations():
        checks += 1
        if abs(float(item["actual"]) - float(item["value"])) > float(item["tol"]):
            failures.append(
                {"check": f"prose:{item['claim']}", "stated": item["value"], "artifact": item["actual"]}
            )

    report = {
        "checks": checks,
        "failures": failures,
        "passed": not failures,
    }
    (RESULTS_ROOT / "manuscript_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if failures:
        for failure in failures:
            print("FAIL", failure)
        print(f"\n{len(failures)} of {checks} checks failed")
        return 1
    print(f"{checks} checks, all passing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
