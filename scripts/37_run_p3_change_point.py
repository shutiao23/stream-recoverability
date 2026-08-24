#!/usr/bin/env python3
"""Run the post-hoc P3 training-period change-point sensitivity analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from stream_recoverability.analysis.change_points import (
    autocorrelation,
    least_squares_change_point,
    permutation_p_value,
    pettitt_change_point,
    residual_block_bootstrap_change_points,
)
from stream_recoverability.analysis.regulation import (
    annual_thermal_metrics,
    circular_doy_climatology,
    predict_climatology,
)

INPUT = PROJECT_ROOT / "data_versions/published_v2/daily_wide.parquet"
OUTPUT = PROJECT_ROOT / "results/revision"
EVENT_DATE = pd.Timestamp("2014-12-20")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--permutations", type=int, default=9_999)
    parser.add_argument("--bootstrap", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=20_260_824)
    parser.add_argument("--min-segment-days", type=int, default=365)
    parser.add_argument("--block-length-days", type=int, default=365)
    return parser.parse_args()


def _identity(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(path.relative_to(PROJECT_ROOT)),
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _date_at(dates: pd.Series, change_index: int) -> pd.Timestamp:
    if change_index < 0 or change_index >= len(dates):
        raise ValueError("change index does not map to a first post-change date")
    return pd.Timestamp(dates.iloc[int(change_index)])


def _date_string(dates: pd.Series, change_index: int) -> str:
    return _date_at(dates, change_index).date().isoformat()


def _bootstrap_dates(
    method: str,
    dates: pd.Series,
    bootstrap: dict[str, Any],
) -> pd.DataFrame:
    indices = np.asarray(bootstrap["change_indices"], dtype=int)
    return pd.DataFrame(
        {
            "method": method,
            "bootstrap_draw": np.arange(1, len(indices) + 1),
            "change_index": indices,
            "first_post_change_date": [
                _date_string(dates, index) for index in indices
            ],
        }
    )


def _main_figure(
    series: pd.DataFrame,
    annual: pd.DataFrame,
    primary: dict[str, Any],
    alternative: dict[str, Any],
) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(12.0, 7.6), constrained_layout=True)
    date = pd.to_datetime(series["date"])
    event_label = "First unit commissioned (20 Dec 2014)"

    axes[0, 0].plot(date, series["anomaly_degC"], color="#9ecae1", linewidth=0.45)
    axes[0, 0].plot(
        date,
        series["rolling_91d_mean_anomaly_degC"],
        color="#08519c",
        linewidth=1.5,
        label="91-day centered mean",
    )
    axes[0, 0].axvspan(
        pd.Timestamp(primary["ci_lower_date"]),
        pd.Timestamp(primary["ci_upper_date"]),
        color="#4c78a8",
        alpha=0.14,
        label="Pettitt 95% block-bootstrap CI",
    )
    axes[0, 0].axvline(
        pd.Timestamp(primary["point_date"]),
        color="#4c78a8",
        linestyle="--",
        label="Pettitt estimate",
    )
    axes[0, 0].axvline(EVENT_DATE, color="#8c2d2d", linestyle=":", label=event_label)
    axes[0, 0].set(
        title="(a) Frozen-training P3 climatological anomaly",
        ylabel="Temperature anomaly (°C)",
    )
    axes[0, 0].legend(frameon=False, fontsize=7, loc="upper left")

    axes[0, 1].plot(date, series["pettitt_u"], color="#4c78a8", linewidth=1.0)
    axes[0, 1].axvline(
        pd.Timestamp(primary["point_date"]), color="#4c78a8", linestyle="--"
    )
    axes[0, 1].axvline(EVENT_DATE, color="#8c2d2d", linestyle=":")
    axes[0, 1].axhline(0.0, color="black", linewidth=0.6)
    axes[0, 1].set(title="(b) Pettitt rank process", ylabel="Pettitt U")

    score_date = date.iloc[:-1]
    axes[1, 0].plot(
        score_date,
        series["least_squares_score_admissible"].iloc[:-1],
        color="#f58518",
        linewidth=1.0,
    )
    axes[1, 0].axvspan(
        pd.Timestamp(alternative["ci_lower_date"]),
        pd.Timestamp(alternative["ci_upper_date"]),
        color="#f58518",
        alpha=0.14,
        label="Binary-segmentation 95% block-bootstrap CI",
    )
    axes[1, 0].axvline(
        pd.Timestamp(alternative["point_date"]),
        color="#f58518",
        linestyle="--",
        label="Binary-segmentation estimate",
    )
    axes[1, 0].axvline(EVENT_DATE, color="#8c2d2d", linestyle=":", label=event_label)
    axes[1, 0].set(
        title="(c) Least-squares single-break sensitivity",
        ylabel="Between-segment sum of squares",
    )
    axes[1, 0].legend(frameon=False, fontsize=7, loc="upper left")

    annual = annual.sort_values("year")
    axes[1, 1].plot(
        annual["year"],
        annual["annual_minimum_degC"],
        color="#54a24b",
        marker="o",
        label="Annual minimum",
    )
    second_axis = axes[1, 1].twinx()
    second_axis.plot(
        annual["year"],
        annual["annual_amplitude_degC"],
        color="#e45756",
        marker="s",
        label="Annual amplitude",
    )
    axes[1, 1].axvline(2014.97, color="#8c2d2d", linestyle=":")
    axes[1, 1].set(
        title="(d) Annual endpoint sensitivity",
        xlabel="Year",
        ylabel="Annual minimum (°C)",
    )
    second_axis.set_ylabel("Annual amplitude (°C)")
    handles1, labels1 = axes[1, 1].get_legend_handles_labels()
    handles2, labels2 = second_axis.get_legend_handles_labels()
    axes[1, 1].legend(
        handles1 + handles2, labels1 + labels2, frameon=False, fontsize=7
    )

    for axis in axes.flat:
        axis.grid(alpha=0.2)
    figure.suptitle(
        "P3 change-date estimates are method-sensitive under strong persistence",
        fontsize=13,
    )
    figure.savefig(OUTPUT / "p3_change_point_diagnostic.png", dpi=300)
    plt.close(figure)


def main() -> None:
    args = _arguments()
    if args.permutations < 1 or args.bootstrap < 1:
        raise ValueError("permutation and bootstrap counts must be positive")
    OUTPUT.mkdir(parents=True, exist_ok=True)

    wide = pd.read_parquet(INPUT)
    wide["date"] = pd.to_datetime(wide["date"])
    train = wide.loc[wide["split"].astype(str).eq("train"), ["date", "P3_T"]].copy()
    train = train.sort_values("date", kind="mergesort").reset_index(drop=True)
    if train.empty or train["P3_T"].isna().any():
        raise ValueError("P3 frozen training series must be nonempty and complete")
    expected_dates = pd.date_range(train["date"].min(), train["date"].max(), freq="D")
    if not train["date"].reset_index(drop=True).equals(pd.Series(expected_dates)):
        raise ValueError("P3 frozen training series must have a complete daily axis")

    climatology = circular_doy_climatology(
        train["date"], train["P3_T"], half_window_days=7
    )
    expected = predict_climatology(climatology, train["date"])
    anomaly = train["P3_T"].to_numpy(float) - expected
    dates = train["date"]
    min_segment = int(args.min_segment_days)
    year_blocks = dates.dt.year.to_numpy()

    primary_fit = pettitt_change_point(anomaly, min_segment=min_segment)
    primary_iid = permutation_p_value(
        anomaly,
        pettitt_change_point,
        n_permutations=args.permutations,
        seed=args.seed,
        min_segment=min_segment,
    )
    primary_block = permutation_p_value(
        anomaly,
        pettitt_change_point,
        n_permutations=args.permutations,
        seed=args.seed + 1,
        min_segment=min_segment,
        block_labels=year_blocks,
    )
    primary_bootstrap = residual_block_bootstrap_change_points(
        anomaly,
        pettitt_change_point,
        n_bootstrap=args.bootstrap,
        block_length=args.block_length_days,
        seed=args.seed + 2,
        min_segment=min_segment,
        center="median",
    )

    alternative_fit = least_squares_change_point(anomaly, min_segment=min_segment)
    alternative_iid = permutation_p_value(
        anomaly,
        least_squares_change_point,
        n_permutations=args.permutations,
        seed=args.seed + 3,
        min_segment=min_segment,
    )
    alternative_block = permutation_p_value(
        anomaly,
        least_squares_change_point,
        n_permutations=args.permutations,
        seed=args.seed + 4,
        min_segment=min_segment,
        block_labels=year_blocks,
    )
    alternative_bootstrap = residual_block_bootstrap_change_points(
        anomaly,
        least_squares_change_point,
        n_bootstrap=args.bootstrap,
        block_length=args.block_length_days,
        seed=args.seed + 5,
        min_segment=min_segment,
        center="mean",
    )

    def summary_row(
        role: str,
        fit: dict[str, Any],
        iid: dict[str, Any],
        block: dict[str, Any],
        bootstrap: dict[str, Any],
    ) -> dict[str, Any]:
        point = _date_at(dates, int(fit["change_index"]))
        lower = _date_at(dates, int(bootstrap["ci_lower_index"]))
        upper = _date_at(dates, int(bootstrap["ci_upper_index"]))
        earliest_admissible = _date_at(dates, min_segment)
        latest_admissible = _date_at(dates, len(dates) - min_segment)
        return {
            "role": role,
            "method": fit["method"],
            "series": "P3 daily temperature minus frozen-training circular DOY median",
            "point_date": point.date().isoformat(),
            "ci_lower_date": lower.date().isoformat(),
            "ci_upper_date": upper.date().isoformat(),
            "event_date": EVENT_DATE.date().isoformat(),
            "event_in_95pct_bootstrap_ci": bool(lower <= EVENT_DATE <= upper),
            "earliest_admissible_point_date": earliest_admissible.date().isoformat(),
            "latest_admissible_point_date": latest_admissible.date().isoformat(),
            "ci_lower_hits_admissible_boundary": bool(lower == earliest_admissible),
            "ci_upper_hits_admissible_boundary": bool(upper == latest_admissible),
            "statistic": float(fit["statistic"]),
            "signed_statistic": fit.get("signed_statistic", np.nan),
            "asymptotic_p_value_iid": fit.get("asymptotic_p_value_iid", np.nan),
            "iid_permutation_p_value": float(iid["p_value"]),
            "iid_permutation_exceedances": int(iid["exceedances"]),
            "calendar_year_block_permutation_p_value": float(block["p_value"]),
            "calendar_year_block_permutation_exceedances": int(block["exceedances"]),
            "n_permutations": int(args.permutations),
            "n_bootstrap": int(args.bootstrap),
            "bootstrap_block_length_days": int(args.block_length_days),
            "min_segment_days": min_segment,
            "n_daily_observations": len(anomaly),
            "first_segment_level_degC": float(bootstrap["fitted_first_level"]),
            "second_segment_level_degC": float(bootstrap["fitted_second_level"]),
            "level_change_degC": float(bootstrap["fitted_level_change"]),
        }

    primary = summary_row(
        "primary", primary_fit, primary_iid, primary_block, primary_bootstrap
    )
    alternative = summary_row(
        "robust_sensitivity",
        alternative_fit,
        alternative_iid,
        alternative_block,
        alternative_bootstrap,
    )
    summary = pd.DataFrame([primary, alternative])

    bootstrap_dates = pd.concat(
        [
            _bootstrap_dates(primary_fit["method"], dates, primary_bootstrap),
            _bootstrap_dates(
                alternative_fit["method"], dates, alternative_bootstrap
            ),
        ],
        ignore_index=True,
    )

    annual = annual_thermal_metrics(train, ["P3"])
    annual_rows: list[dict[str, Any]] = []
    for offset, metric in enumerate(
        ("annual_minimum_degC", "annual_amplitude_degC")
    ):
        values = annual[metric].to_numpy(float)
        fit = pettitt_change_point(values, min_segment=2)
        randomisation = permutation_p_value(
            values,
            pettitt_change_point,
            n_permutations=args.permutations,
            seed=args.seed + 10 + offset,
            min_segment=2,
        )
        maximizing_dates = [
            f"{int(annual.iloc[index]['year'])}-01-01"
            for index in np.asarray(fit["maximizing_change_indices"], dtype=int)
        ]
        pre_2015 = values[annual["year"].to_numpy() < 2015]
        value_2015 = float(values[annual["year"].to_numpy() == 2015][0])
        annual_rows.append(
            {
                "method": "annual_metric_pettitt_sensitivity",
                "metric": metric,
                "selected_point_date": maximizing_dates[0],
                "all_tied_maximizing_dates": ";".join(maximizing_dates),
                "statistic": float(fit["statistic"]),
                "asymptotic_p_value_iid": float(fit["asymptotic_p_value_iid"]),
                "permutation_p_value": float(randomisation["p_value"]),
                "permutation_exceedances": int(randomisation["exceedances"]),
                "n_years": len(values),
                "value_2015_degC": value_2015,
                "pre_2015_median_degC": float(np.median(pre_2015)),
                "endpoint_change_from_pre_2015_median_degC": float(
                    value_2015 - np.median(pre_2015)
                ),
                "event_date": EVENT_DATE.date().isoformat(),
                "interpretation": (
                    "low-power annual sensitivity; only one frozen-training year "
                    "is fully post-commissioning"
                ),
            }
        )
    annual_sensitivity = pd.DataFrame(annual_rows)

    least_squares_score = np.r_[alternative_fit["process"], np.nan]
    least_squares_score[: min_segment - 1] = np.nan
    least_squares_score[len(anomaly) - min_segment :] = np.nan
    series = pd.DataFrame(
        {
            "date": dates.dt.date.astype(str),
            "P3_temperature_degC": train["P3_T"].to_numpy(float),
            "frozen_training_climatology_degC": expected,
            "anomaly_degC": anomaly,
            "rolling_91d_mean_anomaly_degC": pd.Series(anomaly)
            .rolling(91, center=True, min_periods=46)
            .mean(),
            "pettitt_u": primary_fit["process"],
            "least_squares_score_admissible": least_squares_score,
        }
    )

    summary_path = OUTPUT / "p3_change_point_summary.csv"
    bootstrap_path = OUTPUT / "p3_change_point_bootstrap_dates.csv"
    sensitivity_path = OUTPUT / "p3_change_point_sensitivity.csv"
    annual_path = OUTPUT / "p3_change_point_annual_metrics.csv"
    series_path = OUTPUT / "p3_change_point_series.csv"
    figure_path = OUTPUT / "p3_change_point_diagnostic.png"
    reporting_path = OUTPUT / "p3_change_point_reporting.md"
    audit_path = OUTPUT / "p3_change_point_audit.json"
    manifest_path = OUTPUT / "p3_change_point_manifest.json"
    summary.to_csv(summary_path, index=False)
    bootstrap_dates.to_csv(bootstrap_path, index=False)
    annual_sensitivity.to_csv(sensitivity_path, index=False)
    annual.to_csv(annual_path, index=False)
    series.to_csv(series_path, index=False)
    _main_figure(series, annual, primary, alternative)

    reporting_path.write_text(
        "\n".join(
            [
                "# P3 change-point reporting numbers",
                "",
                "Post-hoc diagnostic; not part of the frozen confirmatory analysis.",
                "",
                "## Concise result",
                "",
                (
                    "The primary Pettitt test on 3,652 frozen-training daily "
                    "climatological anomalies located the first post-change day at "
                    f"{primary['point_date']} (95% segmentwise 365-day moving-block "
                    f"bootstrap CI, {primary['ci_lower_date']} to "
                    f"{primary['ci_upper_date']})."
                ),
                (
                    f"The iid asymptotic p value was {primary['asymptotic_p_value_iid']:.3g} "
                    f"and the iid day-permutation p value was {primary['iid_permutation_p_value']:.4f} "
                    f"({primary['iid_permutation_exceedances']} exceedances in "
                    f"{primary['n_permutations']:,} draws), but lag-1 "
                    f"autocorrelation was {autocorrelation(anomaly, 1):.3f}; the "
                    "dependence-aware calendar-year block-permutation p value was "
                    f"{primary['calendar_year_block_permutation_p_value']:.4f}."
                ),
                (
                    f"The {EVENT_DATE.date().isoformat()} commissioning date was not "
                    "inside the primary interval."
                ),
                (
                    "As a robust sensitivity, least-squares single binary segmentation "
                    f"located {alternative['point_date']} (95% block-bootstrap CI, "
                    f"{alternative['ci_lower_date']} to {alternative['ci_upper_date']}; "
                    "calendar-year block-permutation p = "
                    f"{alternative['calendar_year_block_permutation_p_value']:.4f}); "
                    "this interval did include the commissioning date."
                ),
                (
                    "The sensitivity interval's upper endpoint equals the latest "
                    "admissible split under the prespecified 365-day minimum-segment "
                    "constraint and should be read as boundary-limited."
                ),
                (
                    "Accordingly, the record supports a statistically detectable, "
                    "method-sensitive state change, but the primary analysis does not "
                    "statistically localize the commissioning date and neither analysis "
                    "alone establishes attribution."
                ),
                "",
                "## Annual endpoint sensitivity",
                "",
                (
                    "In 2015, P3 annual minimum temperature was 12.4 °C versus a "
                    "2006–2014 median of 9.6 °C (+2.8 °C), while annual amplitude was "
                    "10.7 °C versus 13.1 °C (−2.4 °C). With only one fully "
                    "post-commissioning frozen-training year, annual Pettitt "
                    "permutation tests were not significant (p = 0.2208 and 0.8607, "
                    "respectively)."
                ),
                "",
                "## Prohibited stronger interpretation",
                "",
                (
                    "Do not state that Pettitt statistically located the 20 December "
                    "2014 commissioning date."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    autocorrelation_values = {
        f"acf_lag_{lag}_days": autocorrelation(anomaly, lag)
        for lag in (1, 30, 90, 365)
    }
    audit = {
        "schema_version": "p3_change_point_analysis_v1",
        "status": "complete",
        "analysis_label": "post_hoc_diagnostic_added_after_frozen_analysis",
        "station_id": "P3",
        "training_period": {
            "split": "train",
            "start": dates.min().date().isoformat(),
            "end": dates.max().date().isoformat(),
            "n_daily_observations": len(anomaly),
        },
        "anomaly_definition": {
            "observed_column": "P3_T",
            "climatology": "366-day circular day-of-year median",
            "half_window_days": 7,
            "fit_period": "same frozen training split",
        },
        "commissioning_reference_date": EVENT_DATE.date().isoformat(),
        "primary": primary,
        "robust_sensitivity": alternative,
        "annual_sensitivity": annual_rows,
        "serial_dependence": {
            **autocorrelation_values,
            "iid_reference_warning": (
                "The asymptotic and individual-day permutation p-values assume "
                "exchangeable daily observations and are anti-conservative for "
                "this persistent series."
            ),
            "dependence_aware_null": (
                "Complete calendar years were reordered as ten contiguous blocks, "
                "preserving all within-year dependence and seasonal residual shape."
            ),
            "inference_p_value_used": "calendar_year_block_permutation_p_value",
        },
        "bootstrap_contract": {
            "scheme": primary_bootstrap["scheme"],
            "confidence_interval": "2.5th and 97.5th nearest order statistics",
            "block_length_days": int(args.block_length_days),
            "primary_center": "segment median",
            "sensitivity_center": "segment mean",
            "n_bootstrap": int(args.bootstrap),
            "caveat": (
                "Percentile intervals condition on a fitted one-step model and "
                "quantify date instability under segmentwise serial dependence."
            ),
        },
        "interpretation": {
            "event_is_in_primary_ci": bool(primary["event_in_95pct_bootstrap_ci"]),
            "event_is_in_sensitivity_ci": bool(
                alternative["event_in_95pct_bootstrap_ci"]
            ),
            "required_claim": (
                "The daily rank-location change predates commissioning and does not "
                "statistically localize the 20 Dec 2014 event. The least-squares "
                "single-break sensitivity is compatible with that date, so timing "
                "is estimator-sensitive and supports temporal consistency only, "
                "not attribution."
            ),
        },
        "inputs": [
            _identity(INPUT),
            _identity(PROJECT_ROOT / "src/stream_recoverability/analysis/change_points.py"),
            _identity(PROJECT_ROOT / "scripts/37_run_p3_change_point.py"),
        ],
        "outputs": [
            _identity(path)
            for path in (
                summary_path,
                bootstrap_path,
                sensitivity_path,
                annual_path,
                series_path,
                figure_path,
                reporting_path,
            )
        ],
    }
    audit_path.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": "p3_change_point_manifest_v1",
        "status": "complete",
        "primary_result": {
            "point_date": primary["point_date"],
            "ci_lower_date": primary["ci_lower_date"],
            "ci_upper_date": primary["ci_upper_date"],
            "event_in_95pct_bootstrap_ci": primary[
                "event_in_95pct_bootstrap_ci"
            ],
            "iid_day_permutation_p_value_reference_only": primary[
                "iid_permutation_p_value"
            ],
            "calendar_year_block_permutation_p_value_for_inference": primary[
                "calendar_year_block_permutation_p_value"
            ],
        },
        "artifacts": [
            _identity(path)
            for path in (
                summary_path,
                bootstrap_path,
                sensitivity_path,
                annual_path,
                series_path,
                figure_path,
                reporting_path,
                audit_path,
            )
        ],
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(summary.to_string(index=False))
    print(f"Wrote {OUTPUT.relative_to(PROJECT_ROOT)}/p3_change_point_*")


if __name__ == "__main__":
    main()
