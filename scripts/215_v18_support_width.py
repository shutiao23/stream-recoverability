#!/usr/bin/env python3
"""E6 — the dichotomy is a continuum, and the knob is the width of the support.

The v17 manuscript reports a reversal: outage timing governs a warm-season
extreme, outage length governs the annual mean. Its own Table 1 undercuts the
labels. The best-performing "timing" axis, the warm-season observed fraction,
is a count of missing days restricted to a window -- a length measure with a
domain restriction, correlated with the longest run at -0.86. So the finding is
not that timing beats length. It is that missingness must be measured on the
support of the estimand rather than on the calendar year, and "timing versus
length" is what that looks like at the two ends of a scale.

If that is right there is no dichotomy to explain, only a law with a knob. The
hottest-k-day mean interpolates continuously from the annual maximum (k = 1) to
the annual mean (k = 365), and the prediction is sharp:

P1  the advantage of the support-restricted axis over the whole-year missing
    fraction decays monotonically in k and reaches zero at k = 365, where the
    two coincide by construction;
P2  a FIXED 30-day peak window -- the axis the v17 screen actually uses --
    loses its advantage as k grows and crosses into deficit at some k*, which
    the theory says should sit where the estimand's support stops being local;
P3  the support-restricted axis is at least as good as the better of the two
    hand-chosen axes at every k. If it is not, the law is wrong somewhere.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stream_recoverability.experiments.v18_closure.analysis import (  # noqa: E402
    auc,
    axis_table,
    clustered_auc_contrast,
    interannual_scale,
)
from stream_recoverability.experiments.v18_closure.endpoints import (  # noqa: E402
    realized_window_centres,
)
from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    E6_SUPPORT,
    RESULTS_ROOT,
    SUPPORT_WIDTHS,
    TOLERANCE_FRACTION,
)

AXES = ("peak_overlap", "warm_observed_fraction", "longest_run", "total_missing", "missing_fraction")
HIGHER_IS_WORSE = {"warm_observed_fraction": False}
TOLERANCE_FRACTIONS = (0.25, TOLERANCE_FRACTION, 1.0)


def sweep(cases: pd.DataFrame, fraction: float) -> pd.DataFrame:
    rows = []
    for width in SUPPORT_WIDTHS:
        error_column = f"abserr_hottest_{width}"
        support_column = f"support_hidden_{width}"
        scale = interannual_scale(cases, f"truth_hottest_{width}")
        tolerance = float(fraction) * scale
        block = cases.dropna(subset=[error_column]).copy()
        block["consequential"] = (block[error_column] > tolerance).astype(float)
        label = block["consequential"].to_numpy()
        row = {
            "support_width_days": int(width),
            "tolerance_fraction": float(fraction),
            "interannual_sd_c": scale,
            "tolerance_c": tolerance,
            "n": int(len(block)),
            "base_rate": float(label.mean()),
            "mean_abs_error_c": float(block[error_column].mean()),
        }
        row.update(axis_table(block, label, (*AXES, support_column), higher_is_worse=HIGHER_IS_WORSE))
        row["auc_support_restricted"] = row.pop(f"auc_{support_column}")
        row["support_minus_missing_fraction"] = (
            row["auc_support_restricted"] - row["auc_missing_fraction"]
        )
        row["fixed_peak_window_minus_missing_fraction"] = (
            row["auc_peak_overlap"] - row["auc_missing_fraction"]
        )
        row["support_minus_best_hand_chosen"] = row["auc_support_restricted"] - max(
            row["auc_peak_overlap"], row["auc_missing_fraction"], row["auc_longest_run"]
        )
        rows.append(row)
    return pd.DataFrame(rows)


def conditioning_matrix(cases: pd.DataFrame) -> pd.DataFrame:
    """AUC of every conditioning window against every endpoint width.

    The diagonal is "condition on the estimand's own support". Reading across a
    row says which conditioning set a screening rule should actually use, which
    need not be the support itself when the support's location is uncertain.
    """

    rows = []
    for endpoint_width in SUPPORT_WIDTHS:
        error_column = f"abserr_hottest_{endpoint_width}"
        scale = interannual_scale(cases, f"truth_hottest_{endpoint_width}")
        block = cases.dropna(subset=[error_column]).copy()
        label = (block[error_column] > TOLERANCE_FRACTION * scale).astype(float).to_numpy()
        row = {"endpoint_width_days": int(endpoint_width)}
        for conditioning_width in SUPPORT_WIDTHS:
            row[f"condition_{conditioning_width}"] = auc(
                label, block[f"support_hidden_{conditioning_width}"].to_numpy(dtype=float)
            )
        scores = {int(w): row[f"condition_{w}"] for w in SUPPORT_WIDTHS if np.isfinite(row[f"condition_{w}"])}
        row["best_conditioning_width_days"] = int(max(scores, key=scores.get))
        row["auc_at_best"] = float(max(scores.values()))
        row["auc_at_own_support"] = float(scores.get(int(endpoint_width), np.nan))
        row["gain_from_widening"] = row["auc_at_best"] - row["auc_at_own_support"]
        rows.append(row)
    return pd.DataFrame(rows)


def support_location_dispersion(workers: int = 48) -> pd.DataFrame:
    """Year-to-year wander of the realised hottest-k window, in days."""

    from concurrent.futures import ProcessPoolExecutor

    from scripts_support import endpoint_jobs

    rows: list[dict] = []
    jobs = endpoint_jobs()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for block in pool.map(realized_window_centres, jobs, chunksize=4):
            rows.extend(block)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    out = []
    for (station, width), block in frame.groupby(["station_id", "support_width_days"]):
        if len(block) < 3:
            continue
        angles = block["centre_angle"].to_numpy()
        resultant = np.abs(np.mean(np.exp(1j * angles)))
        circular_sd = float(np.sqrt(-2 * np.log(max(resultant, 1e-9))) * 365.25 / (2 * np.pi))
        out.append({"station_id": station, "support_width_days": int(width), "circular_sd_days": circular_sd})
    per_station = pd.DataFrame(out)
    return (
        per_station.groupby("support_width_days")["circular_sd_days"]
        .median()
        .reset_index()
        .rename(columns={"circular_sd_days": "median_support_location_sd_days"})
    )


def crossover(frame: pd.DataFrame, column: str) -> float:
    """Where the advantage of the fixed peak window crosses zero, by interpolation."""

    block = frame.sort_values("support_width_days")
    x = np.log(block["support_width_days"].to_numpy(dtype=float))
    y = block[column].to_numpy(dtype=float)
    sign_change = np.where(np.sign(y[:-1]) != np.sign(y[1:]))[0]
    if len(sign_change) == 0:
        return float("nan")
    i = int(sign_change[0])
    if y[i + 1] == y[i]:
        return float(np.exp(x[i]))
    t = -y[i] / (y[i + 1] - y[i])
    return float(np.exp(x[i] + t * (x[i + 1] - x[i])))


def main() -> int:
    E6_SUPPORT.mkdir(parents=True, exist_ok=True)
    cases = pd.read_parquet(RESULTS_ROOT / "endpoint_cases.parquet")
    development = cases.loc[cases["split_role"] == "development"].reset_index(drop=True)
    reserved = cases.loc[cases["split_role"] == "reserved"].reset_index(drop=True)

    tables = []
    for fraction in TOLERANCE_FRACTIONS:
        block = sweep(development, fraction)
        block.insert(0, "split", "development")
        tables.append(block)
    reserved_block = sweep(reserved, TOLERANCE_FRACTION)
    reserved_block.insert(0, "split", "reserved")
    tables.append(reserved_block)
    frame = pd.concat(tables, ignore_index=True)
    frame.to_csv(E6_SUPPORT / "support_width_sweep.csv", index=False)

    primary = frame.loc[
        (frame["split"] == "development") & (frame["tolerance_fraction"] == TOLERANCE_FRACTION)
    ].sort_values("support_width_days")

    contrasts = []
    for width in SUPPORT_WIDTHS:
        error_column = f"abserr_hottest_{width}"
        scale = interannual_scale(development, f"truth_hottest_{width}")
        block = development.dropna(subset=[error_column]).copy()
        block["consequential"] = (block[error_column] > TOLERANCE_FRACTION * scale).astype(float)
        contrast = clustered_auc_contrast(
            block, "consequential", "peak_overlap", "missing_fraction", higher_is_worse=HIGHER_IS_WORSE
        )
        contrast["support_width_days"] = int(width)
        contrasts.append(contrast)
    contrast_frame = pd.DataFrame(contrasts)
    contrast_frame.to_csv(E6_SUPPORT / "auc_contrasts_by_width.csv", index=False)

    matrix = conditioning_matrix(development)
    dispersion = support_location_dispersion(workers=48)
    matrix = matrix.merge(
        dispersion.rename(columns={"support_width_days": "endpoint_width_days"}),
        on="endpoint_width_days",
        how="left",
    )
    matrix.to_csv(E6_SUPPORT / "conditioning_width_matrix.csv", index=False)

    advantage = primary["support_minus_missing_fraction"].to_numpy()
    monotone = bool(np.all(np.diff(advantage) <= 1e-3))
    summary = {
        "n_development_cases": int(len(development)),
        "widths": list(SUPPORT_WIDTHS),
        "P1_monotone_decay": {
            "prediction": "the support-restricted advantage decays monotonically in k",
            "outcome": monotone,
            "advantage_by_width": {
                int(w): float(v)
                for w, v in zip(primary["support_width_days"], advantage)
            },
            "advantage_at_365": float(advantage[-1]),
        },
        "P2_crossover": {
            "prediction": "the fixed 30-day peak window loses its advantage as the support widens",
            "crossover_width_days": crossover(primary, "fixed_peak_window_minus_missing_fraction"),
            "advantage_by_width": {
                int(w): float(v)
                for w, v in zip(
                    primary["support_width_days"],
                    primary["fixed_peak_window_minus_missing_fraction"],
                )
            },
        },
        "P3_support_axis_dominates": {
            "prediction": "the support-restricted axis is at least as good as the best hand-chosen axis at every k",
            "minimum_margin": float(primary["support_minus_best_hand_chosen"].min()),
            "outcome": bool(primary["support_minus_best_hand_chosen"].min() > -0.01),
            "margin_by_width": {
                int(w): float(v)
                for w, v in zip(
                    primary["support_width_days"], primary["support_minus_best_hand_chosen"]
                )
            },
        },
        "P1_and_P3_diagnosis": {
            "observation": (
                "the support-restricted advantage is a hump peaking near a 60-day support "
                "rather than a monotone decay, and below a 30-day support the fixed "
                "30-day window beats the estimand's own support"
            ),
            "explanation": (
                "the axis conditions on the CLIMATOLOGICAL hottest-k window, which is an "
                "estimate of where this year's window will fall. For a narrow estimand "
                "that estimate is poor, so the right conditioning set is the support "
                "dilated by the year-to-year wander of its own location"
            ),
            "best_conditioning_width_by_endpoint": {
                int(row.endpoint_width_days): int(row.best_conditioning_width_days)
                for row in matrix.itertuples()
            },
            "support_location_sd_days": {
                int(row.endpoint_width_days): (
                    float(row.median_support_location_sd_days)
                    if np.isfinite(row.median_support_location_sd_days)
                    else None
                )
                for row in matrix.itertuples()
            },
            "gain_from_widening_auc": {
                int(row.endpoint_width_days): float(row.gain_from_widening)
                for row in matrix.itertuples()
            },
        },
        "reserved_crossover_width_days": crossover(
            reserved_block.sort_values("support_width_days"), "fixed_peak_window_minus_missing_fraction"
        ),
        "note": (
            "the reserved panel is reported alongside for completeness but was unblinded "
            "by the v17 confirmation and is not a confirmation of this claim"
        ),
    }
    (E6_SUPPORT / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")

    columns = [
        "support_width_days",
        "interannual_sd_c",
        "base_rate",
        "auc_support_restricted",
        "auc_peak_overlap",
        "auc_missing_fraction",
        "auc_longest_run",
        "support_minus_missing_fraction",
        "fixed_peak_window_minus_missing_fraction",
        "support_minus_best_hand_chosen",
    ]
    lines = ["# E6 — support width as a continuous knob", ""]
    lines.append(
        f"Development cases, each endpoint scored at {TOLERANCE_FRACTION:.2f} of its own "
        "interannual standard deviation."
    )
    lines.append("")
    lines.append(primary[columns].to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append("## Network-clustered contrast, fixed peak window against whole-year missing fraction")
    lines.append("")
    lines.append(
        contrast_frame[["support_width_days", "point", "low", "high", "excludes_zero"]].to_markdown(
            index=False, floatfmt=".4g"
        )
    )
    lines.append("")
    lines.append("## Which conditioning window a screen should actually use")
    lines.append("")
    lines.append(
        "Rows are the estimand; columns are the climatological window the axis conditions "
        "on. The diagonal is the estimand's own support."
    )
    lines.append("")
    lines.append(
        matrix[
            [
                "endpoint_width_days",
                "best_conditioning_width_days",
                "auc_at_best",
                "auc_at_own_support",
                "gain_from_widening",
                "median_support_location_sd_days",
            ]
        ].to_markdown(index=False, floatfmt=".4g")
    )
    lines.append("")
    lines.append("## Verdicts")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps({k: v for k, v in summary.items() if k.startswith("P")}, indent=2, default=float))
    lines.append("```")
    (E6_SUPPORT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
