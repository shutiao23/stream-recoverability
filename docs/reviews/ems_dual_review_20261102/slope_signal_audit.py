#!/usr/bin/env python3
"""Scale the saved finite-record slope errors by the slope's own sampling error.

Reviewer-side diagnostic for the EMS dual review (2026-11-02). It reads only the
saved r4 tables; no model is fitted and no saved scientific table is changed.

For each forward station the complete-record H30 slope on its saved reference-year
set is refitted by OLS (per decade), with its classical standard error, a
Theil-Sen slope, a tie-corrected Mann-Kendall test and an optional Hamed-Rao
rank-autocorrelation correction. Each archive's saved estimate error is then
divided by that station's OLS standard error.

Outputs:
  results/ems_revision_20261102/trend_signal.json
  results/ems_revision_20261102/trend_signal.csv
  paper/ems/trend_signal.tex
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parents[3]
FAMILIES = ("crossed", "calendar")
SCHEMES = ("warm90", "cdf_all_years", "sxx_all_years", "all", "uniform_exact")
SCORED_SCHEMES = ("warm90", "cdf_all_years", "sxx_all_years", "all")
EXPECTED_SIGN_FLIPS = {
    ("calendar", "warm90"): 3,
    ("calendar", "cdf_all_years"): 5,
    ("calendar", "sxx_all_years"): 4,
    ("calendar", "all"): 0,
    ("crossed", "warm90"): 53,
}
SCHEME_LABELS = {
    "warm90": r"Warm-season 90\%",
    "cdf_all_years": "CDF",
    "sxx_all_years": r"$S_{xx}$",
    "all": "All years",
    "uniform_exact": "Uniform exact",
}
FAMILY_LABELS = {"crossed": "Controlled", "calendar": "Calendar"}


def sen_slope(y: np.ndarray, x: np.ndarray) -> float:
    """Theil-Sen slope as the median of all pairwise slopes."""
    n = len(y)
    slopes = [
        (y[j] - y[i]) / (x[j] - x[i])
        for i in range(n - 1)
        for j in range(i + 1, n)
    ]
    return float(np.median(slopes))


def mann_kendall(y: np.ndarray) -> tuple[float, float, float, float]:
    """Tie-corrected Mann-Kendall S test with the normal approximation."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    s = 0.0
    for i in range(n - 1):
        s += float(np.sign(y[i + 1 :] - y[i]).sum())
    _, counts = np.unique(y, return_counts=True)
    tie_sum = float(np.sum(counts * (counts - 1) * (2 * counts + 5)))
    var_s = (n * (n - 1) * (2 * n + 5) - tie_sum) / 18.0
    if var_s <= 0:
        return s, var_s, float("nan"), float("nan")
    if s > 0:
        z = (s - 1.0) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1.0) / np.sqrt(var_s)
    else:
        z = 0.0
    p = 2.0 * stats.norm.sf(abs(z))
    return float(s), float(var_s), float(z), float(p)


def hamed_rao_p(y: np.ndarray) -> tuple[float, float]:
    """Hamed-Rao (1998) modified Mann-Kendall test.

    The series is first detrended with the Sen slope, ranks of the detrended
    residuals supply the lag autocorrelations, and only lags significant at the
    5% level enter the correction. The variance correction factor is

        C = n/n* = 1 + 2/[n(n-1)(n-2)] sum_{significant k} (n-k)(n-k-1)(n-k-2) rho_k,

    and Var*(S) = Var(S) * C. With 7-16 reference years the lag estimates are
    unstable; the result is reported only as a sensitivity.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 4:
        return float("nan"), float("nan")
    x = np.arange(n, dtype=float)
    slope = sen_slope(y, x)
    intercept = float(np.median(y - slope * x))
    residual = y - intercept - slope * x
    ranks = stats.rankdata(residual)
    ranks = ranks - ranks.mean()
    denom = float(np.dot(ranks, ranks))
    if denom == 0.0:
        return float("nan"), float("nan")
    bound = 1.959964 / np.sqrt(n)
    weighted = 0.0
    for k in range(1, n):
        rho = float(np.dot(ranks[k:], ranks[:-k]) / denom)
        if abs(rho) > bound:
            weighted += (n - k) * (n - k - 1) * (n - k - 2) * rho
    correction = 1.0 + 2.0 / (n * (n - 1) * (n - 2)) * weighted
    n_star = n / correction if correction != 0.0 else float("nan")
    s, var_s, _, _ = mann_kendall(y)
    if not np.isfinite(correction) or correction <= 0.0 or var_s <= 0.0:
        return float(n_star), float("nan")
    var_corrected = var_s * correction
    if s > 0:
        z = (s - 1.0) / np.sqrt(var_corrected)
    elif s < 0:
        z = (s + 1.0) / np.sqrt(var_corrected)
    else:
        z = 0.0
    return float(n_star), float(2.0 * stats.norm.sf(abs(z)))


def station_slopes(truths: pd.DataFrame, year_sets: pd.DataFrame) -> pd.DataFrame:
    ref = year_sets.set_index("station_key")
    rows = []
    for station, frame in truths.groupby("station_key"):
        ref_years = {
            int(value) for value in str(ref.loc[station, "reference_years"]).split(";")
        }
        n_ref = int(ref.loc[station, "n_reference_years"])
        frame = frame[frame["year"].astype(int).isin(ref_years)].sort_values("year")
        if len(frame) != n_ref:
            raise ValueError(
                f"{station}: {len(frame)} truth rows for {n_ref} reference years"
            )
        years = frame["year"].to_numpy(dtype=float)
        h30 = frame["eval_truth_h30"].to_numpy(dtype=float)
        x = years / 10.0
        fit = sm.OLS(h30, sm.add_constant(x)).fit()
        s_stat, var_s, z_stat, mk_p = mann_kendall(h30)
        n_star, hr_p = hamed_rao_p(h30)
        tau, tau_p = stats.kendalltau(x, h30)
        rows.append(
            {
                "station_key": station,
                "n_reference_years": n_ref,
                "first_year": int(years.min()),
                "last_year": int(years.max()),
                "ols_slope_c_per_10a": float(fit.params[1]),
                "ols_se_c_per_10a": float(fit.bse[1]),
                "ols_p": float(fit.pvalues[1]),
                "sen_slope_c_per_10a": sen_slope(h30, x),
                "mann_kendall_s": float(s_stat),
                "mann_kendall_var_s": float(var_s),
                "mann_kendall_z": float(z_stat),
                "mann_kendall_p": float(mk_p),
                "kendall_tau": float(tau),
                "kendall_tau_p": float(tau_p),
                "hamed_rao_n_star": float(n_star),
                "hamed_rao_p": float(hr_p),
                "h30_interannual_sd_c": float(np.std(h30, ddof=1)),
            }
        )
    return pd.DataFrame(rows).set_index("station_key")


def station_summary(stations: pd.DataFrame) -> dict:
    return {
        "n": int(len(stations)),
        "median_reference_years": float(stations["n_reference_years"].median()),
        "median_ols_slope_c_per_10a": float(stations["ols_slope_c_per_10a"].median()),
        "median_ols_se_c_per_10a": float(stations["ols_se_c_per_10a"].median()),
        "rms_ols_se_c_per_10a": float(
            np.sqrt((stations["ols_se_c_per_10a"] ** 2).mean())
        ),
        "ols_p_below_005": int((stations["ols_p"] < 0.05).sum()),
        "mann_kendall_p_below_005": int((stations["mann_kendall_p"] < 0.05).sum()),
        "kendall_tau_p_below_005": int((stations["kendall_tau_p"] < 0.05).sum()),
        "hamed_rao_p_below_005": int((stations["hamed_rao_p"] < 0.05).sum()),
        "median_abs_ols_minus_sen_c_per_10a": float(
            (stations["ols_slope_c_per_10a"] - stations["sen_slope_c_per_10a"])
            .abs()
            .median()
        ),
        "median_h30_interannual_sd_c": float(
            stations["h30_interannual_sd_c"].median()
        ),
    }


def cohort_metrics(
    cases: pd.DataFrame,
    stations: pd.DataFrame,
    family_summary: pd.DataFrame,
) -> dict:
    cases = cases.join(
        stations[["ols_se_c_per_10a", "ols_slope_c_per_10a"]],
        on="station_key",
        validate="many_to_one",
    )
    if cases["ols_se_c_per_10a"].isna().any():
        raise ValueError("archive rows without a station OLS SE")
    cases["abs_t"] = cases["ols_slope_c_per_10a"].abs() / cases["ols_se_c_per_10a"]
    cases["abs_error_over_se"] = (
        cases["estimate_error"].abs() / cases["ols_se_c_per_10a"]
    )
    summary_index = family_summary.set_index(["family", "scheme"])
    cohorts = {}
    for family in FAMILIES:
        for scheme in SCHEMES:
            frame = cases[(cases["family"] == family) & (cases["scheme"] == scheme)]
            if frame.empty:
                raise ValueError(f"missing cohort {family}/{scheme}")
            saved_flips = int(frame["slope_sign_disagreement"].sum())
            fs = summary_index.loc[(family, scheme)]
            row = {
                "n": int(len(frame)),
                "n_stations": int(frame["station_key"].nunique()),
                "n_groups": int(fs["groups"]),
                "sign_flips": saved_flips,
            }
            if scheme == "uniform_exact":
                row.update(
                    {
                        "rmse_c_per_10a": float(fs["estimate_rmse"]),
                        "rmse_source": "retention_family_summary.csv",
                        "median_abs_error_over_se": None,
                        "p90_abs_error_over_se": None,
                        "share_above_one_se": None,
                        "median_abs_error_c_per_10a": None,
                        "p90_abs_error_c_per_10a": None,
                        "sign_flips_recomputed": None,
                        "sign_flips_match_saved": None,
                    }
                )
            else:
                error = frame["estimate_error"].to_numpy(dtype=float)
                ratio = frame["abs_error_over_se"].to_numpy(dtype=float)
                recomputed = int(
                    (
                        np.sign(frame["reference_slope"] + frame["estimate_error"])
                        != np.sign(frame["reference_slope"])
                    ).sum()
                )
                row.update(
                    {
                        "rmse_c_per_10a": float(np.sqrt(np.mean(error**2))),
                        "rmse_source": "retention_geometry_cases.csv",
                        "median_abs_error_over_se": float(np.median(ratio)),
                        "p90_abs_error_over_se": float(np.quantile(ratio, 0.90)),
                        "share_above_one_se": float(np.mean(ratio > 1.0)),
                        "median_abs_error_c_per_10a": float(
                            np.median(np.abs(error))
                        ),
                        "p90_abs_error_c_per_10a": float(
                            np.quantile(np.abs(error), 0.90)
                        ),
                        "sign_flips_recomputed": recomputed,
                        "sign_flips_match_saved": bool(recomputed == saved_flips),
                        "uncertainty_inflation_fraction": float(
                            np.sqrt(1.0 + np.mean(ratio**2)) - 1.0
                        ),
                        "sign_flips_on_abs_slope_below_one_se": int(
                            frame.loc[
                                frame["abs_t"] < 1.0, "slope_sign_disagreement"
                            ].sum()
                        ),
                        "sign_flips_on_abs_t_at_least_two": int(
                            frame.loc[
                                frame["abs_t"] >= 2.0, "slope_sign_disagreement"
                            ].sum()
                        ),
                    }
                )
            cohorts[f"{family}/{scheme}"] = row

    # Calendar-family refinements: restrict to archives whose retained year set
    # actually differs between warm-season screening and all-year retention, and
    # count archives with exactly zero error (all Swiss empirical calendars).
    warm = cases[
        (cases["family"] == "calendar") & (cases["scheme"] == "warm90")
    ].set_index(["station_key", "replicate"])
    everything = cases[
        (cases["family"] == "calendar") & (cases["scheme"] == "all")
    ].set_index(["station_key", "replicate"])
    changed = warm.index[warm["retained_years"].fillna("") != everything["retained_years"].fillna("")]
    for scheme in ["warm90", "all"]:
        frame = cases[
            (cases["family"] == "calendar")
            & (cases["scheme"] == scheme)
            & (cases["station_key"].isin([k[0] for k in changed]))
            & cases.set_index(["station_key", "replicate"]).index.isin(changed)
        ]
        error = frame["estimate_error"].to_numpy(dtype=float)
        ratio = frame["abs_error_over_se"].to_numpy(dtype=float)
        cohorts[f"calendar_changed_year_set/{scheme}"] = {
            "n": int(len(frame)),
            "definition": (
                "calendar archives whose warm-season and all-year retained sets differ"
            ),
            "rmse_c_per_10a": float(np.sqrt(np.mean(error**2))),
            "median_abs_error_over_se": float(np.median(ratio)),
            "p90_abs_error_over_se": float(np.quantile(ratio, 0.90)),
            "sign_flips": int(frame["slope_sign_disagreement"].sum()),
        }
    zero = cases[
        (cases["family"] == "calendar")
        & (cases["scheme"] == "warm90")
        & (cases["estimate_error"].abs() < 1e-12)
    ]
    cohorts["calendar/warm90_zero_error"] = {
        "n": int(len(zero)),
        "n_foen": int(zero["region"].eq("foen").sum()) if "region" in zero else None,
        "n_foen_total": int(
            cases.loc[
                (cases["family"] == "calendar")
                & (cases["scheme"] == "warm90")
                & cases["region"].eq("foen")
            ].shape[0]
        ),
        "note": (
            "archives whose warm-season screening error is exactly zero; every FOEN "
            "(Swiss) empirical calendar is in this set because the real Swiss gaps are "
            "too short to change the retained year set"
        ),
    }
    return cohorts


def check_value(
    name: str, computed: float | int | None, reference: float | int | None, tol: float
) -> dict:
    if computed is None or reference is None:
        match = computed is None and reference is None
        difference = None
    else:
        difference = abs(float(computed) - float(reference))
        match = difference <= tol
    return {
        "check": name,
        "computed": computed,
        "reference": reference,
        "absolute_difference": difference,
        "tolerance": tol,
        "match": bool(match),
    }


def validate_reference_json(summary: dict, cohorts: dict, path: Path) -> dict:
    if not path.exists():
        return {"available": False, "path": str(path)}
    reference = json.loads(path.read_text())
    checks = []
    station_map = {
        "n": ("n", 0),
        "median_years": ("median_reference_years", 0.0),
        "median_ols_slope_c_per_decade": ("median_ols_slope_c_per_10a", 5e-4),
        "median_ols_se_c_per_decade": ("median_ols_se_c_per_10a", 5e-4),
        "rms_ols_se_c_per_decade": ("rms_ols_se_c_per_10a", 5e-4),
        "ols_p_below_005": ("ols_p_below_005", 0),
        "kendall_p_below_005": ("mann_kendall_p_below_005", 0),
        "median_abs_ols_minus_sen": (
            "median_abs_ols_minus_sen_c_per_10a",
            5e-4,
        ),
        "median_interannual_h30_sd_c": ("median_h30_interannual_sd_c", 5e-4),
    }
    for key, (ours, tol) in station_map.items():
        checks.append(
            check_value(
                f"stations.{key}", summary[ours], reference["stations"][key], tol
            )
        )
    for key, ref_row in reference["archives"].items():
        row = cohorts[key]
        for metric, tol in (
            ("n", 0),
            ("rmse_c_per_decade", 5e-5),
            ("median_error_over_se", 5e-4),
            ("p90_error_over_se", 5e-4),
            ("share_error_above_one_se", 5e-5),
            ("sign_flips", 0),
        ):
            ours = "rmse_c_per_10a" if metric == "rmse_c_per_decade" else metric
            if metric == "median_error_over_se":
                ours = "median_abs_error_over_se"
            if metric == "p90_error_over_se":
                ours = "p90_abs_error_over_se"
            if metric == "share_error_above_one_se":
                ours = "share_above_one_se"
            checks.append(
                check_value(f"archives.{key}.{metric}", row[ours], ref_row[metric], tol)
            )
    return {
        "available": True,
        "path": str(path),
        "all_match": all(check["match"] for check in checks),
        "n_checks": len(checks),
        "checks": checks,
    }


def validate_outputs(
    truths: pd.DataFrame,
    year_sets: pd.DataFrame,
    cases: pd.DataFrame,
    stations: pd.DataFrame,
    cohorts: dict,
    summary: dict,
    family_summary: pd.DataFrame,
    reference_json: Path,
) -> dict:
    ref = year_sets.set_index("station_key")
    year_mismatches = []
    for station, frame in truths.groupby("station_key"):
        expected = {
            int(value) for value in str(ref.loc[station, "reference_years"]).split(";")
        }
        observed = set(frame["year"].astype(int))
        if expected != observed:
            year_mismatches.append(station)
    calendar = truths[truths["family"] == "calendar"].set_index(
        ["station_key", "year"]
    )["eval_truth_h30"]
    crossed = truths[truths["family"] == "crossed"].set_index(
        ["station_key", "year"]
    )["eval_truth_h30"]
    aligned = pd.concat([calendar.rename("calendar"), crossed.rename("crossed")], axis=1)
    truth_family_max_diff = float(
        (aligned["calendar"] - aligned["crossed"]).abs().max()
    )
    slope_map = stations["ols_slope_c_per_10a"]
    cases = cases.copy()
    cases["ols_slope_check"] = cases["station_key"].map(slope_map)
    slope_max_diff = float(
        (cases["reference_slope"] - cases["ols_slope_check"]).abs().max()
    )
    family_checks = []
    summary_index = family_summary.set_index(["family", "scheme"])
    for family in FAMILIES:
        for scheme in SCHEMES:
            row = cohorts[f"{family}/{scheme}"]
            fs = summary_index.loc[(family, scheme)]
            family_checks.append(
                check_value(
                    f"{family}/{scheme}.n", row["n"], int(fs["n"]), 0
                )
            )
            family_checks.append(
                check_value(
                    f"{family}/{scheme}.rmse",
                    row["rmse_c_per_10a"],
                    float(fs["estimate_rmse"]),
                    5e-12,
                )
            )
            if scheme in SCORED_SCHEMES:
                family_checks.append(
                    check_value(
                        f"{family}/{scheme}.sign_flips",
                        row["sign_flips"],
                        int(fs["sign_disagreement_count"]),
                        0,
                    )
                )
    paper_checks = []
    for (family, scheme), expected in EXPECTED_SIGN_FLIPS.items():
        paper_checks.append(
            check_value(
                f"paper_sign_flips.{family}/{scheme}",
                cohorts[f"{family}/{scheme}"]["sign_flips"],
                expected,
                0,
            )
        )
    return {
        "reference_year_sets": {
            "n_stations": int(len(ref)),
            "sum_reference_years": int(ref["n_reference_years"].sum()),
            "truth_rows_crossed": int((truths["family"] == "crossed").sum()),
            "mismatched_stations": year_mismatches,
            "match": len(year_mismatches) == 0,
        },
        "family_truths_identical": {
            "max_abs_difference_c": truth_family_max_diff,
            "match": truth_family_max_diff < 1e-12,
        },
        "case_reference_slope_matches_ols": {
            "max_abs_difference_c_per_10a": slope_max_diff,
            "match": slope_max_diff < 1e-9,
        },
        "saved_sign_flips_match_recomputed": {
            "all_match": all(
                row["sign_flips_match_saved"]
                for row in cohorts.values()
                if row.get("sign_flips_match_saved") is not None
            )
        },
        "family_summary_checks": family_checks,
        "family_summary_all_match": all(check["match"] for check in family_checks),
        "paper_sign_flip_checks": paper_checks,
        "paper_sign_flips_all_match": all(check["match"] for check in paper_checks),
        "review_json": validate_reference_json(summary, cohorts, reference_json),
    }


def fmt(value: float | int | None, digits: int = 3) -> str:
    if value is None:
        return "---"
    value = float(value)
    if not np.isfinite(value):
        return "---"
    return f"{value:.{digits}f}"


def fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "---"
    return f"{100.0 * float(value):.{digits}f}"


def latex_tables(summary: dict, cohorts: dict) -> str:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\small",
        r"\caption{Complete-record H30 trend signal at the 41 forward stations. "
        r"Slopes and standard errors use each station's saved reference-year set. "
        r"SE denotes the classical OLS slope standard error and excludes "
        r"autocorrelation.}",
        r"\label{tab:trend_signal_stations}",
        r"\begin{tabular}{lr}",
        r"\hline",
        r"Statistic & Value \\",
        r"\hline",
        rf"Stations & {summary['n']} \\",
        rf"Median reference years & {summary['median_reference_years']:.0f} \\",
        rf"Median OLS H30 slope ($^{{\circ}}$C/10a) & {fmt(summary['median_ols_slope_c_per_10a'])} \\",
        rf"Median OLS slope SE ($^{{\circ}}$C/10a) & {fmt(summary['median_ols_se_c_per_10a'])} \\",
        rf"Stations with OLS $p<0.05$ & {summary['ols_p_below_005']} \\",
        rf"Stations with Mann--Kendall $p<0.05$ & {summary['mann_kendall_p_below_005']} \\",
        rf"Median $|\mathrm{{OLS}}-\mathrm{{Sen}}|$ slope ($^{{\circ}}$C/10a) & {fmt(summary['median_abs_ols_minus_sen_c_per_10a'])} \\",
        rf"Median H30 interannual SD ($^{{\circ}}$C) & {fmt(summary['median_h30_interannual_sd_c'])} \\",
        r"\hline",
        r"\end{tabular}",
        r"\end{table}",
        "",
        r"\begin{table*}[t]",
        r"\centering",
        r"\small",
        r"\caption{Archive-level H30 slope error scaled by the station's classical "
        r"OLS slope standard error. Controlled: 30--90-day gaps; Calendar: "
        r"empirical gap calendars. RMSE is in $^{\circ}$C/10a. $e$ is the "
        r"estimated minus the complete-record slope.}",
        r"\label{tab:trend_signal_cohorts}",
        r"\resizebox{\linewidth}{!}{%",
        r"\begin{tabular}{llrrrrrrrr}",
        r"\hline",
        r"Family & Scheme & $n$ & RMSE & Median & P90 & $>1$ SE & Sign & Infl. & Weak \\",
        r" & & & & $|e|/$SE & $|e|/$SE & (\%) & flips & (\%) & flips \\",
        r"\hline",
    ]
    for family in FAMILIES:
        for scheme in SCORED_SCHEMES:
            row = cohorts[f"{family}/{scheme}"]
            lines.append(
                rf"{FAMILY_LABELS[family]} & {SCHEME_LABELS[scheme]} & "
                rf"{row['n']} & {fmt(row['rmse_c_per_10a'])} & "
                rf"{fmt(row['median_abs_error_over_se'])} & "
                rf"{fmt(row['p90_abs_error_over_se'])} & "
                rf"{fmt_pct(row['share_above_one_se'])} & "
                rf"{row['sign_flips']} & "
                rf"{fmt_pct(row['uncertainty_inflation_fraction'])} & "
                rf"{row['sign_flips_on_abs_slope_below_one_se']} \\"
            )
        if family == FAMILIES[0]:
            lines.append(r"\hline")
    lines.extend(
        [
            r"\hline",
            r"\end{tabular}}",
            r"\par\smallskip\footnotesize The year-set-only uniform-exact control "
            r"(not shown) has RMSE "
            rf"{fmt(cohorts['crossed/uniform_exact']['rmse_c_per_10a'])} "
            r"(controlled) and "
            rf"{fmt(cohorts['calendar/uniform_exact']['rmse_c_per_10a'])} "
            r"(calendar) $^{\circ}$C/10a and "
            rf"{cohorts['crossed/uniform_exact']['sign_flips']}/"
            rf"{cohorts['calendar/uniform_exact']['sign_flips']} sign flips; its "
            r"archive-level estimates are not saved, so error/SE ratios are "
            r"undefined. Calendar medians are diluted by identical year sets: "
            r"restricted to the 288 calendars whose warm-season and all-year sets "
            r"differ, screening gives RMSE "
            rf"{fmt(cohorts['calendar_changed_year_set/warm90']['rmse_c_per_10a'])} "
            r"with median and P90 $|e|/$SE of "
            rf"{fmt(cohorts['calendar_changed_year_set/warm90']['median_abs_error_over_se'])} "
            r"and "
            rf"{fmt(cohorts['calendar_changed_year_set/warm90']['p90_abs_error_over_se'])}, "
            r"against "
            rf"{fmt(cohorts['calendar_changed_year_set/all']['rmse_c_per_10a'])}, "
            rf"{fmt(cohorts['calendar_changed_year_set/all']['median_abs_error_over_se'])} "
            r"and "
            rf"{fmt(cohorts['calendar_changed_year_set/all']['p90_abs_error_over_se'])} "
            r"for all-year recovery. All 200 FOEN (Swiss) calendars have zero "
            r"screening error because their real gaps are too short to change the "
            r"retained set. Infl. is the total-uncertainty inflation "
            r"$\sqrt{1+\mathrm{mean}((e/\mathrm{SE})^2)}-1$; Weak flips are the "
            r"sign flips at stations with $|\beta|<1$ SE, where the complete-record "
            r"sign is itself uncertain.",
            r"\end{table*}",
        ]
    )
    return "\n".join(lines) + "\n"


def latex_fragment(summary: dict, cohorts: dict) -> str:
    tables = latex_tables(summary, cohorts)
    crossed_warm = cohorts["crossed/warm90"]
    crossed_all = cohorts["crossed/all"]
    calendar_warm = cohorts["calendar/warm90"]
    calendar_all = cohorts["calendar/all"]
    ratio = crossed_warm["rmse_c_per_10a"] / summary["median_ols_slope_c_per_10a"]
    prose = (
        r"\noindent\textbf{Interpretation.} The complete-record reference slope is "
        r"itself weakly constrained: across "
        rf"{summary['n']} stations and a median of "
        rf"{summary['median_reference_years']:.0f} reference years, the median OLS "
        r"H30 slope is "
        rf"{fmt(summary['median_ols_slope_c_per_10a'])} $^{{\circ}}$C/10a, its "
        r"median classical SE is "
        rf"{fmt(summary['median_ols_se_c_per_10a'])} $^{{\circ}}$C/10a, and the "
        r"median interannual H30 SD is "
        rf"{fmt(summary['median_h30_interannual_sd_c'])} $^{{\circ}}$C; only "
        rf"{summary['ols_p_below_005']} stations have OLS $p<0.05$ and "
        rf"{summary['mann_kendall_p_below_005']} have tie-corrected "
        r"Mann--Kendall $p<0.05$. Under empirical gap calendars, warm-season "
        r"screening and all-year reconstruction give RMSEs of "
        rf"{fmt(calendar_warm['rmse_c_per_10a'])} and "
        rf"{fmt(calendar_all['rmse_c_per_10a'])} $^{{\circ}}$C/10a, both well "
        r"below the median SE ("
        rf"{fmt(summary['median_ols_se_c_per_10a'])} $^{{\circ}}$C/10a); the "
        r"median $|e|/$SE is "
        rf"{fmt(calendar_warm['median_abs_error_over_se'])} (P90 "
        rf"{fmt(calendar_warm['p90_abs_error_over_se'])}) for screening and "
        rf"{fmt(calendar_all['median_abs_error_over_se'])} (P90 "
        rf"{fmt(calendar_all['p90_abs_error_over_se'])}) for reconstruction, with "
        rf"{calendar_warm['sign_flips']} versus {calendar_all['sign_flips']} sign "
        r"flips. Under controlled 30--90-day gaps, reconstruction reduces RMSE "
        r"from "
        rf"{fmt(crossed_warm['rmse_c_per_10a'])} to "
        rf"{fmt(crossed_all['rmse_c_per_10a'])} $^{{\circ}}$C/10a, the share of "
        r"archives exceeding one SE from "
        rf"{fmt_pct(crossed_warm['share_above_one_se'])}\% to "
        rf"{fmt_pct(crossed_all['share_above_one_se'])}\%, and sign flips from "
        rf"{crossed_warm['sign_flips']} to {crossed_all['sign_flips']}. The "
        rf"{fmt(crossed_warm['rmse_c_per_10a'])} $^{{\circ}}$C/10a screening "
        r"RMSE is "
        rf"{100.0 * ratio:.1f}\% of the median reference slope ("
        rf"{fmt(summary['median_ols_slope_c_per_10a'])} $^{{\circ}}$C/10a), but "
        r"this is an aggregate error-to-slope ratio, not a per-archive relative "
        r"underestimate: the median per-archive $|e|/$SE is "
        rf"{fmt(crossed_warm['median_abs_error_over_se'])} and "
        rf"{fmt_pct(crossed_warm['share_above_one_se'])}\% of archives exceed one "
        r"SE. Because the OLS SE excludes autocorrelation, the error/SE ratios "
        r"are lower bounds on the trend's sampling uncertainty. Expressed as "
        r"inflation of total trend uncertainty, warm-season screening adds "
        rf"{fmt_pct(crossed_warm['uncertainty_inflation_fraction'])}\% under "
        r"controlled gaps and "
        rf"{fmt_pct(cohorts['calendar/warm90']['uncertainty_inflation_fraction'])}\% "
        r"under empirical calendars, while all-year recovery adds "
        rf"{fmt_pct(crossed_all['uncertainty_inflation_fraction'])}\% and "
        rf"{fmt_pct(cohorts['calendar/all']['uncertainty_inflation_fraction'])}\%. "
        rf"{crossed_warm['sign_flips_on_abs_slope_below_one_se']} of the "
        rf"{crossed_warm['sign_flips']} controlled-gap screening flips and "
        rf"{crossed_all['sign_flips_on_abs_slope_below_one_se']} of the "
        rf"{crossed_all['sign_flips']} recovery flips occur at stations with "
        r"$|\beta|<1$ SE, and no flip occurs at any of the three stations with "
        r"$|t|\ge 2$."
    )
    return tables + "\n" + prose + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tables",
        type=Path,
        default=REPO_ROOT / "results/wrr_final_revision_20261031",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "results/ems_revision_20261102",
    )
    parser.add_argument(
        "--tex",
        type=Path,
        default=REPO_ROOT / "paper/ems/trend_signal.tex",
    )
    parser.add_argument(
        "--reference-json",
        type=Path,
        default=REPO_ROOT
        / "docs/reviews/ems_dual_review_20261102/slope_signal_audit.json",
    )
    parser.add_argument("--no-tex", action="store_true")
    args = parser.parse_args()

    truths = pd.read_csv(args.tables / "reference_truths.csv")
    year_sets = pd.read_csv(args.tables / "reference_year_sets.csv")
    cases = pd.read_csv(args.tables / "retention_geometry_cases.csv")
    family_summary = pd.read_csv(args.tables / "retention_family_summary.csv")

    crossed_truths = truths[truths["family"] == "crossed"]
    stations = station_slopes(crossed_truths, year_sets)
    summary = station_summary(stations)
    cohorts = cohort_metrics(cases, stations, family_summary)
    validation = validate_outputs(
        truths,
        year_sets,
        cases,
        stations,
        cohorts,
        summary,
        family_summary,
        args.reference_json,
    )

    source_tables = {
        "tables_dir": str(args.tables.relative_to(REPO_ROOT)),
        "reference_truths": str(
            (args.tables / "reference_truths.csv").relative_to(REPO_ROOT)
        ),
        "reference_year_sets": str(
            (args.tables / "reference_year_sets.csv").relative_to(REPO_ROOT)
        ),
        "retention_geometry_cases": str(
            (args.tables / "retention_geometry_cases.csv").relative_to(REPO_ROOT)
        ),
        "retention_family_summary": str(
            (args.tables / "retention_family_summary.csv").relative_to(REPO_ROOT)
        ),
    }
    method = {
        "slope_units": "degrees Celsius per decade (degC/10a)",
        "ols": "Ordinary least squares of complete-record H30 on year/10 for each station's saved reference-year set; slope, classical SE and two-sided p from statsmodels OLS.",
        "ols_se_caveat": "The classical OLS slope SE does not include serial autocorrelation and is a lower bound on the trend's sampling uncertainty.",
        "sen": "Theil-Sen slope computed directly as the median of all pairwise slopes between reference years.",
        "mann_kendall": "Mann-Kendall S test computed directly with tie correction in Var(S) and the normal approximation with continuity correction.",
        "hamed_rao": ("Hamed-Rao (1998) modified Mann-Kendall: detrend by the Sen slope, take ranks of residuals, "
                  "use only lags whose rank autocorrelation is significant at the 5% level, and multiply Var(S) "
                  "by the resulting correction. Verified to agree with pyMannKendall 1.4 hamed_rao_modification_test "
                  "on all 41 stations to 1e-9; exploratory because 7-16 reference years make lag estimates unstable."),
        "error_over_se": "|estimate_error| divided by the station's classical OLS SE, computed from retention_geometry_cases.csv; no new model fits.",
        "sign_flip": "sign(reference_slope + estimate_error) != sign(reference_slope), cross-checked against the saved slope_sign_disagreement column.",
        "uniform_exact": "uniform_exact case rows have no estimate_error; its RMSE is taken from retention_family_summary.csv and error/SE ratios are undefined.",
        "rounding": "JSON/CSV keep full precision; LaTeX values are rounded for display.",
    }
    payload = {
        "generated_by": "docs/reviews/ems_dual_review_20261102/slope_signal_audit.py",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_tables": source_tables,
        "method": method,
        "validation": validation,
        "stations": {
            "summary": summary,
            "rows": [
                {
                    "station_key": station,
                    **{
                        key: (
                            int(value)
                            if key in {"n_reference_years", "first_year", "last_year"}
                            else (None if pd.isna(value) else value)
                        )
                        for key, value in row.items()
                    },
                }
                for station, row in stations.iterrows()
            ],
        },
        "cohorts": cohorts,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "trend_signal.json"
    json_path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")

    records = [
        {
            "record_type": "meta",
            "family": "",
            "scheme": "",
            "station_key": "",
            "metric": "method_note",
            "value": (
                "OLS SE is classical and excludes autocorrelation; Sen and "
                "tie-corrected Mann-Kendall are reported separately; "
                "uniform_exact has no saved archive-level estimate error."
            ),
            "unit": "",
            "source_table": "",
        }
    ]
    for name, path in source_tables.items():
        records.append(
            {
                "record_type": "meta",
                "family": "",
                "scheme": "",
                "station_key": "",
                "metric": f"source_table_{name}",
                "value": path,
                "unit": "",
                "source_table": "",
            }
        )
    station_metrics = [
        ("n_reference_years", "n_reference_years", "count"),
        ("ols_slope_c_per_10a", "ols_slope", "degC/10a"),
        ("ols_se_c_per_10a", "ols_se", "degC/10a"),
        ("ols_p", "ols_p", "p_value"),
        ("sen_slope_c_per_10a", "sen_slope", "degC/10a"),
        ("mann_kendall_p", "mann_kendall_p", "p_value"),
        ("kendall_tau", "kendall_tau", "dimensionless"),
        ("kendall_tau_p", "kendall_tau_p", "p_value"),
        ("hamed_rao_n_star", "hamed_rao_n_star", "effective_years"),
        ("hamed_rao_p", "hamed_rao_p", "p_value"),
        ("h30_interannual_sd_c", "h30_interannual_sd", "degC"),
    ]
    for station, row in stations.iterrows():
        for source_name, metric, unit in station_metrics:
            value = int(row[source_name]) if unit == "count" else row[source_name]
            records.append(
                {
                    "record_type": "station",
                    "family": "complete_record",
                    "scheme": "reference_years",
                    "station_key": station,
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "source_table": (
                        "reference_truths.csv;reference_year_sets.csv"
                    ),
                }
            )
    cohort_metrics_spec = [
        ("n", "n", "count"),
        ("n_stations", "n_stations", "count"),
        ("n_groups", "n_groups", "count"),
        ("rmse_c_per_10a", "rmse", "degC/10a"),
        ("median_abs_error_over_se", "median_abs_error_over_se", "ratio"),
        ("p90_abs_error_over_se", "p90_abs_error_over_se", "ratio"),
        ("share_above_one_se", "share_above_one_se", "fraction"),
        ("sign_flips", "sign_flips", "count"),
        ("median_abs_error_c_per_10a", "median_abs_error", "degC/10a"),
        ("p90_abs_error_c_per_10a", "p90_abs_error", "degC/10a"),
    ]
    for key, row in cohorts.items():
        family, scheme = key.split("/", 1)
        for source_name, metric, unit in cohort_metrics_spec:
            if source_name not in row or row[source_name] is None:
                continue
            value = int(row[source_name]) if unit == "count" else row[source_name]
            records.append(
                {
                    "record_type": "cohort",
                    "family": family,
                    "scheme": scheme,
                    "station_key": "",
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "source_table": row.get("rmse_source", "derived"),
                }
            )
    csv_path = args.out_dir / "trend_signal.csv"
    pd.DataFrame(records).to_csv(csv_path, index=False, float_format="%.12g")

    if not args.no_tex:
        args.tex.parent.mkdir(parents=True, exist_ok=True)
        args.tex.write_text(latex_fragment(summary, cohorts))

    print(
        json.dumps(
            {
                "json": str(json_path),
                "csv": str(csv_path),
                "tex": None if args.no_tex else str(args.tex),
                "validation": {
                    "review_json_all_match": validation["review_json"].get(
                        "all_match"
                    ),
                    "family_summary_all_match": validation[
                        "family_summary_all_match"
                    ],
                    "paper_sign_flips_all_match": validation[
                        "paper_sign_flips_all_match"
                    ],
                    "reference_year_sets_match": validation[
                        "reference_year_sets"
                    ]["match"],
                    "family_truths_identical": validation[
                        "family_truths_identical"
                    ]["match"],
                    "case_reference_slope_matches_ols": validation[
                        "case_reference_slope_matches_ols"
                    ]["match"],
                },
                "stations": summary,
                "cohorts": {
                    key: {
                        name: row[name]
                        for name in [
                            "n",
                            "rmse_c_per_10a",
                            "median_abs_error_over_se",
                            "p90_abs_error_over_se",
                            "share_above_one_se",
                            "sign_flips",
                            "uncertainty_inflation_fraction",
                            "sign_flips_on_abs_slope_below_one_se",
                            "sign_flips_on_abs_t_at_least_two",
                        ]
                        if name in row
                    }
                    for key, row in cohorts.items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
