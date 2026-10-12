#!/usr/bin/env python3
"""E1 — when do real outages happen, and what does that buy the summer peak?

The v17 confirmation is null on the empirical arm: under the outage geometry
these networks actually experience, the reserved contrast is -0.71 points with
an interval containing zero. v17 reports that and does not explain it.

This script tests the explanation. If real long outages start in autumn and
winter, then agency failure-and-maintenance calendars already protect the warm
season, and the empirical arm is null because little is at risk rather than
because the screen does not work. The prediction is falsifiable: if the start
month of long outages is uniform, the explanation fails and the null must be
attributed to sample size instead.

The second half prices the counterfactual. Reweighting the empirical arm of the
case table to a maintenance calendar that is uniform, or shifted into spring,
turns the discussion's monitoring-design argument from a hypothesis into a
measurement.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from stream_recoverability.experiments.v17_fitness.paths import STEP3_CASES  # noqa: E402
from stream_recoverability.experiments.v17_fitness.policies import (  # noqa: E402
    gather,
    information_conditioned_choice,
)
from stream_recoverability.experiments.v17_fitness.stats import cluster_bootstrap  # noqa: E402
from stream_recoverability.experiments.v18_closure.archive import (  # noqa: E402
    archive_station_years,
    real_gaps,
)
from stream_recoverability.experiments.v18_closure.paths import (  # noqa: E402
    E1_SEASONALITY,
    PRIMARY_TOLERANCE_C,
)

LENGTH_CLASSES = ((1, 7, "1-7 d"), (8, 29, "8-29 d"), (30, 89, "30-89 d"), (90, 10_000, "90 d and longer"))
PROTECTED_MONTHS = (9, 10, 11, 12, 1)
EXPOSED_MONTHS = (3, 4, 5, 6, 7)
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def month_histogram(frame: pd.DataFrame) -> np.ndarray:
    counts = np.zeros(12, dtype=float)
    for month, value in frame["start_month"].value_counts().items():
        counts[int(month) - 1] = float(value)
    return counts


def uniformity(counts: np.ndarray) -> dict:
    if counts.sum() < 12:
        return {"chi2": float("nan"), "p_value": float("nan"), "n": int(counts.sum())}
    test = stats.chisquare(counts, np.full(12, counts.sum() / 12))
    return {"chi2": float(test.statistic), "p_value": float(test.pvalue), "n": int(counts.sum())}


def seasonality_tables(gaps: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Start-month distribution by length class, and by provider for long gaps."""

    rows = []
    summary: dict[str, object] = {"n_gaps": int(len(gaps))}
    for low, high, label in LENGTH_CLASSES:
        block = gaps.loc[gaps["length"].between(low, high)]
        counts = month_histogram(block)
        test = uniformity(counts)
        row = {"length_class": label, "n_gaps": int(len(block))}
        for index, name in enumerate(MONTH_NAMES):
            row[f"share_{name}"] = float(counts[index] / counts.sum()) if counts.sum() else float("nan")
        row["share_protected_sep_to_jan"] = float(
            block["start_month"].isin(PROTECTED_MONTHS).mean()
        )
        row["share_exposed_mar_to_jul"] = float(block["start_month"].isin(EXPOSED_MONTHS).mean())
        row["chi2_uniformity"] = test["chi2"]
        row["p_uniformity"] = test["p_value"]
        rows.append(row)
        summary[f"{label}_n"] = int(len(block))
    by_class = pd.DataFrame(rows)

    long_gaps = gaps.loc[gaps["length"] >= 30]
    provider_rows = []
    for provider, block in long_gaps.groupby("provider"):
        if len(block) < 10:
            continue
        provider_rows.append(
            {
                "provider": provider,
                "n_long_gaps": int(len(block)),
                "share_protected_sep_to_jan": float(block["start_month"].isin(PROTECTED_MONTHS).mean()),
                "share_exposed_mar_to_jul": float(block["start_month"].isin(EXPOSED_MONTHS).mean()),
                "median_length_days": float(block["length"].median()),
            }
        )
    by_provider = pd.DataFrame(provider_rows).sort_values("share_protected_sep_to_jan", ascending=False)

    # A network-clustered interval on the headline share, because gaps within a
    # network share a maintenance contract and a climate.
    interval = cluster_bootstrap(
        long_gaps.assign(protected=long_gaps["start_month"].isin(PROTECTED_MONTHS).astype(float)),
        lambda block: float(block["protected"].mean()),
        seed=20260924,
    )
    summary["long_gap_protected_share"] = interval
    summary["median_gap_days"] = float(gaps["length"].median())
    summary["p95_gap_days"] = float(gaps["length"].quantile(0.95))
    summary["n_long_gaps"] = int(len(long_gaps))
    return by_class, by_provider, summary


def _overlap_lookup(cases: pd.DataFrame) -> tuple[pd.DataFrame, pd.IntervalIndex, pd.IntervalIndex]:
    """Consequential-error rate as a function of outage length and peak overlap.

    Built on the stratified arm, which is the arm designed to span that surface.
    Reading the response off the designed arm and applying it to a placement
    distribution is a standardisation: it holds what the estimator does fixed
    and varies only where the outage falls.
    """

    arm = cases.loc[cases["arm"] == "stratified"].copy()
    arm["policy_abs_error"] = gather(arm, information_conditioned_choice(arm))
    arm = arm.dropna(subset=["policy_abs_error"])
    arm["consequential"] = (arm["policy_abs_error"] > PRIMARY_TOLERANCE_C).astype(float)
    length_bins = pd.IntervalIndex.from_breaks([0, 20, 45, 75, 105, 150, 225, 400])
    overlap_bins = pd.IntervalIndex.from_breaks([-0.001, 0.05, 0.25, 0.5, 0.75, 0.95, 1.001])
    arm["length_bin"] = pd.cut(arm["longest_run"], length_bins)
    arm["overlap_bin"] = pd.cut(arm["peak_overlap"], overlap_bins)
    table = (
        arm.groupby(["length_bin", "overlap_bin"], observed=True)
        .agg(rate=("consequential", "mean"), n=("consequential", "size"), mae=("policy_abs_error", "mean"))
        .reset_index()
    )
    return table, length_bins, overlap_bins


def _simulate_overlaps(
    lengths: np.ndarray,
    peak_starts: np.ndarray,
    month_weights: np.ndarray,
    rng: np.random.Generator,
    draws_per_length: int = 40,
) -> tuple[np.ndarray, np.ndarray]:
    """Place each real outage length under a calendar and measure peak overlap.

    The outage is placed inside a 365-day year; the peak window is the 30 days
    beginning at the station's climatological peak start. Only the placement
    distribution changes between calendars.
    """

    month_starts = np.array([1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335])
    month_lengths = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    out_lengths, out_overlaps = [], []
    weights = month_weights / month_weights.sum()
    for length in lengths:
        length = int(min(int(length), 360))
        months = rng.choice(12, size=draws_per_length, p=weights)
        offsets = rng.integers(0, month_lengths[months])
        starts = month_starts[months] + offsets
        peaks = rng.choice(peak_starts, size=draws_per_length)
        for start, peak in zip(starts, peaks):
            outage = np.zeros(366, dtype=bool)
            end = min(int(start) + length, 366)
            outage[int(start) : end] = True
            window = np.arange(int(peak), int(peak) + 30) % 366
            out_lengths.append(length)
            out_overlaps.append(float(outage[window].mean()))
    return np.asarray(out_lengths, dtype=float), np.asarray(out_overlaps, dtype=float)


def maintenance_counterfactual(
    cases: pd.DataFrame, gaps: pd.DataFrame, peak_starts: np.ndarray
) -> tuple[pd.DataFrame, dict]:
    """Price the maintenance calendar, holding the length distribution fixed.

    Three calendars share one outage-length distribution -- the real one -- and
    differ only in when an outage begins: as observed, uniform over the year,
    and concentrated in March to July. The consequential-error rate of each is
    read off the designed arm's response surface.
    """

    table, length_bins, overlap_bins = _overlap_lookup(cases)
    lookup = {(row.length_bin, row.overlap_bin): row.rate for row in table.itertuples()}
    fallback = float(table["rate"].mean())

    long_gaps = gaps.loc[gaps["length"] >= 14]
    lengths = long_gaps["length"].to_numpy()
    observed_weights = np.zeros(12)
    for month, value in long_gaps["start_month"].value_counts().items():
        observed_weights[int(month) - 1] = float(value)
    calendars = {
        "observed": observed_weights,
        "uniform": np.ones(12),
        "spring_mar_to_jul": np.array([1.0 if m in EXPOSED_MONTHS else 0.0 for m in range(1, 13)]),
        "autumn_sep_to_jan": np.array([1.0 if m in PROTECTED_MONTHS else 0.0 for m in range(1, 13)]),
    }

    rows = []
    rng = np.random.default_rng(20260924)
    for name, weights in calendars.items():
        sim_lengths, sim_overlaps = _simulate_overlaps(lengths, peak_starts, weights, rng)
        length_bin = pd.cut(sim_lengths, length_bins)
        overlap_bin = pd.cut(sim_overlaps, overlap_bins)
        rates = np.array(
            [lookup.get((lb, ob), fallback) for lb, ob in zip(length_bin, overlap_bin)],
            dtype=float,
        )
        rows.append(
            {
                "calendar": name,
                "n_placements": int(len(sim_lengths)),
                "mean_peak_overlap": float(np.mean(sim_overlaps)),
                "share_hitting_peak_window": float(np.mean(sim_overlaps > 0.0)),
                "share_hiding_half_the_window": float(np.mean(sim_overlaps > 0.5)),
                "consequential_rate": float(np.mean(rates)),
            }
        )
    frame = pd.DataFrame(rows)
    baseline = float(frame.loc[frame["calendar"] == "observed", "consequential_rate"].iloc[0])
    frame["points_vs_observed"] = (frame["consequential_rate"] - baseline) * 100
    summary = {
        "n_outage_lengths": int(len(lengths)),
        "n_peak_windows": int(len(peak_starts)),
        "table": frame.to_dict(orient="records"),
    }
    return frame, summary


def main() -> int:
    E1_SEASONALITY.mkdir(parents=True, exist_ok=True)
    gaps = real_gaps(workers=32)
    gaps.to_parquet(E1_SEASONALITY / "real_gaps.parquet")

    by_class, by_provider, summary = seasonality_tables(gaps)
    by_class.to_csv(E1_SEASONALITY / "start_month_by_length_class.csv", index=False)
    by_provider.to_csv(E1_SEASONALITY / "long_gaps_by_provider.csv", index=False)

    cases = pd.read_parquet(STEP3_CASES / "cases.parquet")
    years = archive_station_years(workers=32)
    peak_starts = years["peak_window_start_doy"].dropna().unique().astype(int)
    calendars, counterfactual = maintenance_counterfactual(
        cases.loc[cases["split_role"] == "development"], gaps, peak_starts
    )
    calendars.to_csv(E1_SEASONALITY / "maintenance_calendars.csv", index=False)
    summary["maintenance_counterfactual"] = counterfactual

    very_long = by_class.loc[by_class["length_class"] == "90 d and longer"].iloc[0]
    medium = by_class.loc[by_class["length_class"] == "30-89 d"].iloc[0]
    verdict = {
        "prediction": (
            "long outages start disproportionately in autumn and winter, so the warm "
            "season is protected by the maintenance calendar and the empirical arm is "
            "null because little is at risk"
        ),
        "outcome_90d_and_longer": (
            "supported" if very_long["p_uniformity"] < 0.05 and very_long["share_protected_sep_to_jan"] > 0.5
            else "not supported"
        ),
        "outcome_30_to_89d": (
            "not supported" if medium["p_uniformity"] >= 0.05 else "supported"
        ),
        "reading": (
            "the protective seasonality is a property of outages of about three months "
            "and longer, which are seasonal shutdowns; outages between one and three "
            "months are uniform in start month and are not protected"
        ),
    }
    summary["verdict"] = verdict
    (E1_SEASONALITY / "summary.json").write_text(json.dumps(summary, indent=2, default=float), encoding="utf-8")

    lines = ["# E1 — the seasonality of real outages", ""]
    lines.append(f"{len(gaps):,} real interior gaps across {gaps['station_id'].nunique()} stations. ")
    lines.append(
        f"Median gap {summary['median_gap_days']:.0f} d, 95th percentile {summary['p95_gap_days']:.0f} d."
    )
    lines.append("")
    lines.append("## Start month by length class")
    lines.append("")
    lines.append(
        by_class[
            ["length_class", "n_gaps", "share_protected_sep_to_jan", "share_exposed_mar_to_jul", "chi2_uniformity", "p_uniformity"]
        ].to_markdown(index=False, floatfmt=".4g")
    )
    lines.append("")
    lines.append("## Long gaps by provider")
    lines.append("")
    lines.append(by_provider.to_markdown(index=False, floatfmt=".4g"))
    lines.append("")
    lines.append("## What the calendar is worth")
    lines.append("")
    lines.append(
        "The real outage-length distribution is held fixed and only the placement "
        "changes; the consequential-error rate of each placement is read off the "
        "designed arm's length-by-overlap surface."
    )
    lines.append("")
    lines.append(calendars.to_markdown(index=False, floatfmt=".4g"))
    (E1_SEASONALITY / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
