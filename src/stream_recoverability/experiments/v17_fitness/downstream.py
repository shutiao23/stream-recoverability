"""Step 8 — what changes in a scientific product.

A screening rule is only worth publishing if it changes a quantity somebody
uses. Three are evaluated here on the same simulated outages: the multi-year
trend in the annual thermal peak, the count of years above an ecological
threshold, and the identity of the hottest year on record at a station.

Screening costs sample size, so the trade is reported in both directions: the
bias and RMSE of the slope, and the number of station-years that survive.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import theilslopes

from stream_recoverability.experiments.v17_fitness.paths import (
    EXCEEDANCE_THRESHOLDS_C,
    PRIMARY_TOLERANCE_C,
)

MIN_YEARS_FOR_TREND = 6


def one_realization_per_year(
    cases: pd.DataFrame, certificates: pd.DataFrame, *, arm: str = "empirical", seed: int = 0
) -> pd.DataFrame:
    """One outage per station-year, so each year enters the series once."""

    frame = cases.reset_index(drop=True).copy()
    cert = certificates.reset_index(drop=True)
    for column in ("certificate_bound", "certificate_abs_error", "certificate_metric", "certificate_choice"):
        frame[column] = cert[column].to_numpy() if column in cert else np.nan
    pool = frame.loc[frame["arm"].eq(arm)]
    if pool.empty:
        pool = frame
    rng = np.random.default_rng(int(seed))
    pool = pool.assign(_draw=rng.random(len(pool)))
    picked = pool.sort_values("_draw").groupby(["network_id", "station_id", "year"], as_index=False).first()
    return picked.drop(columns=["_draw"])


def _slope(years: np.ndarray, values: np.ndarray) -> float:
    good = np.isfinite(values)
    if int(good.sum()) < MIN_YEARS_FOR_TREND:
        return float("nan")
    try:
        return float(theilslopes(values[good], years[good])[0])
    except (ValueError, ZeroDivisionError):
        return float("nan")


def station_series(picked: pd.DataFrame, *, tolerance: float = PRIMARY_TOLERANCE_C) -> pd.DataFrame:
    """Per station: the truth series and each treatment's screened series."""

    rows: list[dict] = []
    certificate_retention = float((pd.to_numeric(picked["certificate_bound"], errors="coerce") <= tolerance).mean())
    length_threshold = float(
        pd.to_numeric(picked["longest_run"], errors="coerce").quantile(certificate_retention)
    )
    for (network_id, station_id), block in picked.groupby(["network_id", "station_id"]):
        block = block.sort_values("year")
        years = block["year"].to_numpy(dtype=float)
        truth = pd.to_numeric(block["truth_metric"], errors="coerce").to_numpy(dtype=float)
        if len(years) < MIN_YEARS_FOR_TREND or not np.isfinite(truth).all():
            continue
        observed = pd.to_numeric(block["metric_observed_days"], errors="coerce").to_numpy(dtype=float)
        policy_metric = truth + pd.to_numeric(block["err_policy"], errors="coerce").to_numpy(dtype=float)
        certificate_metric = pd.to_numeric(block["certificate_metric"], errors="coerce").to_numpy(dtype=float)
        bound = pd.to_numeric(block["certificate_bound"], errors="coerce").to_numpy(dtype=float)
        length = pd.to_numeric(block["longest_run"], errors="coerce").to_numpy(dtype=float)

        keep_certificate = bound <= tolerance
        keep_length = length <= length_threshold

        treatments = {
            "truth": truth,
            "observed_days_all": observed,
            "reconstruct_all": policy_metric,
            "length_screened": np.where(keep_length, policy_metric, np.nan),
            "certificate_screened": np.where(keep_certificate, certificate_metric, np.nan),
        }
        truth_slope = _slope(years, truth)
        row_base = {
            "network_id": network_id,
            "station_id": station_id,
            "n_years": int(len(years)),
            "truth_slope": truth_slope,
            "length_threshold_days": length_threshold,
        }
        for name, values in treatments.items():
            slope = _slope(years, values)
            rows_kept = int(np.isfinite(values).sum())
            row_base[f"slope_{name}"] = slope
            row_base[f"n_kept_{name}"] = rows_kept
            row_base[f"slope_error_{name}"] = slope - truth_slope if np.isfinite(slope) and np.isfinite(truth_slope) else float("nan")
            for threshold in EXCEEDANCE_THRESHOLDS_C:
                truth_count = int(np.nansum(truth > float(threshold)))
                finite = values[np.isfinite(values)]
                observed_count = int(np.nansum(finite > float(threshold)))
                scale = len(truth) / max(1, len(finite))
                row_base[f"exceed{int(threshold)}_error_{name}"] = observed_count * scale - truth_count
            hottest_truth = int(np.nanargmax(truth))
            if np.isfinite(values).any():
                hottest = int(np.nanargmax(np.where(np.isfinite(values), values, -np.inf)))
                row_base[f"hottest_year_correct_{name}"] = bool(years[hottest] == years[hottest_truth])
            else:
                row_base[f"hottest_year_correct_{name}"] = False
        rows.append(row_base)
    return pd.DataFrame(rows)


def downstream_summary(series: pd.DataFrame) -> pd.DataFrame:
    treatments = ["observed_days_all", "reconstruct_all", "length_screened", "certificate_screened"]
    rows = []
    for name in treatments:
        errors = pd.to_numeric(series[f"slope_error_{name}"], errors="coerce")
        rows.append(
            {
                "treatment": name,
                "n_stations": int(errors.notna().sum()),
                "slope_bias_c_per_year": float(errors.mean()),
                "slope_rmse_c_per_year": float(np.sqrt((errors**2).mean())),
                "slope_mae_c_per_year": float(errors.abs().mean()),
                "mean_years_kept": float(pd.to_numeric(series[f"n_kept_{name}"], errors="coerce").mean()),
                "exceed18_bias_years": float(pd.to_numeric(series["exceed18_error_" + name], errors="coerce").mean()),
                "exceed20_bias_years": float(pd.to_numeric(series["exceed20_error_" + name], errors="coerce").mean()),
                "exceed20_mae_years": float(pd.to_numeric(series["exceed20_error_" + name], errors="coerce").abs().mean()),
                "hottest_year_accuracy": float(series[f"hottest_year_correct_{name}"].mean()),
            }
        )
    return pd.DataFrame(rows)


def sign_error_rate(series: pd.DataFrame) -> pd.DataFrame:
    """How often does a treatment report a warming trend where truth cools, or the reverse?"""

    rows = []
    truth = pd.to_numeric(series["truth_slope"], errors="coerce")
    for name in ["observed_days_all", "reconstruct_all", "length_screened", "certificate_screened"]:
        slope = pd.to_numeric(series[f"slope_{name}"], errors="coerce")
        good = truth.notna() & slope.notna()
        rows.append(
            {
                "treatment": name,
                "n": int(good.sum()),
                "sign_disagreement_rate": float((np.sign(truth[good]) != np.sign(slope[good])).mean()),
                "large_slope_error_rate": float((slope[good] - truth[good]).abs().gt(0.05).mean()),
            }
        )
    return pd.DataFrame(rows)


def per_year_threshold_accuracy(
    picked: pd.DataFrame, *, tolerance: float = PRIMARY_TOLERANCE_C
) -> pd.DataFrame:
    """The per-year product: did this station-year's peak exceed an ecological threshold?

    Multi-year trends average errors away, so a screen helps them little once
    the record is reconstructed at all. A statement about one year does not
    average anything, and that is where a fitness-for-use decision earns its
    place. Screened treatments are scored only on the years they retain, and
    their retention is reported alongside.
    """

    frame = picked.copy()
    truth = pd.to_numeric(frame["truth_metric"], errors="coerce")
    bound = pd.to_numeric(frame["certificate_bound"], errors="coerce")
    length = pd.to_numeric(frame["longest_run"], errors="coerce")
    retention = float((bound <= tolerance).mean())
    length_threshold = float(length.quantile(retention))

    estimates = {
        "observed_days_all": pd.to_numeric(frame["metric_observed_days"], errors="coerce"),
        "reconstruct_all": truth + pd.to_numeric(frame["err_policy"], errors="coerce"),
        "length_screened": truth + pd.to_numeric(frame["err_policy"], errors="coerce"),
        "certificate_screened": pd.to_numeric(frame["certificate_metric"], errors="coerce"),
    }
    keep = {
        "observed_days_all": pd.Series(True, index=frame.index),
        "reconstruct_all": pd.Series(True, index=frame.index),
        "length_screened": length <= length_threshold,
        "certificate_screened": bound <= tolerance,
    }

    rows = []
    for threshold in EXCEEDANCE_THRESHOLDS_C:
        truth_label = truth > float(threshold)
        for name, values in estimates.items():
            mask = keep[name] & values.notna() & truth.notna()
            if int(mask.sum()) == 0:
                continue
            predicted = values[mask] > float(threshold)
            actual = truth_label[mask]
            rows.append(
                {
                    "threshold_c": float(threshold),
                    "treatment": name,
                    "retention": float(mask.mean()),
                    "n_scored": int(mask.sum()),
                    "misclassification_rate": float((predicted != actual).mean()),
                    "false_negative_rate": float((~predicted & actual).sum() / max(1, int(actual.sum()))),
                    "false_positive_rate": float((predicted & ~actual).sum() / max(1, int((~actual).sum()))),
                }
            )
    return pd.DataFrame(rows)
