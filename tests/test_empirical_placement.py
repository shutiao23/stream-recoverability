import numpy as np
import pandas as pd

from stream_recoverability.experiments.empirical_placement import (
    placement_replay_curve,
    training_correlation,
)


def test_training_correlation_uses_square_station_matrix() -> None:
    index = pd.date_range("2010-01-01", "2020-12-31", freq="D")
    x = np.sin(np.arange(len(index)) / 20)
    panel = pd.DataFrame({"a": x, "b": x + 0.1, "c": -x}, index=index)
    correlation = training_correlation(panel)
    assert correlation.shape == (3, 3)
    assert correlation.loc["a", "b"] > 0.9


def test_real_placement_curve_reports_oracle_regret_and_policies() -> None:
    stations = ["a", "b", "c", "d", "e"]
    correlation = pd.DataFrame(
        np.eye(5) + 0.5 * (np.ones((5, 5)) - np.eye(5)),
        index=stations,
        columns=stations,
    )
    rows = []
    for target_index, target in enumerate(stations):
        for donor_index, donor in enumerate(stations):
            if target != donor:
                rows.append(
                    {
                        "target_station": target,
                        "donor_station": donor,
                        "realized_mae": 1.0 + abs(target_index - donor_index),
                    }
                )
    curve = placement_replay_curve(
        pd.DataFrame(rows), correlation, random_repeats=3, seed=2
    )
    assert {
        "simple_risk_minimax",
        "greedy_mutual_information",
        "qr_pivot",
        "distance_even",
        "random",
        "oracle",
    }.issubset(set(curve["policy"]))
    assert curve.loc[curve["policy"].eq("oracle"), "regret"].eq(0).all()
    assert curve["independent_realized_outcomes"].all()
