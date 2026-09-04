#!/usr/bin/env python3
"""Round-2 revision S1: MAE-scale zero-crossing with a network-cluster
bootstrap CI (REVIEW_v14_round2.md Major 1 / Step 1).

The manuscript's operational rule must rest on a pre-declared threshold
definition with an interval, not on an unfounded "~60 d" figure.  This
script freezes the threshold definition used in the revised manuscript:

    threshold(gap length) = first positive-to-negative crossing of the
    unit-mean realized benefit (climatology default) over the designed
    horizon grid 7/30/90/180/365 d, located by piecewise-linear
    interpolation in log10(gap), exactly as in
    scripts/147_run_p4_flip_analysis.py.

Uncertainty: 2,000 network-cluster bootstrap draws (seed 20260903,
networks resampled with replacement; a network drawn k times contributes
its units k times); per draw the crossing day is re-estimated from the
resampled unit means, and the 2.5/97.5 percentiles of the crossing-day
draws are reported.  Point estimates must reproduce the five-point-grid
crossings of `results/v14/p4_flip_analysis/flip_analysis.md` §2
(105.3 d first panel, 91.5 d second panel); the script asserts agreement
within 0.1 d.

Inputs (read-only):
  results/v14/p0_differential/unit_predictions_{first,second}.csv

Outputs:
  results/v14/p4_flip_analysis/mae_crossing_ci.csv
  results/v14/p4_flip_analysis/mae_crossing_ci.md   (report)

Run: PYTHONPATH=$PWD/src python3 scripts/149_run_v14_r2_mae_crossing_ci.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUTPUT = ROOT / "results/v14/p4_flip_analysis"
UNIT_PATHS = {
    "first": ROOT / "results/v14/p0_differential/unit_predictions_first.csv",
    "second": ROOT / "results/v14/p0_differential/unit_predictions_second.csv",
}

# The designed horizon grid on which crossings are defined (flip_analysis.md
# §1): 7/30/90/180-d units are direct; 365-d units have realized benefit but
# no direct fitting support and act as the boundary leg of the curve.
HORIZONS = (7, 14, 30, 60, 90, 180, 365)  # round-2: 14/60 d fitted (W2-A)
SEED = 20260903
N_DRAWS = 2000
REFERENCE_CROSSINGS = {"first": 105.3, "second": 91.5}  # flip_analysis.md §2
TOL_DAYS = 0.1


def log_interp_crossing(days: np.ndarray, benefits: np.ndarray) -> float:
    """First positive-to-negative crossing of benefits vs log10(days).

    Replicates scripts/147_run_p4_flip_analysis.py `_crossings`: linear
    interpolation in log10(gap) between the two bracketing sampled
    horizons.  Returns np.nan when no positive-to-negative flip occurs.
    """
    if len(days) != len(benefits) or len(days) < 2:
        return float("nan")
    order = np.argsort(days)
    days = np.asarray(days, dtype=float)[order]
    benefits = np.asarray(benefits, dtype=float)[order]
    for i in range(len(days) - 1):
        b_i, b_j = benefits[i], benefits[i + 1]
        if np.isnan(b_i) or np.isnan(b_j):
            continue
        if b_i >= 0.0 > b_j:
            d_i, d_j = np.log10(days[i]), np.log10(days[i + 1])
            frac = b_i / (b_i - b_j)
            return float(10.0 ** (d_i + frac * (d_j - d_i)))
    return float("nan")


def crossing_bootstrap_draws(
    frame: pd.DataFrame, rng: np.random.Generator
) -> tuple[float, np.ndarray]:
    """Point crossing + N_DRAWS crossing-day draws over resampled networks."""
    by_net = frame.groupby("network_id", observed=True)
    by_net["realized_benefit"].sum().to_numpy()
    by_net["realized_benefit"].count().to_numpy()
    network_ids = by_net["realized_benefit"].count().index.to_numpy()
    n_nets = len(network_ids)
    # Map every horizon's per-network sum/count without recomputing groups.
    horizons = np.sort(frame["gap_length"].unique())
    sums = np.full((len(horizons), n_nets), np.nan)
    counts = np.zeros((len(horizons), n_nets), dtype=float)
    for i, h in enumerate(horizons):
        sub = frame.loc[frame["gap_length"] == h]
        s = sub.groupby("network_id", observed=True)["realized_benefit"]
        # reindex introduces NaN placeholders for networks absent at h;
        # absent networks contribute zero units, not NaN units.
        sums[i] = np.nan_to_num(s.sum().reindex(network_ids).to_numpy(), nan=0.0)
        counts[i] = np.nan_to_num(s.count().reindex(network_ids).to_numpy(), nan=0.0)
    point = np.empty(len(horizons))
    for i in range(len(horizons)):
        ok = counts[i] > 0
        point[i] = float(np.sum(sums[i][ok]) / np.sum(counts[i][ok]))
    point_crossing = log_interp_crossing(horizons, point)

    draws = np.empty(N_DRAWS, dtype=float)
    masked_sums = np.where(counts > 0, sums, 0.0)
    for d in range(N_DRAWS):
        chosen = rng.integers(0, n_nets, size=n_nets)
        weights = np.bincount(chosen, minlength=n_nets).astype(float)
        mean_by_h = np.empty(len(horizons))
        for i in range(len(horizons)):
            denom = float(np.dot(weights, counts[i]))
            if denom > 0.0:
                mean_by_h[i] = float(np.dot(weights, masked_sums[i]) / denom)
            else:
                mean_by_h[i] = np.nan
        draws[d] = log_interp_crossing(horizons, mean_by_h)
    return point_crossing, draws


def main() -> None:
    rng = np.random.default_rng(SEED)
    rows: list[dict[str, object]] = []
    notes: dict[str, int] = {}
    md_lines = [
        ("# Round-2 S1: MAE-scale zero-crossing of realized benefit with a "
        "network-cluster bootstrap CI"),
        "",
        ("Threshold definition (pre-declared, this revision): the first "
        "positive-to-negative crossing of the unit-mean realized benefit "
        "over the climatology default, on the fitted horizon grid "
        f"{'/'.join(str(h) for h in HORIZONS)} d (all grid points except "
        "365 d carry direct fitting support), located by piecewise-linear "
        "interpolation in log10(gap) (convention of "
        "`scripts/147_run_p4_flip_analysis.py`).  Interval: 2,000 network-"
        "cluster bootstrap draws, seed 20260903; 2.5/97.5 percentiles of the "
        "per-draw crossing day.  The old '~60 d' figure is retired: no "
        "reproducible artifact for an internal sub-grid analysis exists in "
        "`results/v14/` (REVIEW_v14_round2.md Major 1)."),
        "",
        "| panel | point crossing (d) | 95% CI (d) | grid unit rows | n networks |",
        "|---|---|---|---|---|",
    ]
    for panel in ("first", "second"):
        frame = pd.read_csv(UNIT_PATHS[panel])
        frame = frame.loc[np.isin(frame["gap_length"], HORIZONS)].copy()
        if "direct" in frame.columns:
            # 365-d rows carry realized benefit but no direct support; all
            # units at each horizon enter the mean (flip_analysis.md §1).
            pass
        point, draws = crossing_bootstrap_draws(frame, rng)
        finite = draws[np.isfinite(draws)]
        lo, hi = float(np.percentile(finite, 2.5)), float(np.percentile(finite, 97.5))
        ref = REFERENCE_CROSSINGS[panel]
        if not np.isclose(point, ref, atol=TOL_DAYS):
            raise SystemExit(
                f"point crossing {point:.2f} d ({panel}) does not reproduce "
                f"flip_analysis.md reference {ref} d"
            )
        n_units = int(frame["realized_benefit"].count())
        n_nets = int(frame["network_id"].nunique())
        rows.append(
            {
                "panel": panel,
                "grid_days": ",".join(str(h) for h in HORIZONS),
                "point_crossing_day": float(point),
                "ci_low": float(lo),
                "ci_high": float(hi),
                "n_draws": N_DRAWS,
                "seed": SEED,
                "n_unit_rows": n_units,
                "n_networks": n_nets,
                "definition": "first positive-to-negative crossing of unit-mean "
                "realized benefit over climatology default, log10-interpolated",
            }
        )
        md_lines.append(
            f"| {panel} | {point:.1f} | [{lo:.1f}, {hi:.1f}] | {n_units} | "
            f"{n_nets} |"
        )
        notes[panel] = len(draws) - len(finite)
    md_lines.append("")
    for panel in ("first", "second"):
        md_lines.append(
            f"- {panel} panel: {notes[panel]} of {N_DRAWS} draws without a "
            "positive-to-negative flip on the resampled curve."
        )
    table = pd.DataFrame(rows)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT / "mae_crossing_ci.csv", index=False)
    (OUTPUT / "mae_crossing_ci.md").write_text("\n".join(md_lines))
    print(table.to_string(index=False))
    print(f"\nwrote {OUTPUT / 'mae_crossing_ci.csv'}")


if __name__ == "__main__":
    main()
