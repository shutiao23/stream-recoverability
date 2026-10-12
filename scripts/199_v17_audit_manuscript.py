#!/usr/bin/env python3
"""Audit every table in the manuscript against the artifact it claims to quote.

The machine-readable block covers ten headline numbers. The prose carries about
a hundred and seventy more, hand-transcribed, and this session has twice caught
a stale one. This re-derives each table cell from the artifacts and reports any
disagreement, so that the check is a test rather than a proofread.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import RESULTS_ROOT  # noqa: E402

MANUSCRIPT = ROOT / "paper_archived" / "v17" / "manuscript.md"
AUDIT = RESULTS_ROOT / "manuscript_audit.json"
TOL = 0.06  # a quoted figure may be rounded; anything further apart is an error


def rows_of(section: str, text: str) -> list[list[str]]:
    """Markdown table rows inside the section whose heading contains ``section``."""

    pattern = re.compile(rf"#+ .*{re.escape(section)}.*?\n(.*?)(?=\n#+ |\Z)", re.S)
    match = pattern.search(text)
    if not match:
        return []
    out = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        out.append([cell.strip().replace("**", "") for cell in line.strip("|").split("|")])
    return out[1:] if out else []


def number(cell: str) -> float | None:
    cleaned = cell.replace(",", "").replace("°C", "").replace("%", "").replace("−", "-").replace("+", "")
    cleaned = re.sub(r"\(.*?\)", "", cleaned).strip()
    match = re.search(r"-?\d+\.?\d*", cleaned)
    return float(match.group()) if match else None


def main() -> int:
    text = MANUSCRIPT.read_text(encoding="utf-8")
    findings: list[dict] = []

    def check(label: str, quoted, actual, scale: float = 1.0, tol: float = TOL) -> None:
        if quoted is None or actual is None:
            findings.append({"item": label, "status": "unparsed", "quoted": quoted, "actual": actual})
            return
        ok = abs(float(quoted) - float(actual) * scale) <= tol
        findings.append(
            {
                "item": label,
                "status": "ok" if ok else "MISMATCH",
                "quoted": round(float(quoted), 4),
                "expected": round(float(actual) * scale, 4),
            }
        )

    # -- gate table --------------------------------------------------------
    gate = json.loads((RESULTS_ROOT / "step4_ceiling" / "gate.json").read_text())
    gate_rows = rows_of("4.7 Action-space screening", text)
    if len(gate_rows) >= 3:
        check("gate/adopt_reject ceiling", number(gate_rows[0][1]), gate["adopt_reject"]["ceiling_c"], tol=0.001)
        check("gate/method ceiling", number(gate_rows[1][1]), gate["method_selection"]["ceiling_c"], tol=0.001)
        check("gate/retain ceiling (points)", number(gate_rows[2][1]), gate["retain_exclude"]["ceiling_rate"], 100, 0.1)
        check("gate/required C", number(gate_rows[0][2]), gate["adopt_reject"]["required_c"], tol=0.001)
        check("gate/required points", number(gate_rows[2][2]), gate["retain_exclude"]["required_rate"], 100, 0.1)

    # -- axis by metric ----------------------------------------------------
    generality = pd.read_csv(RESULTS_ROOT / "step17_metric_generality" / "metric_generality.csv").set_index("metric")
    metric_rows = rows_of("5.2 RQ1", text)
    keys = {
        "hottest 7": "hottest7", "hottest 30": "hottest30", "amplitude": "amplitude30",
        "annual mean": "annual_mean", "coldest": "coldest30",
    }
    for row in metric_rows:
        if len(row) < 5:  # the mechanism-gradient table in the same section
            continue
        key = next((v for k, v in keys.items() if k in row[0]), None)
        if key is None:
            continue
        check(f"metric/{key} peak overlap", number(row[1]), generality.loc[key, "auc_peak_overlap"], tol=0.002)
        check(f"metric/{key} warm coverage", number(row[2]), generality.loc[key, "auc_warm_coverage"], tol=0.002)
        check(f"metric/{key} length", number(row[3]), generality.loc[key, "auc_longest_run"], tol=0.002)
        expected = "timing" if max(
            generality.loc[key, "auc_peak_overlap"], generality.loc[key, "auc_warm_coverage"]
        ) > generality.loc[key, "auc_longest_run"] else "length"
        findings.append(
            {
                "item": f"metric/{key} winner",
                "status": "ok" if expected in row[-1] else "MISMATCH",
                "quoted": row[-1],
                "expected": expected,
            }
        )

    auc_ci = pd.read_csv(RESULTS_ROOT / "step22_robustness" / "auc_contrasts.csv").set_index("metric")
    for row in rows_of("5.2 RQ1", text):
        if len(row) < 6:
            continue
        key = next((v for k, v in keys.items() if k in row[0]), None)
        if key is None or key not in auc_ci.index:
            continue
        cell = row[4].replace("−", "-").replace("+", "")
        parts = re.findall(r"-?\d+\.\d+", cell)
        if len(parts) == 3:
            check(f"auc_ci/{key} point", float(parts[0]), auc_ci.loc[key, "auc_timing_minus_length"], tol=0.002)
            lo, hi = sorted([float(parts[1]), float(parts[2])])
            check(f"auc_ci/{key} low", lo, min(auc_ci.loc[key, "ci_low"], auc_ci.loc[key, "ci_high"]), tol=0.002)
            check(f"auc_ci/{key} high", hi, max(auc_ci.loc[key, "ci_low"], auc_ci.loc[key, "ci_high"]), tol=0.002)

    # -- tolerance table on the reserved panel -----------------------------
    tolerance = pd.read_csv(RESULTS_ROOT / "step14_paper_tables" / "tolerance_frontier.csv")
    reserved = tolerance.loc[tolerance["panel"].eq("reserved")].set_index("screen")
    names = {"outage-length": "length_rule", "peak-overlap": "peak_overlap_rule", "certificate": "certificate", "random": "random"}
    for row in rows_of("5.4 RQ3", text):
        key = next((v for k, v in names.items() if row[0].startswith(k)), None)
        if key is None or len(row) < 5:
            continue
        check(f"tolerance/{key} >0.25", number(row[1]), reserved.loc[key, "rate_above_0.25"], 100, 0.1)
        check(f"tolerance/{key} >0.5", number(row[2]), reserved.loc[key, "rate_above_0.5"], 100, 0.1)
        check(f"tolerance/{key} >1.0", number(row[3]), reserved.loc[key, "rate_above_1.0"], 100, 0.1)
        check(f"tolerance/{key} severe", number(row[4]), reserved.loc[key, "severe_underestimate_rate"], 100, 0.1)

    # -- arm decomposition -------------------------------------------------
    arms = pd.read_csv(RESULTS_ROOT / "step11_arm_robustness" / "arm_contrasts.csv").set_index(["panel", "arm"])
    for row in rows_of("5.7 RQ5", text):
        if len(row) < 7 or row[1] not in {"empirical", "stratified"}:
            continue
        key = (row[0], row[1])
        check(f"arm/{key} cases", number(row[2]), arms.loc[key, "n_cases"], tol=1)
        check(f"arm/{key} base rate", number(row[3]), arms.loc[key, "base_rate_retain_all"], 100, 0.1)
        check(f"arm/{key} length@70", number(row[4]), arms.loc[key, "length_rule_at_70"], 100, 0.02)
        check(f"arm/{key} certificate@70", number(row[5]), arms.loc[key, "certificate_at_70"], 100, 0.02)
        check(f"arm/{key} contrast", number(row[6]), arms.loc[key, "contrast_points"], tol=0.02)

    # -- ablations ---------------------------------------------------------
    ablations = pd.read_csv(RESULTS_ROOT / "step12_ablations" / "ablations.csv")
    lookup = {
        "outage-length rule (incumbent)": "outage-length rule (incumbent)",
        "three-variable logistic regression": "three-variable logistic screen",
        "peak-overlap alone, no fitting at all": "peak-overlap rule",
        "three-feature gradient boosting": "three_features",
        "geometry and timing only (8 features)": "geometry_and_timing_only",
        "drop donor features": "drop_donor_features",
        "drop the observed-peak margin": "drop_observed_peak_margin",
        "full certificate": "full",
        "full certificate, screening only (no method choice)": "full (screen only)",
    }
    indexed = ablations.set_index("variant")
    for row in rows_of("5.6 RQ4", text):
        name = lookup.get(row[0])
        if name is None or name not in indexed.index or len(row) < 3:
            continue
        check(f"ablation/{name} rate", number(row[1]), indexed.loc[name, "rate_above_0.5_at_70"], 100, 0.02)
        if number(row[2]) is not None:
            check(f"ablation/{name} points", number(row[2]), indexed.loc[name, "points_vs_incumbent"], tol=0.02)

    # -- baseline strength -------------------------------------------------
    baseline = pd.read_csv(RESULTS_ROOT / "step15_baseline_strength" / "baseline_strength.csv")
    res = baseline.loc[baseline["panel"].eq("reserved")]
    for row in rows_of("5.5 RQ3b", text):
        if len(row) < 3:
            continue
        hit = res.loc[res["reconstruction"].str.contains(row[1].split("(")[0].strip()[:18], case=False, regex=False)]
        if hit.empty:
            continue
        check(f"baseline/{row[1][:28]}", number(row[2]), hit["rate_above_0.5_at_70"].iloc[0], 100, 0.02)

    # -- calibration dial --------------------------------------------------
    cluster = json.loads((RESULTS_ROOT / "step18_cluster_conformal" / "summary.json").read_text())["variants"]
    dial = {"pooled": "pooled", "cluster, 0.7 level": "cluster_0.7", "cluster, 0.9 level": "cluster_0.9"}
    for row in rows_of("5.8 RQ6", text):
        key = dial.get(row[0])
        if key is None or len(row) < 6:
            continue
        check(f"calibration/{key} marginal", number(row[1]), cluster[key]["marginal_coverage"], tol=0.002)
        check(f"calibration/{key} minimum", number(row[2]), cluster[key]["per_network"]["min"], tol=0.002)
        check(f"calibration/{key} below 0.85", number(row[3]), cluster[key]["per_network"]["share_below_0.85"], 100, 0.1)
        check(f"calibration/{key} width", number(row[4]), cluster[key]["median_interval_width_c"], tol=0.02)
        check(f"calibration/{key} rate", number(row[5]), cluster[key]["rate_above_tolerance_at_70"], 100, 0.02)

    # -- inline prose claims, the ones a table check cannot see ------------
    lopo = pd.read_csv(RESULTS_ROOT / "step10_confirmation" / "leave_one_provider_out.csv")
    span = re.search(r"ranging from\s*\n?−([\d.]+) points \(\w+\) to −([\d.]+)", text)
    if span:
        check("inline/LOPO best", float(span.group(1)), -lopo["contrast_points"].min(), tol=0.1)
        check("inline/LOPO worst", float(span.group(2)), -lopo["contrast_points"].max(), tol=0.1)
    findings.append(
        {
            "item": "inline/LOPO all intervals exclude zero",
            "status": "ok" if bool((lopo["ci_high_points"] < 0).all()) else "MISMATCH",
            "quoted": "all nine agencies",
            "expected": int((lopo["ci_high_points"] < 0).sum()),
        }
    )

    coverage = pd.read_csv(RESULTS_ROOT / "step10_confirmation" / "coverage.csv")
    overlap = coverage.loc[coverage["stratum"].str.startswith("peak_overlap")]
    widths = re.search(r"adapt from ([\d.]+) °C when the\n?peak window is untouched to ([\d.]+) °C", text)
    if widths:
        check("inline/width at zero overlap", float(widths.group(1)), overlap["median_width_c"].min(), tol=0.01)
        check("inline/width at full overlap", float(widths.group(2)), overlap["median_width_c"].max(), tol=0.01)

    # -- round-4 tables ----------------------------------------------------
    gradients = pd.read_csv(RESULTS_ROOT / "step20_round4" / "mechanism_gradients.csv")
    ratios = gradients.loc[gradients["missing_quartile"].eq("RATIO Q4/Q1")].set_index("metric")
    overlap_ratios = gradients.loc[gradients["peak_overlap"].str.startswith("RATIO")].set_index("metric")
    for row in rows_of("5.2 RQ1", text):
        if len(row) != 3 or "error ratio" in row[1]:
            continue
        key = "hottest30" if "hottest" in row[0] else ("annual_mean" if "annual mean" in row[0] else None)
        if key is None:
            continue
        check(f"gradient/{key} missing axis", number(row[1]), ratios.loc[key, "mean_abs_error_c"], tol=0.06)
        check(f"gradient/{key} overlap axis", number(row[2]), overlap_ratios.loc[key, "mean_abs_error_c"], tol=0.06)

    amplitude = json.loads((RESULTS_ROOT / "step20_round4" / "amplitude_screen.json").read_text())
    amp = re.search(r"gives ([\d.]+)% against the\n?length rule's ([\d.]+)% at 70% retention, a saving of ([\d.]+)\n?points", text)
    if amp:
        check("amplitude/reserved certificate", float(amp.group(1)), amplitude["reserved"]["certificate_at_70"], 100, 0.06)
        check("amplitude/reserved length", float(amp.group(2)), amplitude["reserved"]["length_rule_at_70"], 100, 0.06)
        check("amplitude/reserved saving", float(amp.group(3)), amplitude["reserved"]["points_saved"], tol=0.06)

    close = pd.read_csv(RESULTS_ROOT / "step20_round4" / "near_threshold.csv")
    close_map = {
        "all retained": "all retained",
        "truth within 1.0 °C of 20 °C": "truth within 1.0 °C of 20",
        "truth within 0.5 °C of 20 °C": "truth within 0.5 °C of 20",
    }
    treatments = ["observed_days_all", "reconstruct_all", "length_screened", "certificate_screened"]
    for row in rows_of("5.9 RQ7", text):
        subset = close_map.get(row[0])
        if subset is None or len(row) < 5:
            continue
        block = close.loc[close["subset"].eq(subset)].set_index("treatment")
        for offset, treatment in enumerate(treatments, start=1):
            check(
                f"near-threshold/{subset}/{treatment}",
                number(row[offset]),
                block.loc[treatment, "misclassification_rate"],
                100,
                0.06,
            )

    abstain = pd.read_csv(RESULTS_ROOT / "step20_round4" / "abstain_versus_screen.csv").set_index("policy")
    abstain_map = {
        "screen at the 0.5 °C tolerance": "screen at the 0.5 °C tolerance",
        "abstain where the interval straddles 20 °C": "abstain only where the interval straddles 20 °C",
        "both": "both",
    }
    for row in rows_of("5.9 RQ7", text):
        key = abstain_map.get(row[0])
        if key is None or len(row) != 4:
            continue
        check(f"abstain/{key} judged", number(row[1]), abstain.loc[key, "share_of_years_judged"], 100, 0.06)
        check(f"abstain/{key} misclassification", number(row[2]), abstain.loc[key, "misclassification_rate"], 100, 0.06)
        check(f"abstain/{key} missed", number(row[3]), abstain.loc[key, "false_negative_rate"], 100, 0.06)

    # -- load-bearing inline claims outside the tables ---------------------
    practice = pd.read_csv(RESULTS_ROOT / "step4_ceiling" / "estimator_tolerances.csv").set_index("estimator")
    m = re.search(r"mean\s*\n?absolute error of \*\*([\d.]+) °C, or ([\d.]+) interannual", text)
    if m:
        check("inline/observed-days error", float(m.group(1)), practice.loc["observed_days", "mean_abs_error_c"], tol=0.005)
        check("inline/observed-days in SD", float(m.group(2)), practice.loc["observed_days", "mean_error_in_natural_sd"], tol=0.01)

    verdict = json.loads((RESULTS_ROOT / "step10_confirmation" / "verdict.json").read_text())
    m = re.search(r"\*\*−([\d.]+) points, 95% network-clustered interval\s*\n?−([\d.]+) to −([\d.]+)\*\*", text)
    if m:
        check("inline/confirmation point", -float(m.group(1)), verdict["primary"]["contrast_points"], tol=0.01)
        check("inline/confirmation ci low", -float(m.group(2)), verdict["primary"]["ci_points"][0], tol=0.01)
        check("inline/confirmation ci high", -float(m.group(3)), verdict["primary"]["ci_points"][1], tol=0.01)

    simple = pd.read_csv(RESULTS_ROOT / "step16_simple_rule" / "simple_rule_scores.csv")
    row = simple.loc[simple["panel"].eq("reserved") & simple["screen"].str.startswith("contrast")].iloc[0]
    m = re.search(r"\*\*−([\d.]+) points \(−([\d.]+), −([\d.]+)\)\*\*, and cuts severe", text)
    if m:
        check("inline/simple rule point", -float(m.group(1)), row["rate_above_0.5_at_70"], tol=0.01)
        check("inline/simple rule ci low", -float(m.group(2)), row["mean_abs_error_at_70"], tol=0.01)
        check("inline/simple rule ci high", -float(m.group(3)), row["severe_underestimate_at_70"], tol=0.01)

    noise = json.loads((RESULTS_ROOT / "step22_robustness" / "noise_sensitivity.json").read_text())
    m = re.search(r"development contrast from ([\d.]+) to ([\d.]+) points and the reserved contrast from\s*\n?([\d.]+) to ([\d.]+) points", text)
    if m:
        check("inline/noise dev clean", float(m.group(1)), noise["development"]["contrast_clean_points"], tol=0.02)
        check("inline/noise dev noisy", float(m.group(2)), noise["development"]["contrast_noisy_points"], tol=0.02)
        check("inline/noise res clean", float(m.group(3)), noise["reserved"]["contrast_clean_points"], tol=0.02)
        check("inline/noise res noisy", float(m.group(4)), noise["reserved"]["contrast_noisy_points"], tol=0.02)

    prior = pd.read_csv(RESULTS_ROOT / "step13_prior_years" / "protocol_comparison.csv")
    strict = prior.loc[prior["protocol"].str.startswith("strictly")].iloc[0]
    m = re.search(r"\*\*−([\d.]+) points \(−([\d.]+), −([\d.]+)\)\*\*, with coverage (\d+\.\d+)", text)
    if m:
        check("inline/prior-years point", -float(m.group(1)), strict["contrast_points"], tol=0.02)
        check("inline/prior-years coverage", float(m.group(4)), strict["coverage"], tol=0.002)

    sweep = pd.read_csv(RESULTS_ROOT / "step22_robustness" / "threshold_sweep.csv")
    cert = sweep.loc[sweep["treatment"].eq("certificate_screened"), "misclassification_rate"]
    length_rule = sweep.loc[sweep["treatment"].eq("length_screened"), "misclassification_rate"]
    m = re.search(r"stays between ([\d.]+)% and ([\d.]+)% while\s*\n?the length rule stays between ([\d.]+)% and ([\d.]+)%", text)
    if m:
        check("inline/sweep cert min", float(m.group(1)), cert.min(), 100, 0.02)
        check("inline/sweep cert max", float(m.group(2)), cert.max(), 100, 0.02)
        check("inline/sweep length min", float(m.group(3)), length_rule.min(), 100, 0.02)
        check("inline/sweep length max", float(m.group(4)), length_rule.max(), 100, 0.02)

    hydro = pd.read_csv(RESULTS_ROOT / "step21_hydrology" / "correlations.csv")
    hy_verdict = json.loads((RESULTS_ROOT / "step21_hydrology" / "verdict.json").read_text())
    def rho(predictor: str, target: str, field: str) -> float:
        hit = hydro.loc[hydro["predictor"].eq(predictor) & hydro["target"].eq(target)]
        return float(hit[field].iloc[0]) if not hit.empty else float("nan")

    m = re.search(r"ρ = \*\*−([\d.]+)\*\*, 95% CI −([\d.]+) to\s*\n?−([\d.]+), and ρ = \*\*−([\d.]+)\*\*", text)
    if m:
        check("inline/elevation rho", -float(m.group(1)), rho("ELEV_SITE_M", "donor_synchrony", "spearman_rho"), tol=0.006)
        check("inline/slope rho", -float(m.group(4)), rho("SLOPE_PCT", "donor_synchrony", "spearman_rho"), tol=0.006)
    m = re.search(r"\*\*−([\d.]+) °C\*\* easier than low-baseflow stations \(95% CI −([\d.]+) to −([\d.]+)\)", text)
    if m:
        check("inline/bfi error difference", -float(m.group(1)),
              hy_verdict["johnson_groundwater_test"]["difference_high_minus_low_bfi_c"], tol=0.002)
    m = re.search(r"to 18\.1 °C \(ρ = \*\*−([\d.]+)\*\*, −([\d.]+) to −([\d.]+)\)", text)
    if m:
        check("inline/bfi peak magnitude rho", -float(m.group(1)), rho("BFI_AVE", "peak_magnitude_c", "spearman_rho"), tol=0.006)

    mismatches = [f for f in findings if f["status"] != "ok"]
    AUDIT.write_text(
        json.dumps({"n_checked": len(findings), "findings": findings}, indent=2, default=float),
        encoding="utf-8",
    )
    print(f"checked {len(findings)} table cells against artifacts")
    if mismatches:
        print(f"\n{len(mismatches)} DISAGREEMENTS:")
        for item in mismatches:
            print(" ", item)
        return 1
    print("every table cell in the manuscript matches its artifact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
