#!/usr/bin/env python3
"""Tests for the v14 paired diff-vs-r6 evidence freeze (scripts/145).

Covers (1) the placement-level vs unit-level seasonal-increment property on
a synthetic frame, (2) self-consistency of the canonical
paired_diff_vs_r6.csv when it exists, and (3) the structural flatness of
the r6_diff baseline within (station, gap_length) by construction of the
real aggregation function.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from stream_recoverability.experiments.differential_stress import (
    r6_differential_predictions,
)

RESULTS = (
    Path(__file__).resolve().parents[1]
    / "results"
    / "v14"
    / "p0_differential"
)
SEASONS = ["DJF", "MAM", "JJA", "SON"]


def rho(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = np.isfinite(a) & np.isfinite(b)
    if int(mask.sum()) < 3:
        return float("nan")
    a, b = a[mask], b[mask]
    if np.unique(a).size < 2 or np.unique(b).size < 2:
        return float("nan")
    return float(spearmanr(a, b).statistic)


def _synthetic_seasonal_frame(seed: int = 20260903) -> pd.DataFrame:
    """Placements whose realized benefit has a real per-station seasonal
    component; diff_prediction reads that component while the r6 baseline
    is its station mean (flat within the station)."""

    rng = np.random.default_rng(seed)
    season_signal = np.array([-0.9, 0.2, 0.8, -0.1])
    n_networks = 3
    stations_per_network = 4
    reps = 6
    rows = []
    for ni in range(n_networks):
        for si in range(stations_per_network):
            station = f"n{ni}_st{si}"
            mu = rng.normal(0.0, 0.15)
            amp = rng.uniform(0.4, 1.2)
            cell = mu + amp * season_signal
            for qi, season in enumerate(SEASONS):
                for r in range(reps):
                    realized = cell[qi] + rng.normal(0.0, 0.15)
                    diff_pred = cell[qi] + rng.normal(0.0, 0.03)
                    rows.append(
                        {
                            "network_id": f"net{ni}",
                            "station_id": station,
                            "gap_length": 7,
                            "season": season,
                            "placement": r,
                            "diff_prediction": diff_pred,
                            "r6_diff_prediction": float(cell.mean()),
                            "realized_benefit": realized,
                        }
                    )
    return pd.DataFrame(rows)


def test_placement_level_seasonal_delta_beats_unit_level() -> None:
    frame = _synthetic_seasonal_frame()
    placement_delta = rho(
        frame["diff_prediction"], frame["realized_benefit"]
    ) - rho(frame["r6_diff_prediction"], frame["realized_benefit"])

    unit = (
        frame.groupby(["network_id", "station_id"], as_index=False)
        .agg(
            diff_prediction=("diff_prediction", "mean"),
            r6_diff_prediction=("r6_diff_prediction", "mean"),
            realized_benefit=("realized_benefit", "mean"),
        )
    )
    unit_delta = rho(
        unit["diff_prediction"], unit["realized_benefit"]
    ) - rho(unit["r6_diff_prediction"], unit["realized_benefit"])

    # The seasonal signal is real and only the placement level sees it:
    # rho(diff, realized) at placement level must be clearly above the
    # station-flat r6 baseline ...
    assert placement_delta > 0.25, placement_delta
    # ... while aggregating to station means erases the increment: at the
    # unit level the diff mean and the r6 (station mean) predictor coincide
    # (delta ~ 0 or negative), reproducing the diagnostic of REVIEW_v14.md
    # section 1.3.
    assert abs(unit_delta) < 0.05, unit_delta
    assert placement_delta > unit_delta + 0.25


CANONICAL_CSV = RESULTS / "paired_diff_vs_r6.csv"

# Reviewer point values frozen in REVIEW_v14.md section 1.1 (placement
# level, per duration), reproduced deterministically by scripts/145.  The
# round-2 revision (2026-09-04) fitted 14/60-d durations; the first-panel
# 180-d point pair is updated to the six-duration-grid value (predictions
# for its 1,188 network-mean-fallback rows moved with the extended fitting
# frame; see scripts/150_run_v14_r2_negated_risk.py for the same update).
REVIEWER_POINTS = {
    ("first", 7): (0.265, 0.232),
    ("first", 14): (0.255, 0.217),
    ("first", 30): (0.302, 0.256),
    ("first", 60): (0.311, 0.283),
    ("first", 90): (0.370, 0.353),
    ("first", 180): (0.308, 0.252),
    ("second", 7): (0.297, 0.226),
    ("second", 14): (0.319, 0.256),
    ("second", 30): (0.303, 0.237),
    ("second", 60): (0.327, 0.285),
    ("second", 90): (0.371, 0.331),
    ("second", 180): (0.556, 0.353),
}


@pytest.mark.skipif(
    not CANONICAL_CSV.exists(),
    reason="paired_diff_vs_r6.csv not yet produced by scripts/145",
)
def test_canonical_paired_csv_self_consistency() -> None:
    table = pd.read_csv(CANONICAL_CSV)
    assert len(table) == 12
    assert set(zip(table["panel"], table["duration"])) == set(
        REVIEWER_POINTS
    )
    for _, row in table.iterrows():
        # Internal self-consistency: delta is the point difference, the CI
        # brackets it, and the recorded reviewer cells are reproduced.
        key = (row["panel"], int(row["duration"]))
        assert np.isclose(
            row["delta_rho"], row["rho_diff"] - row["rho_r6"], atol=1e-9
        )
        assert row["delta_ci_lower"] < row["delta_rho"] < row["delta_ci_upper"]
        assert 0.0 <= row["p_gt0"] <= 1.0
        assert int(row["n_draws"]) == 2000
        assert int(row["seed"]) == 20260903
        rev_diff, rev_r6 = REVIEWER_POINTS[key]
        assert np.isclose(row["rho_diff"], rev_diff, atol=0.002), row
        assert np.isclose(row["rho_r6"], rev_r6, atol=0.002), row
    # Sign pattern on the six-duration grid: 10 of the 12 CI lower bounds
    # lie above zero (all six second-panel cells); the two crossing cells
    # are the first-panel 60 d and 90 d cells.
    n_positive = int((table["delta_ci_lower"] > 0).sum())
    assert n_positive == 10
    for dur in (60, 90):
        cell = table.loc[
            (table["panel"] == "first") & (table["duration"] == dur)
        ].iloc[0]
        assert cell["delta_ci_lower"] < 0 < cell["delta_ci_upper"]


def test_r6_baseline_flat_within_station_and_duration() -> None:
    """The real R6 aggregation makes r6_diff_prediction constant within
    (station_id, gap_length) by construction."""

    rng = np.random.default_rng(11)
    rows = []
    for network in ("alpha", "beta"):
        for si in range(3):
            for gap in (7, 30):
                if network == "alpha" and si == 1 and gap == 30:
                    # Deliberately leave one (station, gap) cell without
                    # fitting rows so the network x gap fallback is used.
                    continue
                station = f"{network}_st{si}"
                for season in SEASONS:
                    for p in range(2):
                        benefit = (
                            0.5
                            + rng.normal(0.0, 0.4)
                            + (1.0 if season == "JJA" else 0.0)
                        )
                        rows.append(
                            {
                                "network_id": network,
                                "station_id": station,
                                "gap_length": gap,
                                "season": season,
                                "placement": p,
                                "mae_deg_c": benefit,
                            }
                        )
    fitting = pd.DataFrame(rows)

    evaluation_rows = []
    for network in ("alpha", "beta"):
        for si in range(3):
            for gap in (7, 30):
                for season in SEASONS:
                    for p in range(3):
                        evaluation_rows.append(
                            {
                                "network_id": network,
                                "station_id": f"{network}_st{si}",
                                "gap_length": gap,
                                "season": season,
                                "placement": p,
                            }
                        )
    # One (station, gap) missing from the fitting frame to exercise the
    # fallback level (network x gap mean).
    evaluation_rows.append(
        {
            "network_id": "gamma",
            "station_id": "gamma_st0",
            "gap_length": 7,
            "season": "DJF",
            "placement": 0,
        }
    )
    evaluation = pd.DataFrame(evaluation_rows)

    out = r6_differential_predictions(fitting, evaluation)

    expected_mean = (
        fitting.groupby(["network_id", "station_id", "gap_length"])[
            "mae_deg_c"
        ]
        .mean()
        .rename("expected")
        .reset_index()
    )
    merged = out.merge(
        expected_mean,
        on=["network_id", "station_id", "gap_length"],
        how="left",
    )
    matched = merged["expected"].notna()
    assert np.allclose(
        merged.loc[matched, "r6_diff_prediction"],
        merged.loc[matched, "expected"],
        atol=1e-12,
    )
    # Fallback cell (network x gap mean from the fitting rows).
    fallback = float(
        fitting.loc[
            (fitting["network_id"] == "alpha") & (fitting["gap_length"] == 30),
            "mae_deg_c",
        ].mean()
    )
    fb_row = merged.loc[
        (merged["network_id"] == "alpha")
        & (merged["station_id"] == "alpha_st1")
        & (merged["gap_length"] == 30)
    ]
    assert len(fb_row) > 1  # every evaluation season/start of that cell
    assert np.allclose(
        fb_row["r6_diff_prediction"], fallback, atol=1e-12
    )
    # Flatness: within (station, gap) every evaluation row (across seasons
    # and gap starts) shares one r6 value.
    n_unique = out.groupby(["station_id", "gap_length"])[
        "r6_diff_prediction"
    ].nunique()
    assert (n_unique == 1).all(), "r6_diff_prediction not flat within station"
    # Missing-cell fallback: constant network x gap mean from the fitting
    # frame (checked above); a station from a network absent from the
    # fitting frame falls through to the global mean.
    gamma_row = out.loc[
        (out["network_id"] == "gamma") & (out["station_id"] == "gamma_st0")
    ]
    assert len(gamma_row) == 1
    global_mean = float(fitting["mae_deg_c"].mean())
    assert np.isclose(
        gamma_row["r6_diff_prediction"].iloc[0], global_mean, atol=1e-12
    )
